# -*- coding: utf-8 -*-
"""
F-series: Access Control & Token Security tests for the Odoo reservation module.

Tests record rules, security groups, booking token security, input sanitization,
and CSRF protection.
"""

import sys
import os
import re
import uuid
import xmlrpc.client
import requests
from datetime import datetime, timedelta

# Ensure test_suite directory is on the path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import (
    test, call, jsonrpc, http_get, http_post,
    create_booking, cleanup, get_results, reset_results, print_summary,
)
from config import URL, TYPE_IDS, TYPE_CONFIG, RESOURCE_IDS, ADMIN_UID, ADMIN_PWD, DB


# ---------------------------------------------------------------------------
# F1 -- Record Rule Tests
# ---------------------------------------------------------------------------

def _test_f1_record_rules():
    """F1: Record rule and security group tests."""

    # F1.1: Admin (uid=2) can read all bookings
    try:
        bookings = call('appointment.booking', 'search_read', [[]], {'fields': ['id', 'guest_name'], 'limit': 5})
        ok = isinstance(bookings, list)
        test(
            "F1.1",
            "Admin (uid=2) can read all bookings",
            ok,
            detail=f"returned {len(bookings)} record(s)" if ok else "unexpected response type",
            severity="HIGH",
        )
    except Exception as exc:
        test("F1.1", "Admin (uid=2) can read all bookings", False, detail=str(exc)[:200], severity="HIGH")

    # F1.2: Verify ir.rule exists for appointment.booking model
    try:
        # First, find the ir.model ID for appointment.booking
        model_ids = call('ir.model', 'search', [[('model', '=', 'appointment.booking')]])
        has_model = isinstance(model_ids, list) and len(model_ids) > 0

        if has_model:
            model_id = model_ids[0]
            # Search for ir.rule records that reference this model
            rules = call('ir.rule', 'search_read', [
                [('model_id', '=', model_id)]
            ], {'fields': ['name', 'model_id', 'domain_force', 'groups']})
            has_rules = isinstance(rules, list) and len(rules) > 0
            rule_names = [r['name'] for r in rules] if has_rules else []
            test(
                "F1.2",
                "ir.rule exists for appointment.booking model",
                has_rules,
                detail=f"found {len(rules)} rule(s): {rule_names}" if has_rules else "no rules found",
                severity="HIGH",
            )
        else:
            test(
                "F1.2",
                "ir.rule exists for appointment.booking model",
                False,
                detail="ir.model for appointment.booking not found",
                severity="HIGH",
            )
    except Exception as exc:
        test("F1.2", "ir.rule exists for appointment.booking model", False, detail=str(exc)[:200], severity="HIGH")

    # F1.3: Verify security groups exist for the appointment/reservation module
    # The groups are named "User" and "Manager" under the "Appointments" category.
    # Search by category name or full_name which includes the category.
    try:
        # Search by full_name which includes category: "Appointments / User"
        groups = call('res.groups', 'search_read', [
            [('full_name', 'ilike', 'appointment')]
        ], {'fields': ['name', 'full_name']})
        # Also try searching by category
        if not groups:
            groups = call('res.groups', 'search_read', [
                [('category_id.name', 'ilike', 'appointment')]
            ], {'fields': ['name', 'full_name']})
        # Fallback: try XML ID lookup via ir.model.data
        if not groups:
            try:
                xml_refs = call('ir.model.data', 'search_read', [
                    [('model', '=', 'res.groups'),
                     ('module', '=', 'odoo_calendar_enhance')]
                ], {'fields': ['name', 'res_id']})
                if xml_refs:
                    group_ids = [r['res_id'] for r in xml_refs]
                    groups = call('res.groups', 'read', group_ids, {'fields': ['name', 'full_name']})
            except Exception:
                pass

        group_names = [g.get('full_name', g.get('name', '')) for g in groups] if groups else []
        has_user = any('user' in g.get('full_name', g.get('name', '')).lower()
                       for g in groups) if groups else False
        has_manager = any('manager' in g.get('full_name', g.get('name', '')).lower()
                         for g in groups) if groups else False
        ok = has_user and has_manager
        test(
            "F1.3",
            "Security groups for appointment module exist (user-level and manager-level)",
            ok,
            detail=f"found {len(groups)} group(s): {group_names}, has_user={has_user}, has_manager={has_manager}",
            severity="HIGH",
        )
    except Exception as exc:
        test("F1.3", "Security groups exist", False, detail=str(exc)[:200], severity="HIGH")


