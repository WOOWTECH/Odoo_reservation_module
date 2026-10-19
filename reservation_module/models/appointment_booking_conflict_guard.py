# -*- coding: utf-8 -*-
"""Technical MVCC guards for appointment staff/resource conflict checks."""

from odoo import api, fields, models


class AppointmentBookingConflictGuard(models.Model):
    """One mutable row per independently contended booking dimension.

    This table intentionally stores no customer, staff, resource, or booking
    business data. Updating a stable key before an aggregate conflict query
    serializes concurrent writers under Odoo's REPEATABLE READ isolation: a
    stale concurrent transaction receives PostgreSQL SerializationFailure and
    is retried by Odoo's HTTP transaction wrapper.
    """

    _name = 'appointment.booking.conflict.guard'
    _description = 'Appointment Booking Conflict Guard'
    _rec_name = 'guard_key'
    _order = 'guard_key'

    guard_key = fields.Char(required=True, readonly=True, index=True)
    revision = fields.Integer(required=True, readonly=True, default=0)

    _sql_constraints = [
        (
            'appointment_booking_conflict_guard_key_unique',
            'unique(guard_key)',
            'A booking conflict guard key must be unique.',
        ),
    ]

    @api.model
    def _acquire_keys(self, guard_keys):
        """Mutate every key in deterministic order to acquire MVCC write locks.

        ``INSERT ... ON CONFLICT DO UPDATE`` is deliberate: it both creates a
        missing guard and updates an existing one. Do not replace this with an
        advisory lock or a read-only ``FOR UPDATE``; either can leave a stale
        REPEATABLE READ snapshot unaware of a just-committed booking.
        """
        for guard_key in sorted(set(guard_keys)):
            self.env.cr.execute(
                """
                INSERT INTO appointment_booking_conflict_guard
                    (guard_key, revision, create_uid, create_date, write_uid, write_date)
                VALUES (%s, 1, %s, NOW(), %s, NOW())
                ON CONFLICT (guard_key) DO UPDATE
                SET revision = appointment_booking_conflict_guard.revision + 1,
                    write_uid = EXCLUDED.write_uid,
                    write_date = NOW()
                RETURNING id
                """,
                [guard_key, self.env.uid, self.env.uid],
            )
            self.env.cr.fetchone()
