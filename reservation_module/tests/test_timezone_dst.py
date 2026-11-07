# -*- coding: utf-8 -*-
"""Daylight-saving contrast tests for booking windows and the slot grid.

Finding 5d593007668b (event mode books exactly one availability window)
required a daylight-saving contrast test, but the other tests only use
Asia/Taipei, which has no DST. These use the 2026 changes of two zones:

  Europe/Berlin     2026-03-29  02:00 CET  -> 03:00 CEST  (02:xx never happens)
                    2026-10-25  03:00 CEST -> 02:00 CET   (02:xx happens twice)
  America/New_York  2026-03-08  02:00 EST  -> 03:00 EDT   (02:xx never happens)
                    2026-11-01  02:00 EDT  -> 01:00 EST   (01:xx happens twice)
  Asia/Beirut       2026-03-29  00:00 EET  -> 01:00 EEST  (a zone that changes at midnight:
                                                          00:xx never happens, and a window
                                                          ending at 24:00 the day before ends
                                                          at a wall time that does not exist)
                    2026-10-25  00:00 EEST -> 23:00 EET   (23:xx of the 24th happens twice)

Rules pinned here (tz_utils.py has the arithmetic):

  * window hours are wall clock in the type's zone, converted day by day, so
    the same hours are a different number of real hours on a change day
  * a window whose start or end does not exist (spring gap) is skipped by the
    slot lists *and* the booking form; an ambiguous wall time (autumn) means
    standard time; a window ending at 24:00 ends at the next local midnight
  * a slot lasts ``slot_duration`` of real time, which is what a booking
    stores, so every slot that is offered is accepted by the booking form and
    ends where the stored booking ends

The expected UTC values were worked out by hand and cross-checked against
``zoneinfo`` (an implementation independent of pytz, which the module uses).
"""

from datetime import date, datetime, timedelta

from odoo.addons.website.tools import MockRequest
from odoo.tests.common import HttpCase, TransactionCase, tagged

from ..controllers.main import AppointmentController
from .test_booking_rules import RulesCommon, RulesHttpCommon

try:
    from freezegun import freeze_time
except ImportError:  # pragma: no cover - freezegun ships with Odoo's test deps
    freeze_time = None

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = ZoneInfoNotFoundError = None

FMT = '%Y-%m-%d %H:%M:%S'

# name: (zone, local day of the change, a moment a few days before it)
CHANGE_DAYS = {
    'berlin_spring': ('Europe/Berlin', date(2026, 3, 29), '2026-03-25 12:00:00'),
    'berlin_autumn': ('Europe/Berlin', date(2026, 10, 25), '2026-10-20 12:00:00'),
    'new_york_spring': ('America/New_York', date(2026, 3, 8), '2026-03-03 12:00:00'),
    'new_york_autumn': ('America/New_York', date(2026, 11, 1), '2026-10-27 12:00:00'),
}
# Zones whose clocks change at midnight: only the invariants are checked on
# these (what the slot lists offer is what the booking form takes).
MIDNIGHT_CHANGE_DAYS = {
    'beirut_spring_eve': ('Asia/Beirut', date(2026, 3, 28), '2026-03-25 12:00:00'),
    'beirut_spring': ('Asia/Beirut', date(2026, 3, 29), '2026-03-25 12:00:00'),
    'beirut_autumn_eve': ('Asia/Beirut', date(2026, 10, 24), '2026-10-20 12:00:00'),
    'beirut_autumn': ('Asia/Beirut', date(2026, 10, 25), '2026-10-20 12:00:00'),
}
CHANGE_DAYS_ALL = dict(CHANGE_DAYS, **MIDNIGHT_CHANGE_DAYS)


def utc(text):
    return datetime.strptime(text, FMT)


class DstCommon(RulesCommon):

    def _typed(self, case, windows, scheduled=False, **extra):
        """An appointment type in the zone of ``case`` whose every weekday has
        exactly ``windows`` ((hour_from, hour_to) pairs)."""
        zone = CHANGE_DAYS_ALL[case][0]
        vals = {'timezone': zone, 'is_scheduled': scheduled, 'max_booking_days': 400}
        vals.update(extra)
        appointment_type = self._setup_appointment_type(**vals)
        self._set_windows(appointment_type, [(a, b, {}) for a, b in windows])
        return appointment_type

    def _frozen(self, case):
        if freeze_time is None:
            self.skipTest('freezegun not available')
        return freeze_time(CHANGE_DAYS_ALL[case][2])