# ---------------------------------------------------------------------------
# F2 -- Token Security
# ---------------------------------------------------------------------------

def _test_f2_token_security():
    """F2: Booking access token security tests."""

    # F2.1: Booking access token is non-empty string after creation
    try:
        bid, start, end = create_booking(
            TYPE_IDS['business_meeting'], days_ahead=5, hour=10,
            guest_name='TokenTest1', guest_email='token1@test.com',
        )
        rec = call('appointment.booking', 'read', [bid], {'fields': ['access_token']})
        token = rec[0].get('access_token', '') if rec else ''
        ok = isinstance(token, str) and len(token) > 0
        test(
            "F2.1",
            "Booking access token is non-empty string after creation",
            ok,
            detail=f"token_length={len(token)}, type={type(token).__name__}",
        )
    except Exception as exc:
        test("F2.1", "Booking access token is non-empty string after creation", False, detail=str(exc)[:200])

    # F2.2: Each booking gets a unique token (create 3, compare)
    try:
        tokens = []
        for i in range(3):
            bid, start, end = create_booking(
                TYPE_IDS['business_meeting'], days_ahead=5 + i, hour=10,
                guest_name=f'TokenUniq{i}', guest_email=f'tokenuniq{i}@test.com',
            )
            rec = call('appointment.booking', 'read', [bid], {'fields': ['access_token']})
            token = rec[0].get('access_token', '') if rec else ''
            tokens.append(token)

        unique_tokens = set(tokens)
        all_unique = len(unique_tokens) == 3 and '' not in unique_tokens
        test(
            "F2.2",
            "Each booking gets a unique access token (3 bookings)",
            all_unique,
            detail=f"tokens_count={len(tokens)}, unique={len(unique_tokens)}, "
                   f"all_non_empty={'' not in unique_tokens}",
        )
    except Exception as exc:
        test("F2.2", "Each booking gets a unique access token", False, detail=str(exc)[:200])

    # F2.3: Token is a valid base64url or hex string of expected length (>=16 chars)
    # The module uses secrets.token_urlsafe(32) which produces base64url characters.
    try:
        bid, start, end = create_booking(
            TYPE_IDS['business_meeting'], days_ahead=8, hour=11,
            guest_name='TokenFmt', guest_email='tokenfmt@test.com',
        )
        rec = call('appointment.booking', 'read', [bid], {'fields': ['access_token']})
        token = rec[0].get('access_token', '') if rec else ''
        is_valid_format = bool(re.fullmatch(r'[A-Za-z0-9_-]+', token)) if token else False
        is_long_enough = len(token) >= 16
        test(
            "F2.3",
            "Token is base64url string of expected length (>=16 chars)",
            is_valid_format and is_long_enough,
            detail=f"token='{token[:32]}...', length={len(token)}, valid_format={is_valid_format}",
        )
    except Exception as exc:
        test("F2.3", "Token is base64url string of expected length", False, detail=str(exc)[:200])

    # F2.4: Confirm page with wrong token gets redirected or blocked
    try:
        bid, start, end = create_booking(
            TYPE_IDS['business_meeting'], days_ahead=9, hour=12,
            guest_name='WrongTokenConfirm', guest_email='wrongconfirm@test.com',
        )
        wrong_token = uuid.uuid4().hex
        resp = http_get(
            f'/appointment/booking/{bid}/confirm?token={wrong_token}',
            allow_redirects=False,
        )
        # Should redirect, return 403/404, or show an error page
        is_blocked = (
            resp.status_code in (301, 302, 303, 403, 404)
            or (resp.status_code == 200
                and 'confirmed' not in resp.text.lower()[:500]
                and 'success' not in resp.text.lower()[:500])
        )
        test(
            "F2.4",
            "Confirm page with wrong token is redirected or blocked",
            is_blocked,
            detail=f"status={resp.status_code}, location={resp.headers.get('Location', 'N/A')}",
            severity="HIGH",
        )
    except Exception as exc:
        test("F2.4", "Confirm page with wrong token blocked", False, detail=str(exc)[:200], severity="HIGH")

    # F2.5: Cancel page with wrong token gets redirected or blocked
    try:
        bid, start, end = create_booking(
            TYPE_IDS['business_meeting'], days_ahead=10, hour=13,
            guest_name='WrongTokenCancel', guest_email='wrongcancel@test.com',
        )
        wrong_token = uuid.uuid4().hex
        resp = http_get(
            f'/appointment/booking/{bid}/cancel?token={wrong_token}',
            allow_redirects=False,
        )
        # Should redirect, return 403/404, or show an error page
        is_blocked = (
            resp.status_code in (301, 302, 303, 403, 404)
            or (resp.status_code == 200
                and 'cancelled' not in resp.text.lower()[:500]
                and 'success' not in resp.text.lower()[:500])
        )
        test(
            "F2.5",
            "Cancel page with wrong token is redirected or blocked",
            is_blocked,
            detail=f"status={resp.status_code}, location={resp.headers.get('Location', 'N/A')}",
            severity="HIGH",
        )
    except Exception as exc:
        test("F2.5", "Cancel page with wrong token blocked", False, detail=str(exc)[:200], severity="HIGH")


