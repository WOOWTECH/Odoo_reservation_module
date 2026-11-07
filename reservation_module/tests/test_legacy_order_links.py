# -*- coding: utf-8 -*-
"""Legacy order links and the 18.0.3.2.2 upgrade (sweep 2026-11-07, round 2).

Round 1 judged a booking's order by its lines or by its customer and the
upgrade unlinked every booking that failed the test. But before 18.0.3.2.2 the
website made a new guest contact for every anonymous booking and, in cart
mode, moved the visitor's shared cart to the contact of the latest booking: the
earlier bookings of a cart looked foreign and lost their order, their payment
transaction and (once recomputed) their paid status.

  * guest contacts, and the three grounds of appointment.booking
    _is_own_sale_order (bound line, same customer, shared guest cart, which
    also covers a cart that moved to the visitor's account); the attacker of
    e10ecad8918d, a portal user, is on none of them
  * the shared guest cart of an anonymous visitor is its bookings' own: the
    cart's payment holds or confirms every one of them, cancelling one does
    not cancel the cart of the others
  * the upgrade never unlinks an order, never clears a payment transaction and
    never changes a state or a payment status; a row whose order is still not
    its own (the portal RPC create hole, a staff link to another customer's
    order) is reported once, and stays closed at runtime
"""

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .test_booking_rules import RulesHttpCommon
from .test_payment_binding import BindingCommon, LegacyLinkCommon, OrderPaymentCommon
from .test_security_acl import _load_migration_3_2_2

MARKER = 'order link check 18.0.3.2.2'


class LegacyCartTools:
    """What the anonymous flow of 3.1.x / 3.2.1 left in a database: rows
    written past every check, so they are planted with SQL. Needs
    OrderPaymentCommon."""

    def _guest(self, name):
        """A guest contact, as the anonymous booking form made it."""
        slug = name.lower().replace(' ', '.')
        return self.env['res.partner'].create({
            'name': name, 'email': '%s@guest.example.com' % slug, 'phone': '+886 900 111 222'})

    def _legacy_cart(self, appointment_type, guests, first_day=3):
        """One website cart and one booking per guest: the cart's contact is
        the latest guest, no line is bound to a booking, each booking has a
        section in the cart."""
        product = appointment_type.payment_product_ids
        vals = {'partner_id': guests[-1].id,
                'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': len(guests)})]}
        if 'website_id' in self.env['sale.order']._fields:
            vals['website_id'] = self.env['website'].search([], limit=1).id
        order = self.env['sale.order'].create(vals)
        order.action_quotation_sent()
        order._portal_ensure_token()
        bookings = self.env['appointment.booking']
        for index, guest in enumerate(guests):
            booking = self._new_booking(appointment_type, days=first_day + index, partner=guest)
            booking.write({'state': 'pending_payment', 'guest_name': guest.name,
                           'guest_email': guest.email})
            self._plant_order(booking, order)
            self.env['sale.order.line'].create({
                'order_id': order.id, 'display_type': 'line_section', 'sequence': 999,
                'name': '%s — %s' % (appointment_type.name, booking.name)})
            bookings |= booking
        return order, bookings

    def _stamp(self, bookings, state, payment_status, tx=None):
        """State, payment status and transaction as the old code stored them."""
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE appointment_booking SET state = %s, payment_status = %s, "
            "payment_transaction_id = COALESCE(%s, payment_transaction_id) WHERE id IN %s",
            [state, payment_status, tx.id if tx else None, tuple(bookings.ids)])
        self.env.invalidate_all()

    def _paid_by_own_page(self, booking, order):
        """The booking paid through its own pay page: a done transaction of
        the booking covering the cart, the booking confirmed."""
        tx = self._done_tx(booking, order.amount_total)
        self._stamp(booking, 'confirmed', 'paid', tx)
        return tx

    def _paid_cart(self, appointment_type, guests, first_day, state='confirmed'):
        """A cart paid through the website checkout: the order is confirmed,
        invoiced and paid, its transaction is done and every booking of it has
        that transaction and is paid, as the old Flow 2 left them: confirmed,
        or (``state``) still waiting for staff to confirm."""
        order, bookings = self._legacy_cart(appointment_type, guests, first_day)
        self._invoice_and_pay(order)
        tx = self._order_tx('LEGACY-PAID-%d' % order.id, order)
        tx._set_done()
        self._stamp(bookings, state, 'paid', tx)
        return order, bookings, tx

    def _snapshot(self, bookings):
        self.env.flush_all()
        self.env.invalidate_all()
        return {booking.id: (booking.sale_order_id.id, booking.payment_transaction_id.id,
                             booking.state, booking.payment_status)
                for booking in bookings}

    def _notes(self, booking):
        return self.env['mail.message'].search([
            ('model', '=', 'appointment.booking'), ('res_id', '=', booking.id),
            ('body', 'ilike', MARKER)])

    def _todos(self, booking):
        return self.env['mail.activity'].search([
            ('res_model', '=', 'appointment.booking'), ('res_id', '=', booking.id)])

    def _upgrade(self):
        """The real migration entry point."""
        self.env.flush_all()
        _load_migration_3_2_2().migrate(self.env.cr, '18.0.3.2.1')
        self.env.invalidate_all()

    def _pay_cart(self, order, reference):
        """The cart is paid: invoice paid, transaction done, post-processed."""
        self._invoice_and_pay(order)
        tx = self._order_tx(reference, order)
        tx._set_done()
        self._post_process(tx)
        return tx