# ---------------------------------------------------------------------------
# Window arithmetic (model level)
# ---------------------------------------------------------------------------

#: (case, (hour_from, hour_to)) -> (start_utc, end_utc), or None when the
#: window is skipped because its start or end is a wall time that never happens.
WINDOW_UTC = {
    ('berlin_spring', (0, 6)): ('2026-03-28 23:00:00', '2026-03-29 04:00:00'),     # 5 real hours
    ('berlin_spring', (1, 4)): ('2026-03-29 00:00:00', '2026-03-29 02:00:00'),     # 3 wall hours = 2 real
    ('berlin_spring', (10, 12)): ('2026-03-29 08:00:00', '2026-03-29 10:00:00'),   # CEST, UTC+2
    ('berlin_spring', (20, 24)): ('2026-03-29 18:00:00', '2026-03-29 22:00:00'),   # ends at midnight CEST
    ('berlin_spring', (0, 24)): ('2026-03-28 23:00:00', '2026-03-29 22:00:00'),    # a 23 hour day
    ('berlin_spring', (2, 5)): None,
    ('berlin_spring', (1, 2.5)): None,
    ('berlin_spring', (2.5, 4)): None,
    ('berlin_spring', (1, 2)): None,
    ('berlin_autumn', (0, 6)): ('2026-10-24 22:00:00', '2026-10-25 05:00:00'),     # 7 real hours
    ('berlin_autumn', (1, 4)): ('2026-10-24 23:00:00', '2026-10-25 03:00:00'),     # 3 wall hours = 4 real
    ('berlin_autumn', (10, 12)): ('2026-10-25 09:00:00', '2026-10-25 11:00:00'),   # CET, UTC+1
    ('berlin_autumn', (20, 24)): ('2026-10-25 19:00:00', '2026-10-25 23:00:00'),
    ('berlin_autumn', (0, 24)): ('2026-10-24 22:00:00', '2026-10-25 23:00:00'),    # a 25 hour day
    ('berlin_autumn', (2.5, 4)): ('2026-10-25 01:30:00', '2026-10-25 03:00:00'),   # 02:30 twice: standard time
    ('berlin_autumn', (2, 3)): ('2026-10-25 01:00:00', '2026-10-25 02:00:00'),
    ('new_york_spring', (0, 6)): ('2026-03-08 05:00:00', '2026-03-08 10:00:00'),
    ('new_york_spring', (1, 4)): ('2026-03-08 06:00:00', '2026-03-08 08:00:00'),
    ('new_york_spring', (10, 12)): ('2026-03-08 14:00:00', '2026-03-08 16:00:00'),  # EDT, UTC-4
    ('new_york_spring', (20, 24)): ('2026-03-09 00:00:00', '2026-03-09 04:00:00'),
    ('new_york_spring', (0, 24)): ('2026-03-08 05:00:00', '2026-03-09 04:00:00'),
    ('new_york_spring', (2, 5)): None,
    ('new_york_spring', (2.5, 4)): None,
    ('new_york_autumn', (0, 6)): ('2026-11-01 04:00:00', '2026-11-01 11:00:00'),
    ('new_york_autumn', (1, 4)): ('2026-11-01 06:00:00', '2026-11-01 09:00:00'),   # 01:00 twice: standard time
    ('new_york_autumn', (10, 12)): ('2026-11-01 15:00:00', '2026-11-01 17:00:00'),  # EST, UTC-5
    ('new_york_autumn', (20, 24)): ('2026-11-02 01:00:00', '2026-11-02 05:00:00'),
    ('new_york_autumn', (0, 24)): ('2026-11-01 04:00:00', '2026-11-02 05:00:00'),
    ('new_york_autumn', (2, 5)): ('2026-11-01 07:00:00', '2026-11-01 10:00:00'),
    # Zones that change at midnight: the missing wall time is 00:00 itself, so
    # the evening window of the day before (ending at 24:00) and the night
    # window of the day (starting at 00:00) are skipped like any other window
    # with an edge that never happens.
    ('beirut_spring_eve', (0, 6)): ('2026-03-27 22:00:00', '2026-03-28 04:00:00'),
    ('beirut_spring_eve', (20, 24)): None,
    ('beirut_spring_eve', (0, 24)): None,
    ('beirut_spring', (0, 6)): None,
    ('beirut_spring', (1, 4)): ('2026-03-28 22:00:00', '2026-03-29 01:00:00'),
    ('beirut_spring', (20, 24)): ('2026-03-29 17:00:00', '2026-03-29 21:00:00'),
    ('beirut_autumn_eve', (20, 24)): ('2026-10-24 17:00:00', '2026-10-24 22:00:00'),   # 5 real hours
    ('beirut_autumn_eve', (0, 24)): ('2026-10-23 21:00:00', '2026-10-24 22:00:00'),    # 25 hours
    ('beirut_autumn', (0, 24)): ('2026-10-24 22:00:00', '2026-10-25 22:00:00'),
}


