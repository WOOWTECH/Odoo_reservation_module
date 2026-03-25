# -*- coding: utf-8 -*-
"""Shared fixtures and helpers for Playwright test suite."""

import sys
import os
import datetime
import xmlrpc.client
import json
import traceback

# Add test_suite_pw to path
sys.path.insert(0, os.path.dirname(__file__))

from config import URL, DB, ADMIN_UID, ADMIN_PWD, XMLRPC_OBJECT

# ── XML-RPC helpers ──────────────────────────────────────────────────

_models = xmlrpc.client.ServerProxy(XMLRPC_OBJECT)


def call(model, method, args, kwargs=None):
    """XML-RPC call to Odoo."""
    return _models.execute_kw(DB, ADMIN_UID, ADMIN_PWD, model, method, args, kwargs or {})


def search_read(model, domain, fields, **kw):
    """Shortcut for search_read."""
    return call(model, 'search_read', [domain], {'fields': fields, **kw})


def read_booking(booking_id, fields=None):
    """Read a booking by ID."""
    default_fields = [
        'name', 'state', 'guest_name', 'guest_email', 'guest_phone',
        'guest_count', 'start_datetime', 'end_datetime', 'duration',
        'partner_id', 'calendar_event_id', 'access_token',
        'appointment_type_id', 'staff_user_id', 'resource_id',
        'payment_status', 'payment_amount', 'payment_transaction_id',
        'notes',
    ]
    result = call('appointment.booking', 'read', [[booking_id]], {'fields': fields or default_fields})
    return result[0] if result else None


def find_bookings_by_email(email, limit=10):
    """Find bookings by guest email."""
    return search_read(
        'appointment.booking',
        [('guest_email', '=', email)],
        ['id', 'name', 'state', 'guest_name', 'access_token', 'appointment_type_id',
         'start_datetime', 'partner_id', 'calendar_event_id', 'staff_user_id', 'resource_id'],
        order='id desc', limit=limit,
    )


def delete_booking(booking_id):
    """Delete a booking (reset state first if needed)."""
    try:
        bk = call('appointment.booking', 'read', [[booking_id]], {'fields': ['state']})
        if bk and bk[0]['state'] in ('confirmed', 'done'):
            call('appointment.booking', 'write', [[booking_id], {'state': 'cancelled'}])
        call('appointment.booking', 'unlink', [[booking_id]])
    except Exception:
        try:
            call('appointment.booking', 'write', [[booking_id], {'state': 'draft'}])
            call('appointment.booking', 'unlink', [[booking_id]])
        except Exception:
            pass


def cleanup_test_bookings(email='pw_e2e_test@example.com'):
    """Delete all bookings with the test email."""
    bookings = search_read('appointment.booking', [('guest_email', '=', email)], ['id'])
    for bk in bookings:
        delete_booking(bk['id'])


# ── Date/Time helpers ────────────────────────────────────────────────

def get_future_weekday(days_ahead=3):
    """Get a future date that's a weekday (Mon-Fri)."""
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return d


def get_future_saturday(days_ahead=7):
    """Get a future Saturday (for restaurant evening testing)."""
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    while d.weekday() != 5:
        d += datetime.timedelta(days=1)
    return d


def make_start_datetime(date_obj, hour=10, minute=0):
    """Create a start_datetime string."""
    return f"{date_obj} {hour:02d}:{minute:02d}:00"


# ── Playwright helpers ───────────────────────────────────────────────

def fill_booking_form(page, guest_name, guest_email, guest_phone='', guest_count=1, notes=''):
    """Fill the booking form fields."""
    page.fill('input[name=guest_name]', guest_name)
    page.fill('input[name=guest_email]', guest_email)
    if guest_phone:
        page.fill('input[name=guest_phone]', guest_phone)
    if guest_count != 1:
        page.fill('input[name=guest_count]', str(guest_count))
    if notes:
        page.fill('textarea[name=notes]', notes)


def submit_booking_form(page, timeout=15000):
    """Click the submit button and wait for navigation."""
    btn = page.locator('button[type=submit].btn-primary.btn-lg')
    btn.click()
    page.wait_for_load_state('networkidle', timeout=timeout)


def goto_book_page(page, type_id, start_datetime, staff_id=None, resource_id=None):
    """Navigate to the booking form with params."""
    params = f'start_datetime={start_datetime}'
    if staff_id:
        params += f'&staff_id={staff_id}'
    if resource_id:
        params += f'&resource_id={resource_id}'
    page.goto(f'{URL}/appointment/{type_id}/book?{params}')
    page.wait_for_load_state('networkidle')


# ── Test result tracking ─────────────────────────────────────────────

_results = []


def test(test_id, name, passed, detail='', severity='MEDIUM'):
    """Record a test result."""
    _results.append({
        'id': test_id,
        'name': name,
        'passed': passed,
        'detail': detail,
        'severity': severity,
    })
    status = 'PASS' if passed else 'FAIL'
    print(f'  [{status}] {test_id}: {name} - {detail}')
    return passed


def get_results():
    """Return all results."""
    return _results


def clear_results():
    """Clear results for a new module run."""
    _results.clear()


def take_failure_screenshot(page, test_id):
    """Take a screenshot on failure."""
    safe_id = test_id.replace('.', '_').replace('-', '_')
    path = os.path.join(os.path.dirname(__file__), 'screenshots', f'{safe_id}.png')
    try:
        page.screenshot(path=path)
    except Exception:
        pass
    return path
