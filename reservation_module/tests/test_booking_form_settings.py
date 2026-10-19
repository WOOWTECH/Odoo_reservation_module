# -*- coding: utf-8 -*-
"""預約表單設定（require_guest_*、single_guest_booking）與電話正規化。"""

from datetime import timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.phone_validation.tools import phone_validation

from ..models.booking_identity import normalize_booking_phone, resolve_single_active_assignment


@tagged('-at_install', 'post_install')
class TestBookingFormSettings(TransactionCase):

    def test_defaults_keep_previous_form_behaviour(self):
        appointment_type = self.env['appointment.type'].create({'name': 'Defaults', 'slot_duration': 1.0})
        self.assertTrue(appointment_type.require_guest_name)
        self.assertTrue(appointment_type.require_guest_email)
        self.assertFalse(appointment_type.require_guest_phone)
        self.assertFalse(appointment_type.single_guest_booking)

    def test_phone_only_configuration_is_allowed(self):
        appointment_type = self.env['appointment.type'].create({
            'name': 'Phone only', 'slot_duration': 1.0,
            'require_guest_name': False, 'require_guest_email': False,
            'require_guest_phone': True, 'single_guest_booking': True,
        })
        self.assertTrue(appointment_type.require_guest_phone)

    def test_email_or_phone_must_be_required(self):
        with self.assertRaises(ValidationError):
            self.env['appointment.type'].create({
                'name': 'No contact', 'slot_duration': 1.0,
                'require_guest_email': False, 'require_guest_phone': False,
            })

    def test_booking_without_name_and_email_can_be_stored(self):
        """model 層不設 required：只填電話的預約（markstudio 的設定）可以存。"""
        appointment_type = self.env['appointment.type'].create({
            'name': 'Phone only', 'slot_duration': 1.0,
            'require_guest_name': False, 'require_guest_email': False, 'require_guest_phone': True,
        })
        now = self.env.cr.now()
        booking = self.env['appointment.booking'].create({
            'appointment_type_id': appointment_type.id,
            'guest_phone': '+886912345678',
            'guest_count': 1,
            'start_datetime': now + timedelta(days=1),
            'end_datetime': now + timedelta(days=1, hours=1),
        })
        self.assertFalse(booking.guest_email)


class TestBookingIdentityHelpers(TransactionCase):

    def _normalize(self, value):
        return normalize_booking_phone(value, 'TW', 886, phone_validation.phone_format, UserError)

    def test_taiwan_mobile_is_normalized_to_e164(self):
        self.assertEqual(self._normalize('0912-345-678'), '+886912345678')
        self.assertEqual(self._normalize('０９１２３４５６７８'), '+886912345678')   # 全形

    def test_invalid_phone_inputs_are_rejected(self):
        for value in ('', '---', '12+34', '++886912345678', 'abc', None):
            self.assertIsNone(self._normalize(value), value)

    def test_single_active_assignment(self):
        self.assertEqual(resolve_single_active_assignment(True, None, [7]), (7, None))
        self.assertEqual(resolve_single_active_assignment(True, 8, [7]), (None, 'not_available'))
        self.assertEqual(resolve_single_active_assignment(False, None, [7, 8]), (None, None))
        self.assertEqual(resolve_single_active_assignment(True, 8, [7, 8]), (8, None))