@tagged('post_install', '-at_install')
class TestDstWindows(DstCommon, TransactionCase):
    """appointment.type._get_availability_windows / _interval_in_availability."""

    def _windows(self, appointment_type, day):
        return [(start, end) for start, end, _avail in appointment_type._get_availability_windows(day)]

    def test_window_hours_become_the_right_utc_instants(self):
        types = {}
        for (case, hours), expected in WINDOW_UTC.items():
            day = CHANGE_DAYS_ALL[case][1]
            if case not in types:
                types[case] = self._typed(case, [hours])
            appointment_type = types[case]
            self._set_windows(appointment_type, [(hours[0], hours[1], {})])
            with self.subTest(case=case, hours=hours):
                self.assertEqual(
                    self._windows(appointment_type, day),
                    [(utc(expected[0]), utc(expected[1]))] if expected else [])

    def test_event_booking_must_be_exactly_the_window(self):
        for (case, hours), expected in WINDOW_UTC.items():
            if not expected:
                continue
            start, end = utc(expected[0]), utc(expected[1])
            appointment_type = self._typed(case, [hours])
            check = appointment_type._interval_in_availability
            with self.subTest(case=case, hours=hours):
                self.assertTrue(check(start, end))
                self.assertFalse(check(start, end - timedelta(minutes=1)))
                self.assertFalse(check(start + timedelta(minutes=1), end))
                self.assertFalse(check(start, end + timedelta(hours=1)))
                self.assertFalse(check(start - timedelta(hours=1), end))
                # The window as plain wall clock hours long, which is not the
                # real length on the day the clocks change.
                wall = start + timedelta(hours=hours[1] - hours[0])
                if wall != end:
                    self.assertFalse(check(start, wall), 'wall clock length is not the window')

    def test_event_booking_across_the_whole_day_is_23_or_25_hours(self):
        for case, hours_long in (('berlin_spring', 23), ('new_york_spring', 23),
                                 ('berlin_autumn', 25), ('new_york_autumn', 25)):
            start, end = (utc(value) for value in WINDOW_UTC[(case, (0, 24))])
            appointment_type = self._typed(case, [(0, 24)])
            with self.subTest(case=case):
                self.assertEqual(end - start, timedelta(hours=hours_long))
                self.assertTrue(appointment_type._interval_in_availability(start, end))
                self.assertFalse(appointment_type._interval_in_availability(start, start + timedelta(hours=24)),
                                 'a day is not always 24 hours')

    def test_scheduled_interval_may_sit_anywhere_inside_the_window(self):
        appointment_type = self._typed('berlin_spring', [(0, 6)], scheduled=True)
        check = appointment_type._interval_in_availability
        # window: 2026-03-28 23:00Z - 2026-03-29 04:00Z
        self.assertTrue(check(utc('2026-03-29 00:00:00'), utc('2026-03-29 01:00:00')),
                        '01:00 CET - 03:00 CEST: ends exactly where the gap starts')
        self.assertTrue(check(utc('2026-03-29 03:00:00'), utc('2026-03-29 04:00:00')))
        self.assertFalse(check(utc('2026-03-29 03:30:00'), utc('2026-03-29 04:30:00')))
        self.assertFalse(check(utc('2026-03-28 22:30:00'), utc('2026-03-28 23:30:00')))


