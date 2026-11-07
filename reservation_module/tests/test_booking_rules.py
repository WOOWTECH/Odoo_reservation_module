# -*- coding: utf-8 -*-
"""Booking rules the public routes must enforce server-side (sweep 2026-11-07).

  * capacity: requested party + occupied seats <= capacity on every path
    (form limit, auto-assigned location); capacity 0 counts as 1
  * event mode: one booking = one whole availability window
  * staff/location-specific availability rows apply at booking time
  * roster ids on /slots and /schedule must belong to the type
  * archived / unpublished types are not schedulable or bookable
  * rate limits not keyed only on what the visitor types; per-inbox mail cap
  * payment-required bookings hold their slot during the payment window;
    a failed confirmation after payment is flagged, not swallowed
  * one booking sends the "payment failed" mail once per failed transaction,
    at most once a day and a few times in total
"""

import re
from datetime import datetime, timedelta
from unittest.mock import patch

import psycopg2

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .test_security_acl import _load_migration_3_2_2
from .test_timezone import TAIPEI, TimezoneCommon


def _keep_queued_mails(case):
    """Calendar mails are sent at once (and auto-deleted) in a testing thread:
    keep them queued so the test can count them."""
    patcher = patch.object(type(case.env['mail.mail']), 'send_after_commit', lambda self: None)
    patcher.start()
    case.addCleanup(patcher.stop)


class RulesCommon(TimezoneCommon):

    def _wall(self, days, hour, minute=0):
        """UTC value of Taipei wall time ``hour:minute`` in ``days`` days."""
        day = datetime.now(TAIPEI).date() + timedelta(days=days)
        return self._taipei_wall_to_utc(datetime(day.year, day.month, day.day) + timedelta(hours=hour, minutes=minute))

    @staticmethod
    def _fmt(value):
        return value.strftime('%Y-%m-%d %H:%M:%S')

    def _user(self, name, login):
        return self.env['res.users'].create({'name': name, 'login': login, 'email': '%s@example.com' % login})

    def _room(self, name, capacity):
        return self.env['resource.resource'].create({
            'name': name, 'resource_type': 'material', 'capacity': capacity})

    def _booking(self, appointment_type, start, hours=1, state='confirmed', **extra):
        vals = {
            'appointment_type_id': appointment_type.id,
            'guest_name': 'Existing Guest',
            'guest_email': 'existing@example.com',
            'start_datetime': start,
            'end_datetime': start + timedelta(hours=hours),
            'state': state,
        }
        vals.update(extra)
        return self.env['appointment.booking'].sudo().create(vals)

    def _set_windows(self, appointment_type, windows):
        """Replace the type's availability by ``(hour_from, hour_to, extra)`` rows, every day."""
        appointment_type.availability_ids.unlink()
        self.env['appointment.availability'].create([
            dict({'appointment_type_id': appointment_type.id, 'dayofweek': str(day),
                  'hour_from': hour_from, 'hour_to': hour_to}, **extra)
            for day in range(7) for hour_from, hour_to, extra in windows
        ])


class RulesHttpCommon(RulesCommon):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(
            'reservation_module.require_authenticated_booking', 'False')
        self._csrf_token = None

    def _csrf(self):
        if not self._csrf_token:
            page = self.url_open('/web/login')
            match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text) or re.search(
                r'value="([^"]+)"[^>]*name="csrf_token"', page.text)
            self.assertTrue(match, 'csrf token not found')
            self._csrf_token = match.group(1)
        return self._csrf_token

    def _post(self, appointment_type, start, end=None, headers=None, **values):
        data = {
            'csrf_token': self._csrf(),
            'start_datetime': self._fmt(start),
            'guest_name': 'Rule Guest',
            'guest_email': 'rule.guest@example.com',
            'guest_count': '1',
        }
        if end is not None:
            data['end_datetime'] = self._fmt(end)
        data.update({key: str(value) for key, value in values.items() if value is not None})
        return self.url_open('/appointment/%d/book' % appointment_type.id, data=data, headers=headers)

    def _bookings(self, appointment_type, **domain):
        self.env.invalidate_all()
        return self.env['appointment.booking'].sudo().search(
            [('appointment_type_id', '=', appointment_type.id)]
            + [(key, '=', value) for key, value in domain.items()])

    def _slots(self, appointment_type, day, **params):
        payload = {'date': day.strftime('%Y-%m-%d')}
        payload.update(params)
        return self.make_jsonrpc_request('/appointment/%d/slots' % appointment_type.id, payload)


