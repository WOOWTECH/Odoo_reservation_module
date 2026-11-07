# -*- coding: utf-8 -*-
"""Payment integrity gaps found by the completeness review (sweep 2026-11-07).

  * cancelling a booking never cancels the order of a booking that was paid,
    never calls it "refunded" when nothing was refunded, and tells an
    appointment manager to refund it (GAP 4: the booking's own pay page, an
    unreconciled order payment, a paid invoice)
  * a booking paid on its own pay page takes its lines out of the visitor's
    cart, so the cart cannot charge them a second time; the pay page itself
    takes no second payment, nor one for a cancelled booking
  * the failure bookkeeping reads its UPDATE ... RETURNING result before
    anything flushes (GAP 11 item 6)
  * an unpublished payment product gives the payment configuration error
    page, and clearing / merging a cart that holds a booking says why it
    cannot (GAP 11 item 9)
"""

import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .test_booking_rules import RulesHttpCommon
from .test_payment_binding import EDIT, BindingCommon

MANAGER_GROUP = 'reservation_module.group_appointment_manager'
REFUND_SUMMARY = 'Cancelled booking was paid: refund it'


class IntegrityCommon(BindingCommon):
    """Payments made the way the providers' return flow post-processes them
    (the dummy provider has no journal, so no accounting payment)."""

    def _provider(self, published=False):
        return self.env['payment.provider'].create({
            'name': 'Integrity Dummy', 'code': 'none', 'state': 'test', 'is_published': published,
            'payment_method_ids': [(6, 0, self.env.ref('payment.payment_method_unknown').ids)],
        })

    def _post_process(self, tx):
        Tx = type(self.env['payment.transaction'])
        if hasattr(Tx, '_create_payment'):
            with patch.object(Tx, '_create_payment', return_value=None):
                tx._post_process()
        else:
            tx._post_process()
        self.env.invalidate_all()

    def _own_tx(self, booking, reference, amount=None):
        """A transaction made on the booking's own pay page, as the route
        makes it (the amount is the booking's lines, the booking points to it)."""
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self._provider().id,
            'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
            'reference': reference,
            'amount': amount if amount is not None else booking._get_payment_amount(),
            'currency_id': booking._get_payment_currency().id,
            'partner_id': booking.partner_id.id,
            'appointment_booking_id': booking.id,
        })
        booking.payment_transaction_id = tx
        return tx

    def _pay_on_own_page(self, booking, reference):
        tx = self._own_tx(booking, reference)
        tx._set_done()
        self._post_process(tx)
        return tx

    def _order_tx(self, order, reference, amount=None):
        return self.env['payment.transaction'].sudo().create({
            'provider_id': self._provider().id,
            'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
            'reference': reference,
            'amount': order.amount_total if amount is None else amount,
            'currency_id': order.currency_id.id,
            'partner_id': order.partner_id.id,
            'sale_order_ids': [(6, 0, order.ids)],
        })

    def _refund_activities(self, booking):
        return booking.activity_ids.filtered(lambda activity: activity.summary == REFUND_SUMMARY)

    def _refund_notes(self, booking, reference):
        return booking.message_ids.filtered(
            lambda m: reference in (m.body or '') and 'refund' in (m.body or '').lower())