# ---------------------------------------------------------------------------
# Slot lists (controller level, no HTTP)
# ---------------------------------------------------------------------------

#: scheduled, window 0-6, 1 hour slots every hour: (start, end, start_time, end_time)
HOURLY_SLOTS = {
    'berlin_spring': [      # no 02:xx; the 01:00 slot is the real hour before the gap
        ('2026-03-28 23:00:00', '2026-03-29 00:00:00', '00:00', '01:00'),
        ('2026-03-29 00:00:00', '2026-03-29 01:00:00', '01:00', '03:00'),
        ('2026-03-29 01:00:00', '2026-03-29 02:00:00', '03:00', '04:00'),
        ('2026-03-29 02:00:00', '2026-03-29 03:00:00', '04:00', '05:00'),
        ('2026-03-29 03:00:00', '2026-03-29 04:00:00', '05:00', '06:00'),
    ],
    'berlin_autumn': [      # 02:00 is the second one (CET); the first 02:xx hour has no slot
        ('2026-10-24 22:00:00', '2026-10-24 23:00:00', '00:00', '01:00'),
        ('2026-10-24 23:00:00', '2026-10-25 00:00:00', '01:00', '02:00'),
        ('2026-10-25 01:00:00', '2026-10-25 02:00:00', '02:00', '03:00'),
        ('2026-10-25 02:00:00', '2026-10-25 03:00:00', '03:00', '04:00'),
        ('2026-10-25 03:00:00', '2026-10-25 04:00:00', '04:00', '05:00'),
        ('2026-10-25 04:00:00', '2026-10-25 05:00:00', '05:00', '06:00'),
    ],
    'new_york_spring': [
        ('2026-03-08 05:00:00', '2026-03-08 06:00:00', '00:00', '01:00'),
        ('2026-03-08 06:00:00', '2026-03-08 07:00:00', '01:00', '03:00'),
        ('2026-03-08 07:00:00', '2026-03-08 08:00:00', '03:00', '04:00'),
        ('2026-03-08 08:00:00', '2026-03-08 09:00:00', '04:00', '05:00'),
        ('2026-03-08 09:00:00', '2026-03-08 10:00:00', '05:00', '06:00'),
    ],
    'new_york_autumn': [    # 01:00 is the second one (EST); the first 01:xx hour has no slot
        ('2026-11-01 04:00:00', '2026-11-01 05:00:00', '00:00', '01:00'),
        ('2026-11-01 06:00:00', '2026-11-01 07:00:00', '01:00', '02:00'),
        ('2026-11-01 07:00:00', '2026-11-01 08:00:00', '02:00', '03:00'),
        ('2026-11-01 08:00:00', '2026-11-01 09:00:00', '03:00', '04:00'),
        ('2026-11-01 09:00:00', '2026-11-01 10:00:00', '04:00', '05:00'),
        ('2026-11-01 10:00:00', '2026-11-01 11:00:00', '05:00', '06:00'),
    ],
}

#: scheduled, window 0-6, 2 hour slots every hour
TWO_HOUR_SLOTS = {
    'berlin_spring': [
        ('2026-03-28 23:00:00', '2026-03-29 01:00:00', '00:00', '03:00'),
        ('2026-03-29 00:00:00', '2026-03-29 02:00:00', '01:00', '04:00'),
        ('2026-03-29 01:00:00', '2026-03-29 03:00:00', '03:00', '05:00'),
        ('2026-03-29 02:00:00', '2026-03-29 04:00:00', '04:00', '06:00'),
    ],
    'new_york_autumn': [
        ('2026-11-01 04:00:00', '2026-11-01 06:00:00', '00:00', '01:00'),
        ('2026-11-01 06:00:00', '2026-11-01 08:00:00', '01:00', '03:00'),
        ('2026-11-01 07:00:00', '2026-11-01 09:00:00', '02:00', '04:00'),
        ('2026-11-01 08:00:00', '2026-11-01 10:00:00', '03:00', '05:00'),
        ('2026-11-01 09:00:00', '2026-11-01 11:00:00', '04:00', '06:00'),
    ],
}


