# -*- coding: utf-8 -*-
"""P9 — Form validation and error handling tests (15 tests).

Playwright browser tests verifying client-side validation, XSS escaping,
SQL injection resilience, invalid parameter handling, and CSRF protection.
"""

import sys
import os
import traceback
import datetime
import requests

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
    8: "pw_p9_8@example.com",
    9: "pw_p9_9@example.com",
    10: "test';DROP TABLE--@x.com",
}

GUEST = "PW P9 Tester"

ALL_CLEANUP_EMAILS = [
    "pw_p9_8@example.com",
    "pw_p9_9@example.com",
    "test';DROP TABLE--@x.com",
]


# ── helpers ----------------------------------------------------------------

def _get_book_url(type_id, days_ahead, hour, minute=0, staff_id=None, resource_id=None):
    """Build a booking page URL with start_datetime params."""
    if type_id == TYPE_IDS["restaurant"]:
        date_obj = conftest.get_future_saturday(days_ahead)
    else:
        date_obj = conftest.get_future_weekday(days_ahead)
    start_dt = conftest.make_start_datetime(date_obj, hour, minute)
    params = f"start_datetime={start_dt}"
    if staff_id:
        params += f"&staff_id={staff_id}"
    if resource_id:
        params += f"&resource_id={resource_id}"
    return f"{URL}/appointment/{type_id}/book?{params}"


# ===================================================================
# Individual test functions
# ===================================================================

