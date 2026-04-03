# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
from odoo import fields


class TestAppointmentBooking(TransactionCase):
    """Test suite for appointment booking core logic."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Guest',
            'email': 'guest@test.com',
            'phone': '0912345678',
        })
        cls.staff_user = cls.env['res.users'].create({
            'name': 'Test Staff',
            'login': 'test_staff_appt',
            'email': 'staff@test.com',
        })
        cls.resource = cls.env['resource.resource'].create({
            'name': 'Test Room',
            'resource_type': 'material',
            'capacity': 2,
        })
        cls.appointment_type = cls.env['appointment.type'].create({
            'name': 'Test Appointment',
            'slot_duration': 1.0,
            'max_booking_days': 30,
            'min_booking_hours': 0,
            'auto_confirm': False,
            'require_payment': False,
            'is_published': True,
            'staff_user_ids': [(4, cls.staff_user.id)],
            'resource_ids': [(4, cls.resource.id)],
        })

    def _create_booking(self, **kwargs):
        """Helper to create a booking with sane defaults."""
        now = fields.Datetime.now()
        vals = {
            'appointment_type_id': self.appointment_type.id,
            'guest_name': 'Test Guest',
            'guest_email': 'guest@test.com',
            'guest_count': 1,
            'start_datetime': now + timedelta(days=1),
            'end_datetime': now + timedelta(days=1, hours=1),
            'partner_id': self.partner.id,
        }
        vals.update(kwargs)
        return self.env['appointment.booking'].create(vals)

    # ── State machine tests ──────────────────────────────────────

    def test_booking_create_draft(self):
        """Booking is created in draft state."""
        booking = self._create_booking()
        self.assertEqual(booking.state, 'draft')
        self.assertTrue(booking.access_token)
        self.assertNotEqual(booking.name, 'New')

    def test_confirm_booking(self):
        """Draft booking can be confirmed."""
        booking = self._create_booking()
        booking.action_confirm()
        self.assertEqual(booking.state, 'confirmed')

    def test_done_from_confirmed(self):
        """Confirmed booking can be marked done."""
        booking = self._create_booking()
        booking.action_confirm()
        booking.action_done()
        self.assertEqual(booking.state, 'done')

    def test_cancel_draft(self):
        """Draft booking can be cancelled."""
        booking = self._create_booking()
        booking.action_cancel()
        self.assertEqual(booking.state, 'cancelled')

    def test_cancel_confirmed(self):
        """Confirmed booking can be cancelled."""
        booking = self._create_booking()
        booking.action_confirm()
        booking.action_cancel()
        self.assertEqual(booking.state, 'cancelled')

    def test_draft_from_cancelled(self):
        """Cancelled booking can be reset to draft."""
        booking = self._create_booking()
        booking.action_cancel()
        booking.action_draft()
        self.assertEqual(booking.state, 'draft')

    def test_no_draft_from_done(self):
        """Done booking cannot be reset to draft."""
        booking = self._create_booking()
        booking.action_confirm()
        booking.action_done()
        booking.action_draft()  # should silently do nothing
        self.assertEqual(booking.state, 'done')

    # ── Validation tests ─────────────────────────────────────────

    def test_guest_count_minimum(self):
        """Guest count below 1 raises ValidationError."""
        with self.assertRaises(ValidationError):
            self._create_booking(guest_count=0)

    def test_end_before_start_raises(self):
        """End datetime before start raises ValidationError."""
        now = fields.Datetime.now()
        with self.assertRaises(ValidationError):
            self._create_booking(
                start_datetime=now + timedelta(days=1, hours=2),
                end_datetime=now + timedelta(days=1, hours=1),
            )

    # ── Conflict detection tests ─────────────────────────────────

    def test_staff_conflict_detected(self):
        """Staff conflict is detected for overlapping bookings."""
        now = fields.Datetime.now()
        start = now + timedelta(days=2)
        end = start + timedelta(hours=1)

        booking1 = self._create_booking(
            staff_user_id=self.staff_user.id,
            start_datetime=start,
            end_datetime=end,
        )
        booking1.action_confirm()

        conflict = self.env['appointment.booking']._check_booking_conflict(
            start_dt=start,
            end_dt=end,
            staff_user_id=self.staff_user.id,
        )
        self.assertTrue(conflict['staff_conflict'])

    def test_resource_conflict_at_capacity(self):
        """Resource conflict detected when capacity is reached."""
        now = fields.Datetime.now()
        start = now + timedelta(days=3)
        end = start + timedelta(hours=1)

        # Resource capacity is 2, create 2 confirmed bookings
        for _ in range(2):
            b = self._create_booking(
                resource_id=self.resource.id,
                start_datetime=start,
                end_datetime=end,
            )
            b.action_confirm()

        conflict = self.env['appointment.booking']._check_booking_conflict(
            start_dt=start,
            end_dt=end,
            resource_id=self.resource.id,
        )
        self.assertTrue(conflict['resource_conflict'])
        self.assertEqual(conflict['resource_remaining'], 0)

    def test_resource_no_conflict_under_capacity(self):
        """No resource conflict when under capacity."""
        now = fields.Datetime.now()
        start = now + timedelta(days=4)
        end = start + timedelta(hours=1)

        b = self._create_booking(
            resource_id=self.resource.id,
            start_datetime=start,
            end_datetime=end,
        )
        b.action_confirm()

        conflict = self.env['appointment.booking']._check_booking_conflict(
            start_dt=start,
            end_dt=end,
            resource_id=self.resource.id,
        )
        self.assertFalse(conflict['resource_conflict'])
        self.assertEqual(conflict['resource_remaining'], 1)

    def test_no_conflict_different_time(self):
        """No conflict for non-overlapping time slots."""
        now = fields.Datetime.now()
        start1 = now + timedelta(days=5)
        end1 = start1 + timedelta(hours=1)

        b = self._create_booking(
            staff_user_id=self.staff_user.id,
            start_datetime=start1,
            end_datetime=end1,
        )
        b.action_confirm()

        start2 = end1 + timedelta(hours=1)
        end2 = start2 + timedelta(hours=1)
        conflict = self.env['appointment.booking']._check_booking_conflict(
            start_dt=start2,
            end_dt=end2,
            staff_user_id=self.staff_user.id,
        )
        self.assertFalse(conflict['staff_conflict'])

    def test_confirm_blocks_on_staff_conflict(self):
        """Confirming a booking raises UserError when staff is double-booked."""
        now = fields.Datetime.now()
        start = now + timedelta(days=6)
        end = start + timedelta(hours=1)

        b1 = self._create_booking(
            staff_user_id=self.staff_user.id,
            start_datetime=start,
            end_datetime=end,
        )
        b1.action_confirm()

        b2 = self._create_booking(
            staff_user_id=self.staff_user.id,
            start_datetime=start,
            end_datetime=end,
        )
        with self.assertRaises(UserError):
            b2.action_confirm()

    # ── Payment status on cancellation ───────────────────────────

    def test_cancel_pending_payment_resets_status(self):
        """Cancelling a pending-payment booking sets payment_status to not_required."""
        booking = self._create_booking(
            payment_status='pending',
            payment_amount=100.0,
        )
        booking.action_cancel()
        self.assertEqual(booking.payment_status, 'not_required')

    def test_cancel_paid_booking_sets_refunded(self):
        """Cancelling a paid booking sets payment_status to refunded."""
        booking = self._create_booking(
            payment_status='paid',
            payment_amount=100.0,
        )
        booking.action_confirm()
        booking.action_cancel()
        self.assertEqual(booking.payment_status, 'refunded')

    # ── Reminder cron ────────────────────────────────────────────

    def test_cron_sends_reminders(self):
        """Cron sends reminders for bookings within the reminder window."""
        self.appointment_type.reminder_hours = 24
        now = fields.Datetime.now()
        booking = self._create_booking(
            start_datetime=now + timedelta(hours=12),
            end_datetime=now + timedelta(hours=13),
        )
        booking.action_confirm()
        self.assertFalse(booking.reminder_sent)

        # Run cron
        self.env['appointment.booking']._cron_send_reminders()
        booking.invalidate_recordset()
        self.assertTrue(booking.reminder_sent)

    def test_cron_skips_far_future_bookings(self):
        """Cron does not remind bookings far in the future."""
        self.appointment_type.reminder_hours = 24
        now = fields.Datetime.now()
        booking = self._create_booking(
            start_datetime=now + timedelta(days=7),
            end_datetime=now + timedelta(days=7, hours=1),
        )
        booking.action_confirm()

        self.env['appointment.booking']._cron_send_reminders()
        booking.invalidate_recordset()
        self.assertFalse(booking.reminder_sent)

    # ── Duration compute ─────────────────────────────────────────

    def test_duration_computed(self):
        """Duration is computed from start/end times."""
        now = fields.Datetime.now()
        booking = self._create_booking(
            start_datetime=now + timedelta(days=1),
            end_datetime=now + timedelta(days=1, hours=2),
        )
        self.assertAlmostEqual(booking.duration, 2.0, places=1)
