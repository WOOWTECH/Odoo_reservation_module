# -*- coding: utf-8 -*-
"""Shared test helpers and framework"""

import xmlrpc.client
import requests
import json
import time
import sys
from datetime import datetime, timedelta
from config import URL, DB, ADMIN_UID, ADMIN_PWD, XMLRPC_OBJECT

MODELS = xmlrpc.client.ServerProxy(XMLRPC_OBJECT)

# ---- Result tracking ----
_results = []
_cleanup_ids = []  # (model, id) tuples for cleanup


def call(model, method, args, kwargs=None):
    """Call Odoo XML-RPC method"""
    if kwargs:
        return MODELS.execute_kw(DB, ADMIN_UID, ADMIN_PWD, model, method, args, kwargs)
    return MODELS.execute_kw(DB, ADMIN_UID, ADMIN_PWD, model, method, args)


def jsonrpc(path, params):
    """Call Odoo JSON-RPC endpoint"""
    resp = requests.post(
        f"{URL}{path}",
        json={'jsonrpc': '2.0', 'method': 'call', 'params': params, 'id': 1},
        headers={'Content-Type': 'application/json'},
        timeout=30,
    )
    return resp


def http_get(path, **kwargs):
    """HTTP GET request"""
    return requests.get(f"{URL}{path}", timeout=30, **kwargs)


def http_post(path, data=None, json_data=None, session=None, **kwargs):
    """HTTP POST request"""
    s = session or requests.Session()
    if json_data:
        return s.post(f"{URL}{path}", json=json_data, timeout=30, **kwargs)
    return s.post(f"{URL}{path}", data=data, timeout=30, **kwargs)


def test(test_id, name, passed, detail="", severity="MEDIUM"):
    """Record a test result"""
    status = "PASS" if passed else "FAIL"
    _results.append({
        'id': test_id,
        'name': name,
        'status': status,
        'detail': detail,
        'severity': severity,
    })
    icon = "  [PASS]" if passed else "  [FAIL]"
    print(f"{icon} {test_id}: {name}" + (f" - {detail}" if detail else ""))
    return passed


def create_booking(apt_type_id, days_ahead=3, hour=10, duration_hours=1.0,
                   guest_name='Test Guest', guest_email='test@test.com',
                   guest_count=1, resource_id=None, staff_id=None, **extra):
    """Helper to create a test booking"""
    start = (datetime.now() + timedelta(days=days_ahead)).replace(
        hour=hour, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=duration_hours)
    vals = {
        'appointment_type_id': apt_type_id,
        'guest_name': guest_name,
        'guest_email': guest_email,
        'guest_count': guest_count,
        'start_datetime': start.strftime('%Y-%m-%d %H:%M:%S'),
        'end_datetime': end.strftime('%Y-%m-%d %H:%M:%S'),
    }
    if resource_id:
        vals['resource_id'] = resource_id
    if staff_id:
        vals['staff_user_id'] = staff_id
    vals.update(extra)
    bid = call('appointment.booking', 'create', [vals])
    _cleanup_ids.append(('appointment.booking', bid))
    return bid, start, end


def cleanup():
    """Delete all test-created records"""
    global _cleanup_ids
    for model, rec_id in reversed(_cleanup_ids):
        try:
            # Reset to draft first if it's a booking
            if model == 'appointment.booking':
                booking = call(model, 'read', [rec_id], {'fields': ['state']})
                if booking and booking[0]['state'] in ('confirmed', 'done'):
                    try:
                        call(model, 'action_draft', [rec_id])
                    except Exception:
                        pass
                elif booking and booking[0]['state'] == 'cancelled':
                    try:
                        call(model, 'action_draft', [rec_id])
                    except Exception:
                        pass
            call(model, 'unlink', [[rec_id]])
        except Exception:
            pass
    _cleanup_ids = []


def get_results():
    """Return all test results"""
    return _results


def reset_results():
    """Reset results for a new test module"""
    global _results
    _results = []


def print_summary(module_name=""):
    """Print test summary"""
    passed = sum(1 for r in _results if r['status'] == 'PASS')
    failed = sum(1 for r in _results if r['status'] == 'FAIL')
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"  {module_name} RESULTS: {passed}/{total} PASS, {failed}/{total} FAIL")
    print(f"{'=' * 60}")
    if failed:
        print("\n  FAILURES:")
        for r in _results:
            if r['status'] == 'FAIL':
                print(f"    [{r['severity']}] {r['id']}: {r['name']} - {r['detail']}")
    return passed, failed, total


def future_date_str(days=3):
    """Get a future date string in YYYY-MM-DD format"""
    return (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')


def future_datetime_str(days=3, hour=10):
    """Get a future datetime string"""
    dt = (datetime.now() + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0)
    return dt.strftime('%Y-%m-%d %H:%M:%S')