@tagged('post_install', '-at_install')
class TestDstSlotLists(DstCommon, TransactionCase):
    """The slot lists the booking page shows, on the days the clocks change."""

    def _slots(self, appointment_type, case):
        day = CHANGE_DAYS_ALL[case][1]
        with self._frozen(case), MockRequest(self.env):
            controller = AppointmentController()
            make = controller._get_scheduled_slots if appointment_type.is_scheduled else controller._get_event_slots
            return make(appointment_type, day, None, None)['slots']

    @staticmethod
    def _rows(slots):
        return [(slot['start'], slot['end'], slot['start_time'], slot['end_time']) for slot in slots]

    def test_hourly_grid_on_the_change_days(self):
        for case, expected in HOURLY_SLOTS.items():
            appointment_type = self._typed(case, [(0, 6)], scheduled=True)
            with self.subTest(case=case):
                self.assertEqual(self._rows(self._slots(appointment_type, case)), expected)

    def test_two_hour_slots_that_straddle_the_change_are_two_real_hours(self):
        for case, expected in TWO_HOUR_SLOTS.items():
            appointment_type = self._typed(case, [(0, 6)], scheduled=True, slot_duration=2.0, slot_interval=1.0)
            with self.subTest(case=case):
                rows = self._rows(self._slots(appointment_type, case))
                self.assertEqual(rows, expected)
                for start, end, _start_time, _end_time in rows:
                    self.assertEqual(utc(end) - utc(start), timedelta(hours=2),
                                     'what the booking form stores: start + slot_duration')

    def test_a_slot_longer_than_the_real_window_is_not_offered(self):
        # 00:00-03:00 is only 2 real hours on the day the clocks go forward.
        for case in ('berlin_spring', 'new_york_spring'):
            appointment_type = self._typed(case, [(0, 3)], scheduled=True, slot_duration=3.0, slot_interval=1.0)
            with self.subTest(case=case):
                self.assertEqual(self._slots(appointment_type, case), [])
        # ... and exactly fits the 4 real hours of the day the clocks go back.
        appointment_type = self._typed('berlin_autumn', [(0, 3)], scheduled=True, slot_duration=3.0, slot_interval=1.0)
        self.assertEqual(self._rows(self._slots(appointment_type, 'berlin_autumn')), [
            ('2026-10-24 22:00:00', '2026-10-25 01:00:00', '00:00', '02:00'),
            ('2026-10-24 23:00:00', '2026-10-25 02:00:00', '01:00', '03:00'),
        ])

    def test_windows_with_an_edge_in_the_gap_offer_nothing(self):
        # Neither the slot list nor the booking form takes a window whose start
        # or end is a wall time that never happens; they must agree.
        for case, hours in (('berlin_spring', (2, 5)), ('berlin_spring', (0, 2.5)), ('new_york_spring', (2, 5)),
                            ('new_york_spring', (1, 2.5))):
            appointment_type = self._typed(case, [hours], scheduled=True)
            day = CHANGE_DAYS_ALL[case][1]
            with self.subTest(case=case, hours=hours):
                self.assertEqual(self._slots(appointment_type, case), [])
                self.assertEqual(appointment_type._get_availability_windows(day), [])

    def test_a_booking_in_the_repeated_hour_does_not_hide_its_neighbours(self):
        # The hour that happens twice has no slot of its own (it is the standard
        # time one that is offered). A staff booking placed in the first of the
        # two hours touches the slot before it and the one after it, it does
        # not overlap them: both stay on offer, so the whole grid is listed.
        for case, booking_start in (('berlin_autumn', '2026-10-25 00:00:00'),
                                    ('new_york_autumn', '2026-11-01 05:00:00')):
            staff = self._user('DST Staff', 'dst_staff_slots_%s' % case)
            appointment_type = self._typed(case, [(0, 6)], scheduled=True, assign_staff=True,
                                           staff_user_ids=[(6, 0, staff.ids)])
            self._booking(appointment_type, utc(booking_start), staff_user_id=staff.id)
            day = CHANGE_DAYS_ALL[case][1]
            with self.subTest(case=case), self._frozen(case), MockRequest(self.env):
                slots = AppointmentController()._get_scheduled_slots(appointment_type, day, None, staff.id)['slots']
                self.assertEqual([slot['start'] for slot in slots],
                                 [row[0] for row in HOURLY_SLOTS[case]])

    def test_a_booking_inside_a_slot_removes_exactly_that_slot_on_the_change_day(self):
        for case, booking_start, removed in (('berlin_spring', '2026-03-29 01:00:00', '2026-03-29 01:00:00'),
                                             ('new_york_autumn', '2026-11-01 07:00:00', '2026-11-01 07:00:00')):
            staff = self._user('DST Staff', 'dst_staff_busy_%s' % case)
            appointment_type = self._typed(case, [(0, 6)], scheduled=True, assign_staff=True,
                                           staff_user_ids=[(6, 0, staff.ids)])
            self._booking(appointment_type, utc(booking_start), staff_user_id=staff.id)
            day = CHANGE_DAYS_ALL[case][1]
            with self.subTest(case=case), self._frozen(case), MockRequest(self.env):
                slots = AppointmentController()._get_scheduled_slots(appointment_type, day, None, staff.id)['slots']
                self.assertEqual([slot['start'] for slot in slots],
                                 [row[0] for row in HOURLY_SLOTS[case] if row[0] != removed])

    def test_event_slots_are_the_windows_the_booking_form_accepts(self):
        hours = [(1, 4), (10, 12), (20, 24), (2.5, 4), (0, 6), (0, 24)]
        for case in CHANGE_DAYS_ALL:
            appointment_type = self._typed(case, hours)
            day = CHANGE_DAYS_ALL[case][1]
            slots = self._slots(appointment_type, case)
            windows = {(start.strftime(FMT), end.strftime(FMT))
                       for start, end, _avail in appointment_type._get_availability_windows(day)}
            with self.subTest(case=case):
                self.assertEqual({(slot['start'], slot['end']) for slot in slots}, windows)
                self.assertEqual(len(slots), len(windows))
                for slot in slots:
                    self.assertTrue(appointment_type._interval_in_availability(utc(slot['start']), utc(slot['end'])))

    def test_event_slots_on_the_change_days(self):
        expected = {
            'berlin_spring': [('2026-03-29 00:00:00', '2026-03-29 02:00:00', '01:00', '04:00'),
                              ('2026-03-29 08:00:00', '2026-03-29 10:00:00', '10:00', '12:00'),
                              ('2026-03-29 18:00:00', '2026-03-29 22:00:00', '20:00', '00:00')],
            'berlin_autumn': [('2026-10-24 23:00:00', '2026-10-25 03:00:00', '01:00', '04:00'),
                              ('2026-10-25 01:30:00', '2026-10-25 03:00:00', '02:30', '04:00'),
                              ('2026-10-25 09:00:00', '2026-10-25 11:00:00', '10:00', '12:00'),
                              ('2026-10-25 19:00:00', '2026-10-25 23:00:00', '20:00', '00:00')],
            'new_york_spring': [('2026-03-08 06:00:00', '2026-03-08 08:00:00', '01:00', '04:00'),
                                ('2026-03-08 14:00:00', '2026-03-08 16:00:00', '10:00', '12:00'),
                                ('2026-03-09 00:00:00', '2026-03-09 04:00:00', '20:00', '00:00')],
            'new_york_autumn': [('2026-11-01 06:00:00', '2026-11-01 09:00:00', '01:00', '04:00'),
                                ('2026-11-01 07:30:00', '2026-11-01 09:00:00', '02:30', '04:00'),
                                ('2026-11-01 15:00:00', '2026-11-01 17:00:00', '10:00', '12:00'),
                                ('2026-11-02 01:00:00', '2026-11-02 05:00:00', '20:00', '00:00')],
        }
        for case, rows in expected.items():
            appointment_type = self._typed(case, [(1, 4), (10, 12), (20, 24), (2.5, 4)])
            with self.subTest(case=case):
                self.assertEqual(self._rows(self._slots(appointment_type, case)), rows)


