# -*- coding: utf-8 -*-
"""What the mails to a visitor-typed address contain (finding 94f32de1e119).

The public booking form takes any e-mail address and any name, and the module
mails that address. Volume is bounded by the rate limits and the per-inbox
mail cap (test_booking_rules.py, test_booking_client_key.py); this file pins
the other half of the finding's remediation: a mail to an address nobody
verified carries no visitor-supplied free text except the booking reference
(made by the system) and the guest's own name, which is escaped.

Residual, accepted: the name itself (at most 256 characters, escaped, in the
greeting "Dear <name>," of the module's mails and in the attendee name of the
calendar invitation) still reaches the typed address. Removing it needs the
address to be verified first (a confirmation step in the anonymous booking
flow) or a mail without a greeting; both change what every visitor of the
three live sites sees, which the finding itself marked as "discuss". The
notes, the phone number and anything else the form takes never appear.
"""

import re
from datetime import timedelta

from odoo.tests.common import HttpCase, tagged

from .test_booking_rules import RulesHttpCommon, _keep_queued_mails

#: every template that mails the guest of a booking
GUEST_TEMPLATES = [
    'reservation_module.email_template_booking_created',
    'reservation_module.email_template_booking_confirmed',
    'reservation_module.email_template_booking_reminder',
    'reservation_module.email_template_booking_done',
    'reservation_module.email_template_booking_cancelled',
    'reservation_module.email_template_payment_failure',
]

NAME = 'Mallory <b>CLICK</b> http://evil.example/pay'
NOTES = 'NOTES-SENTINEL wire the fee to evil.example/fee'
PHONE = '+886912345678'
EMAIL = 'victim@example.org'
#: other places a visitor could put text: the phone digits in any formatting
PHONE_DIGITS = ('886912345678', '0912345678', '912345678')


def _html_escaped(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def visitor_text_in(mail, booking):
    """What ``mail`` shows that the visitor typed, apart from the booking
    reference and the guest's own name (escaped as stored, and again as a
    template prints it). Returns the leaked markers; an empty list is clean."""
    allowed = [booking.name, booking.guest_name, _html_escaped(booking.guest_name)]
    text = '%s\n%s' % (mail.subject or '', mail.body_html or '')
    for value in sorted(allowed, key=len, reverse=True):
        text = text.replace(value, '')
    leaks = [marker for marker in ('NOTES-SENTINEL', 'evil.example', 'CLICK', 'Mallory') if marker in text]
    leaks += [digits for digits in PHONE_DIGITS if digits in text]
    # no link can be planted: the only anchors are the module's own
    leaks += ['href=%s' % href for href in re.findall(r'href="([^"]*)"', mail.body_html or '')
              if 'evil' in href or 'mailto:%s' % EMAIL in href]
    return leaks


@tagged('post_install', '-at_install')
class TestGuestMailContent(RulesHttpCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.appointment_type = self._setup_appointment_type()
        _keep_queued_mails(self)
        self.response = self._post(
            self.appointment_type, self._wall(3, 10), guest_name=NAME, guest_email=EMAIL,
            guest_phone=PHONE, notes=NOTES)
        self.booking = self._bookings(self.appointment_type)
        self.assertEqual(len(self.booking), 1, 'the booking was made through the public form')

    def _visitor_mails(self):
        self.env.invalidate_all()
        return self.env['mail.mail'].sudo().search([
            '|', ('email_to', 'ilike', EMAIL), ('recipient_ids.email', 'ilike', EMAIL)])

    def _send_every_guest_mail(self):
        for xmlid in GUEST_TEMPLATES:
            self.assertTrue(self.booking._send_guest_mail(xmlid), xmlid)
        # core's mails of the booking's event: date change and "send by mail"
        self.booking.write({'start_datetime': self.booking.start_datetime + timedelta(hours=1),
                            'end_datetime': self.booking.end_datetime + timedelta(hours=1)})
        self.booking.calendar_event_id.action_sendmail()

    def test_the_form_kept_what_was_typed(self):
        # The test is only meaningful if the hostile values are on the booking.
        self.assertIn('Mallory', self.booking.guest_name)
        self.assertIn('NOTES-SENTINEL', self.booking.notes)
        self.assertEqual(self.booking.guest_phone, PHONE)
        self.assertEqual(self.booking.guest_email, EMAIL)

    def test_no_mail_to_the_typed_address_carries_other_visitor_text(self):
        self._send_every_guest_mail()
        mails = self._visitor_mails()
        models = {mail.model for mail in mails}
        self.assertEqual(models, {'appointment.booking', 'calendar.event'},
                         'module mails and the calendar invitation / date change')
        self.assertGreaterEqual(len(mails.filtered(lambda mail: mail.model == 'appointment.booking')),
                                len(GUEST_TEMPLATES))
        for mail in mails:
            with self.subTest(subject=mail.subject, model=mail.model):
                self.assertEqual(visitor_text_in(mail, self.booking), [])

    def test_subjects_and_senders_are_not_visitor_text(self):
        self._send_every_guest_mail()
        for mail in self._visitor_mails():
            with self.subTest(subject=mail.subject):
                self.assertIn(self.booking.name, mail.subject)
                self.assertNotIn('Mallory', mail.subject or '')
                self.assertNotIn(EMAIL, mail.email_from or '')
                self.assertNotIn('Mallory', mail.email_from or '')

    def test_the_name_is_printed_as_text_never_as_markup(self):
        self._send_every_guest_mail()
        greeted = self._visitor_mails().filtered(lambda mail: mail.model == 'appointment.booking')
        self.assertTrue(greeted)
        for mail in greeted:
            with self.subTest(subject=mail.subject):
                self.assertNotIn('<b>CLICK</b>', mail.body_html)
                self.assertIn('Dear Mallory', mail.body_html)

    def test_the_check_itself_catches_a_leak(self):
        # Guard against a vacuous test: a mail with the notes, the phone or a
        # planted link in it is reported.
        mail = self.env['mail.mail'].sudo().create({
            'subject': 'Your booking %s' % self.booking.name,
            'body_html': '<p>Dear %s, %s</p><p>%s</p><a href="http://evil.example/pay">pay</a>' % (
                _html_escaped(self.booking.guest_name), self.booking.name, NOTES + ' ' + PHONE),
            'email_to': EMAIL,
        })
        leaks = visitor_text_in(mail, self.booking)
        self.assertIn('NOTES-SENTINEL', leaks)
        self.assertIn('evil.example', leaks)
        self.assertIn('886912345678', leaks)
        self.assertTrue([leak for leak in leaks if leak.startswith('href=')])
        clean = self.env['mail.mail'].sudo().create({
            'subject': 'Your booking %s' % self.booking.name,
            'body_html': '<p>Dear %s, %s</p>' % (_html_escaped(self.booking.guest_name), self.booking.name),
            'email_to': EMAIL,
        })
        self.assertEqual(visitor_text_in(clean, self.booking), [])