# ---------------------------------------------------------------------------
# 1a3da47bd48b capacity
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestCapacityRules(RulesCommon, TransactionCase):

    def setUp(self):
        super().setUp()
        self.small = self._room('Small Room', 3)
        self.large = self._room('Large Room', 5)
        self.appointment_type = self._setup_appointment_type(
            assign_location=True, auto_confirm=False,
            resource_ids=[(6, 0, [self.small.id, self.large.id])])
        self.start = self._wall(3, 10)

    def test_auto_assign_location_needs_room_for_whole_party(self):
        # small: 2 of 3 seats taken in the slot; large has more bookings this
        # month, so the "fewest bookings" balancing alone would pick small.
        self._booking(self.appointment_type, self.start, resource_id=self.small.id, guest_count=2)
        for hour in (14, 15):
            self._booking(self.appointment_type, self._wall(3, hour), resource_id=self.large.id)
        group = self._booking(self.appointment_type, self.start, state='draft', guest_count=2)
        self.assertEqual(group._auto_assign_location(), self.large)
        self.assertEqual(group.resource_id, self.large)

    def test_auto_assign_location_returns_empty_when_no_room(self):
        self._booking(self.appointment_type, self.start, resource_id=self.small.id, guest_count=3)
        self._booking(self.appointment_type, self.start, resource_id=self.large.id, guest_count=4)
        group = self._booking(self.appointment_type, self.start, state='draft', guest_count=2)
        self.assertFalse(group._auto_assign_location())
        self.assertFalse(group.resource_id)

    def test_capacity_zero_counts_as_one(self):
        self.small.capacity = 0
        self.assertEqual(self.small._get_booking_capacity(), 1)
        conflict = self.env['appointment.booking']._check_booking_capacity(
            self.start, self.start + timedelta(hours=1), resource_id=self.small.id, guest_count=2)
        self.assertTrue(conflict['resource_full'])
        conflict = self.env['appointment.booking']._check_booking_capacity(
            self.start, self.start + timedelta(hours=1), resource_id=self.small.id, guest_count=1)
        self.assertFalse(conflict['resource_full'])


