# -*- coding: utf-8 -*-
"""Payment and ownership gaps left open by round 2 (sweep 2026-11-07, round 3).

  * a row kept by the upgrade because its order is not its own (ATK-0002,
    e10ecad8918d) may still carry the "paid" the old rule stored from that
    order's invoice: nothing that lets a booking go ahead trusts the stored
    status (action_confirm, a payment that confirms or holds the booking)
  * money received is netted against what was given back per booking: a
    small credit note no longer hides the order's payments, and another
    booking's credit note no longer takes this booking's payment back
  * the "refund it" to-do of a cancelled paid booking is one per booking
    whatever language asked for it; the note says what credit notes already
    returned and, for a booking made before its lines were bound, that the
    amount cannot be told apart from the rest of the cart
  * a payment transaction refused at creation (a race: the booking was paid
    or its slot sold meanwhile) leaves nothing behind
  * a cancelled booking, or one whose order was cancelled, that holds part
    of its price reads "paid" (money is held, a refund is due) but is never
    taken for paid in full
"""

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .test_legacy_order_links import LegacyCartTools
from .test_payment_binding import EDIT, LegacyLinkCommon
from .test_payment_integrity import IntegrityCommon, IntegrityHttpCommon

REFUND_TYPE_XMLID = 'reservation_module.mail_activity_type_refund_due'


# ---------------------------------------------------------------------------
# The rows the upgrade keeps (ATK-0002)
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestKeptRowGate(LegacyCartTools, LegacyLinkCommon, TransactionCase):
    """Mallory's second row sits on Bob's paid order and carries the "paid"
    the old rule stored. The upgrade keeps the row and its status (it only
    reports them); nothing may let it go ahead on that status."""

    def setUp(self):
        super().setUp()
        self._invoice_and_pay(self.victim_order)
        self.victim_tx = self._order_tx('GATE-DONE')
        self.victim_tx._set_done()
        self.paid_row = self._new_booking(self.appointment_type, days=4, partner=self.legacy.partner_id)
        self._plant_order(self.paid_row, self.victim_order)
        self._stamp(self.paid_row, 'pending_payment', 'paid', self.victim_tx)

    def test_the_row_keeps_its_stored_status_through_the_upgrade(self):
        self.assertEqual(self.paid_row.payment_status, 'paid')
        self._upgrade()
        self.assertEqual(self.paid_row.payment_status, 'paid', 'the upgrade never rewrites a status')
        self.assertEqual(self.paid_row.state, 'pending_payment')
        self.assertEqual(self.paid_row.sale_order_id, self.victim_order)

    def test_staff_cannot_confirm_the_row_on_that_status(self):
        self._upgrade()
        with self.assertRaisesRegex(UserError, 'Payment is required'):
            self.paid_row.action_confirm()
        self.assertEqual(self.paid_row.state, 'pending_payment')
        self.assertFalse(self.paid_row.calendar_event_id, 'no event was made for it')
        self.assertEqual(self.paid_row.payment_status, 'paid', 'refusing does not rewrite the status either')

    def test_the_refusal_says_which_order_does_not_count(self):
        with self.assertRaises(UserError) as caught:
            self.paid_row.action_confirm()
        message = str(caught.exception)
        self.assertIn(self.victim_order.name, message)
        self.assertIn('not an order of this booking', message)
        self.assertNotIn(self.victim_order.access_token, message)

    def test_a_payment_of_that_order_does_not_confirm_or_hold_the_row(self):
        self.appointment_type.auto_confirm = True
        hold = self.paid_row.payment_hold_until
        self.assertFalse(self.paid_row._is_paid_by(self.victim_tx), 'the stored status is not payment')
        self.paid_row._confirm_after_payment(self.victim_tx)
        self.assertEqual(self.paid_row.state, 'pending_payment')
        self.assertFalse(self.paid_row.payment_confirm_failed)
        self.assertEqual(self.paid_row.payment_hold_until, hold)
        self.assertFalse(self.paid_row.calendar_event_id)

    def test_the_stored_status_is_not_taken_for_a_payment_already_made(self):
        self.assertEqual(self.paid_row.payment_status, 'paid')
        self.assertFalse(self.paid_row._is_covered_by_payment(), 'it is not "already paid" either')
        self.paid_row._check_open_for_payment()  # raises when the booking counts as paid already
        self.assertEqual(self.paid_row.payment_status, 'paid', 'the stored status was left alone')

    def test_the_status_worked_out_now_is_not_the_stored_one(self):
        self.assertEqual(self.paid_row.payment_status, 'paid')
        self.assertEqual(self.paid_row._get_live_payment_status(), 'pending')
        self.assertFalse(self.paid_row._is_fully_paid())

    def test_a_booking_that_is_really_paid_still_confirms(self):
        own = self._new_booking(self.appointment_type, days=6)
        self._invoice_and_pay(own._create_sale_order())
        self.assertEqual(own.payment_status, 'paid')
        own.action_confirm()
        self.assertEqual(own.state, 'confirmed')

    def test_a_stale_pending_status_does_not_block_a_booking_that_is_paid(self):
        own = self._new_booking(self.appointment_type, days=6)
        self._invoice_and_pay(own._create_sale_order())
        self._stamp(own, 'pending_payment', 'pending')
        self.assertEqual(own.payment_status, 'pending', 'precondition: the stored status is stale')
        own.action_confirm()
        self.assertEqual(own.state, 'confirmed')