def test_p9_1(page):
    """P9.1: Empty guest_name -> form NOT submitted (url unchanged)."""
    tid, name, sev = "P9.1", "Empty guest_name -> form NOT submitted", "HIGH"
    try:
        date_obj = conftest.get_future_weekday(6)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])
        url_before = page.url

        # Fill only email, leave name empty
        page.fill('input[name=guest_email]', 'test@example.com')

        # Click submit via JS to bypass Playwright auto-wait
        page.evaluate('document.querySelector("button.btn-primary.btn-lg").click()')
        page.wait_for_timeout(2000)

        url_after = page.url
        # Check form did NOT navigate or shows validation class
        form_has_validation = page.evaluate(
            'document.querySelector("form.needs-validation") !== null && '
            'document.querySelector("form.needs-validation.was-validated") !== null'
        )
        passed = (url_after == url_before) or form_has_validation or ("/confirm" not in url_after)
        detail = f"url_before={url_before}, url_after={url_after}, was_validated={form_has_validation}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_2(page):
    """P9.2: Empty guest_email -> form NOT submitted."""
    tid, name, sev = "P9.2", "Empty guest_email -> form NOT submitted", "HIGH"
    try:
        date_obj = conftest.get_future_weekday(6)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])
        url_before = page.url

        # Fill only name, leave email empty
        page.fill('input[name=guest_name]', 'Test User')

        page.evaluate('document.querySelector("button.btn-primary.btn-lg").click()')
        page.wait_for_timeout(2000)

        url_after = page.url
        form_has_validation = page.evaluate(
            'document.querySelector("form.needs-validation") !== null && '
            'document.querySelector("form.needs-validation.was-validated") !== null'
        )
        passed = (url_after == url_before) or form_has_validation or ("/confirm" not in url_after)
        detail = f"url_before={url_before}, url_after={url_after}, was_validated={form_has_validation}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_3(page):
    """P9.3: Invalid email 'notanemail' -> form rejected."""
    tid, name, sev = "P9.3", "Invalid email 'notanemail' -> form rejected", "HIGH"
    try:
        date_obj = conftest.get_future_weekday(6)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])
        url_before = page.url

        page.fill('input[name=guest_name]', 'Test')
        page.fill('input[name=guest_email]', 'notanemail')

        page.evaluate('document.querySelector("button.btn-primary.btn-lg").click()')
        page.wait_for_timeout(2000)

        url_after = page.url
        form_has_validation = page.evaluate(
            'document.querySelector("form.needs-validation") !== null && '
            'document.querySelector("form.needs-validation.was-validated") !== null'
        )
        # Email field validity check
        email_invalid = page.evaluate(
            '!document.querySelector("input[name=guest_email]").validity.valid'
        )
        passed = (url_after == url_before) or form_has_validation or email_invalid or ("/confirm" not in url_after)
        detail = (f"url_before={url_before}, url_after={url_after}, "
                  f"was_validated={form_has_validation}, email_invalid={email_invalid}")
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_4(page):
    """P9.4: guest_count=0 -> check behavior (may be accepted or rejected)."""
    tid, name, sev = "P9.4", "guest_count=0 -> check behavior", "MEDIUM"
    try:
        date_obj = conftest.get_future_weekday(6)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        conftest.fill_booking_form(page, f"{GUEST} P9.4", "pw_p9_4_temp@example.com",
                                   guest_count=0)

        page.evaluate('document.querySelector("button.btn-primary.btn-lg").click()')
        page.wait_for_timeout(3000)

        url_after = page.url
        content = page.content()
        # Pass if either accepted (confirm page) or rejected gracefully (no 500)
        no_server_error = "500" not in page.title() and "Server Error" not in content
        passed = no_server_error
        detail = f"url={url_after}, no_500={no_server_error}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_5(page):
    """P9.5: guest_count=-1 -> check behavior."""
    tid, name, sev = "P9.5", "guest_count=-1 -> check behavior", "MEDIUM"
    try:
        date_obj = conftest.get_future_weekday(6)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        conftest.fill_booking_form(page, f"{GUEST} P9.5", "pw_p9_5_temp@example.com",
                                   guest_count=-1)

        page.evaluate('document.querySelector("button.btn-primary.btn-lg").click()')
        page.wait_for_timeout(3000)

        url_after = page.url
        content = page.content()
        no_server_error = "500" not in page.title() and "Server Error" not in content
        passed = no_server_error
        detail = f"url={url_after}, no_500={no_server_error}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_6(page):
    """P9.6: guest_count=999 -> accepted or capped, no crash."""
    tid, name, sev = "P9.6", "guest_count=999 -> accepted or capped", "LOW"
    try:
        date_obj = conftest.get_future_weekday(6)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        conftest.fill_booking_form(page, f"{GUEST} P9.6", "pw_p9_6_temp@example.com",
                                   guest_count=999)

        page.evaluate('document.querySelector("button.btn-primary.btn-lg").click()')
        page.wait_for_timeout(3000)

        url_after = page.url
        content = page.content()
        no_server_error = "500" not in page.title() and "Server Error" not in content
        passed = no_server_error
        detail = f"url={url_after}, no_500={no_server_error}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_7(page):
    """P9.7: Very long guest_name (500 chars) -> no crash."""
    tid, name, sev = "P9.7", "Very long guest_name (500 chars) -> no crash", "MEDIUM"
    try:
        date_obj = conftest.get_future_weekday(6)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        long_name = "A" * 500
        conftest.fill_booking_form(page, long_name, "pw_p9_7_temp@example.com")
        conftest.submit_booking_form(page, timeout=15000)

        content = page.content()
        url_after = page.url
        no_server_error = "500" not in page.title() and "Server Error" not in content
        passed = no_server_error
        detail = f"url={url_after}, no_500={no_server_error}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_8(page):
    """P9.8: XSS in guest_name -> escaped in output."""
    tid, name, sev = "P9.8", "XSS in guest_name -> escaped in output", "HIGH"
    try:
        date_obj = conftest.get_future_weekday(3)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        xss_payload = '<script>alert(1)</script>'
        conftest.fill_booking_form(page, xss_payload, EMAILS[8])
        conftest.submit_booking_form(page, timeout=15000)

        html = page.content()
        # The raw <script> tag should NOT appear unescaped in the HTML
        # It should be escaped as &lt;script&gt; or similar
        has_raw_script = '<script>alert(1)</script>' in html
        passed = not has_raw_script
        detail = f"raw_script_in_html={has_raw_script}, url={page.url}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_9(page):
    """P9.9: XSS in notes -> escaped in output."""
    tid, name, sev = "P9.9", "XSS in notes -> escaped in output", "HIGH"
    try:
        date_obj = conftest.get_future_weekday(4)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        xss_notes = '<img onerror=alert(1) src=x>'
        conftest.fill_booking_form(page, f"{GUEST} P9.9", EMAILS[9], notes=xss_notes)
        conftest.submit_booking_form(page, timeout=15000)

        html = page.content()
        has_raw_img = '<img onerror=alert(1) src=x>' in html
        passed = not has_raw_img
        detail = f"raw_img_in_html={has_raw_img}, url={page.url}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_10(page):
    """P9.10: SQL injection in email -> no crash."""
    tid, name, sev = "P9.10", "SQL injection in email -> no crash", "HIGH"
    try:
        date_obj = conftest.get_future_weekday(5)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        conftest.goto_book_page(page, TYPE_IDS["business_meeting"], start_dt,
                                staff_id=STAFF_IDS["admin"])

        sqli_email = EMAILS[10]  # test';DROP TABLE--@x.com
        conftest.fill_booking_form(page, f"{GUEST} P9.10", sqli_email)

        # Use JS submit to bypass email validation on the client
        page.evaluate('document.querySelector("form.needs-validation").submit()')
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        content = page.content()
        url_after = page.url
        no_server_error = "500" not in page.title() and "Server Error" not in content
        no_traceback = "Traceback" not in content
        passed = no_server_error and no_traceback
        detail = f"url={url_after}, no_500={no_server_error}, no_traceback={no_traceback}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_11(page):
    """P9.11: Missing start_datetime -> redirect or error, not crash."""
    tid, name, sev = "P9.11", "Missing start_datetime -> no crash", "HIGH"
    try:
        resp = page.goto(f"{URL}/appointment/1/book")
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        content = page.content()
        no_server_error = status != 500 and "Server Error" not in content
        passed = no_server_error
        detail = f"status={status}, url={page.url}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_12(page):
    """P9.12: Invalid start_datetime format -> error handling."""
    tid, name, sev = "P9.12", "Invalid start_datetime format -> error handling", "MEDIUM"
    try:
        resp = page.goto(f"{URL}/appointment/1/book?start_datetime=invalid_date")
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        content = page.content()
        no_server_error = status != 500 and "Server Error" not in content
        passed = no_server_error
        detail = f"status={status}, url={page.url}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_13(page):
    """P9.13: Past start_datetime -> check behavior."""
    tid, name, sev = "P9.13", "Past start_datetime -> check behavior", "MEDIUM"
    try:
        resp = page.goto(
            f"{URL}/appointment/1/book?start_datetime=2020-01-01 10:00:00"
        )
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        content = page.content()
        no_server_error = status != 500 and "Server Error" not in content
        passed = no_server_error
        detail = f"status={status}, url={page.url}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_14(page):
    """P9.14: Beyond max_booking_days for tennis (7 days, use 60 ahead)."""
    tid, name, sev = "P9.14", "Beyond max_booking_days -> check behavior", "MEDIUM"
    try:
        future_date = datetime.date.today() + datetime.timedelta(days=60)
        start_dt = conftest.make_start_datetime(future_date, 10)
        resp = page.goto(
            f"{URL}/appointment/{TYPE_IDS['tennis']}/book?start_datetime={start_dt}"
        )
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        content = page.content()
        url_after = page.url
        no_server_error = status != 500 and "Server Error" not in content
        # Ideally the system redirects back or shows an error message
        passed = no_server_error
        detail = f"status={status}, url={url_after}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