def _oracle_slots(zone, day, hour_from, hour_to, duration, interval):
    """The slots a window should give, worked out with zoneinfo: walk the
    wall clock from the window start in steps of ``interval`` hours, skip wall
    times that never happen, let ambiguous ones mean standard time (the
    second occurrence), and keep a slot only if ``duration`` real hours from
    its start still end inside the window."""
    tz = ZoneInfo(zone)
    utc_tz = ZoneInfo('UTC')

    def at(wall):
        aware = wall.replace(tzinfo=tz, fold=1)
        back = aware.astimezone(utc_tz).astimezone(tz).replace(tzinfo=None)
        return aware.astimezone(utc_tz).replace(tzinfo=None) if back == wall else None

    midnight = datetime(day.year, day.month, day.day)
    first = midnight + timedelta(hours=hour_from)
    last = midnight + timedelta(hours=hour_to)
    window_start, window_end = at(first), at(last)
    if window_start is None or window_end is None:
        return []
    slots = []
    wall = first
    while wall < last:
        start = at(wall)
        if start is not None and start + timedelta(hours=duration) <= window_end:
            slots.append((start, start + timedelta(hours=duration)))
        wall += timedelta(hours=interval)
    return slots


@tagged('post_install', '-at_install')
class TestDstSlotGridSweep(DstCommon, TransactionCase):
    """Every window / duration / interval on the change days, against an
    independent oracle and against the rule the booking form applies."""

    WINDOWS = [(0, 6), (1, 4), (2, 5), (0, 3), (1, 2.5), (22, 24), (0, 24), (8, 17)]
    SHAPES = [(1.0, 1.0), (1.5, 0.5), (2.0, 1.0), (3.0, 1.0), (0.5, 0.5)]

    def setUp(self):
        super().setUp()
        if ZoneInfo is None:
            self.skipTest('zoneinfo not available')

    def test_slot_grid_matches_the_oracle_and_the_booking_check(self):
        controller = AppointmentController()
        for case, (zone, day, _now) in CHANGE_DAYS_ALL.items():
            appointment_type = self._typed(case, [(0, 6)], scheduled=True)
            for hours in self.WINDOWS:
                self._set_windows(appointment_type, [(hours[0], hours[1], {})])
                for duration, interval in self.SHAPES:
                    appointment_type.write({'slot_duration': duration, 'slot_interval': interval})
                    with self.subTest(case=case, hours=hours, duration=duration, interval=interval):
                        try:
                            expected = _oracle_slots(zone, day, hours[0], hours[1], duration, interval)
                        except ZoneInfoNotFoundError:
                            self.skipTest('tz database not available')
                        with self._frozen(case), MockRequest(self.env):
                            slots = controller._get_scheduled_slots(appointment_type, day, None, None)['slots']
                        self.assertEqual([(utc(s['start']), utc(s['end'])) for s in slots], expected)
                        for slot in slots:
                            start, end = utc(slot['start']), utc(slot['end'])
                            self.assertEqual(end - start, timedelta(hours=duration))
                            self.assertTrue(appointment_type._interval_in_availability(start, end),
                                            'offered, so the booking form must take it')