class IntegrityHttpCommon(IntegrityCommon, RulesHttpCommon):

    def _json(self, url, params):
        response = self.url_open(url, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        return response.json()

    def _skip_without_website_sale(self):
        if not self.env['ir.module.module'].search_count(
                [('name', '=', 'website_sale'), ('state', '=', 'installed')]):
            self.skipTest('website_sale is not installed')


@tagged('post_install', '-at_install')
class TestPaidBookingCancellation(IntegrityCommon, TransactionCase):
    """GAP 4: _release_sale_order judged "paid" by invoices only. A booking
    paid on its own pay page (a done transaction, no invoice) or through an
    order payment that was never reconciled got its order cancelled and read
    "refunded" with nothing refunded."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=True)
        self.booking = self._new_booking(self.appointment_type)
        self.order = self.booking._create_sale_order()

    def _assert_flagged(self, booking, reference):
        self.assertEqual(booking.state, 'cancelled')
        self.assertEqual(booking.payment_status, 'paid', 'the money was not given back')
        notes = self._refund_notes(booking, reference)
        self.assertTrue(notes, 'a note names the payment')
        self.assertIn(self.env.company.currency_id.symbol, notes[0].body, 'and what it was')
        activities = self._refund_activities(booking)
        self.assertEqual(len(activities), 1, 'one activity asks for the refund')
        self.assertTrue(activities.user_id.has_group(MANAGER_GROUP))

    def test_cancel_after_paying_on_the_own_pay_page(self):
        tx = self._pay_on_own_page(self.booking, 'INT-OWN-1')
        self.assertEqual(self.booking.state, 'confirmed')
        self.assertEqual(self.booking.payment_status, 'paid')
        order = self.booking.sale_order_id
        self.booking.action_cancel()
        self.assertNotEqual(order.state, 'cancel', 'the paid order is not cancelled')
        self._assert_flagged(self.booking, tx.reference)

    def test_cancel_after_paying_on_the_own_pay_page_without_settlement(self):
        """Whatever left the order open (a payment recorded by hand, a booking
        paid before the lines were settled): the money is still found."""
        tx = self._own_tx(self.booking, 'INT-OWN-2')
        tx._set_done()
        self.env.invalidate_all()
        self.assertEqual(self.booking.payment_status, 'paid')
        self.assertEqual(self.order.state, 'sent')
        self.booking.action_cancel()
        self.assertEqual(self.order.state, 'sent', 'the paid order is not cancelled')
        self._assert_flagged(self.booking, tx.reference)

    def test_cancel_after_an_unreconciled_order_payment(self):
        """sale.automatic_invoice off: the order is paid by a done transaction
        but no payment is reconciled with its invoice."""
        self.env['ir.config_parameter'].sudo().set_param('sale.automatic_invoice', 'False')
        tx = self._order_tx(self.order, 'INT-ORDER-1')
        tx._set_done()
        self._post_process(tx)
        self.assertEqual(self.order.state, 'sale')
        self.assertEqual(self.booking.state, 'pending_payment', 'unreconciled: not confirmed')
        self.booking.action_cancel()
        self.assertEqual(self.order.state, 'sale', 'the paid order is not cancelled')
        self._assert_flagged(self.booking, tx.reference)

    def test_cancel_with_a_paid_invoice_tells_staff(self):
        invoice = self._invoice_and_pay(self.order)
        self.assertEqual(self.booking.payment_status, 'paid')
        self.booking.action_cancel()
        self.assertNotEqual(self.order.state, 'cancel')
        self._assert_flagged(self.booking, invoice.name)

    def test_cancel_with_a_part_paid_invoice_is_not_cancelled_either(self):
        order = self.order.sudo()
        order.action_confirm()
        move = order._create_invoices()
        move.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids).create(
                {'amount': move.amount_total / 2})._create_payments()
        self.env.invalidate_all()
        self.assertEqual(move.payment_state, 'partial')
        self.booking.action_cancel()
        self.assertNotEqual(self.order.state, 'cancel')
        self._assert_flagged(self.booking, move.name)

    def test_paid_invoice_for_other_items_is_not_this_bookings_money(self):
        """Only the invoices of the booking's own lines count: the cart's
        other items were paid, the booking was not."""
        other = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Pen', 2.0).id, 'product_uom_qty': 1})
        self._invoice_and_pay(self.order, lines=other)
        self.assertEqual(self.booking.payment_status, 'pending')
        self.assertFalse(self.booking._get_paid_invoices())
        self.assertFalse(self.booking._holds_payment())
        self.booking.action_cancel()
        self.assertEqual(self.order.state, 'sale', 'the order also holds the paid items: kept')
        self.assertFalse(self._refund_activities(self.booking))
        self.assertTrue(self.booking.message_ids.filtered(
            lambda m: 'also holds other items' in (m.body or '')))

    def test_legacy_booking_with_a_paid_invoice_is_flagged(self):
        """A booking made before its lines were bound is paid by its order."""
        order = self.env['sale.order'].create({
            'partner_id': self.booking.partner_id.id,
            'order_line': [(0, 0, {'product_id': self.appointment_type.payment_product_ids.id,
                                   'product_uom_qty': 1})],
        })
        legacy = self._new_booking(self.appointment_type, days=5, partner=self.booking.partner_id)
        legacy.write({'state': 'pending_payment', 'sale_order_id': order.id})
        self.assertFalse(legacy.payment_line_count or legacy.payment_line_ids)
        invoice = self._invoice_and_pay(order)
        self.assertEqual(legacy.payment_status, 'paid')
        legacy.action_cancel()
        self.assertNotEqual(order.state, 'cancel')
        self._assert_flagged(legacy, invoice.name)

    def test_a_credit_note_takes_the_invoice_payment_back(self):
        """The accounting way to refund an invoiced order: the money held is
        what the paid invoices took minus the credit notes."""
        invoice = self._invoice_and_pay(self.order)
        self.assertTrue(self.booking._holds_payment())
        refund = invoice._reverse_moves()
        refund.action_post()
        self.env.invalidate_all()
        self.assertFalse(self.booking._get_paid_invoices())
        self.assertFalse(self.booking._holds_payment())
        self.booking.action_cancel()
        self.assertEqual(self.order.state, 'cancel')
        self.assertEqual(self.booking.payment_status, 'refunded')
        self.assertFalse(self._refund_activities(self.booking))

    def test_a_credit_note_takes_the_order_payment_back_too(self):
        """An order paid by a transaction, invoiced, and credited: the
        transaction stays "done" but the credit note is the refund."""
        tx = self._order_tx(self.order, 'INT-ORDER-3')
        tx._set_done()
        self._post_process(tx)
        self.assertTrue(self.booking._holds_payment())
        invoice = self.order.invoice_ids.filtered(lambda move: move.move_type == 'out_invoice')
        self.assertTrue(invoice)
        refund = invoice._reverse_moves()
        refund.action_post()
        self.env.invalidate_all()
        self.assertFalse(self.booking._holds_payment())

    def test_staff_cancelling_the_order_does_not_make_a_paid_booking_refunded(self):
        self._own_tx(self.booking, 'INT-OWN-3')._set_done()
        self.env.invalidate_all()
        self.order._action_cancel()
        self.env.invalidate_all()
        self.assertEqual(self.booking.payment_status, 'paid')

    def test_a_refunded_payment_lets_the_order_go(self):
        tx = self._own_tx(self.booking, 'INT-OWN-4')
        tx._set_done()
        refund = tx._create_child_transaction(tx.amount, is_refund=True)
        refund._set_done()
        self.env.invalidate_all()
        self.booking.action_cancel()
        self.assertEqual(self.order.state, 'cancel')
        self.assertEqual(self.booking.payment_status, 'refunded')
        self.assertFalse(self._refund_activities(self.booking))

    def test_refunds_are_netted_out_of_the_money_held(self):
        tx = self._own_tx(self.booking, 'INT-OWN-4B')
        tx._set_done()
        self.assertEqual(self.booking._get_received_transactions(), tx)
        self.assertTrue(self.booking._holds_payment())
        partial = tx._create_child_transaction(tx.amount / 4, is_refund=True)
        partial._set_done()
        self.env.invalidate_all()
        self.assertEqual(self.booking._get_received_transactions(), tx, 'a part refund leaves money held')
        self.assertEqual(self.booking.payment_status, 'paid', 'and the booking stays paid')
        rest = tx._create_child_transaction(tx.amount * 3 / 4, is_refund=True)
        rest._set_done()
        self.env.invalidate_all()
        self.assertFalse(self.booking._get_received_transactions())
        self.assertFalse(self.booking._holds_payment())
        self.assertEqual(self.booking.payment_status, 'pending', 'a payment refunded in full pays nothing')

    def test_unpaid_cancel_is_unchanged(self):
        pending = self._own_tx(self.booking, 'INT-OWN-5')
        pending._set_pending()
        failed = self._own_tx(self.booking, 'INT-OWN-6')
        failed._set_error('declined')
        self.env.invalidate_all()
        self.booking.action_cancel()
        self.assertEqual(self.order.state, 'cancel')
        self.assertEqual(self.booking.payment_status, 'refunded')
        self.assertFalse(self._refund_activities(self.booking))

    def test_payment_for_other_items_is_not_this_bookings_money(self):
        """A shared cart paid without the booking's lines (they were removed
        from it): that money is not the booking's."""
        other = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Pen', 2.0).id, 'product_uom_qty': 1})
        self.booking.payment_line_ids.with_context(**EDIT).unlink()
        tx = self._order_tx(self.order, 'INT-ORDER-2', amount=other.price_total)
        tx._set_done()
        self.env.invalidate_all()
        self.assertFalse(self.booking._get_received_transactions())
        self.assertFalse(self.booking._holds_payment())

    def test_two_cancellations_ask_for_one_refund(self):
        tx = self._own_tx(self.booking, 'INT-OWN-7')
        tx._set_done()
        self.env.invalidate_all()
        self.booking.action_cancel()
        self.booking.action_draft()
        self.booking.action_cancel()
        self.assertEqual(len(self._refund_activities(self.booking)), 1)

    def test_late_payment_on_a_cancelled_booking_is_flagged(self):
        """A payment started before the cancellation and completed after it
        (a transfer): the booking is cancelled already, the money came in."""
        tx = self._own_tx(self.booking, 'INT-LATE-1')
        tx._set_pending()
        self._post_process(tx)
        self.booking.action_cancel()
        self.assertEqual(self.order.state, 'cancel')
        self.assertEqual(self.booking.payment_status, 'refunded')
        tx._set_done()
        self._post_process(tx)
        self._assert_flagged(self.booking, tx.reference)