# ---------------------------------------------------------------------------
# Guest contacts and the grounds of _is_own_sale_order
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestGuestContact(BindingCommon, TransactionCase):
    """A guest contact is a live contact nobody can log in as."""

    def setUp(self):
        super().setUp()
        self.Booking = self.env['appointment.booking']

    def _user_for(self, partner, login):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': partner.name, 'login': login, 'partner_id': partner.id,
            'groups_id': [(6, 0, self.env.ref('base.group_portal').ids)],
        })

    def test_plain_contacts_are_guests(self):
        guest = self._partner('Gina')
        self.assertTrue(self.Booking._is_guest_contact(guest))
        child = self.env['res.partner'].create({'name': 'Gina Home', 'parent_id': guest.id,
                                                'type': 'delivery'})
        self.assertTrue(self.Booking._is_guest_contact(child), 'a checkout address of a guest')

    def test_nobody_and_archived_contacts_are_not_guests(self):
        self.assertFalse(self.Booking._is_guest_contact(self.env['res.partner']))
        guest = self._partner('Gina')
        guest.active = False
        self.assertFalse(self.Booking._is_guest_contact(guest))

    def test_contacts_with_a_login_are_not_guests(self):
        staff = self._user('Clerk', 'guest_rule_clerk').partner_id
        for partner in (self._portal_partner('Ivy'), staff,
                        self.env.ref('base.partner_root'),  # OdooBot
                        self.env.ref('base.public_user').partner_id,
                        self.env['website'].search([], limit=1).user_id.partner_id):
            self.assertFalse(self.Booking._is_guest_contact(partner), partner.display_name)

    def test_archived_login_still_counts(self):
        partner = self._portal_partner('Ivy')
        partner.user_ids.active = False
        self.assertTrue(partner.active)
        self.assertFalse(self.Booking._is_guest_contact(partner))

    def test_closed_account_with_archived_contact_is_not_a_guest(self):
        """The portal "delete my account" flow archives the user and the
        partner, the cron then deletes the user; the partner survives when
        something still points at it."""
        partner = self._portal_partner('Ivy')
        user = partner.user_ids
        user.action_archive()
        partner.action_archive()
        user.unlink()
        self.assertFalse(partner.user_ids)
        self.assertFalse(self.Booking._is_guest_contact(partner))

    def test_the_family_of_a_login_is_not_guests(self):
        company = self.env['res.partner'].create({'name': 'Acme Ltd', 'is_company': True})
        buyer = self.env['res.partner'].create({'name': 'Wile', 'parent_id': company.id})
        sibling = self.env['res.partner'].create({'name': 'Road', 'parent_id': company.id})
        self.assertTrue(self.Booking._is_guest_contact(company))
        user = self._user_for(buyer, 'guest_rule_wile')
        for partner in (company, buyer, sibling):
            self.assertFalse(self.Booking._is_guest_contact(partner), partner.name)
        self.assertTrue(self.Booking._is_guest_contact(self._partner('Gina')), 'unrelated guests stay')
        # The login and its contact are archived (an account being closed).
        user.action_archive()
        buyer.action_archive()
        for partner in (company, sibling):
            self.assertFalse(self.Booking._is_guest_contact(partner), partner.name)

    def test_a_login_of_another_company_counts(self):
        other = self.env['res.company'].create({'name': 'Other Company'})
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Foreign Ivy', 'login': 'guest_rule_other_company',
            'company_id': other.id, 'company_ids': [(6, 0, other.ids)],
            'groups_id': [(6, 0, self.env.ref('base.group_portal').ids)],
        })
        # Asked on behalf of somebody who works in the main company only.
        in_main_company = self.Booking.with_context(allowed_company_ids=self.env.company.ids)
        self.assertFalse(in_main_company._is_guest_contact(user.partner_id))

    def test_a_guest_that_gets_an_account_stops_being_one(self):
        guest = self._partner('Gina')
        self.assertTrue(self.Booking._is_guest_contact(guest))
        self._user_for(guest, 'guest_rule_gina')
        self.assertFalse(self.Booking._is_guest_contact(guest))


