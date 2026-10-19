# -*- coding: utf-8 -*-
"""Isolated-DB regressions for aggregate booking conflict locking.

These tests require PostgreSQL/Odoo and are intentionally tagged post-install:
the two-cursor case commits independent disposable-test transactions to prove
that a stale REPEATABLE READ writer receives SerializationFailure for retry.
"""

import threading
import time
from datetime import timedelta
from types import SimpleNamespace

from psycopg2.errors import SerializationFailure

from odoo import api, fields, sql_db, SUPERUSER_ID
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('-at_install', 'post_install', 'booking_conflict_guard')
class TestBookingConflictGuard(TransactionCase):

    def test_guarded_aggregate_queries_execute_without_for_update_error(self):
        """COUNT/SUM remain ordinary aggregates after guard mutation."""
        Booking = self.env['appointment.booking']
        start = fields.Datetime.now() + timedelta(days=1)
        calendar = self.env.company.resource_calendar_id or self.env['resource.calendar'].create({'name': 'Guard test calendar'})
        resource = self.env['resource.resource'].create({
            'name': 'Guard test resource', 'resource_type': 'material',
            'calendar_id': calendar.id, 'capacity': 2,
        })
        result = Booking._check_booking_conflict(
            start_dt=start,
            end_dt=start + timedelta(hours=1),
            staff_user_id=9000001,
            resource_id=resource.id,
            lock=True,
        )
        self.assertFalse(result['staff_conflict'])
        self.assertFalse(result['resource_conflict'])
        self.assertEqual(
            self.env['appointment.booking.conflict.guard'].search_count([
                ('guard_key', 'in', ['staff:9000001', f'resource:{resource.id}']),
            ]),
            2,
        )

    @mute_logger('odoo.sql_db')
    def test_two_cursors_get_serialization_failure_for_same_guard(self):
        """A stale concurrent writer must fail outward for Odoo request retry."""
        database = sql_db.db_connect(self.env.cr.dbname)
        start = fields.Datetime.now() + timedelta(days=2)
        staff_id = 9000003
        errors = []
        second_started = threading.Event()
        guard_class = type(self.env['appointment.booking.conflict.guard'])

        # Use physical cursors, not Registry TestCursor wrappers sharing the
        # TransactionCase transaction.  Odoo 18 does not require Environment.manage().
        with database.cursor() as cr1, database.cursor() as cr2:
            env1 = api.Environment(cr1, SUPERUSER_ID, {})
            # Pin cursor two's snapshot before cursor one creates/updates key.
            cr2.execute('SELECT COUNT(*) FROM appointment_booking_conflict_guard')
            env1['appointment.booking']._check_booking_conflict(
                start_dt=start,
                end_dt=start + timedelta(hours=1),
                staff_user_id=staff_id,
                lock=True,
            )

            def acquire_from_stale_snapshot():
                # TransactionCase holds the registry test lock in the parent
                # thread. Exercise the real SQL guard with this physical cursor
                # without trying to acquire that registry lock in the worker.
                holder = SimpleNamespace(env=SimpleNamespace(cr=cr2, uid=SUPERUSER_ID))
                second_started.set()
                try:
                    guard_class._acquire_keys(holder, [f'staff:{staff_id}'])
                except Exception as error:  # Assert exact DB error after join.
                    errors.append(error)
                    # Production lets this escape to Odoo's retry wrapper.
                    cr2.rollback()

            thread = threading.Thread(target=acquire_from_stale_snapshot)
            thread.start()
            self.assertTrue(second_started.wait(timeout=2))
            # Let cursor two reach the contended UPSERT before releasing c1.
            time.sleep(0.1)
            cr1.commit()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), 'second cursor did not finish')

        with database.cursor() as cleanup:
            cleanup.execute('DELETE FROM appointment_booking_conflict_guard WHERE guard_key = %s', [f'staff:{staff_id}'])
            cleanup.commit()
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], SerializationFailure)
