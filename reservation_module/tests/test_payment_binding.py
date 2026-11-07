# -*- coding: utf-8 -*-
"""A booking is paid only by money for its own order lines (sweep 2026-11-07).

  * sale_order_id is bound to the booking: never an order of another
    customer; cancelling / paying never touches or reveals a foreign order
    (e10ecad8918d). The attacker is a portal user (a contact with a login);
    guest contacts of anonymous visitors are not (test_legacy_order_links)
  * the lines a booking adds are bound to it; customers cannot lower or
    remove them from the (shared) website cart; payment_status looks only at
    those lines being invoiced and paid, or at a booking transaction that
    covers them (f94e04013795, 7f0060bd8934)
  * the booking's own pay page charges the amount of its lines, computed on
    the server
  * a shared-cart payment that does not pay the booking's own lines neither
    holds, confirms nor flags the booking; booking lines cannot be removed
    through the linked_line_id cascade
  * failed payments cannot flood the booking's chatter (bab08eb294c9)
"""

import json
from datetime import timedelta
from unittest.mock import patch

import polib

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_module_path
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .test_booking_rules import PaymentHoldCommon, RulesHttpCommon
from .test_security_acl import _load_migration_3_2_2

EDIT = {'reservation_booking_line_edit': True}


class BindingCommon(PaymentHoldCommon):

    def _partner(self, name):
        return self.env['res.partner'].create({'name': name, 'email': '%s@example.com' % name.lower()})

    def _product(self, name, price):
        vals = {'name': name, 'type': 'service', 'list_price': price, 'sale_ok': True}
        if 'is_published' in self.env['product.product']._fields:
            vals['is_published'] = True
        return self.env['product.product'].create(vals)

    def _portal_partner(self, name):
        """The contact of a portal user: a registered customer, somebody who
        can log in (so never a guest contact)."""
        login = 'binding_%s' % name.lower().replace(' ', '_')
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': name, 'login': login, 'email': '%s@example.com' % login,
            'groups_id': [(6, 0, self.env.ref('base.group_portal').ids)],
        })
        return user.partner_id

    def _foreign_order(self):
        """An order of another, registered customer (Bob, a portal user),
        with a portal token."""
        order = self.env['sale.order'].create({
            'partner_id': self._portal_partner('Bob').id,
            'order_line': [(0, 0, {'product_id': self._product('Bob Stuff', 999.0).id,
                                   'product_uom_qty': 1})],
        })
        order.action_quotation_sent()
        order._portal_ensure_token()
        return order

    def _plant_order(self, booking, order):
        """Data written before the ownership check existed."""
        self.env.flush_all()
        self.env.cr.execute("UPDATE appointment_booking SET sale_order_id = %s WHERE id = %s",
                            [order.id, booking.id])
        self.env.invalidate_all()

    def _pay_invoice(self, invoice):
        invoice.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids).create({})._create_payments()
        self.env.invalidate_all()
        return invoice

    def _invoice_and_pay(self, order, lines=None):
        """Confirm ``order`` and pay an invoice of ``lines`` (default: all)."""
        order = order.sudo()
        if order.state in ('draft', 'sent'):
            order.action_confirm()
        if lines is None:
            invoice = order._create_invoices()
        else:
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': order.partner_id.id,
                'invoice_line_ids': [(0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.product_uom_qty,
                    'price_unit': line.price_unit,
                    'sale_line_ids': [(6, 0, line.ids)],
                }) for line in lines],
            })
        return self._pay_invoice(invoice)

    def _new_booking(self, appointment_type, days=3, guest_count=1, partner=None):
        return self._booking(appointment_type, self._wall(days, 10), state='draft',
                             staff_user_id=self.host.id, guest_count=guest_count,
                             partner_id=(partner or self._partner('Alice')).id)

    def _done_tx(self, booking, amount, **extra):
        provider = self.env['payment.provider'].create({
            'name': 'Binding Dummy', 'code': 'none', 'state': 'test',
            'payment_method_ids': [(6, 0, self.env.ref('payment.payment_method_unknown').ids)],
        })
        tx = self.env['payment.transaction'].sudo().create(dict({
            'provider_id': provider.id,
            'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
            'reference': 'BIND-%s-%s' % (booking.id, amount),
            'amount': amount,
            'currency_id': booking._get_payment_currency().id,
            'partner_id': booking.partner_id.id,
            'appointment_booking_id': booking.id,
        }, **extra))
        booking.payment_transaction_id = tx
        tx._set_done()
        self.env.invalidate_all()
        return tx