@tagged('post_install', '-at_install')
class TestOwnOrderGrounds(BindingCommon, TransactionCase):
    """Bound line, same customer or shared guest cart; the check on a new link
    asks the same question."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=False)

    def _order_of(self, partner):
        return self.env['sale.order'].create({'partner_id': partner.id})

    def _booking_of(self, partner, days=3):
        return self._booking(self.appointment_type, self._wall(days, 10), state='draft',
                             partner_id=partner.id if partner else False)

    def test_who_owns_which_order(self):
        guest, other_guest = self._partner('Gina'), self._partner('Hank')
        registered, other_registered = self._portal_partner('Ivy'), self._portal_partner('Jack')
        archived = self._partner('Kim')
        archived.active = False
        company = self.env['res.partner'].create({'name': 'Acme Ltd', 'is_company': True})
        colleague = self.env['res.partner'].create({'name': 'Wile', 'parent_id': company.id})
        rows = [
            # (what it is, booking's contact, order's contact, the order is the booking's)
            ('same contact', guest, guest, True),
            ('same customer', colleague, company, True),
            ('two guests: the shared cart of a visitor', guest, other_guest, True),
            ("guest on a registered customer's order", guest, registered, False),
            ("portal user on a guest's order", registered, guest, False),
            ("portal user on another customer's order", registered, other_registered, False),
            ('portal user on its own order', registered, registered, True),
            ('archived guest', archived, guest, False),
            ('order of an archived guest', guest, archived, False),
            ('booking without a contact', False, guest, False),
        ]
        for index, (label, booking_partner, order_partner, own) in enumerate(rows):
            order = self._order_of(order_partner)
            booking = self._booking_of(booking_partner, days=3 + index)
            self.assertEqual(booking._is_own_sale_order(order), own, label)
            if own:
                booking.write({'sale_order_id': order.id})
                self.assertEqual(booking.sale_order_id, order, label)
            else:
                with self.assertRaises(ValidationError, msg=label), self.env.cr.savepoint():
                    booking.write({'sale_order_id': order.id})

    def test_bound_line_wins_over_the_contacts(self):
        booking = self._booking_of(self._portal_partner('Ivy'))
        order = booking._create_sale_order()
        self.assertTrue(booking._is_own_sale_order(order))
        order.partner_id = self._portal_partner('Jack')  # the cart moved to somebody else
        self.assertTrue(booking._is_own_sale_order(order))

    def test_a_booking_cannot_be_created_on_a_registered_customers_order(self):
        registered_order = self._foreign_order()
        for partner in (self._partner('Gina'), self._portal_partner('Mallory')):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self._booking(self.appointment_type, self._wall(5, 10), state='draft',
                              partner_id=partner.id, sale_order_id=registered_order.id)

    def test_the_shared_cart_rows_can_also_be_written_through_the_orm(self):
        """Rows like the old code wrote pass the check on a new link too."""
        guests = [self._partner(name) for name in ('Gina', 'Hank', 'Ivan')]
        order = self._order_of(guests[-1])
        for index, guest in enumerate(guests):
            booking = self._booking(self.appointment_type, self._wall(3 + index, 10),
                                    state='pending_payment', partner_id=guest.id,
                                    sale_order_id=order.id)
            self.assertEqual(booking.sale_order_id, order)


# ---------------------------------------------------------------------------
# The shared guest cart at runtime
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestLegacyGuestCart(LegacyCartTools, OrderPaymentCommon, TransactionCase):
    """Three anonymous bookings, three guest contacts, one cart whose contact
    is the third guest."""

    def _setup_cart(self, auto_confirm):
        self.appointment_type = self._paid_type(auto_confirm=auto_confirm)
        guests = [self._guest(name) for name in ('Gina Guest', 'Hank Guest', 'Ivan Guest')]
        self.order, self.bookings = self._legacy_cart(self.appointment_type, guests)
        self.first, self.second, self.third = self.bookings

    def test_every_guest_booking_is_the_carts_own(self):
        self._setup_cart(auto_confirm=True)
        for booking in self.bookings:
            self.assertTrue(booking._is_own_sale_order(self.order), booking.name)
            self.assertEqual(booking._get_own_sale_order(), self.order, booking.name)
        self.assertEqual(self.order._get_own_bookings(), self.bookings)

    def test_every_guest_gets_the_carts_link_and_amount(self):
        self._setup_cart(auto_confirm=True)
        link = self._own_link(self.order)
        for booking in self.bookings:
            self.assertEqual(booking._get_payment_url(), link, booking.name)
            self.assertEqual(booking._get_payment_amount(), self.order.amount_total, booking.name)
        for xmlid in self.TEMPLATES:
            self.assertIn(link, self._render(xmlid, self.first), xmlid)

    def test_the_cart_payment_confirms_every_guest_booking(self):
        self._setup_cart(auto_confirm=True)
        tx = self._pay_cart(self.order, 'LEGACY-CART-CONFIRM')
        for booking in self.bookings:
            self.assertEqual(booking.state, 'confirmed', booking.name)
            self.assertEqual(booking.payment_transaction_id, tx, booking.name)
            self.assertEqual(booking.payment_status, 'paid', booking.name)

    def test_the_cart_payment_holds_the_manual_confirmation_bookings(self):
        self._setup_cart(auto_confirm=False)
        tx = self._pay_cart(self.order, 'LEGACY-CART-HOLD')
        for booking in self.bookings:
            self.assertEqual(booking.state, 'pending_payment', booking.name)
            self.assertEqual(booking.payment_transaction_id, tx, booking.name)
            self.assertEqual(booking.payment_hold_until, booking.end_datetime, booking.name)
            self.assertFalse(booking.payment_confirm_failed)

    def test_a_failed_cart_payment_is_reported_to_one_guest_only(self):
        self._setup_cart(auto_confirm=True)
        tx = self._order_tx('LEGACY-CART-FAIL', self.order)
        tx._set_error('declined')
        self._post_process(tx)
        self.assertTrue(tx.appointment_failure_notified)
        self.assertEqual(sum(self.bookings.mapped('payment_failure_count')), 1)

    def test_cancelling_guests_keeps_the_cart_until_the_last_one(self):
        self._setup_cart(auto_confirm=True)
        self.third.action_cancel()  # the cart's own contact
        self.assertNotEqual(self.order.state, 'cancel', 'the others still wait for their payment')
        self.first.action_cancel()
        self.assertNotEqual(self.order.state, 'cancel')
        self.second.action_cancel()
        self.assertEqual(self.order.state, 'cancel', 'nobody is left in the cart')
        self.assertEqual(set(self.bookings.mapped('state')), {'cancelled'})

    def test_a_cart_that_moved_to_the_visitors_account_is_still_the_guests(self):
        """The visitor logged in before paying: the website moved the cart to
        the account's contact, which is no guest. The cart still holds the
        section it made for each of the guest bookings."""
        self._setup_cart(auto_confirm=True)
        self.order.partner_id = self._portal_partner('Visitor Account')
        for booking in self.bookings:
            self.assertTrue(booking._is_own_sale_order(self.order), booking.name)
            self.assertEqual(booking._get_payment_url(), self._own_link(self.order), booking.name)
        self.assertEqual(self.order._get_own_bookings(), self.bookings)
        other = self._new_booking(self.appointment_type, days=9, partner=self._guest('Mia Guest'))
        self._plant_order(other, self.order)
        self.assertFalse(other._is_own_sale_order(self.order), 'no section was made for this booking')
        self._pay_cart(self.order, 'LEGACY-CART-ACCOUNT')
        self.assertEqual(set(self.bookings.mapped('state')), {'confirmed'})
        self.assertEqual(other.state, 'draft')

    def test_a_portal_row_named_like_a_cart_booking_is_still_foreign(self):
        """The section only counts for a guest's booking: the portal user of
        the RPC hole could choose the booking reference, not their contact."""
        self._setup_cart(auto_confirm=True)
        row = self._new_booking(self.appointment_type, days=9, partner=self._portal_partner('Eve'))
        row.name = self.first.name
        self._plant_order(row, self.order)
        self.assertTrue(row._has_cart_section(self.order))
        self.assertFalse(row._is_own_sale_order(self.order))
        self.assertFalse(row._get_payment_url())

    def test_a_registered_customers_row_is_not_part_of_the_cart(self):
        self._setup_cart(auto_confirm=True)
        row = self._new_booking(self.appointment_type, days=9, partner=self._portal_partner('Eve'))
        self._plant_order(row, self.order)
        self.assertFalse(row._is_own_sale_order(self.order))
        self.assertEqual(self.order._get_own_bookings(), self.bookings)
        self.assertFalse(row._get_payment_url())
        tx = self._pay_cart(self.order, 'LEGACY-CART-EVE')
        self.assertEqual(row.state, 'draft')
        self.assertNotEqual(row.payment_transaction_id, tx)
        self.assertEqual(set(self.bookings.mapped('state')), {'confirmed'})


# ---------------------------------------------------------------------------
# The upgrade on legitimate legacy data
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestLegacyCartUpgrade(LegacyCartTools, OrderPaymentCommon, TransactionCase):
    """The critic's data: a cart with a confirmed and paid booking, a booking
    still to pay and the cart's own contact, and a fully paid cart."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type(auto_confirm=True)
        guests = [self._guest(name) for name in ('Gina Guest', 'Hank Guest', 'Ivan Guest')]
        self.order, self.bookings = self._legacy_cart(self.appointment_type, guests)
        self.paid_one, self.waiting, self.owner = self.bookings
        self.own_tx = self._paid_by_own_page(self.paid_one, self.order)
        paid_guests = [self._guest(name) for name in ('Kay Guest', 'Lee Guest')]
        self.paid_order, self.paid_bookings, self.paid_tx = self._paid_cart(
            self.appointment_type, paid_guests, first_day=8)
        self.everyone = self.bookings | self.paid_bookings

    def test_precondition_the_data_is_what_the_old_code_left(self):
        self.assertEqual(self.paid_one.state, 'confirmed')
        self.assertEqual(self.paid_one.payment_status, 'paid')
        self.assertEqual(self.paid_one.payment_transaction_id, self.own_tx)
        self.assertEqual(self.own_tx.state, 'done')
        self.assertEqual(self.waiting.state, 'pending_payment')
        self.assertEqual(self.waiting.payment_status, 'pending')
        self.assertEqual(self.paid_order.state, 'sale')
        self.assertTrue(self.paid_order.invoice_ids.filtered(
            lambda invoice: invoice.payment_state in ('paid', 'in_payment')))
        for booking in self.everyone:
            self.assertEqual(booking.payment_line_count, 0, 'lines were not bound yet')
            self.assertFalse(booking.payment_line_ids)

    def test_upgrade_keeps_every_link_transaction_state_and_status(self):
        before = self._snapshot(self.everyone)
        self._upgrade()
        self.assertEqual(self._snapshot(self.everyone), before)
        for booking in self.bookings:
            self.assertEqual(booking.sale_order_id, self.order)
        self.assertEqual(self.paid_one.payment_transaction_id, self.own_tx)
        self.assertEqual(self.paid_one.payment_status, 'paid')
        self.assertEqual(self.paid_one.state, 'confirmed')
        for booking in self.paid_bookings:
            self.assertEqual(booking.sale_order_id, self.paid_order)
            self.assertEqual(booking.payment_transaction_id, self.paid_tx)

    def test_upgrade_does_not_report_a_legitimate_cart(self):
        self._upgrade()
        for booking in self.everyone:
            self.assertFalse(self._notes(booking), booking.name)
            self.assertFalse(self._todos(booking), booking.name)

    def test_paid_bookings_stay_paid_when_their_status_is_recomputed_later(self):
        self._upgrade()
        self.env.add_to_compute(self.everyone._fields['payment_status'], self.everyone)
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(self.paid_one.payment_status, 'paid')
        for booking in self.paid_bookings:
            self.assertEqual(booking.payment_status, 'paid', booking.name)
        self.assertEqual(self.waiting.payment_status, 'pending')

    def test_a_paid_booking_waiting_for_staff_stays_paid_and_can_be_confirmed(self):
        """Open and paid: the cart was paid, a manual-confirmation booking
        waits for staff. The recompute of open bookings keeps it paid."""
        guests = [self._guest('Ola Guest'), self._guest('Pat Guest')]
        order, bookings, tx = self._paid_cart(
            self.appointment_type, guests, first_day=16, state='pending_payment')
        before = self._snapshot(bookings)
        self.assertEqual({v[2:] for v in before.values()}, {('pending_payment', 'paid')})
        self._upgrade()
        self.assertEqual(self._snapshot(bookings), before)
        for booking in bookings:
            self.assertFalse(self._notes(booking), booking.name)
            self.assertFalse(booking.message_ids.filtered(
                lambda m: 'payment status check' in (m.body or '')), booking.name)
        bookings[0].action_confirm()
        self.assertEqual(bookings[0].state, 'confirmed')
        self.assertEqual(bookings[0].payment_status, 'paid')

    def test_a_cart_that_moved_to_the_visitors_account_is_not_reported(self):
        guests = [self._guest('Mia Guest'), self._guest('Ned Guest')]
        order, bookings = self._legacy_cart(self.appointment_type, guests, first_day=14)
        order.partner_id = self._portal_partner('Visitor Account')
        before = self._snapshot(bookings)
        self._upgrade()
        self.assertEqual(self._snapshot(bookings), before)
        for booking in bookings:
            self.assertEqual(booking.sale_order_id, order)
            self.assertFalse(self._notes(booking), booking.name)
            self.assertFalse(self._todos(booking), booking.name)

    def test_upgrade_is_safe_to_run_twice(self):
        self._upgrade()
        once = self._snapshot(self.everyone)
        self._upgrade()
        self.assertEqual(self._snapshot(self.everyone), once)
        for booking in self.everyone:
            self.assertFalse(self._notes(booking))

    def test_the_booking_still_to_pay_is_confirmed_when_the_cart_is_paid(self):
        self._upgrade()
        tx = self._pay_cart(self.order, 'LEGACY-UPGRADED-PAID')
        self.assertEqual(self.waiting.state, 'confirmed')
        self.assertEqual(self.waiting.payment_transaction_id, tx)
        self.assertEqual(self.owner.state, 'confirmed')
        self.assertEqual(self.owner.payment_transaction_id, tx)
        self.assertEqual(self.paid_one.payment_transaction_id, self.own_tx, 'the page payment is kept')
        self.assertEqual(self.paid_one.payment_status, 'paid')

    def test_the_booking_still_to_pay_is_held_when_the_cart_is_paid(self):
        self.appointment_type.auto_confirm = False
        self._upgrade()
        tx = self._pay_cart(self.order, 'LEGACY-UPGRADED-HOLD')
        self.assertEqual(self.waiting.state, 'pending_payment')
        self.assertEqual(self.waiting.payment_transaction_id, tx)
        self.assertEqual(self.waiting.payment_hold_until, self.waiting.end_datetime)

    def test_every_guest_still_gets_the_link_of_its_own_cart_only(self):
        self._upgrade()
        for booking in self.bookings:
            self.assertEqual(booking._get_payment_url(), self._own_link(self.order), booking.name)
        for booking in self.paid_bookings:
            self.assertEqual(booking._get_payment_url(), self._own_link(self.paid_order), booking.name)