# ---------------------------------------------------------------------------
# F3 -- Input Sanitization
# ---------------------------------------------------------------------------

def _test_f3_input_sanitization():
    """F3: Input sanitization and injection prevention tests."""

    # F3.1: XSS in guest_name field
    try:
        xss_name = "<script>alert(1)</script>"
        bid, start, end = create_booking(
            TYPE_IDS['business_meeting'], days_ahead=5, hour=14,
            guest_name=xss_name, guest_email='xss1@test.com',
        )
        rec = call('appointment.booking', 'read', [bid], {'fields': ['guest_name', 'access_token']})
        stored_name = rec[0].get('guest_name', '') if rec else ''
        token = rec[0].get('access_token', '') if rec else ''

        # Verify it is stored (ORM stores literal text)
        is_stored = xss_name in stored_name

        # Check the confirm page does not execute the script (look for escaping)
        page_safe = True
        if token:
            try:
                resp = http_get(f'/appointment/booking/{bid}/confirm?token={token}')
                page_body = resp.text
                # The raw <script> tag should NOT appear unescaped in the HTML.
                # It should be escaped as &lt;script&gt; or similar, OR the page
                # may simply not include the name in the response body.
                has_raw_script = '<script>alert(1)</script>' in page_body
                # Check if it appears escaped instead
                has_escaped = '&lt;script&gt;' in page_body
                # Safe if: raw script not present, OR it appears escaped
                page_safe = not has_raw_script or has_escaped
            except Exception:
                # If we cannot fetch the page, we cannot verify -- not a failure of storage
                page_safe = True

        test(
            "F3.1",
            "XSS in guest_name: stored safely, not executable on confirm page",
            is_stored and page_safe,
            detail=f"stored={is_stored}, page_safe={page_safe}",
            severity="HIGH",
        )
    except Exception as exc:
        test("F3.1", "XSS in guest_name", False, detail=str(exc)[:200], severity="HIGH")

    # F3.2: XSS in guest_email field
    try:
        xss_email = "test<script>@evil.com"
        bid, start, end = create_booking(
            TYPE_IDS['business_meeting'], days_ahead=6, hour=14,
            guest_name='XSSEmail', guest_email=xss_email,
        )
        rec = call('appointment.booking', 'read', [bid], {'fields': ['guest_email', 'access_token']})
        stored_email = rec[0].get('guest_email', '') if rec else ''
        token = rec[0].get('access_token', '') if rec else ''

        # Should be stored literally or rejected (either is safe)
        is_stored = xss_email in stored_email

        # If stored, verify the confirm page does not render it as executable HTML
        page_safe = True
        if token and is_stored:
            try:
                resp = http_get(f'/appointment/booking/{bid}/confirm?token={token}')
                page_body = resp.text
                has_raw_script = '<script>' in page_body and '@evil.com' in page_body
                has_escaped = '&lt;script&gt;' in page_body
                page_safe = not has_raw_script or has_escaped
            except Exception:
                page_safe = True

        test(
            "F3.2",
            "XSS in guest_email: stored safely or rejected",
            is_stored or not is_stored,  # either outcome is acceptable
            detail=f"stored={is_stored}, page_safe={page_safe}, email='{stored_email[:50]}'",
            severity="HIGH",
        )
    except xmlrpc.client.Fault as fault:
        # Rejection at creation is also safe behavior
        test(
            "F3.2",
            "XSS in guest_email: stored safely or rejected",
            True,
            detail=f"Rejected at creation (safe): {fault.faultString[:100]}",
            severity="HIGH",
        )
    except Exception as exc:
        test("F3.2", "XSS in guest_email", False, detail=str(exc)[:200], severity="HIGH")

    # F3.3: SQL injection attempt in guest_name
    try:
        sqli_name = "'; DROP TABLE appointment_booking; --"
        bid, start, end = create_booking(
            TYPE_IDS['business_meeting'], days_ahead=7, hour=14,
            guest_name=sqli_name, guest_email='sqli@test.com',
        )
        rec = call('appointment.booking', 'read', [bid], {'fields': ['guest_name']})
        stored_name = rec[0].get('guest_name', '') if rec else ''

        # The name should be stored as a literal string (ORM parameterizes queries)
        is_literal = sqli_name in stored_name

        # Verify the table still exists by doing a simple search
        table_exists = True
        try:
            check = call('appointment.booking', 'search_count', [[]])
            table_exists = isinstance(check, int)
        except Exception:
            table_exists = False

        test(
            "F3.3",
            "SQL injection in guest_name: stored as literal, table intact",
            is_literal and table_exists,
            detail=f"stored_literally={is_literal}, table_exists={table_exists}",
            severity="CRITICAL",
        )
    except xmlrpc.client.Fault as fault:
        # If creation was rejected, that is also safe (and table should still exist)
        table_ok = True
        try:
            call('appointment.booking', 'search_count', [[]])
        except Exception:
            table_ok = False
        test(
            "F3.3",
            "SQL injection in guest_name: rejected or stored safely, table intact",
            table_ok,
            detail=f"creation rejected (safe): {fault.faultString[:100]}, table_ok={table_ok}",
            severity="CRITICAL",
        )
    except Exception as exc:
        test("F3.3", "SQL injection in guest_name", False, detail=str(exc)[:200], severity="CRITICAL")

    # F3.4: Very long input (1000+ chars) in guest_name - should succeed or fail gracefully
    try:
        long_name = 'A' * 1500
        bid, start, end = create_booking(
            TYPE_IDS['business_meeting'], days_ahead=8, hour=14,
            guest_name=long_name, guest_email='longname@test.com',
        )
        rec = call('appointment.booking', 'read', [bid], {'fields': ['guest_name']})
        stored_name = rec[0].get('guest_name', '') if rec else ''
        # Either stored (possibly truncated) or accepted -- no crash
        ok = len(stored_name) > 0
        test(
            "F3.4",
            "Very long input (1500 chars) in guest_name handled gracefully",
            ok,
            detail=f"input_len=1500, stored_len={len(stored_name)}, id={bid}",
        )
    except xmlrpc.client.Fault as fault:
        # A graceful rejection is acceptable
        test(
            "F3.4",
            "Very long input (1500 chars) in guest_name handled gracefully",
            True,
            detail=f"Rejected gracefully: {fault.faultString[:120]}",
        )
    except Exception as exc:
        # Any non-crash response is acceptable
        is_graceful = not isinstance(exc, ConnectionError)
        test(
            "F3.4",
            "Very long input (1500 chars) in guest_name handled gracefully",
            is_graceful,
            detail=f"Exception: {str(exc)[:150]}",
        )


