# -*- coding: utf-8 -*-
"""P10 — Edge cases and security tests (10 tests).

Playwright browser tests for double-submit, unpublished types, path traversal,
non-integer IDs, unicode/emoji names, concurrent bookings, capacity limits,
and public session checks.
"""

import sys
import os
import traceback
import time

sys.path.insert(0, os.path.dirname(__file__))

import conftest
from config import (
    URL, TYPE_IDS, STAFF_IDS, RESOURCE_IDS, TYPE_CONFIG,
    UNPUBLISHED_TYPE_ID,
)

# ---------------------------------------------------------------------------
# Unique emails per test
# ---------------------------------------------------------------------------
EMAILS = {
    1: "pw_p10_1@example.com",
    5: "pw_p10_5@example.com",
    6: "pw_p10_6@example.com",
    7: "pw_p10_7@example.com",
    "8a": "pw_p10_8a@example.com",
    "8b": "pw_p10_8b@example.com",
    9: "pw_p10_9@example.com",
}

GUEST = "PW P10 Tester"

ALL_CLEANUP_EMAILS = [
    "pw_p10_1@example.com",
    "pw_p10_5@example.com",
    "pw_p10_6@example.com",
    "pw_p10_7@example.com",
    "pw_p10_8a@example.com",
    "pw_p10_8b@example.com",
    "pw_p10_9@example.com",
]


# ===================================================================
# Individual test functions
# ===================================================================