# ---------------------------------------------------------------------------
# The upgrade on rows that are not the booking's order
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestForeignRowsUpgrade(LegacyCartTools, LegacyLinkCommon, TransactionCase):
    """e10ecad8918d: the portal user's booking on another customer's order
    (Bob, a registered customer) and the links staff made by hand are kept,
    reported once and closed at runtime. self.legacy is Mallory's pending
    booking on Bob's order."""

    def setUp(self):
        super().setUp()
        # Bob paid; the old code marked a second row of Mallory's paid by it.
        self._invoice_and_pay(self.victim_order)
        self.victim_tx = self._order_tx('FOREIGN-DONE')
        self.victim_tx._set_done()
        self.paid_row = self._new_booking(self.appointment_type, days=4, partner=self.legacy.partner_id)
        self._plant_order(self.paid_row, self.victim_order)
        self._stamp(self.paid_row, 'pending_payment', 'paid', self.victim_tx)
        self.rows = self.legacy | self.paid_row
        self.token = self.victim_order.access_token

    def _staff_rows(self):
        carol = self._new_booking(self.appointment_type, days=8, partner=self._partner('Carol'))
        dave = self._new_booking(self.appointment_type, days=9, partner=self._portal_partner('Dave'))
        erin = self._new_booking(self.appointment_type, days=10, partner=self._portal_partner('Erin'))
        for row in carol | dave | erin:
            self._plant_order(row, self.victim_order)
        self._stamp(erin, 'confirmed', 'paid', self.victim_tx)
        return carol, dave, erin

    def test_the_attack_rows_are_kept_and_nothing_about_them_changes(self):
        before = self._snapshot(self.rows)
        self._upgrade()
        self.assertEqual(self._snapshot(self.rows), before)
        for row in self.rows:
            self.assertEqual(row.sale_order_id, self.victim_order, row.name)
        self.assertEqual(self.paid_row.payment_transaction_id, self.victim_tx)
        self.assertEqual(self.paid_row.payment_status, 'paid', 'a status is never changed by the upgrade')
        self.assertEqual(self.victim_order.state, 'sale')

    def test_an_attack_row_is_noted_once_and_a_manager_gets_a_todo(self):
        self._upgrade()
        notes = self._notes(self.legacy)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes.subtype_id, self.env.ref('mail.mt_note'), 'internal note')
        self.assertIn(self.victim_order.name, notes.body)
        self.assertNotIn(self.token, notes.body)
        todos = self._todos(self.legacy)
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos.activity_type_id, self.env.ref('mail.mail_activity_data_todo'))
        managers = self.env.ref('reservation_module.group_appointment_manager')
        self.assertIn(todos.user_id, managers.users)
        self.assertFalse(todos.user_id._is_superuser(), 'not OdooBot')
        self.assertIn(self.legacy.name, todos.summary)
        self.assertNotIn('old rule', notes.body)
        paid_note = self._notes(self.paid_row)
        self.assertIn('Paid status comes from the old rule', paid_note.body, 'a kept Paid is warned about')
        # Reported once.
        self._upgrade()
        self.assertEqual(len(self._notes(self.legacy)), 1)
        self.assertEqual(len(self._todos(self.legacy)), 1)
        self.assertFalse(_load_migration_3_2_2()._flag_foreign_sale_orders(self.env))

    def test_a_to_do_that_cannot_be_scheduled_does_not_stop_the_upgrade(self):
        Booking = type(self.env['appointment.booking'])
        with patch.object(Booking, 'activity_schedule', side_effect=RuntimeError('no activity type')):
            self._upgrade()
        for row in self.rows:
            self.assertEqual(len(self._notes(row)), 1, row.name)
            self.assertFalse(self._todos(row), row.name)
            self.assertEqual(row.sale_order_id, self.victim_order)

    def test_a_finished_or_cancelled_row_is_noted_without_a_todo(self):
        past = self._booking(self.appointment_type, self._wall(-6, 10), state='done',
                             partner_id=self._portal_partner('Frank').id)
        cancelled = self._new_booking(self.appointment_type, days=7,
                                      partner=self._portal_partner('Gail'))
        cancelled.state = 'cancelled'
        for row in (past, cancelled):
            self._plant_order(row, self.victim_order)
        self._upgrade()
        for row in (past, cancelled):
            self.assertEqual(len(self._notes(row)), 1, row.name)
            self.assertFalse(self._todos(row), row.name)
            self.assertEqual(row.sale_order_id, self.victim_order)

    def test_the_attack_rows_stay_closed_at_runtime(self):
        self._upgrade()
        for row in self.rows:
            self.assertFalse(row._is_own_sale_order(self.victim_order), row.name)
            self.assertFalse(row._get_payment_url(), row.name)
            self.assertEqual(row._get_payment_amount(), 0.0, row.name)
        for xmlid in self.TEMPLATES:
            body = self._render(xmlid, self.legacy)
            self.assertNotIn(self.token, body, xmlid)
            self.assertNotIn('/my/orders/%d' % self.victim_order.id, body, xmlid)
        self.assertFalse(self.victim_order._get_own_bookings())
        # Bob's later payment problem does not reach Mallory.
        tx = self._order_tx('FOREIGN-LATE-FAIL')
        tx._set_error('declined')
        self._post_process(tx)
        self.assertFalse(tx.appointment_failure_notified)
        self.assertFalse(self.env['mail.mail'].sudo().search([('email_to', 'ilike', 'mallory.inbox')]))
        self.assertFalse(self.env['mail.mail'].sudo().search([('body_html', 'ilike', self.token)]))

    def test_cancelling_an_attack_row_leaves_the_order_alone(self):
        self._upgrade()
        state = self.victim_order.state
        invoices = self.victim_order.invoice_ids
        self.legacy.action_cancel()
        self.assertEqual(self.legacy.state, 'cancelled')
        self.assertEqual(self.victim_order.state, state)
        self.assertEqual(self.victim_order.invoice_ids, invoices)
        self.assertEqual(self.legacy.sale_order_id, self.victim_order)

    def test_such_a_link_still_cannot_be_created(self):
        self._upgrade()
        for partner in (self.legacy.partner_id, self._partner('Carol')):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self._booking(self.appointment_type, self._wall(11, 10), state='draft',
                              partner_id=partner.id, sale_order_id=self.victim_order.id)

    def test_the_recompute_leaves_a_row_that_is_not_the_orders_alone(self):
        mig = _load_migration_3_2_2()
        self.assertEqual(mig._recompute_open_payment_status(self.env), [])
        self.env.invalidate_all()
        self.assertEqual(self.paid_row.payment_status, 'paid')

    def test_staff_links_to_another_customers_order_are_kept_and_noted(self):
        carol, dave, erin = self._staff_rows()
        rows = carol | dave | erin
        before = self._snapshot(rows)
        self._upgrade()
        self.assertEqual(self._snapshot(rows), before)
        for row in rows:
            self.assertEqual(row.sale_order_id, self.victim_order, row.name)
            self.assertEqual(len(self._notes(row)), 1, row.name)
            self.assertFalse(row._get_payment_url(), row.name)
        self.assertEqual(erin.state, 'confirmed')
        self.assertEqual(erin.payment_status, 'paid')
        self.assertEqual(erin.payment_transaction_id, self.victim_tx)

    def test_a_portal_row_on_a_guests_cart_is_reported_and_the_guests_are_not(self):
        self.appointment_type.auto_confirm = True
        guests = [self._guest('Gina Guest'), self._guest('Hank Guest')]
        cart, bookings = self._legacy_cart(self.appointment_type, guests, first_day=12)
        eve = self._new_booking(self.appointment_type, days=15, partner=self._portal_partner('Eve'))
        self._plant_order(eve, cart)
        self._upgrade()
        self.assertEqual(eve.sale_order_id, cart)
        self.assertEqual(len(self._notes(eve)), 1)
        for booking in bookings:
            self.assertFalse(self._notes(booking), booking.name)
        self.assertFalse(eve._is_own_sale_order(cart))
        tx = self._pay_cart(cart, 'FOREIGN-GUEST-CART')
        self.assertEqual(eve.state, 'draft')
        self.assertNotEqual(eve.payment_transaction_id, tx)
        self.assertEqual(set(bookings.mapped('state')), {'confirmed'})

    def test_the_pre_upgrade_query_lists_what_the_upgrade_reports(self):
        """The read-only query to run before upgrading names the bookings the
        upgrade then reports, and none of the legitimate carts' bookings."""
        mig = _load_migration_3_2_2()
        carol, dave, erin = self._staff_rows()
        self.appointment_type.auto_confirm = True
        cart, cart_bookings = self._legacy_cart(
            self.appointment_type, [self._guest('Gina Guest'), self._guest('Hank Guest')], first_day=12)
        moved, moved_bookings = self._legacy_cart(
            self.appointment_type, [self._guest('Mia Guest'), self._guest('Ned Guest')], first_day=15)
        moved.partner_id = self._portal_partner('Visitor Account')
        eve = self._new_booking(self.appointment_type, days=19, partner=self._portal_partner('Eve'))
        self._plant_order(eve, cart)
        self.env.flush_all()
        self.env.cr.execute(mig.PRE_UPGRADE_CHECK_SQL)
        listed = {row[0] for row in self.env.cr.fetchall()}
        self.assertEqual(listed, set((self.rows | carol | dave | erin | eve).ids))
        self.assertFalse(listed & set((cart_bookings | moved_bookings).ids))
        self.assertEqual(set(mig._flag_foreign_sale_orders(self.env)), listed)

    def test_a_closed_account_does_not_reopen_the_row_on_a_guests_cart(self):
        cart, bookings = self._legacy_cart(self.appointment_type, [self._guest('Gina Guest')],
                                           first_day=12)
        eve_partner = self._portal_partner('Eve')
        eve = self._new_booking(self.appointment_type, days=15, partner=eve_partner)
        self._plant_order(eve, cart)
        user = eve_partner.user_ids
        self._upgrade()
        self.assertFalse(eve._is_own_sale_order(cart))
        user.action_archive()  # the login is archived
        self.assertFalse(eve._is_own_sale_order(cart))
        eve_partner.action_archive()  # what the portal "delete my account" flow does
        user.unlink()
        self.assertFalse(eve._is_own_sale_order(cart))
        self.assertFalse(eve._get_payment_url())