@tagged('post_install', '-at_install')
class TestStatusFollowsOwnership(LegacyLinkCommon, TransactionCase):
    """The stored status also follows the contacts that decide whose an order
    is (a booking made before its lines were bound has nothing else)."""

    def setUp(self):
        super().setUp()
        self.alice = self._partner('Alice Owner')
        product = self.appointment_type.payment_product_ids
        self.order = self.env['sale.order'].create({
            'partner_id': self.alice.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1})],
        })
        self.row = self._new_booking(self.appointment_type, days=5, partner=self.alice)
        self.row.write({'state': 'pending_payment', 'sale_order_id': self.order.id})
        self._invoice_and_pay(self.order)
        self.assertFalse(self.row.payment_line_count or self.row.payment_line_ids)
        self.assertEqual(self.row.payment_status, 'paid')

    def test_changing_the_booking_contact_changes_the_status(self):
        self.row.partner_id = self._portal_partner('Mallory Mover')
        self.assertFalse(self.row._is_own_sale_order(self.order))
        self.assertEqual(self.row.payment_status, 'pending')

    def test_changing_the_order_contact_changes_the_status(self):
        self.order.partner_id = self._portal_partner('Mallory Mover')
        self.assertFalse(self.row._is_own_sale_order(self.order))
        self.assertEqual(self.row.payment_status, 'pending')


# ---------------------------------------------------------------------------
# Money received, net of what was given back
# ---------------------------------------------------------------------------

class MoneyCommon(IntegrityCommon):
    """Orders paid, invoiced and credited the way accounting does it."""

    def _credit_note(self, invoice, price=None):
        """A posted credit note of ``invoice``; with ``price`` every product
        line is credited at that unit price (a discount, not the whole)."""
        refund = invoice._reverse_moves()
        if price is not None:
            refund.invoice_line_ids.filtered(lambda line: line.display_type == 'product').price_unit = price
        refund.action_post()
        self.env.invalidate_all()
        return refund

    def _pay_without_accounting_payment(self, order, reference):
        """The order is paid by a done transaction whose accounting payment
        is never made (a provider without journal, sale.automatic_invoice
        off): the order is confirmed and invoiced (the module's safety net),
        and the invoice stays open."""
        tx = self._order_tx(order, reference)
        tx._set_done()
        self._post_process(tx)
        return tx

    def _product_lines(self, booking):
        return booking.payment_line_ids.filtered(lambda line: not line.display_type)

    def _two_bookings_in_one_order(self, appointment_type):
        """Two bookings of one customer in one order, as the website cart
        makes them (each with its own bound section and product line)."""
        first = self._new_booking(appointment_type, days=6)
        order = first._create_sale_order()
        second = self._new_booking(appointment_type, days=7, partner=first.partner_id)
        Line = self.env['sale.order.line'].with_context(**EDIT)
        Line.create({'order_id': order.id, 'display_type': 'line_section',
                     'name': 'Second booking', 'appointment_booking_id': second.id})
        Line.create({'order_id': order.id, 'product_id': appointment_type.payment_product_ids.id,
                     'product_uom_qty': 1, 'appointment_booking_id': second.id,
                     'appointment_booking_qty': 1})
        second.write({'sale_order_id': order.id, 'payment_line_count': 1, 'state': 'pending_payment'})
        return first, second, order

    def _legacy_booking(self, appointment_type, partner, days=5):
        """A booking made before its lines were bound, on an order of its customer."""
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': appointment_type.payment_product_ids.id,
                                   'product_uom_qty': 1})],
        })
        legacy = self._new_booking(appointment_type, days=days, partner=partner)
        legacy.write({'state': 'pending_payment', 'sale_order_id': order.id})
        self.assertFalse(legacy.payment_line_count or legacy.payment_line_ids)
        return legacy, order

    def _asks_for_a_refund(self, booking, order, reference=None):
        """Cancelling kept the order, left the status at paid and asked for
        one refund."""
        self.assertEqual(booking.state, 'cancelled')
        self.assertNotEqual(order.state, 'cancel', 'the order of a paid booking is kept')
        self.assertEqual(booking.payment_status, 'paid', 'the money was not given back')
        self.assertEqual(len(self._refund_activities(booking)), 1)
        if reference:
            self.assertTrue(self._refund_notes(booking, reference), 'a note names the payment')