# ---------------------------------------------------------------------------
# End to end: the booking form on the change days
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestDstBookingForm(DstCommon, RulesHttpCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.host = self._user('DST Host', 'dst_host_rules')

    def _event_type(self, case, windows):
        return self._typed(case, windows, assign_staff=True, staff_user_ids=[(6, 0, self.host.ids)])

    def _frozen(self, case):
        # CSRF tokens expire: ask for a fresh one at the frozen moment.
        self._csrf_token = None
        return super()._frozen(case)

    def _slots_of(self, appointment_type, case):
        return self._slots(appointment_type, CHANGE_DAYS_ALL[case][1])['slots']

    def test_event_window_is_booked_exactly_across_the_change(self):
        for case, hours in (('berlin_autumn', (0, 24)), ('berlin_spring', (1, 4)), ('new_york_spring', (20, 24)),
                            ('new_york_autumn', (1, 4))):
            appointment_type = self._event_type(case, [hours])
            start, end = (utc(value) for value in WINDOW_UTC[(case, hours)])
            with self.subTest(case=case, hours=hours), self._frozen(case):
                slots = self._slots_of(appointment_type, case)
                self.assertEqual([(s['start'], s['end']) for s in slots],
                                 [(start.strftime(FMT), end.strftime(FMT))],
                                 'the slot list offers the window')
                response = self._post(appointment_type, start, end, guest_email='%s@example.com' % case)
                self.assertNotIn('outside available hours', response.text)
                booking = self._bookings(appointment_type)
                self.assertEqual((booking.start_datetime, booking.end_datetime, booking.state),
                                 (start, end, 'confirmed'))

    def test_event_booking_with_the_wall_clock_length_is_refused(self):
        for case, hours in (('berlin_autumn', (0, 24)), ('berlin_spring', (0, 24)), ('berlin_spring', (1, 4)),
                            ('berlin_autumn', (1, 4)), ('new_york_autumn', (0, 6))):
            appointment_type = self._event_type(case, [hours])
            start, end = (utc(value) for value in WINDOW_UTC[(case, hours)])
            wall_end = start + timedelta(hours=hours[1] - hours[0])
            self.assertNotEqual(wall_end, end)
            with self.subTest(case=case, hours=hours), self._frozen(case):
                response = self._post(appointment_type, start, wall_end, guest_email='%s@example.com' % case)
                self.assertIn('outside available hours', response.text)
                self.assertFalse(self._bookings(appointment_type))

    def test_event_booking_that_cuts_the_window_is_refused(self):
        for case, hours in (('berlin_spring', (20, 24)), ('new_york_autumn', (10, 12)), ('berlin_autumn', (10, 12))):
            appointment_type = self._event_type(case, [hours])
            start, end = (utc(value) for value in WINDOW_UTC[(case, hours)])
            with self.subTest(case=case, hours=hours), self._frozen(case):
                for short_end in (end - timedelta(hours=1), end - timedelta(minutes=1)):
                    response = self._post(appointment_type, start, short_end, guest_email='%s@example.com' % case)
                    self.assertIn('outside available hours', response.text)
                self.assertFalse(self._bookings(appointment_type))

    def test_event_window_in_the_gap_is_neither_offered_nor_booked(self):
        # The window would start or end at a wall time that never happens. A
        # request for the nearest real instants (as if the window were
        # clipped to the gap) is not a window either.
        for case, hours, start, end in (
                ('berlin_spring', (2.5, 4), '2026-03-29 01:00:00', '2026-03-29 02:00:00'),
                ('new_york_spring', (2, 5), '2026-03-08 07:00:00', '2026-03-08 09:00:00')):
            appointment_type = self._event_type(case, [hours])
            with self.subTest(case=case, hours=hours), self._frozen(case):
                self.assertEqual(self._slots_of(appointment_type, case), [])
                response = self._post(appointment_type, utc(start), utc(end), guest_email='%s@example.com' % case)
                self.assertTrue('outside available hours' in response.text or 'No availability' in response.text)
                self.assertFalse(self._bookings(appointment_type))

    def test_every_scheduled_slot_that_is_offered_can_be_booked(self):
        for case, duration in (('berlin_spring', 2.0), ('new_york_autumn', 2.0), ('berlin_autumn', 1.0)):
            appointment_type = self._typed(case, [(0, 6)], scheduled=True, slot_duration=duration, slot_interval=1.0)
            with self.subTest(case=case), self._frozen(case):
                slots = self._slots_of(appointment_type, case)
                self.assertTrue(slots)
                for index, slot in enumerate(slots):
                    response = self._post(appointment_type, utc(slot['start']),
                                          guest_email='%s%d@example.com' % (case, index))
                    self.assertNotIn('outside available hours', response.text, slot)
                    self.assertNotIn('No availability', response.text, slot)
                bookings = self._bookings(appointment_type).sorted('start_datetime')
                self.assertEqual([(b.start_datetime.strftime(FMT), b.end_datetime.strftime(FMT)) for b in bookings],
                                 [(slot['start'], slot['end']) for slot in slots],
                                 'a booking ends where the slot list said the slot ends')