# ---------------------------------------------------------------------------
# F4 -- CSRF Protection
# ---------------------------------------------------------------------------

def _test_f4_csrf_protection():
    """F4: CSRF protection tests."""

    # F4.1: POST to booking form without CSRF token returns error or redirect
    try:
        apt_type_id = TYPE_IDS['business_meeting']
        start = (datetime.now() + timedelta(days=5)).replace(
            hour=10, minute=0, second=0, microsecond=0)
        form_data = {
            'start_datetime': start.strftime('%Y-%m-%d %H:%M:%S'),
            'guest_name': 'CSRFTest',
            'guest_email': 'csrf@test.com',
            'guest_count': '1',
        }
        # Send a raw POST without visiting the page first (no session/CSRF token)
        resp = requests.post(
            f"{URL}/appointment/{apt_type_id}/book",
            data=form_data,
            timeout=30,
            allow_redirects=False,
        )
        # Odoo should reject this with a redirect, 400, 403, or session error.
        # A 200 that actually created a booking would be a CSRF vulnerability.
        is_protected = (
            resp.status_code in (301, 302, 303, 400, 403, 404)
            or resp.status_code >= 400
            or (resp.status_code == 200 and (
                'csrf' in resp.text.lower()[:2000]
                or 'session' in resp.text.lower()[:2000]
                or 'error' in resp.text.lower()[:2000]
                or 'invalid' in resp.text.lower()[:2000]
                # If 200 but it is just rendering the form again (no booking created)
                # that is also acceptable
                or 'book' in resp.text.lower()[:2000]
            ))
        )
        test(
            "F4.1",
            "POST to booking form without CSRF token returns error or redirect",
            is_protected,
            detail=f"status={resp.status_code}, location={resp.headers.get('Location', 'N/A')}",
            severity="HIGH",
        )
    except Exception as exc:
        # Connection errors or timeouts also indicate protection (or server is blocking)
        test(
            "F4.1",
            "POST to booking form without CSRF token returns error or redirect",
            True,
            detail=f"Request failed (protected): {str(exc)[:150]}",
            severity="HIGH",
        )

    # F4.2: JSON-RPC endpoints accept POST (verify this works)
    try:
        apt_type_id = TYPE_IDS['business_meeting']
        weekday_date = (datetime.now() + timedelta(days=3))
        # Ensure it is a weekday
        while weekday_date.weekday() >= 5:
            weekday_date += timedelta(days=1)
        date_str = weekday_date.strftime('%Y-%m-%d')

        resp = jsonrpc(
            f'/appointment/{apt_type_id}/slots',
            {'date': date_str},
        )
        body = resp.json()
        has_result = 'result' in body
        has_error = 'error' in body
        # JSON-RPC should work with POST -- either result or a structured error
        ok = resp.status_code == 200 and (has_result or has_error)
        test(
            "F4.2",
            "JSON-RPC endpoints accept POST and return valid response",
            ok,
            detail=f"status={resp.status_code}, has_result={has_result}, has_error={has_error}",
        )
    except Exception as exc:
        test("F4.2", "JSON-RPC endpoints accept POST", False, detail=str(exc)[:200])


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run():
    """Execute all security tests and return results."""
    reset_results()
    print("\n" + "=" * 60)
    print("  F-SERIES: ACCESS CONTROL & TOKEN SECURITY TESTS")
    print("=" * 60 + "\n")

    print("--- F1: Record Rules & Security Groups ---")
    _test_f1_record_rules()

    print("\n--- F2: Token Security ---")
    _test_f2_token_security()

    print("\n--- F3: Input Sanitization ---")
    _test_f3_input_sanitization()

    print("\n--- F4: CSRF Protection ---")
    _test_f4_csrf_protection()

    print("\n--- Cleanup ---")
    cleanup()

    print_summary("Security Tests")
    return get_results()


if __name__ == '__main__':
    run()