@tagged('post_install', '-at_install')
class TestPaidBookingCancellationRoute(IntegrityHttpCommon, HttpCase):
    """The token link a guest cancels with."""

    def test_token_cancel_of_a_paid_booking(self):
        appointment_type = self._paid_type(auto_confirm=True)
        booking = self._new_booking(appointment_type)
        booking._create_sale_order()
        tx = self._pay_on_own_page(booking, 'INT-ROUTE-1')
        order = booking.sale_order_id
        response = self.url_open('/appointment/booking/%d/cancel' % booking.id, data={
            'token': booking.access_token, 'csrf_token': self._csrf()})
        self.assertEqual(response.status_code, 200)
        self.env.invalidate_all()
        self.assertEqual(booking.state, 'cancelled')
        self.assertNotEqual(order.state, 'cancel')
        self.assertEqual(booking.payment_status, 'paid')
        self.assertTrue(self._refund_notes(booking, tx.reference))


@tagged('post_install', '-at_install')
class TestPayPageSettlement(IntegrityCommon, TransactionCase):
    """Flow 1: the booking's own pay page paid its lines. They leave the order
    they were added to (the cart), and the order that holds them takes no
    payment."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=True, payment_per_person=True)
        self.booking = self._new_booking(self.appointment_type, guest_count=2)
        self.order = self.booking._create_sale_order()

    def _shared_cart(self):
        """The booking's order also holds a second booking and a mug (as the
        website cart does)."""
        second = self._new_booking(self.appointment_type, days=4, partner=self.booking.partner_id)
        Line = self.env['sale.order.line'].with_context(**EDIT)
        Line.create({'order_id': self.order.id, 'display_type': 'line_section',
                     'name': 'Second booking', 'appointment_booking_id': second.id})
        Line.create({'order_id': self.order.id, 'product_id': self.appointment_type.payment_product_ids.id,
                     'product_uom_qty': 1, 'appointment_booking_id': second.id,
                     'appointment_booking_qty': 1})
        second.write({'sale_order_id': self.order.id, 'payment_line_count': 1, 'state': 'pending_payment'})
        mug = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Mug', 5.0).id, 'product_uom_qty': 1})
        return second, mug

    def test_a_cart_of_one_booking_is_confirmed_in_place(self):
        before = self.order.order_line
        tx = self._pay_on_own_page(self.booking, 'INT-SET-1')
        self.assertEqual(self.booking.sale_order_id, self.order)
        self.assertEqual(self.order.state, 'sale')
        self.assertEqual(self.order.order_line, before)
        self.assertEqual(self.booking.payment_transaction_id, tx)
        self.assertEqual(self.booking.payment_status, 'paid')
        self.assertEqual(self.booking.state, 'confirmed')

    def test_paid_lines_leave_a_shared_cart(self):
        second, mug = self._shared_cart()
        cart = self.order
        lines = self.booking.payment_line_ids
        self.assertTrue(lines)
        self.assertEqual(lines.order_id, cart)
        total = self.booking._get_payment_amount()
        tx = self._pay_on_own_page(self.booking, 'INT-SET-2')
        settled = self.booking.sale_order_id
        self.assertNotEqual(settled, cart)
        self.assertEqual(settled.state, 'sale')
        self.assertEqual(settled.order_line, lines)
        self.assertEqual(settled.partner_id, self.booking.partner_id)
        self.assertEqual(settled.currency_id, cart.currency_id)
        self.assertEqual(settled.pricelist_id, cart.pricelist_id)
        self.assertAlmostEqual(settled.amount_total, total)
        self.assertAlmostEqual(tx.amount, total)
        self.assertEqual(self.booking.payment_status, 'paid')
        self.assertEqual(self.booking.payment_transaction_id, tx)
        # The cart keeps what is not paid, and can still be paid for that.
        self.assertEqual(cart.state, 'sent')
        self.assertFalse(cart.order_line & lines)
        self.assertIn(mug, cart.order_line)
        self.assertEqual(second.sale_order_id, cart)
        self.assertEqual(second.payment_status, 'pending')
        self.assertNotIn(self.booking, cart.booking_ids)

    def test_the_cart_does_not_charge_the_paid_lines_again(self):
        second, mug = self._shared_cart()
        cart = self.order
        amount_before = cart.amount_total
        self._pay_on_own_page(self.booking, 'INT-SET-3')
        self.assertLess(cart.amount_total, amount_before)
        cart_tx = self._order_tx(cart, 'INT-SET-3-CART')
        self.assertAlmostEqual(cart_tx.amount, second._get_payment_amount() + mug.price_total)

    def test_a_second_payment_on_the_pay_page_is_refused(self):
        self.appointment_type.auto_confirm = False
        tx = self._own_tx(self.booking, 'INT-SET-4')
        tx._set_done()
        self._post_process(tx)
        self.assertEqual(self.booking.state, 'pending_payment', 'waits for staff')
        self.assertEqual(self.booking.payment_status, 'paid')
        with self.assertRaisesRegex(UserError, 'already been paid'), self.env.cr.savepoint():
            self._own_tx(self.booking, 'INT-SET-4-AGAIN')

    def test_a_confirmed_booking_takes_no_payment(self):
        self._pay_on_own_page(self.booking, 'INT-SET-4B')
        self.assertEqual(self.booking.state, 'confirmed')
        with self.assertRaisesRegex(UserError, 'can no longer be paid'), self.env.cr.savepoint():
            self._own_tx(self.booking, 'INT-SET-4B-AGAIN')

    def test_an_order_with_a_paid_booking_takes_no_payment(self):
        """Settlement could not take the lines out: the cart still must not
        charge them again."""
        tx = self._own_tx(self.booking, 'INT-SET-5')
        tx._set_done()
        self.env.invalidate_all()
        self.assertEqual(self.booking.payment_status, 'paid')
        self.assertEqual(self.order.state, 'sent')
        with self.assertRaisesRegex(UserError, 'already been paid'), self.env.cr.savepoint():
            self._order_tx(self.order, 'INT-SET-5-CART')

    def test_a_cancelled_booking_takes_no_payment(self):
        self.booking.action_cancel()
        with self.assertRaisesRegex(UserError, 'can no longer be paid'), self.env.cr.savepoint():
            self._own_tx(self.booking, 'INT-SET-6')

    def test_failed_settlement_leaves_the_order_and_says_so(self):
        SaleOrder = type(self.env['sale.order'])
        with patch.object(SaleOrder, 'action_confirm', side_effect=UserError('nope')):
            tx = self._pay_on_own_page(self.booking, 'INT-SET-7')
        self.assertEqual(self.booking.sale_order_id, self.order)
        self.assertEqual(self.order.state, 'sent')
        self.assertEqual(self.booking.payment_status, 'paid')
        self.assertEqual(self.booking.state, 'confirmed', 'the payment still confirms the booking')
        self.assertTrue(self.booking.message_ids.filtered(
            lambda m: 'do not pay that order again' in (m.body or '') and tx.reference in (m.body or '')))
        with self.assertRaisesRegex(UserError, 'already been paid'), self.env.cr.savepoint():
            self._order_tx(self.order, 'INT-SET-7-CART')

    def test_an_unexpected_settlement_error_does_not_stop_the_payment(self):
        """Settlement is best effort: the payment is post-processed and the
        booking confirmed whatever goes wrong with the order."""
        SaleOrder = type(self.env['sale.order'])
        with patch.object(SaleOrder, 'action_confirm', side_effect=RuntimeError('boom')):
            tx = self._pay_on_own_page(self.booking, 'INT-SET-7B')
        self.assertTrue(tx.is_post_processed)
        self.assertEqual((self.booking.state, self.booking.payment_status), ('confirmed', 'paid'))
        self.assertEqual(self.booking.sale_order_id, self.order)
        self.assertEqual(self.order.state, 'sent')

    def test_a_payment_of_an_order_is_not_settled_on_the_pay_page(self):
        tx = self._order_tx(self.order, 'INT-SET-8')
        tx._set_done()
        self.assertFalse(self.booking._settle_order_after_own_payment(tx))
        self.assertEqual(self.booking.sale_order_id, self.order)
        self.assertEqual(self.order.state, 'sent')

    def test_a_payment_that_does_not_cover_the_lines_is_not_settled(self):
        short = self._own_tx(self.booking, 'INT-SET-9', amount=1.0)
        short._set_done()
        self.assertFalse(self.booking._settle_order_after_own_payment(short))
        self.assertEqual(self.booking.sale_order_id, self.order)
        self.assertEqual(self.order.state, 'sent')


@tagged('post_install', '-at_install')
class TestPaymentFailureClaim(IntegrityCommon, TransactionCase):
    """GAP 11 item 6: invalidate_recordset() flushes. Run between the
    UPDATE ... RETURNING and cr.fetchone() it replaced the result."""

    def setUp(self):
        super().setUp()
        self.booking = self._new_booking(self._paid_type())
        self.booking.state = 'pending_payment'
        self.tx = self._own_tx(self.booking, 'INT-FAIL-1', amount=10.0)
        self.tx._set_error('declined')

    def test_the_claim_survives_a_flush_after_it(self):
        """What a flush of any pending write does: it runs a statement that
        returns nothing."""
        Tx = type(self.env['payment.transaction'])
        invalidate = Tx.invalidate_recordset

        def noisy(records, fnames=None, flush=True):
            records.env.cr.execute('SELECT 1 WHERE FALSE')
            return invalidate(records, fnames, flush)
        with patch.object(Tx, 'invalidate_recordset', noisy):
            self.assertTrue(self.booking._handle_payment_failure(transaction=self.tx))
        self.env.invalidate_all()
        self.assertTrue(self.tx.appointment_failure_notified)
        self.assertEqual(self.booking.payment_failure_count, 1)
        self.assertFalse(self.booking._handle_payment_failure(transaction=self.tx), 'only once')

    def test_pending_orm_writes_do_not_break_the_claim(self):
        """A flag written through the ORM and not flushed yet: the claim sees
        it (the transaction is already handled) instead of failing."""
        self.tx.appointment_failure_notified = True
        self.assertFalse(self.booking._handle_payment_failure(transaction=self.tx))
        self.env.invalidate_all()
        self.assertEqual(self.booking.payment_failure_count, 0)



@tagged('post_install', '-at_install')
class TestCartModeIntegrity(IntegrityHttpCommon, HttpCase):
    """The real website cart."""

    def setUp(self):
        super().setUp()
        self._skip_without_website_sale()
        self.appointment_type = self._paid_type(auto_confirm=True, payment_per_person=True)

    def _book(self, days, email, guests):
        response = self._post(self.appointment_type, self._wall(days, 10), guest_email=email,
                              guest_count=guests)
        self.assertIn('/shop/cart', response.url)
        return self._bookings(self.appointment_type, guest_email=email)

    def _pay_page(self, booking, provider):
        Tx = type(self.env['payment.transaction'])
        with patch.object(Tx, '_get_processing_values', lambda self: {'reference': self.reference}):
            return self._json('/appointment/payment/transaction/%d' % booking.id, {
                'access_token': booking.access_token,
                'provider_id': provider.id,
                'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
                'flow': 'direct',
            })

    def test_booking_paid_on_its_page_cannot_be_paid_again_in_the_cart(self):
        first = self._book(3, 'int.first@example.com', 2)
        second = self._book(4, 'int.second@example.com', 1)
        cart = second.sale_order_id
        self.assertEqual(first.sale_order_id, cart, 'one shared cart')
        self._json('/shop/cart/update_json', {'product_id': self._product('Int Mug', 5.0).id, 'add_qty': 1})
        self.env.invalidate_all()
        lines = first.payment_line_ids
        self.assertTrue(lines)
        provider = self._provider(published=True)
        result = self._pay_page(first, provider)
        self.assertIn('result', result, result)
        self.env.invalidate_all()
        tx = first.payment_transaction_id
        self.assertEqual(tx.appointment_booking_id, first)
        tx._set_done()
        self._post_process(tx)
        # The paid booking is confirmed and settled on an order of its own...
        self.assertEqual(first.state, 'confirmed')
        self.assertEqual(first.payment_status, 'paid')
        settled = first.sale_order_id
        self.assertNotEqual(settled, cart)
        self.assertEqual(settled.order_line, lines)
        self.assertEqual(settled.state, 'sale')
        # ... the visitor's cart holds what is still to pay ...
        self.assertEqual(cart.state, 'draft')
        self.assertFalse(cart.order_line & lines)
        self.assertEqual(second.sale_order_id, cart)
        self.assertEqual(second.payment_status, 'pending')
        page = self.url_open('/shop/cart')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Int Mug', page.text)
        # ... and the pay page takes no second payment.
        again = self._pay_page(first, provider)
        self.assertIn('error', again['result'], again)
        self.env.invalidate_all()
        self.assertEqual(self.env['payment.transaction'].search_count(
            [('appointment_booking_id', '=', first.id)]), 1)

    def test_a_cancelled_booking_takes_no_payment_on_its_page(self):
        booking = self._book(3, 'int.cancel@example.com', 1)
        booking.action_cancel()
        self.env.invalidate_all()
        result = self._pay_page(booking, self._provider(published=True))
        self.assertIn('can no longer be paid', result['result'].get('error', ''), result)
        self.assertFalse(self.env['payment.transaction'].search([('appointment_booking_id', '=', booking.id)]))


@tagged('post_install', '-at_install')
class TestPayPageRender(IntegrityHttpCommon, HttpCase):
    """Flow 1's page is the one the return route shows when nothing was paid:
    it has to render for a provider that offers a method with tokenization
    (it failed with a TypeError: show_tokenize_input_mapping was missing)."""

    def test_pay_page_renders_the_payment_form(self):
        method = self.env['payment.method'].create({
            'name': 'Integrity Card', 'code': 'integritycard', 'active': True,
            'support_tokenization': True})
        self.env['payment.provider'].create({
            'name': 'Integrity Tokenizing', 'code': 'none', 'state': 'test', 'is_published': True,
            'allow_tokenization': True, 'payment_method_ids': [(6, 0, method.ids)]})
        booking = self._new_booking(self._paid_type())
        booking._create_sale_order()
        self.assertEqual(booking.state, 'pending_payment')
        response = self.url_open('/appointment/payment/validate?booking_id=%d&token=%s' % (
            booking.id, booking.access_token))
        self.assertEqual(response.status_code, 200)
        self.assertIn('o_payment_form', response.text)
        self.assertIn('Integrity Card', response.text)
        self.assertIn('Payment was not completed', response.text)