@tagged('post_install', '-at_install')
class TestBookingOrderOwnership(BindingCommon, TransactionCase):
    """e10ecad8918d: a booking never points at, cancels or hands out another
    customer's order."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=False)
        self.booking = self._new_booking(self.appointment_type)
        self.foreign = self._foreign_order()

    def test_foreign_order_cannot_be_linked(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.booking.write({'sale_order_id': self.foreign.id})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._booking(self.appointment_type, self._wall(5, 10), state='draft',
                          partner_id=self._portal_partner('Mallory').id,
                          sale_order_id=self.foreign.id)

    def test_order_of_the_same_customer_can_be_linked(self):
        order = self.env['sale.order'].create({'partner_id': self.booking.partner_id.id})
        self.booking.write({'sale_order_id': order.id})
        self.assertEqual(self.booking.sale_order_id, order)
        self.assertTrue(self.booking._get_payment_url())

    def test_cancel_leaves_a_foreign_order_alone(self):
        self._plant_order(self.booking, self.foreign)
        state = self.foreign.state
        self.booking.action_cancel()
        self.assertEqual(self.booking.state, 'cancelled')
        self.assertEqual(self.foreign.state, state)

    def test_foreign_order_token_is_never_handed_out(self):
        self._plant_order(self.booking, self.foreign)
        self.assertFalse(self.booking._get_payment_url())
        self.assertFalse(self.booking._create_sale_order())
        self.assertEqual(self.booking._get_payment_amount(), 0.0)
        self.assertEqual(self.booking.payment_status, 'pending')

    def test_own_order_is_cancelled_with_the_booking(self):
        order = self.booking._create_sale_order()
        self.assertIn('/my/orders/%d?access_token=' % order.id, self.booking._get_payment_url())
        self.booking.action_cancel()
        self.assertEqual(order.state, 'cancel')


@tagged('post_install', '-at_install')
class TestBookingOrderOwnershipRoutes(BindingCommon, RulesHttpCommon, HttpCase):
    """e10ecad8918d: the token pages never redirect to or print a foreign
    order's access token."""

    def test_pages_do_not_reveal_a_foreign_order(self):
        appointment_type = self._paid_type(auto_confirm=False)
        booking = self._new_booking(appointment_type)
        booking.state = 'pending_payment'
        foreign = self._foreign_order()
        self._plant_order(booking, foreign)
        for path in ('/appointment/booking/%d/pay', '/appointment/booking/%d/confirm',
                     '/appointment/booking/%d'):
            response = self.url_open((path % booking.id) + '?token=%s' % booking.access_token)
            self.assertNotIn(foreign.access_token, response.url, path)
            self.assertNotIn(foreign.access_token, response.text, path)
        self.env.invalidate_all()
        self.assertNotEqual(foreign.state, 'cancel')

    def test_order_page_lists_only_its_own_booking(self):
        """The order's portal page links to the order's booking, never to a
        row of another customer pointing at the order (final review)."""
        appointment_type = self._paid_type(auto_confirm=False)
        legacy = self._new_booking(appointment_type, partner=self._portal_partner('Mallory'))
        foreign = self._foreign_order()
        self._plant_order(legacy, foreign)
        own = self._new_booking(appointment_type, days=5)
        order = own._create_sale_order()
        self.env.flush_all()
        response = self.url_open(foreign.get_portal_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(legacy.name, response.text)
        self.assertNotIn('/my/ext-bookings/%d' % legacy.id, response.text)
        response = self.url_open(order.get_portal_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn('/my/ext-bookings/%d' % own.id, response.text)


@tagged('post_install', '-at_install')
class TestBookingLinesPayment(BindingCommon, TransactionCase):
    """f94e04013795 / 7f0060bd8934: only the booking's own lines, paid, make
    the booking paid."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=False, payment_per_person=True)
        self.booking = self._new_booking(self.appointment_type, guest_count=3)
        self.order = self.booking._create_sale_order()
        self.line = self.order.order_line.filtered(lambda l: not l.display_type)
        self.portal_user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Cart Visitor', 'login': 'binding_cart_visitor', 'email': 'visitor@example.com',
            'groups_id': [(6, 0, self.env.ref('base.group_portal').ids)],
        })

    def test_lines_are_bound_to_the_booking(self):
        self.assertEqual(self.line.appointment_booking_id, self.booking)
        self.assertEqual(self.line.appointment_booking_qty, 3)
        self.assertEqual(self.line.product_uom_qty, 3)
        self.assertEqual(self.booking.payment_line_count, 1)
        self.assertTrue(self.order.order_line.filtered('display_type').appointment_booking_id)
        self.assertEqual(self.booking._get_payment_amount(), self.line.price_total)

    def test_paid_lines_make_the_booking_paid(self):
        self._invoice_and_pay(self.order)
        self.assertEqual(self.booking.payment_status, 'paid')
        self.booking.action_confirm()
        self.assertEqual(self.booking.state, 'confirmed')

    def test_lowered_quantity_paid_is_not_paid(self):
        self.line.with_context(**EDIT).write({'product_uom_qty': 1})
        self._invoice_and_pay(self.order)
        self.assertEqual(self.booking.payment_status, 'pending')
        with self.assertRaises(UserError):
            self.booking.action_confirm()

    def test_paid_invoice_for_other_items_is_not_paid(self):
        other = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Mug', 5.0).id, 'product_uom_qty': 1})
        self._invoice_and_pay(self.order, lines=other)
        self.assertEqual(self.booking.payment_status, 'pending')
        # Paying the booking's own line afterwards does make it paid.
        self._pay_invoice(self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.order.partner_id.id,
            'invoice_line_ids': [(0, 0, {'product_id': self.line.product_id.id, 'quantity': 3,
                                         'price_unit': self.line.price_unit,
                                         'sale_line_ids': [(6, 0, self.line.ids)]})],
        }))
        self.assertEqual(self.booking.payment_status, 'paid')

    def test_shared_order_booking_without_its_lines_is_not_paid(self):
        second = self._new_booking(self.appointment_type, days=4, partner=self.booking.partner_id)
        product = self.appointment_type.payment_product_ids
        Line = self.env['sale.order.line'].with_context(**EDIT)
        second_line = Line.create({'order_id': self.order.id, 'product_id': product.id,
                                   'product_uom_qty': 1, 'appointment_booking_id': second.id,
                                   'appointment_booking_qty': 1})
        second.write({'sale_order_id': self.order.id, 'payment_line_count': 1})
        second_line.with_context(**EDIT).unlink()
        self._invoice_and_pay(self.order)
        self.assertEqual(self.booking.payment_status, 'paid')
        self.assertEqual(second.payment_status, 'pending')

    def test_credit_note_takes_the_payment_back(self):
        invoice = self._invoice_and_pay(self.order)
        self.assertEqual(self.booking.payment_status, 'paid')
        refund = invoice._reverse_moves()
        refund.action_post()
        self.env.invalidate_all()
        self.assertNotEqual(self.booking.payment_status, 'paid')

    def test_customers_cannot_lower_or_drop_booking_lines(self):
        as_visitor = self.line.with_user(self.portal_user).sudo()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            as_visitor.write({'product_uom_qty': 1})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            as_visitor.unlink()
        other_order = self.env['sale.order'].create({'partner_id': self.booking.partner_id.id})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            as_visitor.write({'order_id': other_order.id})
        as_visitor.write({'product_uom_qty': 4})  # more is fine
        self.assertEqual(self.line.product_uom_qty, 4)
        # Staff may still edit the order; the booking is then judged on it.
        self.line.write({'product_uom_qty': 2})
        self.assertEqual(self.booking.payment_status, 'pending')

    def test_booking_line_cannot_be_hung_under_another_line(self):
        """A booking line made the linked child of another line would be
        deleted with it by the database cascade, past every ORM check."""
        other = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Sticker', 1.0).id,
            'product_uom_qty': 1})
        as_visitor = self.line.with_user(self.portal_user).sudo()
        for vals in ({'linked_line_id': other.id}, {'combo_item_id': False, 'product_uom_qty': 3}):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                as_visitor.write(vals)
        self.assertFalse(self.line.linked_line_id)
        # Lines linked that way earlier (by staff, or before this check):
        # their parent cannot be removed by the customer either.
        self.line.with_context(**EDIT).write({'linked_line_id': other.id})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            other.with_user(self.portal_user).sudo().unlink()
        self.assertTrue(self.line.exists())

    def test_customers_cannot_bind_existing_lines(self):
        other = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Pen', 2.0).id,
            'product_uom_qty': 1})
        as_visitor = other.with_user(self.portal_user).sudo()
        for vals in ({'appointment_booking_id': self.booking.id}, {'appointment_booking_qty': 1}):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                as_visitor.write(vals)
        self.assertFalse(other.appointment_booking_id)

    def test_zero_booked_quantity_is_not_paid(self):
        self.line.with_context(**EDIT).write({'appointment_booking_qty': 0})
        self.env.invalidate_all()
        self.assertEqual(self.booking.payment_status, 'pending')

    def test_customers_cannot_bind_lines(self):
        line = self.env['sale.order.line'].with_user(self.portal_user).sudo().create({
            'order_id': self.order.id, 'product_id': self._product('Free', 1.0).id,
            'product_uom_qty': 1, 'appointment_booking_id': self.booking.id,
            'appointment_booking_qty': 3})
        self.assertFalse(line.appointment_booking_id)

    def test_cancel_in_a_shared_cart_removes_only_the_booking_lines(self):
        other = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Tea', 7.0).id, 'product_uom_qty': 1})
        self.booking.action_cancel()
        self.assertEqual(self.order.state, 'sent')
        self.assertEqual(self.order.order_line, other)
        self.assertFalse(self.booking.sale_order_id)
        self.assertEqual(self.booking.payment_status, 'not_required')

    def test_booking_transaction_must_cover_its_lines(self):
        total = self.booking._get_payment_amount()
        partial = self._done_tx(self.booking, total - 1)
        self.assertEqual(self.booking.payment_status, 'pending')
        with self.assertRaises(UserError):
            self._done_tx(self.booking, total)
        partial._create_child_transaction(partial.amount, is_refund=True)._set_done()
        self._done_tx(self.booking, total)
        self.assertEqual(self.booking.payment_status, 'paid')

    def test_upgrade_recomputes_open_bookings(self):
        other = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': self._product('Gift', 3.0).id, 'product_uom_qty': 1})
        self._invoice_and_pay(self.order, lines=other)
        self.env.flush_all()
        self.env.cr.execute("UPDATE appointment_booking SET payment_status = 'paid' WHERE id = %s",
                            [self.booking.id])  # what the old rule stored
        self.env.invalidate_all()
        mig = _load_migration_3_2_2()
        changed = mig._recompute_open_payment_status(self.env)
        self.assertIn(self.booking.id, changed)
        self.env.invalidate_all()
        self.assertEqual(self.booking.payment_status, 'pending')
        notes = self.booking.message_ids.filtered(
            lambda m: 'payment status check 18.0.3.2.2' in (m.body or ''))
        self.assertEqual(len(notes), 1, 'the lowered status is noted on the booking')
        self.assertEqual(notes.subtype_id, self.env.ref('mail.mt_note'))
        self.assertEqual(mig._recompute_open_payment_status(self.env), [], 'safe to re-run')
        self.assertEqual(len(self.booking.message_ids.filtered(
            lambda m: 'payment status check 18.0.3.2.2' in (m.body or ''))), 1)


@tagged('post_install', '-at_install')
class TestCartModeBinding(BindingCommon, RulesHttpCommon, HttpCase):
    """f94e04013795 / 7f0060bd8934 through the real website cart."""

    def setUp(self):
        super().setUp()
        if not self.env['ir.module.module'].search_count(
                [('name', '=', 'website_sale'), ('state', '=', 'installed')]):
            self.skipTest('website_sale is not installed')
        self.appointment_type = self._paid_type(auto_confirm=False, payment_per_person=True)

    def _json(self, url, params):
        response = self.url_open(url, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        return response.json()

    def _book(self, days, email, guests):
        response = self._post(self.appointment_type, self._wall(days, 10), guest_email=email,
                              guest_count=guests)
        self.assertIn('/shop/cart', response.url)
        return self._bookings(self.appointment_type, guest_email=email)

    def test_cart_lines_of_a_booking_cannot_be_lowered(self):
        booking = self._book(3, 'cart.guest@example.com', 3)
        line = booking.payment_line_ids.filtered(lambda l: not l.display_type)
        self.assertEqual(line.product_uom_qty, 3)
        for qty in (1, 0):
            result = self._json('/shop/cart/update_json', {
                'product_id': line.product_id.id, 'line_id': line.id, 'set_qty': qty})
            self.assertIn('error', result, 'qty %s accepted' % qty)
        self.env.invalidate_all()
        self.assertTrue(line.exists())
        self.assertEqual(line.product_uom_qty, 3)
        result = self._json('/shop/cart/clear', {})
        self.assertIn('error', result)
        self.env.invalidate_all()
        self.assertTrue(line.exists())

    def test_booking_line_cannot_be_removed_through_a_linked_line(self):
        booking = self._book(3, 'cart.cascade@example.com', 3)
        line = booking.payment_line_ids.filtered(lambda l: not l.display_type)
        cheap = self._json('/shop/cart/update_json', {
            'product_id': self._product('Cheap', 1.0).id, 'add_qty': 1})['result']['line_id']
        result = self._json('/shop/cart/update_json', {
            'product_id': line.product_id.id, 'line_id': line.id, 'set_qty': 3,
            'linked_line_id': cheap})
        self.assertIn('error', result, 'a booking line was hung under another line')
        self._json('/shop/cart/update_json', {
            'product_id': self.env['sale.order.line'].sudo().browse(cheap).product_id.id,
            'line_id': cheap, 'set_qty': 0})
        self.env.invalidate_all()
        self.assertTrue(line.exists())
        self.assertEqual(line.product_uom_qty, 3)

    def test_bookings_in_one_cart_keep_their_own_lines(self):
        first = self._book(3, 'cart.first@example.com', 1)
        second = self._book(4, 'cart.second@example.com', 2)
        self.assertEqual(first.sale_order_id, second.sale_order_id, 'one shared cart')
        first_line = first.payment_line_ids.filtered(lambda l: not l.display_type)
        second_line = second.payment_line_ids.filtered(lambda l: not l.display_type)
        self.assertTrue(first_line and second_line)
        self.assertNotEqual(first_line, second_line)
        self.assertEqual((first_line.product_uom_qty, second_line.product_uom_qty), (1, 2))
        # Buying more of the same product in the shop may add to a booking
        # line, but never below what the booking needs.
        product = first_line.product_id
        self._json('/shop/cart/update_json', {'product_id': product.id, 'add_qty': 1})
        self.env.invalidate_all()
        self.assertEqual(second_line.product_uom_qty, 2)
        self.assertNotIn('error', self._json('/shop/cart/update_json', {
            'product_id': product.id, 'line_id': first_line.id, 'set_qty': 1}))
        self.assertIn('error', self._json('/shop/cart/update_json', {
            'product_id': product.id, 'line_id': second_line.id, 'set_qty': 1}))
        self.env.invalidate_all()
        self.assertEqual((first_line.product_uom_qty, second_line.product_uom_qty), (1, 2))
        self.assertTrue(first._get_payment_url())
        self.assertTrue(second._get_payment_url(), 'the cart was moved to the second guest')

    def test_pay_page_charges_the_booking_lines_only(self):
        booking = self._book(3, 'cart.payer@example.com', 2)
        self._json('/shop/cart/update_json', {'product_id': self._product('Big Extra', 500.0).id,
                                              'add_qty': 1})
        self.env.invalidate_all()
        lines_total = sum(booking.payment_line_ids.mapped('price_total'))
        self.assertLess(lines_total, booking.sale_order_id.amount_total)
        provider = self.env['payment.provider'].create({
            'name': 'Booking Page Dummy', 'code': 'none', 'state': 'test', 'is_published': True,
            'payment_method_ids': [(6, 0, self.env.ref('payment.payment_method_unknown').ids)],
        })
        Tx = type(self.env['payment.transaction'])
        with patch.object(Tx, '_get_processing_values', lambda self: {'reference': self.reference}):
            result = self._json('/appointment/payment/transaction/%d' % booking.id, {
                'access_token': booking.access_token,
                'provider_id': provider.id,
                'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
                'flow': 'direct',
                'amount': 1,
                'landing_route': 'https://evil.example.com/',
            })
        self.assertIn('result', result, result)
        self.env.invalidate_all()
        tx = booking.payment_transaction_id
        self.assertEqual(tx.appointment_booking_id, booking)
        self.assertAlmostEqual(tx.amount, lines_total)
        self.assertEqual(tx.currency_id, booking.sale_order_id.currency_id)
        self.assertNotIn('evil', tx.landing_route or '')
        tx._set_done()
        self.env.invalidate_all()
        self.assertEqual(booking.payment_status, 'paid')


@tagged('post_install', '-at_install')
class TestSharedCartPayment(BindingCommon, TransactionCase):
    """f94e04013795 / 7f0060bd8934: a payment of the shared cart that does not
    pay the booking's own lines neither holds the slot until the appointment
    nor confirms the booking or raises a "paid, not confirmed" alert."""

    def _shared_cart(self, auto_confirm, days):
        appointment_type = self._paid_type(auto_confirm=auto_confirm, payment_per_person=True)
        booking = self._new_booking(appointment_type, days=days, guest_count=3)
        order = booking._create_sale_order()
        self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self._product('Sticker', 1.0).id,
            'product_uom_qty': 1})
        self.assertEqual(booking.state, 'pending_payment')
        return booking, order

    def _order_tx(self, order, amount, reference):
        provider = self.env['payment.provider'].create({
            'name': 'Cart Dummy', 'code': 'none', 'state': 'test',
            'payment_method_ids': [(6, 0, self.env.ref('payment.payment_method_unknown').ids)],
        })
        return self.env['payment.transaction'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
            'reference': reference, 'amount': amount,
            'currency_id': order.currency_id.id, 'partner_id': order.partner_id.id,
            'sale_order_ids': [(6, 0, order.ids)],
        })

    def _post_process(self, tx):
        Tx = type(self.env['payment.transaction'])
        if hasattr(Tx, '_create_payment'):
            with patch.object(Tx, '_create_payment', return_value=None):
                tx._post_process()
        else:
            tx._post_process()
        self.env.invalidate_all()

    def _assert_untouched(self, booking, hold, tx):
        self.assertEqual(booking.state, 'pending_payment')
        self.assertEqual(booking.payment_status, 'pending')
        self.assertEqual(booking.payment_hold_until, hold, 'the hold was not extended')
        self.assertFalse(booking.payment_confirm_failed)
        self.assertFalse(booking.activity_ids, 'no "paid booking needs confirmation" activity')
        self.assertNotEqual(booking.payment_transaction_id, tx)

    def _pay_cart_without_the_booking_lines(self, auto_confirm):
        booking, order = self._shared_cart(auto_confirm, days=3)
        # What the linked_line_id cascade did: the booking lines are gone.
        booking.payment_line_ids.with_context(**EDIT).unlink()
        self.env.invalidate_all()
        hold = booking.payment_hold_until
        tx = self._order_tx(order, order.amount_total, 'CART-OTHER')
        tx._set_done()
        self._post_process(tx)
        self._assert_untouched(booking, hold, tx)

    def test_paying_the_cart_without_the_booking_lines(self):
        self._pay_cart_without_the_booking_lines(auto_confirm=False)

    def test_paying_the_cart_without_the_booking_lines_auto_confirm(self):
        self._pay_cart_without_the_booking_lines(auto_confirm=True)

    def _pay_part_of_the_cart(self, auto_confirm):
        booking, order = self._shared_cart(auto_confirm, days=5)
        hold = booking.payment_hold_until
        wire = self._order_tx(order, 1.0, 'CART-PART-WIRE')
        wire._set_pending()
        self._post_process(wire)
        self.assertFalse(booking.payment_pending_hold_granted)
        tx = self._order_tx(order, 1.0, 'CART-PART')
        tx._set_done()
        self._post_process(tx)
        self._assert_untouched(booking, hold, tx)

    def test_paying_part_of_the_cart(self):
        self._pay_part_of_the_cart(auto_confirm=False)

    def test_paying_part_of_the_cart_auto_confirm(self):
        self._pay_part_of_the_cart(auto_confirm=True)

    def test_paying_the_whole_cart_keeps_the_slot(self):
        booking, order = self._shared_cart(False, days=7)
        tx = self._order_tx(order, order.amount_total, 'CART-ALL')
        tx._set_done()
        self._post_process(tx)
        self.assertEqual(booking.payment_transaction_id, tx)
        self.assertEqual(booking.payment_hold_until, booking.end_datetime)


@tagged('post_install', '-at_install')
class TestPaymentFailureNotes(BindingCommon, TransactionCase):
    """bab08eb294c9: failed payments of one booking cannot flood its chatter
    or the guest's inbox."""

    def test_failure_notes_are_capped(self):
        appointment_type = self._paid_type()
        booking = self._new_booking(appointment_type)
        booking.write({'state': 'pending_payment', 'guest_email': 'notes.victim@example.org'})
        provider = self.env['payment.provider'].create({
            'name': 'Notes Dummy', 'code': 'none', 'state': 'test',
            'payment_method_ids': [(6, 0, self.env.ref('payment.payment_method_unknown').ids)],
        })
        for index in range(12):
            tx = self.env['payment.transaction'].sudo().create({
                'provider_id': provider.id,
                'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
                'reference': 'NOTES-%d' % index, 'amount': 100.0,
                'currency_id': self.env.company.currency_id.id,
                'partner_id': booking.partner_id.id, 'appointment_booking_id': booking.id,
            })
            tx._set_error('declined')
            tx._post_process()
        self.env.invalidate_all()
        self.assertEqual(booking.payment_failure_count, 12, 'every failure is counted')
        notes = booking.message_ids.filtered(lambda m: 'Payment failure #' in (m.body or ''))
        self.assertEqual(len(notes), 6, '5 notes, then one saying the rest are only counted')
        mails = self.env['mail.mail'].sudo().search([
            ('model', '=', 'appointment.booking'), ('res_id', '=', booking.id),
            ('subject', 'ilike', 'Payment failed')])
        self.assertLessEqual(len(mails), 1)

    def test_note_limit_zero_means_no_notes(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'reservation_module.payment_failure_note_limit', '0')
        booking = self._new_booking(self._paid_type())
        booking.write({'state': 'pending_payment'})
        provider = self.env['payment.provider'].create({
            'name': 'No Notes Dummy', 'code': 'none', 'state': 'test',
            'payment_method_ids': [(6, 0, self.env.ref('payment.payment_method_unknown').ids)],
        })
        for index in range(3):
            tx = self.env['payment.transaction'].sudo().create({
                'provider_id': provider.id,
                'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
                'reference': 'NO-NOTES-%d' % index, 'amount': 100.0,
                'currency_id': self.env.company.currency_id.id,
                'partner_id': booking.partner_id.id, 'appointment_booking_id': booking.id,
            })
            tx._set_error('declined')
            tx._post_process()
        self.env.invalidate_all()
        self.assertEqual(booking.payment_failure_count, 3)
        self.assertFalse(booking.message_ids.filtered(lambda m: 'Payment failure #' in (m.body or '')))


class OrderPaymentCommon(BindingCommon):
    """Payment transactions of an order, post-processed as the provider
    would (the dummy provider has no journal, so no accounting payment)."""

    TEMPLATES = ('reservation_module.email_template_booking_created',
                 'reservation_module.email_template_payment_failure')

    def setUp(self):
        super().setUp()
        self.provider = self.env['payment.provider'].create({
            'name': 'Legacy Dummy', 'code': 'none', 'state': 'test',
            'payment_method_ids': [(6, 0, self.env.ref('payment.payment_method_unknown').ids)],
        })

    def _order_tx(self, reference, order=None):
        order = order or self.victim_order
        return self.env['payment.transaction'].sudo().create({
            'provider_id': self.provider.id,
            'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
            'reference': reference,
            'amount': order.amount_total,
            'currency_id': order.currency_id.id,
            'partner_id': order.partner_id.id,
            'sale_order_ids': [(6, 0, order.ids)],
        })

    def _post_process(self, tx):
        Tx = type(self.env['payment.transaction'])
        if hasattr(Tx, '_create_payment'):
            with patch.object(Tx, '_create_payment', return_value=None):
                tx._post_process()
        else:
            tx._post_process()
        self.env.invalidate_all()

    def _render(self, xmlid, booking, lang=None):
        template = self.env.ref(xmlid)
        return template._render_field('body_html', booking.ids, set_lang=lang)[booking.id]

    def _own_link(self, order):
        return '/my/orders/%d?access_token=%s' % (order.id, order.access_token)


class LegacyLinkCommon(OrderPaymentCommon):
    """A booking row written before the ownership check existed (the
    pre-upgrade portal RPC create hole, or an old manual link) that points at
    another customer's order (Bob's, a registered customer). Mallory, whose
    row it is, is a portal user: the RPC hole needed a login."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=False)
        self.victim_order = self._foreign_order()
        self.assertTrue(self.victim_order.access_token)
        self.legacy = self._new_booking(self.appointment_type, partner=self._portal_partner('Mallory'))
        self.legacy.write({'state': 'pending_payment', 'guest_email': 'mallory.inbox@example.com'})
        self._plant_order(self.legacy, self.victim_order)


@tagged('post_install', '-at_install')
class TestForeignOrderLegacyLinks(LegacyLinkCommon, TransactionCase):
    """e10ecad8918d (final review): such a row is not the order's booking.
    The order's failed payment does not mail its guest the order's token,
    the order's own payment is not refused because of the row's slot, guest
    mail templates never print the order's token, and the upgrade reports the
    row without changing it (test_legacy_order_links has the whole upgrade)."""

    def test_failed_order_payment_does_not_mail_the_legacy_guest(self):
        self.assertEqual(self.legacy.payment_status, 'pending')
        tx = self._order_tx('LEGACY-ERROR')
        tx._set_error('Card declined')
        self._post_process(tx)
        token = self.victim_order.access_token
        self.assertFalse(self.env['mail.mail'].sudo().search([
            ('model', '=', 'appointment.booking'), ('body_html', 'ilike', token)]))
        self.assertFalse(self.env['mail.message'].sudo().search([
            ('model', '=', 'appointment.booking'), ('body', 'ilike', token)]))
        self.assertFalse(self.env['mail.mail'].sudo().search([('email_to', 'ilike', 'mallory.inbox')]))
        self.assertEqual(self.legacy.payment_failure_count, 0)
        self.assertFalse(tx.appointment_failure_notified)

    def test_the_order_can_still_be_paid(self):
        # The legacy row's slot was sold since: its own payment would be refused.
        self._booking(self.appointment_type, self.legacy.start_datetime,
                      staff_user_id=self.host.id, partner_id=self._partner('Carol').id)
        with self.assertRaises(UserError):
            self.legacy._ensure_payment_hold()
        hold = self.legacy.payment_hold_until
        tx = self._order_tx('LEGACY-PAY')
        self.assertEqual(tx.sale_order_ids, self.victim_order)
        tx._set_done()
        self._post_process(tx)
        self.assertEqual(self.legacy.state, 'pending_payment')
        self.assertNotEqual(self.legacy.payment_transaction_id, tx)
        self.assertEqual(self.legacy.payment_hold_until, hold)

    def test_guest_mail_templates_never_print_a_foreign_order(self):
        for xmlid in self.TEMPLATES:
            body = self._render(xmlid, self.legacy)
            self.assertNotIn(self.victim_order.access_token, body, xmlid)
            self.assertNotIn('/my/orders/%d' % self.victim_order.id, body, xmlid)
        own = self._new_booking(self.appointment_type, days=5)
        order = own._create_sale_order()
        for xmlid in self.TEMPLATES:
            self.assertIn(self._own_link(order), self._render(xmlid, own), xmlid)

    def _legacy_order_of(self, partner):
        product = self.appointment_type.payment_product_ids
        return self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1})],
        })

    def test_a_foreign_row_does_not_keep_the_owner_booking_unpaid(self):
        bob = self.victim_order.partner_id
        order = self._legacy_order_of(bob)
        owner = self._new_booking(self.appointment_type, days=7, partner=bob)
        self._plant_order(owner, order)
        self._plant_order(self.legacy, order)
        self._invoice_and_pay(order)
        self.env.add_to_compute(owner._fields['payment_status'], owner)
        self.assertEqual(owner.payment_status, 'paid')

    def test_a_foreign_row_does_not_keep_the_owner_order_open(self):
        bob = self.victim_order.partner_id
        order = self._legacy_order_of(bob)
        order.action_quotation_sent()
        owner = self._new_booking(self.appointment_type, days=7, partner=bob)
        self._plant_order(owner, order)
        self._plant_order(self.legacy, order)
        owner.action_cancel()
        self.assertEqual(order.state, 'cancel')

    def test_upgrade_reports_the_foreign_order_and_changes_nothing(self):
        mig = _load_migration_3_2_2()
        alice = self._new_booking(self.appointment_type, days=6)
        alice_order = self.env['sale.order'].create({'partner_id': alice.partner_id.id})
        self._plant_order(alice, alice_order)  # an older link to the customer's own order
        failed = self._order_tx('LEGACY-OLD-FAIL')
        failed._set_error('declined')
        # What the old Flow 2 wrote when the order was paid: the order's tx.
        self.legacy.payment_transaction_id = failed
        self.env.flush_all()
        mig.migrate(self.env.cr, '18.0.3.2.1')
        self.env.invalidate_all()
        self.assertEqual(self.legacy.sale_order_id, self.victim_order, 'the link is kept')
        self.assertEqual(self.legacy.payment_transaction_id, failed, 'the transaction is kept')
        self.assertEqual(alice.sale_order_id, alice_order)
        notes = self.legacy.message_ids.filtered(lambda m: self.victim_order.name in (m.body or ''))
        self.assertEqual(len(notes), 1, 'the row is noted once')
        self.assertTrue(all(m.subtype_id == self.env.ref('mail.mt_note') for m in notes))
        self.assertNotEqual(self.victim_order.state, 'cancel')
        # Runtime still treats the order as somebody else's.
        self.assertFalse(self.legacy._get_payment_url())
        self.assertFalse(self._order_tx('LEGACY-AFTER')._get_held_bookings())
        # Safe to re-run: nothing is reported twice.
        self.assertFalse(mig._flag_foreign_sale_orders(self.env))
        self.assertEqual(alice.sale_order_id, alice_order)
        self.assertEqual(self.legacy.sale_order_id, self.victim_order)


@tagged('post_install', '-at_install')
class TestPaymentLinkTranslations(LegacyLinkCommon, TransactionCase):
    """e10ecad8918d (final review): mail.template.body_html is translated as a
    whole (translate=True), so an upgrade only replaces the English body. The
    zh_TW body shipped in i18n and the translated bodies stored on existing
    databases must not read the token from sale_order_id either."""

    def setUp(self):
        super().setUp()
        for code in ('zh_TW', 'zh_CN'):
            self.env['res.lang']._activate_lang(code)
        self.own = self._new_booking(self.appointment_type, days=5)
        self.own_order = self.own._create_sale_order()

    def _shipped_bodies(self, filename):
        """body_html entries of the two templates in an i18n file, read as the
        translation import wizard does (without the .pot merge)."""
        path = get_module_path('reservation_module') + '/i18n/' + filename
        bodies = {}
        for entry in polib.pofile(path):
            for occurrence, _line in entry.occurrences:
                for xmlid in self.TEMPLATES:
                    if occurrence == 'model:mail.template,body_html:' + xmlid:
                        bodies[xmlid] = entry
        return bodies

    def _store_translation(self, xmlid, lang, body):
        """As if the translation had been loaded into this database."""
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE mail_template SET body_html = body_html || jsonb_build_object(%s, %s::text)"
            " WHERE id = %s", [lang, body, self.env.ref(xmlid).id])
        self.env.invalidate_all()

    def test_shipped_bodies_use_the_booking_own_order(self):
        for filename in ('zh_TW.po', 'zh_CN.po', 'reservation_module.pot'):
            bodies = self._shipped_bodies(filename)
            self.assertEqual(set(bodies), set(self.TEMPLATES), filename)
            for xmlid, entry in bodies.items():
                self.assertNotIn('sale_order_id', entry.msgid, (filename, xmlid))
                self.assertNotIn('sale_order_id', entry.msgstr, (filename, xmlid))
        for xmlid, entry in self._shipped_bodies('zh_TW.po').items():
            self._store_translation(xmlid, 'zh_TW', entry.msgstr)
            self.assertIn('付款', self.env.ref(xmlid).with_context(lang='zh_TW').body_html, xmlid)
            self.assertNotIn(self.victim_order.access_token, self._render(xmlid, self.legacy, 'zh_TW'),
                             xmlid)
            self.assertIn(self._own_link(self.own_order), self._render(xmlid, self.own, 'zh_TW'), xmlid)

    def test_upgrade_rewrites_stored_translations(self):
        mig = _load_migration_3_2_2()
        xmlid = 'reservation_module.email_template_payment_failure'
        template = self.env.ref(xmlid)
        stale = (
            '<div><p>應付金額 <t t-out="object.sale_order_id.amount_total if object.sale_order_id else 0"/></p>'
            '<t t-if="object.sale_order_id"><a t-attf-href="{{ object.sale_order_id.get_portal_url() }}">'
            '重試付款</a></t><t t-else=""><a t-att-href="object.get_portal_url()">查看預約</a></t></div>')
        custom = ('<div><a t-attf-href="/my/orders/{{ object.sale_order_id.id }}'
                  '?access_token={{ object.sale_order_id.access_token }}">自訂付款連結</a></div>')
        self._store_translation(xmlid, 'zh_TW', stale)
        self._store_translation(xmlid, 'zh_CN', custom)
        self.assertIn(self.victim_order.access_token, self._render(xmlid, self.legacy, 'zh_TW'),
                      'precondition: the stored body leaks the order token')

        self.assertIn(template.id, mig._fix_payment_link_translations(self.env))
        self.env.invalidate_all()
        zh_tw = template.with_context(lang='zh_TW').body_html
        self.assertNotIn('sale_order_id', zh_tw)
        self.assertIn('重試付款', zh_tw, 'the stored wording is kept')
        zh_cn = template.with_context(lang='zh_CN').body_html
        self.assertNotIn('自訂付款連結', zh_cn, 'a body still reading the token is dropped')
        self.assertEqual(zh_cn, template.with_context(lang='en_US').body_html)
        for lang in ('zh_TW', 'zh_CN'):
            self.assertNotIn(self.victim_order.access_token, self._render(xmlid, self.legacy, lang), lang)
        self.assertIn(self._own_link(self.own_order), self._render(xmlid, self.own, 'zh_TW'))
        self.assertFalse(mig._fix_payment_link_translations(self.env), 'safe to re-run')

    def test_upgrade_rewrites_old_taiwan_mail_time_widgets(self):
        """An existing zh_TW body is retained on -u, so repair its QWeb time."""
        mig = _load_migration_3_2_2()
        self.appointment_type.timezone = 'Asia/Taipei'
        self.env.user.tz = 'UTC'
        path = get_module_path('reservation_module') + '/i18n/zh_TW.po'
        entries = polib.pofile(path)
        xmlids = (
            'reservation_module.email_template_booking_reminder',
            'reservation_module.email_template_booking_confirmed',
            'reservation_module.email_template_booking_created',
            'reservation_module.email_template_booking_done',
            'reservation_module.email_template_booking_cancelled',
        )
        before_render = {}
        for xmlid in xmlids:
            occurrence = 'model:mail.template,body_html:' + xmlid
            entry = next(e for e in entries if any(loc == occurrence for loc, _ in e.occurrences))
            old_body = entry.msgstr.replace(', &quot;tz_name&quot;: object.display_tz', '')
            self.assertNotIn('tz_name', old_body)
            self._store_translation(xmlid, 'zh_TW', old_body)
            before_render[xmlid] = self._render(xmlid, self.own, 'zh_TW')
        changed = mig._fix_payment_link_translations(self.env)
        self.env.invalidate_all()
        converter = self.env['ir.qweb.field.datetime'].with_context(lang='zh_TW')
        local_time = converter.value_to_html(self.own.start_datetime, {'tz_name': 'Asia/Taipei'})
        utc_time = converter.value_to_html(self.own.start_datetime, {'tz_name': 'UTC'})
        self.assertNotEqual(local_time, utc_time)
        for xmlid in xmlids:
            self.assertIn(self.env.ref(xmlid).id, changed)
            body = self.env.ref(xmlid).with_context(lang='zh_TW').body_html
            self.assertEqual(body.count('&quot;tz_name&quot;: object.display_tz'), 2)
            after = self._render(xmlid, self.own, 'zh_TW')
            self.assertNotEqual(before_render[xmlid], after, xmlid)
            self.assertIn(local_time, after, xmlid)
            self.assertNotIn(utc_time, after, xmlid)
            self.assertIn('tz_name', body)
        self.assertFalse(mig._fix_payment_link_translations(self.env))