@tagged('post_install', '-at_install')
class TestLegacyCartRoutes(LegacyCartTools, LegacyLinkCommon, RulesHttpCommon, HttpCase):
    """The pages of the token links, for the shared guest cart and for a row
    that is not the order's."""

    def test_a_guest_of_the_cart_is_sent_to_the_cart(self):
        guests = [self._guest('Gina Guest'), self._guest('Hank Guest')]
        order, bookings = self._legacy_cart(self.appointment_type, guests, first_day=12)
        self._upgrade()
        self.env.flush_all()
        for booking in bookings:
            response = self.url_open(
                '/appointment/booking/%d/pay?token=%s' % (booking.id, booking.access_token))
            self.assertEqual(response.status_code, 200)
            self.assertIn('/my/orders/%d' % order.id, response.url, booking.name)
            self.assertIn(order.access_token, response.url, booking.name)

    def test_the_pages_of_a_row_that_is_not_the_orders_reveal_nothing(self):
        self._upgrade()
        self.env.flush_all()
        for path in ('/appointment/booking/%d/pay', '/appointment/booking/%d/confirm',
                     '/appointment/booking/%d'):
            response = self.url_open((path % self.legacy.id) + '?token=%s' % self.legacy.access_token)
            self.assertNotIn(self.victim_order.access_token, response.url, path)
            self.assertNotIn(self.victim_order.access_token, response.text, path)
        self.env.invalidate_all()
        self.assertEqual(self.legacy.sale_order_id, self.victim_order)
        self.assertNotEqual(self.victim_order.state, 'cancel')