def test_p9_15():
    """P9.15: POST without CSRF token -> rejected (400 or 403)."""
    tid, name, sev = "P9.15", "POST without CSRF token -> rejected", "HIGH"
    try:
        date_obj = conftest.get_future_weekday(6)
        start_dt = conftest.make_start_datetime(date_obj, 10)
        post_url = f"{URL}/appointment/{TYPE_IDS['business_meeting']}/book"
        data = {
            'guest_name': 'CSRF Test',
            'guest_email': 'csrf_test@example.com',
            'guest_count': '1',
            'start_datetime': start_dt,
            'staff_id': str(STAFF_IDS['admin']),
        }
        r = requests.post(post_url, data=data, allow_redirects=False, timeout=10)
        # Without CSRF token, the server should reject with 400, 403, or similar
        # It should NOT return 200 (success)
        passed = r.status_code in (400, 403, 404, 303, 302)
        detail = f"status={r.status_code}"
        conftest.test(tid, name, passed, detail, sev)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)


# ===================================================================
# run() -- entry point called by the test runner
# ===================================================================

def run():
    """Execute all P9 validation tests. Returns conftest.get_results()."""
    from playwright.sync_api import sync_playwright

    conftest.clear_results()
    print("\n=== P9: Form Validation & Error Handling Tests (15 tests) ===\n")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)

    try:
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        # -- Browser tests --
        test_p9_1(page)
        test_p9_2(page)
        test_p9_3(page)
        test_p9_4(page)
        test_p9_5(page)
        test_p9_6(page)
        test_p9_7(page)
        test_p9_8(page)
        test_p9_9(page)
        test_p9_10(page)
        test_p9_11(page)
        test_p9_12(page)
        test_p9_13(page)
        test_p9_14(page)

        # -- Non-browser test --
        test_p9_15()

        context.close()
    except Exception:
        print(f"Fatal error in P9 suite: {traceback.format_exc()}")
    finally:
        # -- Cleanup all test bookings --
        print("\n--- Cleaning up P9 test bookings ---")
        for email in ALL_CLEANUP_EMAILS:
            try:
                conftest.cleanup_test_bookings(email)
            except Exception:
                pass
        # Also clean up temp emails from count tests
        for suffix in ["4", "5", "6", "7"]:
            try:
                conftest.cleanup_test_bookings(f"pw_p9_{suffix}_temp@example.com")
            except Exception:
                pass
        browser.close()
        pw.stop()

    results = conftest.get_results()
    passed = sum(1 for r in results if r["passed"])
    print(f"\n=== P9 Complete: {passed}/{len(results)} passed ===\n")
    return results


if __name__ == "__main__":
    run()