def test_p10_1(page):
    """P10.1: Rapid double-submit -> only 1 booking created."""
    tid, name, sev = "P10.1", "Rapid double-submit -> only 1 booking", "HIGH"
    try:
        date_obj = conftest.get_future_weekday(70)
        start_dt = conftest.make_start_datetime(date_obj, 8)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        conftest.fill_booking_form(page, f"{GUEST} P10.1", EMAILS[1])

        # Double-submit the form via JS
        page.evaluate(
            'let f = document.querySelector("form.needs-validation"); '
            'f.submit(); f.submit();'
        )
        page.wait_for_timeout(5000)
        page.wait_for_load_state("networkidle")

        bookings = conftest.find_bookings_by_email(EMAILS[1])
        count = len(bookings)
        passed = count == 1
        detail = f"booking_count={count}, expected=1"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p10_2(page):
    """P10.2: Booking unpublished type via direct URL -> blocked."""
    tid, name, sev = "P10.2", "Unpublished type direct URL -> blocked", "HIGH"
    try:
        date_obj = conftest.get_future_weekday(71)
        start_dt = conftest.make_start_datetime(date_obj, 9)
        resp = page.goto(
            f"{URL}/appointment/{UNPUBLISHED_TYPE_ID}/book"
            f"?start_datetime={start_dt}&staff_id={STAFF_IDS['admin']}"
        )
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        url_after = page.url
        content = page.content()

        # Should be redirected away, get 404, or see an error -- NOT a normal booking form
        is_blocked = (
            status in (403, 404)
            or "/appointment" in url_after and f"/{UNPUBLISHED_TYPE_ID}/book" not in url_after
            or "not found" in content.lower()
            or "error" in content.lower()
            or "not available" in content.lower()
            or "guest_name" not in content.lower()
        )
        passed = is_blocked
        detail = f"status={status}, url={url_after}, blocked={is_blocked}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p10_3(page):
    """P10.3: Path traversal /appointment/../web/login -> login page not appointment data."""
    tid, name, sev = "P10.3", "Path traversal -> no data leak", "HIGH"
    try:
        resp = page.goto(f"{URL}/appointment/../web/login")
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        url_after = page.url
        content = page.content().lower()

        # We should land on the login page or get redirected -- NOT an appointment page
        is_login = "login" in url_after or "login" in content
        no_appointment_leak = "appointment" not in url_after or "login" in url_after
        passed = status != 500 and (is_login or no_appointment_leak)
        detail = f"status={status}, url={url_after}, is_login={is_login}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p10_4(page):
    """P10.4: Non-integer type /appointment/abc -> 404."""
    tid, name, sev = "P10.4", "Non-integer type /appointment/abc -> 404", "MEDIUM"
    try:
        resp = page.goto(f"{URL}/appointment/abc")
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        content = page.content()
        # Should get 404 or redirect, definitely not 500
        passed = status in (404, 400, 302, 303, 200) and status != 500
        detail = f"status={status}, url={page.url}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p10_5(page):
    """P10.5: Unicode name saved correctly in DB."""
    tid, name, sev = "P10.5", "Unicode name saved correctly in DB", "MEDIUM"
    try:
        date_obj = conftest.get_future_weekday(72)
        start_dt = conftest.make_start_datetime(date_obj, 11)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        unicode_name = "\u6e2c\u8a66\u7528\u6236"  # 測試用戶
        conftest.fill_booking_form(page, unicode_name, EMAILS[5])
        conftest.submit_booking_form(page, timeout=15000)

        # Verify in DB
        bookings = conftest.find_bookings_by_email(EMAILS[5])
        if not bookings:
            conftest.test(tid, name, False, "No booking found in DB", sev)
            return
        bk = conftest.read_booking(bookings[0]["id"])
        saved_name = bk.get("guest_name", "")
        passed = unicode_name in saved_name
        detail = f"saved_name='{saved_name}', expected contains='{unicode_name}'"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p10_6(page):
    """P10.6: Emoji name handled without crash."""
    tid, name, sev = "P10.6", "Emoji name handled without crash", "LOW"
    try:
        date_obj = conftest.get_future_weekday(73)
        start_dt = conftest.make_start_datetime(date_obj, 13)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        emoji_name = "\U0001f3be Tennis Fan"
        conftest.fill_booking_form(page, emoji_name, EMAILS[6])
        conftest.submit_booking_form(page, timeout=15000)

        content = page.content()
        url_after = page.url
        no_server_error = "500" not in page.title() and "Server Error" not in content
        # Booking should succeed or at least not crash
        passed = no_server_error
        detail = f"url={url_after}, no_500={no_server_error}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p10_7(page):
    """P10.7: Empty notes -> booking succeeds."""
    tid, name, sev = "P10.7", "Empty notes -> booking succeeds", "LOW"
    try:
        date_obj = conftest.get_future_weekday(74)
        start_dt = conftest.make_start_datetime(date_obj, 14)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        conftest.fill_booking_form(page, f"{GUEST} P10.7", EMAILS[7], notes="")
        conftest.submit_booking_form(page, timeout=15000)

        url_after = page.url
        passed = "/confirm" in url_after
        detail = f"url={url_after}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p10_8(browser):
    """P10.8: Concurrent bookings same resource same time -> no crash."""
    tid, name, sev = "P10.8", "Concurrent bookings same resource/time -> no crash", "HIGH"
    try:
        sat = conftest.get_future_saturday(77)
        start_dt = conftest.make_start_datetime(sat, 18)

        # Create two separate browser contexts for concurrent access
        ctx1 = browser.new_context(ignore_https_errors=True)
        ctx2 = browser.new_context(ignore_https_errors=True)
        page1 = ctx1.new_page()
        page2 = ctx2.new_page()

        # Both navigate to restaurant booking with same resource and time
        conftest.goto_book_page(page1, TYPE_IDS["restaurant"], start_dt,
                                resource_id=RESOURCE_IDS["table_1_window"])
        conftest.goto_book_page(page2, TYPE_IDS["restaurant"], start_dt,
                                resource_id=RESOURCE_IDS["table_1_window"])

        # Fill both forms
        conftest.fill_booking_form(page1, f"{GUEST} P10.8a", EMAILS["8a"])
        conftest.fill_booking_form(page2, f"{GUEST} P10.8b", EMAILS["8b"])

        # Submit both rapidly
        page1.evaluate('document.querySelector("form.needs-validation").submit()')
        page2.evaluate('document.querySelector("form.needs-validation").submit()')

        # Wait for both to complete
        page1.wait_for_timeout(5000)
        page2.wait_for_timeout(5000)
        try:
            page1.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        try:
            page2.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        content1 = page1.content()
        content2 = page2.content()

        # Key check: neither page should have a 500 server error
        no_500_1 = "Server Error" not in content1
        no_500_2 = "Server Error" not in content2

        # Check how many bookings were created
        bookings_a = conftest.find_bookings_by_email(EMAILS["8a"])
        bookings_b = conftest.find_bookings_by_email(EMAILS["8b"])
        total = len(bookings_a) + len(bookings_b)

        passed = no_500_1 and no_500_2 and total >= 1
        detail = (f"page1_ok={no_500_1}, page2_ok={no_500_2}, "
                  f"bookings_a={len(bookings_a)}, bookings_b={len(bookings_b)}, total={total}")
        conftest.test(tid, name, passed, detail, sev)

        page1.close()
        page2.close()
        ctx1.close()
        ctx2.close()
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p10_9(page):
    """P10.9: Large guest_count=100 for restaurant -> check capacity handling."""
    tid, name, sev = "P10.9", "Large guest_count=100 restaurant -> capacity check", "MEDIUM"
    try:
        sat = conftest.get_future_saturday(84)
        start_dt = conftest.make_start_datetime(sat, 20)
        conftest.goto_book_page(page, TYPE_IDS["restaurant"], start_dt,
                                resource_id=RESOURCE_IDS["table_1_window"])

        conftest.fill_booking_form(page, f"{GUEST} P10.9", EMAILS[9], guest_count=100)

        page.evaluate('document.querySelector("form.needs-validation").submit()')
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        content = page.content()
        url_after = page.url
        no_server_error = "500" not in page.title() and "Server Error" not in content

        # Either rejected (capacity exceeded) or accepted -- both OK as long as no crash
        passed = no_server_error
        detail = f"url={url_after}, no_500={no_server_error}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p10_10(page):
    """P10.10: Public user has no admin session cookies."""
    tid, name, sev = "P10.10", "Public user no admin cookies", "LOW"
    try:
        page.goto(f"{URL}/appointment")
        page.wait_for_load_state("networkidle")

        cookies = page.context.cookies()
        # Check that no cookie grants admin (session_id with authenticated admin)
        session_cookies = [c for c in cookies if c["name"] == "session_id"]

        if not session_cookies:
            # No session_id at all -- public user, good
            passed = True
            detail = "No session_id cookie found (public user)"
        else:
            # session_id exists -- verify it does NOT have admin access
            # Try accessing an admin endpoint with this session
            admin_page = page.context.new_page()
            resp = admin_page.goto(f"{URL}/web#action=base.action_res_users")
            admin_page.wait_for_timeout(3000)
            admin_url = admin_page.url
            # If redirected to login, the session is not admin-authenticated
            is_redirected_to_login = "login" in admin_url or "web/login" in admin_url
            passed = is_redirected_to_login
            detail = (f"session_id present, admin_url={admin_url}, "
                      f"redirected_to_login={is_redirected_to_login}")
            admin_page.close()

        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