@tagged('post_install', '-at_install')
class TestCreditNoteNetting(MoneyCommon, TransactionCase):
    """_get_received_transactions dropped every transaction of an order as
    soon as the order had any posted credit note, so a small discount made a
    paid booking read "refunded" when it was cancelled."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=True)
        self.booking = self._new_booking(self.appointment_type)
        self.order = self.booking._create_sale_order()

    def test_part_refund_of_direct_payment_blocks_confirmation(self):
        tx = self._own_tx(self.booking, 'PART-DIRECT')
        tx._set_done()
        self.assertTrue(self.booking._is_fully_paid())
        tx._create_child_transaction(1, is_refund=True)._set_done()
        self.env.invalidate_all()
        self.assertFalse(self.booking._is_fully_paid())
        with self.assertRaisesRegex(UserError, 'already been paid'):
            self.booking._check_open_for_payment()
        with self.assertRaisesRegex(UserError, 'Payment is required'):
            self.booking.action_confirm()

    def test_part_refund_of_order_payment_no_longer_covers_cart(self):
        tx = self._order_tx(self.order, 'PART-CART')
        tx._set_done()
        self.assertTrue(self.booking._tx_covers_booking(tx))
        tx._create_child_transaction(1, is_refund=True)._set_done()
        self.env.invalidate_all()
        self.assertFalse(self.booking._tx_covers_booking(tx))
        with self.assertRaisesRegex(UserError, 'already been paid'):
            self.booking._check_open_for_payment()

    def test_shared_cart_refund_cannot_pay_both_bookings_with_one_balance(self):
        first, second, order = self._two_bookings_in_one_order(self.appointment_type)
        tx = self._order_tx(order, 'SHARED-REFUND')
        tx._set_done()
        invoice = self._invoice_and_pay(order)
        invoice._get_reconciled_payments().write({'payment_transaction_id': tx.id})
        self.assertTrue(first._is_fully_paid())
        self.assertTrue(second._is_fully_paid())
        tx._create_child_transaction(first._get_payment_amount(), is_refund=True)._set_done()
        self.env.invalidate_all()
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertFalse(first._is_fully_paid())
        self.assertFalse(second._is_fully_paid())
        first.action_cancel()
        second.action_cancel()
        for booking in (first, second):
            notes = self._refund_notes(booking, tx.reference)
            self.assertTrue(notes)
            self.assertIn('not the amount owed to this booking', notes[0].body)
            self.assertNotIn('SHARED-REFUND (', notes[0].body)

    def test_order_invoice_still_marked_paid_does_not_hide_provider_refund(self):
        tx = self._order_tx(self.order, 'PART-PAID-INVOICE')
        tx._set_done()
        invoice = self._invoice_and_pay(self.order)
        payments = invoice._get_reconciled_payments()
        self.assertEqual(len(payments), 1)
        payments.write({'payment_transaction_id': tx.id})
        self.assertEqual(invoice.payment_state, 'paid')
        tx._create_child_transaction(1, is_refund=True)._set_done()
        self.env.invalidate_all()
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertFalse(self.booking._is_fully_paid())
        with self.assertRaisesRegex(UserError, 'Payment is required'):
            self.booking.action_confirm()

    def _invoice_paid_by_provider(self):
        tx = self._own_tx(self.booking, 'PROVIDER-INVOICE')
        tx._set_done()
        invoice = self._invoice_and_pay(self.order)
        payments = invoice._get_reconciled_payments()
        self.assertEqual(len(payments), 1)
        payments.write({'payment_transaction_id': tx.id})
        return tx, invoice

    def test_full_provider_refund_does_not_leave_a_false_invoice_refund_task(self):
        tx, invoice = self._invoice_paid_by_provider()
        tx._create_child_transaction(tx.amount, is_refund=True)._set_done()
        self.env.invalidate_all()
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertFalse(self.booking._get_received_transactions())
        self.assertFalse(self.booking._get_paid_invoices())
        self.assertFalse(self.booking._holds_payment())
        self.booking.action_cancel()
        self.assertFalse(self._refund_activities(self.booking))

    def test_replacement_bank_payment_after_provider_refund_allows_confirmation(self):
        tx, invoice = self._invoice_paid_by_provider()
        tx._create_child_transaction(tx.amount, is_refund=True)._set_done()
        self.env.invalidate_all()
        self.assertFalse(self.booking._is_fully_paid())
        invoice.line_ids.filtered(lambda line: line.account_type == 'asset_receivable').remove_move_reconcile()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids).create({})._create_payments()
        self.env.invalidate_all()
        self.assertTrue(self.booking._is_fully_paid())
        self.booking.action_confirm()
        self.assertEqual(self.booking.state, 'confirmed')

    def test_replacement_bank_statement_after_provider_refund_allows_confirmation(self):
        tx, invoice = self._invoice_paid_by_provider()
        old_payment = invoice._get_reconciled_payments()
        journal = old_payment.journal_id
        tx._create_child_transaction(tx.amount, is_refund=True)._set_done()
        receivable = invoice.line_ids.filtered(lambda line: line.account_type == 'asset_receivable')
        receivable.remove_move_reconcile()
        statement = self.env['account.bank.statement.line'].create({
            'payment_ref': invoice.name, 'journal_id': journal.id,
            'partner_id': invoice.partner_id.id, 'amount': invoice.amount_total,
        })
        _liquidity, suspense, _other = statement._seek_for_lines()
        suspense.account_id = receivable.account_id
        (suspense + receivable).reconcile()
        self.env.invalidate_all()
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertFalse(invoice._get_reconciled_payments())
        self.assertEqual(invoice._get_reconciled_statement_lines(), statement)
        self.assertTrue(self.booking._is_fully_paid())
        with self.assertRaisesRegex(UserError, 'already been paid'):
            self.booking._check_open_for_payment()
        self.booking.action_confirm()
        self.assertEqual(self.booking.state, 'confirmed')

    def test_a_small_credit_note_does_not_hide_the_order_payment(self):
        tx = self._pay_without_accounting_payment(self.order, 'NET-SMALL')
        refund = self._credit_note(self.order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice'),
                                   price=5.0)
        self.assertTrue(self.order.invoice_ids & refund)
        self.assertEqual(self.booking._get_received_transactions(), tx)
        self.assertTrue(self.booking._holds_payment())
        self.booking.action_cancel()
        self._asks_for_a_refund(self.booking, self.order, tx.reference)
        note = self._refund_notes(self.booking, tx.reference)[0].body
        self.assertIn('Credit notes already issued', note)
        self.assertIn('does not prove', note)
        self.assertIn('%.2f' % refund.amount_total, note, 'the note says what the credit note already returned')

    def test_a_full_credit_note_without_cash_refund_keeps_the_payment(self):
        tx = self._pay_without_accounting_payment(self.order, 'NET-FULL')
        self._credit_note(self.order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice'))
        self.assertEqual(self.booking._get_received_transactions(), tx)
        self.assertTrue(self.booking._holds_payment())
        self.booking.action_cancel()
        self._asks_for_a_refund(self.booking, self.order, tx.reference)

    def test_a_small_credit_note_does_not_take_a_paid_invoice_back(self):
        invoice = self._invoice_and_pay(self.order)
        self._credit_note(invoice, price=5.0)
        self.assertEqual(self.booking._get_paid_invoices(), invoice)
        self.booking.action_cancel()
        self._asks_for_a_refund(self.booking, self.order, invoice.name)

    def test_the_credit_note_of_another_booking_does_not_take_this_payment_back(self):
        """Two bookings, each with an invoice of its own, both paid; the
        second invoice is credited. That credit note is the second booking's
        refund and no one else's."""
        first, second, order = self._two_bookings_in_one_order(self.appointment_type)
        first_invoice = self._invoice_and_pay(order, lines=self._product_lines(first))
        second_invoice = self._invoice_and_pay(order, lines=self._product_lines(second))
        self._credit_note(second_invoice)
        self.assertEqual(first._get_paid_invoices(), first_invoice)
        self.assertTrue(first._holds_payment())
        self.assertEqual(second._get_paid_invoices(), second_invoice,
                         'the credit note alone is not evidence of a cash refund')
        self.assertTrue(second._holds_payment())
        first.action_cancel()
        self._asks_for_a_refund(first, order, first_invoice.name)
        self.assertEqual(order.state, 'sale', 'the order also holds the other booking')
        self.assertEqual(first._get_credited_amount(), 0)
        self.assertGreater(second._get_credited_amount(), 0)

    def test_the_credit_note_for_other_items_does_not_hide_the_booking_payment(self):
        """The cart was paid in one payment; the credit note is for the
        mug alone."""
        mug = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Mug', 5.0).id, 'product_uom_qty': 1})
        self.order.action_confirm()
        mug_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.order.partner_id.id,
            'invoice_line_ids': [(0, 0, {'product_id': mug.product_id.id, 'quantity': 1,
                                         'price_unit': mug.price_unit, 'sale_line_ids': [(6, 0, mug.ids)]})],
        })
        mug_invoice.action_post()
        self._credit_note(mug_invoice)
        tx = self._order_tx(self.order, 'NET-MUG')
        tx._set_done()
        self.assertEqual(self.booking._get_received_transactions(), tx)
        self.booking.action_cancel()
        self._asks_for_a_refund(self.booking, self.order, tx.reference)
        self.assertEqual(self.booking._get_credited_amount(), 0, 'the mug credit note is not its own')

    def test_crediting_booking_lines_without_cash_refund_keeps_the_payment_visible(self):
        """The cart was paid in one payment, the booking's own lines were
        credited in full: what is left of the payment is the mug's."""
        mug = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Mug', 5.0).id, 'product_uom_qty': 1})
        tx = self._order_tx(self.order, 'NET-REST')
        tx._set_done()
        invoice = self._invoice_and_pay(self.order, lines=self._product_lines(self.booking))
        self._credit_note(invoice)
        self.assertEqual(self.order.amount_total, self.booking._get_payment_amount() + mug.price_total)
        self.assertGreater(tx.amount, self.booking._get_payment_amount())
        self.assertEqual(self.booking._get_received_transactions(), tx)
        self.assertTrue(self.booking._holds_payment())

    def test_refunds_made_on_the_transaction_are_still_netted(self):
        tx = self._own_tx(self.booking, 'NET-REFUNDED')
        tx._set_done()
        self.assertEqual(self.booking._get_received_transactions(), tx)
        tx._create_child_transaction(tx.amount, is_refund=True)._set_done()
        self.env.invalidate_all()
        self.assertFalse(self.booking._get_received_transactions())

    def test_only_actual_transaction_refunds_reduce_the_money_held(self):
        """A posted credit note is not a cash refund."""
        tx = self._own_tx(self.booking, 'NET-ADD')
        tx._set_done()
        tx._create_child_transaction(tx.amount / 2, is_refund=True)._set_done()
        self.order.action_confirm()
        invoice = self.order._create_invoices()
        invoice.action_post()
        self._credit_note(invoice, price=self._product_lines(self.booking).price_unit / 4)
        self.env.invalidate_all()
        self.assertEqual(self.booking._get_received_transactions(), tx, 'a quarter is still held')
        tx._create_child_transaction(tx.amount / 4, is_refund=True)._set_done()
        self.env.invalidate_all()
        self.assertEqual(self.booking._get_received_transactions(), tx, 'the credit note is not cash')
        tx._create_child_transaction(tx.amount / 4, is_refund=True)._set_done()
        self.env.invalidate_all()
        self.assertFalse(self.booking._get_received_transactions())


