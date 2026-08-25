# -*- coding: utf-8 -*-
"""Pure timezone helpers for the UTC storage contract (18.0.3.0.0).

This module deliberately imports nothing from Odoo so that the arithmetic at
the heart of the UTC refactor can be unit-tested without a running server
(see tests/test_timezone_pure.py).

Storage contract
----------------
``appointment.booking.start_datetime`` / ``end_datetime`` are **naive
datetimes expressed in UTC**, the Odoo convention.

Configuration, by contrast, is authored in local wall time:

* ``appointment.availability.hour_from`` / ``hour_to`` are wall-clock hours in
  ``appointment_type.timezone``;
* the date a visitor picks in the calendar widget is a local date.

Every conversion between those two worlds goes through the functions below.
Rule of thumb used across the module: iterate and compare *wall clock* values
in local time, then convert to UTC right before touching the ORM.
"""

from datetime import datetime, timedelta

import pytz

__all__ = [
    'get_tz',
    'local_to_utc',
    'utc_to_local',
    'today_local',
    'hour_to_local_dt',
    'local_month_bounds_utc',
]


def get_tz(tz_name):
    """Return a pytz timezone, falling back to UTC for empty/unknown names."""
    try:
        return pytz.timezone(tz_name or 'UTC')
    except pytz.UnknownTimeZoneError:
        return pytz.UTC


def local_to_utc(tz, naive_local):
    """Naive local wall time -> naive UTC (the value stored in the DB).

    Uses ``tz.localize()`` rather than ``.replace(tzinfo=tz)``: a pytz zone
    object carries its *earliest* historical offset until it is localized, so
    ``.replace(tzinfo=pytz.timezone('Asia/Taipei'))`` yields LMT +08:06 and
    silently shifts every value by six minutes. ``localize()`` also resolves
    the correct DST offset for the date in question.
    """
    if naive_local is None:
        return None
    return tz.localize(naive_local).astimezone(pytz.utc).replace(tzinfo=None)


def utc_to_local(tz, naive_utc):
    """Naive UTC (as stored in the DB) -> naive local wall time."""
    if naive_utc is None:
        return None
    return pytz.utc.localize(naive_utc).astimezone(tz).replace(tzinfo=None)


def today_local(tz):
    """Today's date in ``tz``.

    ``fields.Date.context_today()`` is unreliable on the frontend: the public
    user has no timezone set, so it silently falls back to the UTC date.
    """
    return datetime.now(tz).date()


def hour_to_local_dt(day_start_local, hour_float):
    """Turn an availability Float hour into a naive local datetime.

    Adding a timedelta (rather than calling ``.replace(hour=...)``) keeps
    ``hour_to == 24.0`` expressible: it becomes midnight of the next day,
    which ``.replace(hour=24)`` cannot represent at all.
    """
    hours = int(hour_float)
    minutes = int(round((hour_float % 1) * 60))
    return day_start_local + timedelta(hours=hours, minutes=minutes)


def local_month_bounds_utc(tz, naive_utc):
    """``[start, end)`` UTC bounds of the *local* calendar month containing
    ``naive_utc``.

    Used for the "fewest bookings this month" balancing: a UTC month edge
    would put the first/last hours of a month in the wrong bucket.
    """
    local_start = utc_to_local(tz, naive_utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)
    if local_start.month == 12:
        local_end = local_start.replace(year=local_start.year + 1, month=1)
    else:
        local_end = local_start.replace(month=local_start.month + 1)
    return local_to_utc(tz, local_start), local_to_utc(tz, local_end)