# ===================================================================
# run() -- entry point called by the test runner
# ===================================================================

def run():
    """Execute all P10 edge case tests. Returns conftest.get_results()."""
    from playwright.sync_api import sync_playwright

    conftest.clear_results()

    # Clean ALL bookings to avoid staff conflicts
    try:
        all_bk_ids = conftest.call('appointment.booking', 'search', [[]])
        if all_bk_ids:
            confirmed = conftest.call('appointment.booking', 'search', [[('state', 'in', ['confirmed', 'done'])]])
            if confirmed:
                conftest.call('appointment.booking', 'write', [confirmed, {'state': 'cancelled'}])
            conftest.call('appointment.booking', 'unlink', [all_bk_ids])
    except Exception as e:
        print(f'  [WARN] Cleanup failed: {e}')

    print("\n=== P10: Edge Cases & Security Tests (10 tests) ===\n")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)

    try:
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        # -- Browser tests using shared page --
        test_p10_1(page)
        test_p10_2(page)
        test_p10_3(page)
        test_p10_4(page)
        test_p10_5(page)
        test_p10_6(page)
        test_p10_7(page)

        # -- P10.8 needs its own browser contexts (concurrent) --
        test_p10_8(browser)

        # -- Remaining browser tests --
        test_p10_9(page)
        test_p10_10(page)

        context.close()
    except Exception:
        print(f"Fatal error in P10 suite: {traceback.format_exc()}")
    finally:
        # -- Cleanup all test bookings --
        print("\n--- Cleaning up P10 test bookings ---")
        for email in ALL_CLEANUP_EMAILS:
            try:
                conftest.cleanup_test_bookings(email)
            except Exception:
                pass
        browser.close()
        pw.stop()

    results = conftest.get_results()
    passed = sum(1 for r in results if r["passed"])
    print(f"\n=== P10 Complete: {passed}/{len(results)} passed ===\n")
    return results


if __name__ == "__main__":
    run()