@tagged('post_install', '-at_install')
class TestLegacyCreditNotes(MoneyCommon, TransactionCase):
    """A booking made before its lines were bound has the whole order for its
    price: every credit note of the order is its own."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=False)
        self.legacy, self.order = self._legacy_booking(self.appointment_type, self._partner('Lena Legacy'))

    def test_a_small_credit_note_leaves_the_paid_order_held(self):
        invoice = self._invoice_and_pay(self.order)
        self._credit_note(invoice, price=5.0)
        self.assertEqual(self.legacy._get_paid_invoices(), invoice)
        self.legacy.action_cancel()
        self._asks_for_a_refund(self.legacy, self.order, invoice.name)
        self.assertGreater(self.legacy._get_credited_amount(), 0)

    def test_a_full_credit_note_without_cash_refund_keeps_the_invoice_visible(self):
        invoice = self._invoice_and_pay(self.order)
        self._credit_note(invoice)
        self.assertTrue(self.legacy._holds_payment())
        self.legacy.action_cancel()
        self._asks_for_a_refund(self.legacy, self.order, invoice.name)

    def test_an_unreconciled_order_payment_is_held_after_a_small_credit_note(self):
        self.env['ir.config_parameter'].sudo().set_param('sale.automatic_invoice', 'False')
        self.order.action_confirm()
        invoice = self.order._create_invoices()
        invoice.action_post()
        tx = self._order_tx(self.order, 'LEGACY-NET')
        tx._set_done()
        self._credit_note(invoice, price=5.0)
        self.assertEqual(self.legacy._get_received_transactions(), tx)
        self.legacy.action_cancel()
        self._asks_for_a_refund(self.legacy, self.order, tx.reference)


# ---------------------------------------------------------------------------
# One refund request per booking, and what it says
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestRefundRequest(MoneyCommon, TransactionCase):

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=True)

    def _paid_booking(self):
        booking = self._new_booking(self.appointment_type)
        order = booking._create_sale_order()
        tx = self._own_tx(booking, 'ASK-OWN-%d' % booking.id)
        tx._set_done()
        self.env.invalidate_all()
        return booking, order, tx

    def _any_refund_activities(self, booking):
        """Whatever the language of its summary."""
        return booking.activity_ids.filtered(
            lambda activity: 'refund' in (activity.summary or '').lower() or '退款' in (activity.summary or ''))

    def test_an_open_request_in_another_language_is_not_asked_again(self):
        booking, order, tx = self._paid_booking()
        booking.activity_schedule(
            REFUND_TYPE_XMLID, user_id=booking._get_refund_followup_user().id,
            summary='已取消的預約已付款：請退款')
        self.assertEqual(len(self._any_refund_activities(booking)), 1)
        booking.action_cancel()
        self.assertEqual(booking.state, 'cancelled')
        self.assertEqual(len(self._any_refund_activities(booking)), 1, 'one refund, one to-do')
        self.assertFalse(self._refund_notes(booking, tx.reference), 'and no second note')

    def test_old_generic_refund_todo_is_reused_and_migrated(self):
        from .test_legacy_order_links import _load_migration_3_2_2
        self.env['res.lang']._activate_lang('zh_TW')
        booking, order, tx = self._paid_booking()
        old = booking.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=booking._get_refund_followup_user().id,
            summary='已取消的預約已付款：請退款')
        booking.action_cancel()
        self.assertEqual(booking.activity_ids, old)
        self.assertEqual(_load_migration_3_2_2()._migrate_refund_activities(self.env), 1)
        self.assertEqual(old.activity_type_id, self.env.ref(REFUND_TYPE_XMLID))
        self.assertEqual(_load_migration_3_2_2()._migrate_refund_activities(self.env), 0)
        self.assertEqual(booking.activity_ids, old)

    def test_two_cancellations_in_two_languages_ask_once(self):
        self.env['res.lang']._activate_lang('zh_TW')
        booking, order, tx = self._paid_booking()
        in_chinese = booking.with_context(lang='zh_TW')
        in_english = booking.with_context(lang='en_US')
        self.assertNotEqual(
            in_chinese.env._('Cancelled booking was paid: refund it'),
            in_english.env._('Cancelled booking was paid: refund it'),
            'precondition: the summary is translated')
        self.assertNotEqual(
            in_chinese.env._('Cancelled booking was paid: refund it'),
            'Cancelled booking was paid: refund it')
        in_chinese.action_cancel()
        self.assertEqual(len(self._any_refund_activities(booking)), 1)
        booking.action_draft()
        in_english.action_cancel()
        self.assertEqual(len(self._any_refund_activities(booking)), 1)
        notes = booking.message_ids.filtered(lambda m: tx.reference in (m.body or ''))
        self.assertEqual(len(notes), 1)

    def test_a_request_that_was_done_can_be_asked_again(self):
        booking, order, tx = self._paid_booking()
        booking.action_cancel()
        self._refund_activities(booking).action_done()
        self.assertFalse(self._any_refund_activities(booking))
        booking.action_draft()
        booking.action_cancel()
        self.assertEqual(len(self._any_refund_activities(booking)), 1)

    def test_the_request_has_its_own_activity_type(self):
        booking, order, tx = self._paid_booking()
        booking.action_cancel()
        activity = self._refund_activities(booking)
        self.assertEqual(activity.activity_type_id, self.env.ref(REFUND_TYPE_XMLID))
        self.assertEqual(activity.activity_type_id.res_model, 'appointment.booking')

    def test_a_legacy_booking_note_says_the_amount_cannot_be_told_apart(self):
        partner = self._partner('Lena Legacy')
        legacy, order = self._legacy_booking(self.appointment_type, partner)
        invoice = self._invoice_and_pay(order)
        legacy.action_cancel()
        self._asks_for_a_refund(legacy, order, invoice.name)
        note = self._refund_notes(legacy, invoice.name)[0].body
        self.assertIn('cannot be told apart', note)
        self.assertIn(order.name, note)
        activity = self._refund_activities(legacy)
        self.assertIn('cannot be told apart', activity.note)

    def test_a_booking_with_its_own_lines_gets_no_such_warning(self):
        booking, order, tx = self._paid_booking()
        booking.action_cancel()
        self.assertTrue(self._refund_notes(booking, tx.reference))
        self.assertNotIn('cannot be told apart', self._refund_notes(booking, tx.reference)[0].body)
        self.assertNotIn('Credit notes already issued', self._refund_notes(booking, tx.reference)[0].body)


# ---------------------------------------------------------------------------
# A refused payment transaction leaves nothing behind
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestRefusedTransactionLeavesNothing(IntegrityCommon, TransactionCase):
    """The checks run after the row exists. A caller that catches the refusal
    (the booking's pay route does) kept the draft transaction: the booking's
    transaction list, the money search and the provider all saw an orphan."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=False)
        self.booking = self._new_booking(self.appointment_type)
        self.order = self.booking._create_sale_order()

    def _count(self, reference):
        return self.env['payment.transaction'].sudo().search_count([('reference', '=', reference)])

    def test_a_second_payment_for_a_paid_booking_leaves_no_row(self):
        paid = self._own_tx(self.booking, 'REFUSED-PAID')
        paid._set_done()
        self.env.invalidate_all()
        with self.assertRaisesRegex(UserError, 'already been paid'):
            self._own_tx(self.booking, 'REFUSED-AGAIN')
        self.assertEqual(self._count('REFUSED-AGAIN'), 0)
        self.assertEqual(self.booking.payment_transaction_ids, paid)

    def test_an_order_payment_for_a_paid_booking_leaves_no_row(self):
        self._own_tx(self.booking, 'REFUSED-PAID-2')._set_done()
        self.env.invalidate_all()
        with self.assertRaisesRegex(UserError, 'already been paid'):
            self._order_tx(self.order, 'REFUSED-CART')
        self.assertEqual(self._count('REFUSED-CART'), 0)

    def test_a_payment_for_a_slot_sold_meanwhile_leaves_no_row_and_no_hold_change(self):
        hold = self.booking.payment_hold_until
        self.booking.payment_hold_until = False
        self._booking(self.appointment_type, self.booking.start_datetime, staff_user_id=self.host.id)
        with self.assertRaisesRegex(UserError, 'no longer available'):
            self._own_tx(self.booking, 'REFUSED-SOLD')
        self.assertEqual(self._count('REFUSED-SOLD'), 0)
        self.assertFalse(self.booking.payment_hold_until)
        self.assertTrue(hold)

    def test_an_accepted_payment_is_kept(self):
        tx = self._own_tx(self.booking, 'ACCEPTED')
        self.assertEqual(self._count('ACCEPTED'), 1)
        self.assertEqual(tx.state, 'draft')
        self.assertEqual(self.booking.payment_transaction_ids, tx)


@tagged('post_install', '-at_install')
class TestRefusedTransactionRoute(IntegrityHttpCommon, HttpCase):

    def test_the_pay_route_leaves_no_draft_transaction_when_it_loses_the_race(self):
        """The route's own check passes, then the booking is paid by another
        payment before this one is created: the route answers with the
        refusal and the draft transaction it had begun is gone."""
        booking = self._new_booking(self._paid_type(auto_confirm=False))
        booking._create_sale_order()
        provider = self._provider(published=True)
        paid = self._own_tx(booking, 'ROUTE-RACE-PAID')
        paid._set_done()
        self.env.flush_all()
        original = type(booking)._check_open_for_payment
        calls = []

        def first_check_passes(record):
            calls.append(record.id)
            if len(calls) == 1:
                return None  # the route looked before the other payment came in
            return original(record)

        Tx = type(self.env['payment.transaction'])
        with patch.object(type(booking), '_check_open_for_payment', first_check_passes), \
                patch.object(Tx, '_get_processing_values', lambda self: {'reference': self.reference}):
            result = self._json('/appointment/payment/transaction/%d' % booking.id, {
                'access_token': booking.access_token,
                'provider_id': provider.id,
                'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
                'flow': 'direct',
            })
        self.assertGreaterEqual(len(calls), 2, 'the refusal came from the creation')
        self.assertIn('already been paid', result['result'].get('error', ''), result)
        self.env.invalidate_all()
        self.assertEqual(self.env['payment.transaction'].sudo().search(
            [('appointment_booking_id', '=', booking.id)]), paid)


# ---------------------------------------------------------------------------
# Paid means paid in full, wherever a booking was cancelled with money held
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestMoneyHeldIsNotPaidInFull(MoneyCommon, TransactionCase):
    """A cancelled booking, or one whose order was cancelled, that still holds
    part of its price reads "paid": money is held and a refund is due. That is
    not "covered": confirming asks for payment in full."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=False)
        self.booking = self._new_booking(self.appointment_type)
        self.order = self.booking._create_sale_order()
        self.order.action_confirm()
        self.invoice = self.order._create_invoices()
        self.invoice.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=self.invoice.ids).create(
                {'amount': self.invoice.amount_total / 2})._create_payments()
        self.env.invalidate_all()

    def test_part_of_the_price_is_not_payment_in_full(self):
        self.assertEqual(self.invoice.payment_state, 'partial')
        self.assertTrue(self.booking._holds_payment())
        self.assertEqual(self.booking.payment_status, 'pending')
        with self.assertRaisesRegex(UserError, 'Payment is required'):
            self.booking.action_confirm()
        self.assertFalse(self.booking._is_fully_paid())

    def test_a_cancelled_booking_reads_paid_while_money_is_held(self):
        self.booking.action_cancel()
        self.assertEqual(self.booking.payment_status, 'paid', 'money is held: a refund is due')
        self.assertEqual(len(self._refund_activities(self.booking)), 1)
        self.assertFalse(self.booking._is_fully_paid())

    def test_reopening_a_cancelled_booking_does_not_make_it_confirmable(self):
        self.booking.action_cancel()
        self.booking.action_draft()
        self.assertEqual(self.booking.payment_status, 'pending')
        with self.assertRaisesRegex(UserError, 'Payment is required'):
            self.booking.action_confirm()
        self.assertEqual(self.booking.state, 'draft')

    def test_an_open_booking_whose_order_was_cancelled_cannot_be_confirmed_on_part_of_the_price(self):
        self.order._action_cancel()
        self.env.invalidate_all()
        self.assertEqual(self.order.state, 'cancel')
        self.assertIn(self.booking.state, ('draft', 'pending_payment'))
        self.assertEqual(self.booking.payment_status, 'paid', 'money is held, so it reads paid')
        with self.assertRaisesRegex(UserError, 'Payment is required'):
            self.booking.action_confirm()
        self.assertNotEqual(self.booking.state, 'confirmed')
        self.assertFalse(self.booking.calendar_event_id)
        self.assertFalse(self.booking._is_fully_paid())

    def test_it_cannot_be_paid_a_second_time_either(self):
        """Refusing a second payment goes by the wide reading: money is held."""
        self.order._action_cancel()
        self.env.invalidate_all()
        with self.assertRaisesRegex(UserError, 'already been paid'):
            self.booking._check_open_for_payment()
        self.assertTrue(self.booking._is_covered_by_payment())

    def test_a_booking_paid_in_full_on_a_cancelled_order_still_confirms(self):
        """The order was cancelled by staff after it was paid in full: the
        money is in, the booking can still be confirmed."""
        remainder = self.invoice.amount_residual
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=self.invoice.ids).create(
                {'amount': remainder})._create_payments()
        self.env.invalidate_all()
        self.order._action_cancel()
        self.env.invalidate_all()
        self.booking.action_confirm()
        self.assertEqual(self.booking.state, 'confirmed')
        self.assertTrue(self.booking._is_fully_paid())