@tagged('post_install', '-at_install')
class TestCapacityRoutes(RulesHttpCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.room_a = self._room('Room A', 1)
        self.room_b = self._room('Room B', 1)
        self.appointment_type = self._setup_appointment_type(
            assign_location=True, allow_customer_choose_location=True,
            resource_ids=[(6, 0, [self.room_a.id, self.room_b.id])])
        self.start = self._wall(3, 10)

    def test_form_limit_uses_capacity_one_for_zero(self):
        self.room_a.capacity = 0
        response = self._post(self.appointment_type, self.start, resource_id=self.room_a.id, guest_count=2)
        self.assertIn('Maximum 1 guests allowed', response.text)
        self.assertFalse(self._bookings(self.appointment_type))

    def test_no_unassigned_booking_when_every_location_is_full(self):
        self._booking(self.appointment_type, self.start, resource_id=self.room_a.id)
        self._booking(self.appointment_type, self.start, resource_id=self.room_b.id)
        response = self._post(self.appointment_type, self.start, guest_email='late@example.com')
        self.assertIn('No location has room', response.text)
        self.assertFalse(self._bookings(self.appointment_type, guest_email='late@example.com'))
        self.assertFalse(self.env['res.partner'].sudo().search([('email', '=', 'late@example.com')]))

    def test_auto_assigned_location_when_one_is_free(self):
        self._booking(self.appointment_type, self.start, resource_id=self.room_a.id)
        self._post(self.appointment_type, self.start, guest_email='ok@example.com')
        booking = self._bookings(self.appointment_type, guest_email='ok@example.com')
        self.assertEqual(booking.resource_id, self.room_b)
        self.assertEqual(booking.state, 'confirmed')


# ---------------------------------------------------------------------------
# 5d593007668b event windows
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestEventWindowBinding(RulesHttpCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.staff = self._user('Event Host', 'event_host_rules')
        self.appointment_type = self._setup_appointment_type(
            is_scheduled=False, assign_staff=True, staff_user_ids=[(6, 0, self.staff.ids)])
        self._set_windows(self.appointment_type, [(10.0, 12.0, {}), (20.0, 24.0, {})])
        self.morning = self._wall(3, 10)
        self.evening = self._wall(3, 20)
        self.midnight = self._wall(4, 0)

    def test_sub_interval_of_window_is_refused(self):
        response = self._post(self.appointment_type, self.morning, self.morning + timedelta(minutes=1))
        self.assertIn('outside available hours', response.text)
        self.assertFalse(self._bookings(self.appointment_type))

    def test_end_far_past_a_24h_window_is_refused(self):
        response = self._post(self.appointment_type, self.evening, self.evening + timedelta(days=30))
        self.assertIn('outside available hours', response.text)
        self.assertFalse(self._bookings(self.appointment_type))

    def test_window_ending_at_midnight_is_booked(self):
        self._post(self.appointment_type, self.evening, self.midnight)
        booking = self._bookings(self.appointment_type)
        self.assertEqual(len(booking), 1)
        self.assertEqual(booking.end_datetime, self.midnight)
        self.assertEqual(booking.state, 'confirmed')

    def test_missing_end_takes_the_window_end(self):
        self._post(self.appointment_type, self.morning)
        booking = self._bookings(self.appointment_type)
        self.assertEqual(booking.end_datetime, self.morning + timedelta(hours=2))

    def test_slots_and_form_agree(self):
        day = datetime.now(TAIPEI).date() + timedelta(days=3)
        slots = self._slots(self.appointment_type, day)['slots']
        self.assertIn((self._fmt(self.evening), self._fmt(self.midnight)),
                      [(slot['start'], slot['end']) for slot in slots])

    def test_form_with_forged_end_goes_back_to_schedule(self):
        response = self.url_open('/appointment/%d/book?start_datetime=%s&end_datetime=%s' % (
            self.appointment_type.id, self._fmt(self.morning).replace(' ', '%20'),
            self._fmt(self.morning + timedelta(days=9)).replace(' ', '%20')))
        self.assertIn('/schedule', response.url)


# ---------------------------------------------------------------------------
# 494a49d74072 staff / location specific availability
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestMemberAvailability(RulesHttpCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.alpha = self._user('Alpha Morning', 'alpha_morning_rules')
        self.beta = self._user('Beta Afternoon', 'beta_afternoon_rules')
        self.appointment_type = self._setup_appointment_type(
            assign_staff=True, allow_customer_choose_staff=True,
            staff_user_ids=[(6, 0, [self.alpha.id, self.beta.id])])
        self._set_windows(self.appointment_type, [
            (8.0, 12.0, {'user_id': self.alpha.id}),
            (13.0, 17.0, {'user_id': self.beta.id}),
        ])
        self.afternoon = self._wall(3, 14)

    def test_staff_outside_own_window_is_refused(self):
        response = self._post(self.appointment_type, self.afternoon, staff_id=self.alpha.id)
        self.assertIn('outside available hours', response.text)
        self.assertFalse(self._bookings(self.appointment_type))

    def test_staff_inside_own_window_is_booked(self):
        self._post(self.appointment_type, self.afternoon, staff_id=self.beta.id)
        self.assertEqual(self._bookings(self.appointment_type).staff_user_id, self.beta)

    def test_auto_assign_picks_the_scheduled_member(self):
        self._post(self.appointment_type, self.afternoon)
        booking = self._bookings(self.appointment_type)
        self.assertEqual(len(booking), 1)
        self.assertEqual(booking.staff_user_id, self.beta)

    def test_no_booking_when_the_scheduled_member_is_busy(self):
        self._booking(self.appointment_type, self.afternoon, staff_user_id=self.beta.id)
        response = self._post(self.appointment_type, self.afternoon, guest_email='late@example.com')
        self.assertIn('No staff member is available', response.text)
        self.assertFalse(self._bookings(self.appointment_type, guest_email='late@example.com'))


# ---------------------------------------------------------------------------
# f822d4609029 roster ids, e418705181c8 active / published
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestPublicRouteBinding(RulesHttpCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.roster_staff = self._user('Roster Staff', 'roster_staff_rules')
        self.outsider = self._user('Outside Staff', 'outside_staff_rules')
        self.outside_room = self._room('Outside Room', 2)
        self.appointment_type = self._setup_appointment_type(
            assign_staff=True, allow_customer_choose_staff=True,
            staff_user_ids=[(6, 0, [self.roster_staff.id])])
        other_type = self._setup_appointment_type(
            name='Other Type', assign_staff=True, assign_location=True,
            staff_user_ids=[(6, 0, [self.outsider.id])],
            resource_ids=[(6, 0, [self.outside_room.id])])
        # The outsider is busy at 10:00 in another type; the slot list of this
        # type must not reveal that.
        self.busy = self._wall(3, 10)
        self._booking(other_type, self.busy, staff_user_id=self.outsider.id,
                      resource_id=self.outside_room.id, guest_count=2)
        self.day = datetime.now(TAIPEI).date() + timedelta(days=3)

    def test_slots_refuse_outside_staff_like_unknown_id(self):
        outsider = self._slots(self.appointment_type, self.day, staff_id=self.outsider.id)
        unknown = self._slots(self.appointment_type, self.day, staff_id=987654321)
        self.assertNotIn('slots', outsider)
        self.assertEqual(outsider, unknown)

    def test_slots_refuse_outside_resource(self):
        outsider = self._slots(self.appointment_type, self.day, resource_id=self.outside_room.id)
        unknown = self._slots(self.appointment_type, self.day, resource_id=987654321)
        self.assertNotIn('slots', outsider)
        self.assertEqual(outsider, unknown)

    def test_slots_for_roster_staff_still_work(self):
        slots = self._slots(self.appointment_type, self.day, staff_id=self.roster_staff.id)['slots']
        self.assertIn(self._fmt(self.busy), [slot['start'] for slot in slots])

    def test_schedule_does_not_preselect_outsider(self):
        page = self.url_open('/appointment/%d/schedule?staff_id=%d&resource_id=%d' % (
            self.appointment_type.id, self.outsider.id, self.outside_room.id))
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('data-staff-id="%d"' % self.outsider.id, page.text)
        self.assertNotIn('data-resource-id="%d"' % self.outside_room.id, page.text)

    def test_archived_type_is_not_bookable(self):
        start = self._wall(3, 11)
        self._csrf()
        self.appointment_type.active = False
        self.assertTrue(self.appointment_type.is_published)
        page = self.url_open('/appointment/%d/book?start_datetime=%s' % (
            self.appointment_type.id, self._fmt(start).replace(' ', '%20')))
        self.assertNotIn('/book', page.url)
        self._post(self.appointment_type, start)
        self.assertFalse(self.env['appointment.booking'].sudo().with_context(active_test=False).search(
            [('appointment_type_id', '=', self.appointment_type.id)]))
        for url in ('/appointment/%d', '/appointment/%d/schedule'):
            self.assertNotIn('/%d' % self.appointment_type.id,
                             self.url_open(url % self.appointment_type.id).url)

    def test_unpublished_or_archived_type_has_no_slots_or_dates(self):
        for vals in ({'is_published': False}, {'is_published': True, 'active': False}):
            self.appointment_type.write(vals)
            self.assertNotIn('slots', self._slots(self.appointment_type, self.day))
            dates = self.make_jsonrpc_request(
                '/appointment/%d/event_dates' % self.appointment_type.id,
                {'year': self.day.year, 'month': self.day.month})
            self.assertEqual(dates, {'dates': []})

    def test_event_dates_rejects_bad_input(self):
        dates = self.make_jsonrpc_request(
            '/appointment/%d/event_dates' % self.appointment_type.id, {'year': 'x', 'month': 13})
        self.assertEqual(dates, {'dates': []})


# ---------------------------------------------------------------------------
# 94f32de1e119 rate limits / mail relay
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestBookingRateLimits(RulesHttpCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.appointment_type = self._setup_appointment_type()
        self.ICP = self.env['ir.config_parameter'].sudo()

    def _hour(self, index):
        return self._wall(3, 8 + index)

    def test_client_address_limit_ignores_changing_email(self):
        # The test server is reached over loopback, a hop: the client is the
        # address the Cloudflare edge reports (see test_booking_client_key).
        self.ICP.set_param('reservation_module.booking_rate_limit_per_ip', '2')
        for index in range(3):
            response = self._post(self.appointment_type, self._hour(index),
                                  headers={'CF-Connecting-IP': '8.8.4.4'},
                                  guest_email='rotating%d@example.com' % index)
        self.assertIn('Too many booking attempts', response.text)
        self.assertEqual(len(self._bookings(self.appointment_type)), 2)

    def test_plus_and_case_variants_share_the_mailbox_limit(self):
        self.ICP.set_param('reservation_module.booking_rate_limit_per_ip', '0')
        emails = ['victim@example.com', 'Victim@Example.com', 'victim+1@example.com',
                  'victim+2@example.com', 'VICTIM+3@example.com', 'victim+4@example.com']
        for index, email in enumerate(emails):
            response = self._post(self.appointment_type, self._hour(index), guest_email=email)
        self.assertIn('Too many booking attempts', response.text)
        self.assertEqual(len(self._bookings(self.appointment_type)), 5)

    def test_per_type_cap(self):
        self.ICP.set_param('reservation_module.booking_rate_limit_per_ip', '0')
        self.ICP.set_param('reservation_module.booking_rate_limit_per_type', '1')
        self._post(self.appointment_type, self._hour(0), guest_email='first@example.com')
        response = self._post(self.appointment_type, self._hour(1), guest_email='second@example.com')
        self.assertIn('Too many booking attempts', response.text)
        self.assertEqual(len(self._bookings(self.appointment_type)), 1)

    def test_guest_mails_to_one_inbox_are_capped(self):
        self.ICP.set_param('reservation_module.guest_mail_daily_limit', '1')
        for index, email in enumerate(['target@example.com', 'target+x@example.com']):
            self._post(self.appointment_type, self._hour(index), guest_email=email)
        bookings = self._bookings(self.appointment_type)
        self.assertEqual(len(bookings), 2)
        mails = self.env['mail.mail'].sudo().search([
            ('email_to', 'ilike', 'target'), ('model', '=', 'appointment.booking')])
        self.assertEqual(len(mails), 1, 'only the first booking for this inbox may send mail')
        suppressed = bookings.sorted('id')[-1]
        self.assertTrue(any('not sent' in (message.body or '') for message in suppressed.message_ids))

    def _mails_to(self, pattern):
        return self.env['mail.mail'].sudo().search([
            '|', ('email_to', 'ilike', pattern), ('recipient_ids.email', 'ilike', pattern)])

    def test_calendar_invitations_respect_the_mailbox_cap(self):
        # Every mail any model sends to the visitor-typed address counts:
        # core's calendar invitation (.ics) is sent from calendar.event.
        self.ICP.set_param('reservation_module.guest_mail_daily_limit', '1')
        _keep_queued_mails(self)
        emails = ['victim+0@example.org', 'victim+1@example.org', 'victim+2@example.org']
        for index, email in enumerate(emails):
            self._post(self.appointment_type, self._hour(index), guest_email=email)
        bookings = self._bookings(self.appointment_type).sorted('id')
        self.assertEqual(len(bookings), 3)
        self.assertTrue(all(booking.state == 'confirmed' and booking.calendar_event_id
                            for booking in bookings))
        first = bookings[0]
        mails = self._mails_to('victim')
        self.assertTrue(mails.filtered(lambda mail: mail.model == 'calendar.event'),
                        'the first booking still gets its invitation')
        allowed = {('appointment.booking', first.id), ('calendar.event', first.calendar_event_id.id)}
        self.assertEqual({(mail.model, mail.res_id) for mail in mails} - allowed, set(),
                         'bookings past the cap send no mail of any kind to the guest')

    def test_backend_bookings_are_not_mail_capped(self):
        self.ICP.set_param('reservation_module.guest_mail_daily_limit', '1')
        for index in range(2):
            booking = self._booking(self.appointment_type, self._hour(index), state='draft',
                                    guest_email='desk@example.com')
            self.assertTrue(booking._guest_mail_allowed())


@tagged('post_install', '-at_install')
class TestCalendarMailCap(RulesCommon, TransactionCase):
    """The per-inbox cap also holds for core calendar mails sent later."""

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(
            'reservation_module.guest_mail_daily_limit', '1')
        self.appointment_type = self._setup_appointment_type()
        _keep_queued_mails(self)

    def _public_booking(self, hour, email):
        partner = self.env['res.partner'].create({'name': 'Cap Guest', 'email': email})
        booking = self._booking(self.appointment_type, self._wall(3, hour), state='draft',
                                guest_email=email, partner_id=partner.id, client_ip_hash='cap-test')
        booking.action_confirm()
        return booking

    def _event_mails(self, booking):
        return self.env['mail.mail'].sudo().search([
            ('model', '=', 'calendar.event'), ('res_id', '=', booking.calendar_event_id.id)])

    def test_reschedule_mail_follows_the_cap(self):
        allowed = self._public_booking(9, 'cap.victim@example.org')
        capped = self._public_booking(11, 'cap.victim+1@example.org')
        self.assertTrue(self._event_mails(allowed), 'invitation of the first booking')
        self.assertFalse(self._event_mails(capped), 'no invitation past the cap')
        before = len(self._event_mails(allowed))
        for booking in (allowed, capped):
            booking.write({'start_datetime': booking.start_datetime + timedelta(hours=1),
                           'end_datetime': booking.end_datetime + timedelta(hours=1)})
        self.assertGreater(len(self._event_mails(allowed)), before, 'date-change mail is sent')
        self.assertFalse(self._event_mails(capped), 'no date-change mail past the cap')
        capped.calendar_event_id.action_sendmail()
        self.assertFalse(self._event_mails(capped))


# ---------------------------------------------------------------------------
# 83afd6490089 payment hold / confirm failure
# ---------------------------------------------------------------------------

class PaymentHoldCommon(RulesCommon):

    def _paid_type(self, **overrides):
        self.host = self._user('Paid Host', 'paid_host_rules_%s' % self.__class__.__name__.lower())
        product_vals = {'name': 'Session Fee', 'type': 'service', 'list_price': 100.0, 'sale_ok': True}
        if 'is_published' in self.env['product.product']._fields:
            product_vals['is_published'] = True  # website cart only takes published products
        vals = dict(
            require_payment=True, auto_confirm=True, assign_staff=True,
            staff_user_ids=[(6, 0, self.host.ids)],
            payment_product_ids=[(0, 0, product_vals)],
        )
        vals.update(overrides)
        return self._setup_appointment_type(**vals)


@tagged('post_install', '-at_install')
class TestPaymentHoldRoutes(PaymentHoldCommon, RulesHttpCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type()
        self.start = self._wall(3, 10)

    def test_second_visitor_cannot_buy_a_held_slot(self):
        self._post(self.appointment_type, self.start, guest_email='first@example.com')
        first = self._bookings(self.appointment_type, guest_email='first@example.com')
        self.assertEqual(first.state, 'pending_payment')
        self.assertTrue(first.payment_hold_until)
        self.assertGreater(first.payment_hold_until, fields.Datetime.now())

        response = self._post(self.appointment_type, self.start, guest_email='second@example.com')
        self.assertIn('no longer available', response.text)
        self.assertFalse(self._bookings(self.appointment_type, guest_email='second@example.com'))

        day = datetime.now(TAIPEI).date() + timedelta(days=3)
        starts = [slot['start'] for slot in self._slots(self.appointment_type, day)['slots']]
        self.assertNotIn(self._fmt(self.start), starts, 'a held slot is not offered')

    def test_pay_page_reloads_do_not_move_the_deadline(self):
        self._post(self.appointment_type, self.start, guest_email='first@example.com')
        first = self._bookings(self.appointment_type, guest_email='first@example.com')
        now = fields.Datetime.now()
        first.write({'payment_hold_started_at': now - timedelta(minutes=25),
                     'payment_hold_until': now + timedelta(minutes=5)})
        deadline = first.payment_hold_until
        for _index in range(2):
            self.url_open('/appointment/booking/%d/pay?token=%s' % (first.id, first.access_token))
        self.env.invalidate_all()
        self.assertEqual(first.payment_hold_until, deadline)

    def test_expired_hold_releases_the_slot(self):
        self._post(self.appointment_type, self.start, guest_email='first@example.com')
        first = self._bookings(self.appointment_type, guest_email='first@example.com')
        first.payment_hold_until = fields.Datetime.now() - timedelta(minutes=1)
        self._post(self.appointment_type, self.start, guest_email='second@example.com')
        self.assertTrue(self._bookings(self.appointment_type, guest_email='second@example.com'))


@tagged('post_install', '-at_install')
class TestPaymentHoldModel(PaymentHoldCommon, TransactionCase):

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type()
        self.start = self._wall(3, 10)
        self.booking = self._booking(self.appointment_type, self.start, state='draft',
                                     staff_user_id=self.host.id, partner_id=self.env['res.partner'].create(
                                         {'name': 'Payer', 'email': 'payer@example.com'}).id)
        self.order = self.booking._create_sale_order()
        provider = self.env['payment.provider'].create({
            'name': 'Rules Dummy', 'code': 'none', 'state': 'test',
            'payment_method_ids': [(6, 0, self.env.ref('payment.payment_method_unknown').ids)],
        })
        self.tx_vals = {
            'provider_id': provider.id,
            'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
            'amount': self.order.amount_total,
            'currency_id': self.order.currency_id.id,
            'partner_id': self.booking.partner_id.id,
            'sale_order_ids': [(6, 0, self.order.ids)],
        }

    def _tx(self, reference):
        return self.env['payment.transaction'].sudo().create(dict(self.tx_vals, reference=reference))

    def _post_process(self, tx):
        # The dummy provider has no journal; the accounting payment created by
        # account_payment is not what these tests are about.
        Tx = type(self.env['payment.transaction'])
        if hasattr(Tx, '_create_payment'):
            with patch.object(Tx, '_create_payment', return_value=None):
                return tx._post_process()
        return tx._post_process()

    def _take_slot(self):
        self.booking.payment_hold_until = fields.Datetime.now() - timedelta(minutes=1)
        return self._booking(self.appointment_type, self.start, staff_user_id=self.host.id)

    def test_sale_order_starts_the_hold(self):
        self.assertEqual(self.booking.state, 'pending_payment')
        self.assertGreater(self.booking.payment_hold_until, fields.Datetime.now())
        conflict = self.env['appointment.booking']._check_booking_conflict(
            self.start, self.start + timedelta(hours=1), staff_user_id=self.host.id)
        self.assertTrue(conflict['staff_conflict'])

    def test_no_payment_for_a_slot_sold_after_the_hold(self):
        self._take_slot()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self._tx('RULES-TAKEN')

    def _late_in_the_window(self):
        """As if 25 of the 30 minutes of the payment window had passed."""
        now = fields.Datetime.now()
        self.booking.write({'payment_hold_started_at': now - timedelta(minutes=25),
                            'payment_hold_until': now + timedelta(minutes=5)})
        return self.booking.payment_hold_until

    def test_expired_hold_is_payable_but_not_renewed(self):
        expired = fields.Datetime.now() - timedelta(minutes=1)
        self.booking.payment_hold_until = expired
        self._tx('RULES-RENEW')  # the slot is free: paying is allowed
        self.assertEqual(self.booking.payment_hold_until, expired)

    def test_new_transactions_do_not_move_the_deadline(self):
        deadline = self._late_in_the_window()
        for index in range(3):
            self._tx('RULES-AGAIN-%d' % index)
            self.booking._ensure_payment_hold()
        self.assertEqual(self.booking.payment_hold_until, deadline)

    def test_legacy_booking_gets_one_window(self):
        legacy = self._booking(self.appointment_type, self._wall(4, 10), state='pending_payment',
                               staff_user_id=self.host.id)
        self.assertFalse(legacy.payment_hold_until)
        legacy._ensure_payment_hold()
        self.assertTrue(legacy.payment_hold_started_at)
        self.assertGreater(legacy.payment_hold_until, fields.Datetime.now())
        legacy.payment_hold_until = fields.Datetime.now() - timedelta(minutes=1)
        legacy._ensure_payment_hold()
        self.assertLess(legacy.payment_hold_until, fields.Datetime.now())

    def test_repeated_pending_transfers_hold_once(self):
        first = self._tx('RULES-WIRE-1')
        first._set_pending()
        self._post_process(first)
        self.assertTrue(self.booking.payment_pending_hold_granted)
        self.assertGreater(self.booking.payment_hold_until, fields.Datetime.now() + timedelta(hours=2))
        # Later: the long hold is nearly over; another wire transfer is started.
        nearly_over = fields.Datetime.now() + timedelta(minutes=5)
        self.booking.payment_hold_until = nearly_over
        second = self._tx('RULES-WIRE-2')
        second._set_pending()
        self._post_process(second)
        self.assertEqual(self.booking.payment_hold_until, nearly_over)

    def test_pending_hold_never_passes_the_appointment(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'reservation_module.payment_pending_hold_hours', '10000')
        tx = self._tx('RULES-WIRE-LONG')
        tx._set_pending()
        self._post_process(tx)
        self.assertEqual(self.booking.payment_hold_until, self.booking.end_datetime)

    def test_no_pending_hold_on_a_sold_slot(self):
        tx = self._tx('RULES-WIRE-SOLD')
        self._take_slot()
        tx._set_pending()
        self._post_process(tx)
        self.assertFalse(self.booking.payment_pending_hold_granted)
        self.assertLess(self.booking.payment_hold_until, fields.Datetime.now())

    def test_pending_transfer_keeps_the_slot_longer(self):
        tx = self._tx('RULES-PENDING')
        tx._set_pending()
        self._post_process(tx)
        self.assertGreater(self.booking.payment_hold_until, fields.Datetime.now() + timedelta(hours=2))

    def test_failed_confirmation_after_payment_is_flagged(self):
        tx = self._tx('RULES-DONE')
        self._take_slot()
        tx._set_done()
        self._post_process(tx)
        self.assertEqual(self.booking.state, 'pending_payment')
        self.assertTrue(self.booking.payment_confirm_failed)
        self.assertTrue(self.booking.activity_ids, 'staff gets a follow-up activity')
        self.assertTrue(any('could not be confirmed' in (message.body or '')
                            for message in self.booking.message_ids))
        self.assertGreaterEqual(self.booking.payment_hold_until, self.booking.end_datetime)

    def test_slot_conflict_after_payment_is_flagged(self):
        tx = self._tx('RULES-CONFLICT')
        self._take_slot()
        tx._set_done()
        Booking = type(self.env['appointment.booking'])

        def paid(records):
            for record in records:
                record.payment_status = 'paid'
        with patch.object(Booking, '_compute_payment_status', paid):
            self.booking.invalidate_recordset(['payment_status'])
            self._post_process(tx)
        self.assertEqual(self.booking.state, 'pending_payment')
        self.assertTrue(self.booking.payment_confirm_failed)
        self.assertTrue(any('already booked' in (message.body or '')
                            for message in self.booking.message_ids))

    def test_serialization_failure_is_not_swallowed(self):
        tx = self._tx('RULES-RETRY')
        tx._set_done()
        Booking = type(self.env['appointment.booking'])
        with patch.object(Booking, 'action_confirm',
                          side_effect=psycopg2.errors.SerializationFailure('retry me')):
            with self.assertRaises(psycopg2.errors.SerializationFailure):
                self._post_process(tx)


@tagged('post_install', '-at_install')
class TestPaymentFailureMails(PaymentHoldCommon, RulesHttpCommon, HttpCase):
    """94f32de1e119: one booking cannot make the form mail a typed address
    over and over (return page reloads, repeated failed transactions)."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._paid_type()
        self._post(self.appointment_type, self._wall(3, 10), guest_email='relay.victim@example.org')
        self.booking = self._bookings(self.appointment_type, guest_email='relay.victim@example.org')
        self.assertEqual(self.booking.state, 'pending_payment')
        self.assertTrue(self.booking.client_ip_hash, 'a public-form booking')
        self.provider = self.env['payment.provider'].create({
            'name': 'Failure Dummy', 'code': 'none', 'state': 'test',
            'payment_method_ids': [(6, 0, self.env.ref('payment.payment_method_unknown').ids)],
        })

    def _failed_tx(self, reference):
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self.provider.id,
            'payment_method_id': self.env.ref('payment.payment_method_unknown').id,
            'reference': reference,
            'amount': 100.0,
            'currency_id': self.booking.currency_id.id or self.env.company.currency_id.id,
            'partner_id': self.booking.partner_id.id,
            'appointment_booking_id': self.booking.id,
        })
        self.booking.payment_transaction_id = tx
        tx._set_error('Card declined')
        return tx

    def _validate(self, times=1):
        self.env.flush_all()
        for _index in range(times):
            response = self.url_open('/appointment/payment/validate?booking_id=%d&token=%s'
                                     % (self.booking.id, self.booking.access_token))
            self.assertEqual(response.status_code, 200)
        self.env.invalidate_all()
        return response

    def _failure_mails(self):
        return self.env['mail.mail'].sudo().search([
            ('model', '=', 'appointment.booking'), ('res_id', '=', self.booking.id),
            ('subject', 'ilike', 'Payment failed')])

    def _failure_notes(self):
        return self.booking.message_ids.filtered(lambda m: 'Payment failure #' in (m.body or ''))

    def test_return_page_without_a_transaction_is_not_a_failure(self):
        self._validate(times=4)
        self.assertFalse(self._failure_mails())
        self.assertEqual(self.booking.payment_failure_count, 0)

    def test_return_page_reloads_send_one_failure_mail(self):
        tx = self._failed_tx('RULES-FAIL-RELOAD')
        self._validate(times=5)
        self.assertEqual(len(self._failure_mails()), 1)
        self.assertEqual(self.booking.payment_failure_count, 1)
        self.assertEqual(len(self._failure_notes()), 1)
        # The webhook reporting the same transaction afterwards changes nothing.
        tx._post_process()
        self.env.invalidate_all()
        self.assertEqual(len(self._failure_mails()), 1)
        self.assertEqual(self.booking.payment_failure_count, 1)

    def test_new_failed_transactions_mail_once_a_day_and_a_few_times_total(self):
        for index in range(3):
            self._failed_tx('RULES-FAIL-%d' % index)._post_process()
        self.env.invalidate_all()
        self.assertEqual(self.booking.payment_failure_count, 3, 'every failure is counted')
        self.assertEqual(len(self._failure_notes()), 3, 'and noted for staff')
        self.assertEqual(len(self._failure_mails()), 1, 'but mailed once a day')
        for index in range(3):
            self.booking.payment_failure_mailed_at = fields.Datetime.now() - timedelta(days=2)
            self._failed_tx('RULES-FAIL-LATER-%d' % index)._post_process()
        self.env.invalidate_all()
        self.assertEqual(len(self._failure_mails()), 3, 'at most 3 in total')
        self.assertEqual(self.booking.payment_failure_count, 6)

    def test_settled_booking_reports_no_failure(self):
        self._failed_tx('RULES-FAIL-SETTLED')
        self.booking.state = 'cancelled'
        response = self._validate(times=3)
        self.assertIn('/appointment/booking/%d?token=' % self.booking.id, response.url)
        self.assertFalse(self._failure_mails())
        self.assertEqual(self.booking.payment_failure_count, 0)

    def test_upgrade_marks_already_reported_failures(self):
        tx = self._failed_tx('RULES-FAIL-LEGACY')
        self.booking.payment_failure_count = 2  # reported twice by the old code
        self.env.flush_all()
        mig = _load_migration_3_2_2()
        self.assertGreaterEqual(mig._mark_reported_payment_failures(self.env.cr), 1)
        self.env.invalidate_all()
        self.assertTrue(tx.appointment_failure_notified)
        self.assertEqual(self.booking.payment_failure_mail_count, 2)
        self._validate(times=2)
        self.assertFalse(self._failure_mails(), 'already reported before the upgrade')
        self.assertEqual(self.booking.payment_failure_count, 2)
        self.assertEqual(mig._mark_reported_payment_failures(self.env.cr), 0)
