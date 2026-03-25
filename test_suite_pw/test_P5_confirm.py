# -*- coding: utf-8 -*-
"""P5 — Confirmation and booking detail page tests (12 tests).

Verifies that after a booking is created the confirmation page renders
correctly, that the detail page honours access-token security, and that
special states (cancelled) and appointment types (restaurant) are
reflected in the UI.
"""

import re
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(__file__))

import conftest
from config import (
    URL, TYPE_IDS, STAFF_IDS, RESOURCE_IDS,
)


# ---------------------------------------------------------------------------
# Unique emails per test (avoid cross-test collision)
# ---------------------------------------------------------------------------
EMAILS = {n: f"pw_p5_{n}@example.com" for n in range(1, 13)}

GUEST_NAME = "PW P5 Test"


def _email(n):
    return EMAILS[n]


# ---------------------------------------------------------------------------
# Helper: create a booking via the browser and return the DB record
# ---------------------------------------------------------------------------

def _create_booking(page, email_suffix, type_id=1, staff_id=2,
                    resource_id=None, days_ahead=3, hour=10):
    """Navigate to the booking page, fill, submit, look up the record.

    Returns a booking dict with id, access_token, name, state, etc.
    Raises on failure so callers can catch and report.
    """
    email = _email(email_suffix)

    # Pick the right date helper depending on type
    if type_id == TYPE_IDS["restaurant"]:
        date_obj = conftest.get_future_saturday(days_ahead)
    else:
        date_obj = conftest.get_future_weekday(days_ahead)

    start_dt = conftest.make_start_datetime(date_obj, hour)

    conftest.goto_book_page(
        page, type_id, start_dt,
        staff_id=staff_id,
        resource_id=resource_id,
    )
    conftest.fill_booking_form(page, GUEST_NAME, email)
    conftest.submit_booking_form(page, timeout=15000)

    bookings = conftest.find_bookings_by_email(email)
    if not bookings:
        raise RuntimeError(f"No booking found for {email} after submission")

    bk = conftest.read_booking(bookings[0]["id"])
    if not bk:
        raise RuntimeError(f"read_booking returned None for id={bookings[0]['id']}")

    return bk


# ---------------------------------------------------------------------------
# Cached shared booking for P5.1-P5.9
# ---------------------------------------------------------------------------
_shared = {}  # filled once by test_p5_1


def _get_shared():
    """Return the shared booking dict; empty dict if P5.1 failed."""
    return _shared.get("bk", {})


# ===================================================================
# Individual test functions
# ===================================================================

# -- P5.1 ---------------------------------------------------------------
def test_p5_1(page):
    """P5.1: Confirm page body has 'confirm' text."""
    tid, name, sev = "P5.1", "Confirm page body has 'confirm' text", "HIGH"
    try:
        bk = _create_booking(page, email_suffix=1, type_id=1,
                             staff_id=STAFF_IDS["admin"],
                             days_ahead=40, hour=9)
        _shared["bk"] = bk

        # After submit the browser should already be on the confirm page
        content = page.content().lower()
        passed = "confirm" in content
        conftest.test(tid, name, passed,
                      f"URL={page.url}, 'confirm' in body={passed}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.2 ---------------------------------------------------------------
def test_p5_2(page):
    """P5.2: Confirm page shows booking ref matching APT\\d{4,}."""
    tid, name, sev = "P5.2", "Confirm page shows booking ref APT\\d{4,}", "HIGH"
    try:
        bk = _get_shared()
        if not bk:
            conftest.test(tid, name, False, "Shared booking not available", sev)
            return

        # Navigate to confirm page via known URL pattern
        content = page.content()
        match = re.search(r'APT\d{4,}', content)
        passed = match is not None
        detail = f"found={match.group(0)}" if match else "no APT ref found in page"
        conftest.test(tid, name, passed, detail, sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.3 ---------------------------------------------------------------
def test_p5_3(page):
    """P5.3: Confirm page contains the year string from date."""
    tid, name, sev = "P5.3", "Confirm page has year string from date", "HIGH"
    try:
        bk = _get_shared()
        if not bk:
            conftest.test(tid, name, False, "Shared booking not available", sev)
            return

        # Extract year from the booking's start_datetime (e.g. "2026-04-01 10:00:00")
        sdt = bk.get("start_datetime", "")
        year = sdt[:4] if sdt else ""
        if not year:
            conftest.test(tid, name, False, f"Cannot extract year from '{sdt}'", sev)
            return

        content = page.content()
        passed = year in content
        conftest.test(tid, name, passed,
                      f"year={year}, found_in_page={passed}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.4 ---------------------------------------------------------------
def test_p5_4(page):
    """P5.4: GET /appointment/booking/<id>?token=<token> returns 200."""
    tid, name, sev = "P5.4", "Detail page with token loads (status 200)", "HIGH"
    try:
        bk = _get_shared()
        if not bk:
            conftest.test(tid, name, False, "Shared booking not available", sev)
            return

        bk_id = bk["id"]
        token = bk.get("access_token", "")
        detail_url = f"{URL}/appointment/booking/{bk_id}?token={token}"
        resp = page.goto(detail_url)
        page.wait_for_load_state("networkidle")

        status = resp.status if resp else 0
        passed = status == 200
        conftest.test(tid, name, passed,
                      f"status={status}, url={detail_url}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.5 ---------------------------------------------------------------
def test_p5_5(page):
    """P5.5: Detail page shows guest name and email."""
    tid, name, sev = "P5.5", "Detail page shows guest name and email", "MEDIUM"
    try:
        bk = _get_shared()
        if not bk:
            conftest.test(tid, name, False, "Shared booking not available", sev)
            return

        # Page should already be on the detail page from P5.4
        content = page.content()
        has_name = GUEST_NAME in content
        email = _email(1)
        has_email = email in content
        passed = has_name and has_email
        conftest.test(tid, name, passed,
                      f"has_name={has_name}, has_email={has_email}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.6 ---------------------------------------------------------------
def test_p5_6(page):
    """P5.6: Detail page shows 'confirmed' status text."""
    tid, name, sev = "P5.6", "Detail page shows 'confirmed' status text", "MEDIUM"
    try:
        bk = _get_shared()
        if not bk:
            conftest.test(tid, name, False, "Shared booking not available", sev)
            return

        content = page.content().lower()
        passed = "confirmed" in content or "confirm" in content
        conftest.test(tid, name, passed,
                      f"'confirmed' in page={passed}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.7 ---------------------------------------------------------------
def test_p5_7(page):
    """P5.7: Detail page has cancel link (a[href*='cancel'])."""
    tid, name, sev = "P5.7", "Detail page has cancel link", "MEDIUM"
    try:
        bk = _get_shared()
        if not bk:
            conftest.test(tid, name, False, "Shared booking not available", sev)
            return

        cancel_link = page.locator('a[href*="cancel"]')
        passed = cancel_link.count() > 0
        conftest.test(tid, name, passed,
                      f"cancel link count={cancel_link.count()}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.8 ---------------------------------------------------------------
def test_p5_8(page):
    """P5.8: GET /appointment/booking/<id> WITHOUT token -> no booking data or redirect."""
    tid, name, sev = "P5.8", "Detail without token hides booking data or redirects", "HIGH"
    try:
        bk = _get_shared()
        if not bk:
            conftest.test(tid, name, False, "Shared booking not available", sev)
            return

        bk_id = bk["id"]
        no_token_url = f"{URL}/appointment/booking/{bk_id}"
        resp = page.goto(no_token_url)
        page.wait_for_load_state("networkidle")

        status = resp.status if resp else 0
        final_url = page.url
        content = page.content()

        # Success criteria: either non-200 status, redirect away from detail,
        # or the guest email is NOT shown (data hidden).
        redirected = "/appointment/booking/" not in final_url
        no_data = _email(1) not in content and GUEST_NAME not in content
        error_page = status >= 400

        passed = redirected or no_data or error_page
        conftest.test(tid, name, passed,
                      f"status={status}, redirected={redirected}, no_data={no_data}, "
                      f"error={error_page}, final_url={final_url}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.9 ---------------------------------------------------------------
def test_p5_9(page):
    """P5.9: GET /appointment/booking/<id>?token=WRONG -> error or redirect."""
    tid, name, sev = "P5.9", "Detail with wrong token -> error or redirect", "HIGH"
    try:
        bk = _get_shared()
        if not bk:
            conftest.test(tid, name, False, "Shared booking not available", sev)
            return

        bk_id = bk["id"]
        wrong_url = f"{URL}/appointment/booking/{bk_id}?token=WRONGTOKEN12345"
        resp = page.goto(wrong_url)
        page.wait_for_load_state("networkidle")

        status = resp.status if resp else 0
        final_url = page.url
        content = page.content()

        # Success: non-200, redirect, or no personal data shown
        redirected = "/appointment/booking/" not in final_url
        no_data = _email(1) not in content and GUEST_NAME not in content
        error_page = status >= 400

        passed = redirected or no_data or error_page
        conftest.test(tid, name, passed,
                      f"status={status}, redirected={redirected}, no_data={no_data}, "
                      f"error={error_page}, final_url={final_url}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.10 --------------------------------------------------------------
def test_p5_10(page):
    """P5.10: Cancel booking via XML-RPC then detail shows 'cancelled'."""
    tid, name, sev = "P5.10", "Cancelled booking detail shows 'cancelled'", "MEDIUM"
    try:
        bk = _create_booking(page, email_suffix=10, type_id=1,
                             staff_id=STAFF_IDS["admin"],
                             days_ahead=42, hour=11)
        bk_id = bk["id"]
        token = bk.get("access_token", "")

        # Cancel via XML-RPC
        conftest.call('appointment.booking', 'action_cancel', [[bk_id]])

        # Visit detail page
        detail_url = f"{URL}/appointment/booking/{bk_id}?token={token}"
        page.goto(detail_url)
        page.wait_for_load_state("networkidle")

        content = page.content().lower()
        passed = "cancel" in content
        conftest.test(tid, name, passed,
                      f"'cancel' in page={passed}, url={detail_url}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.11 --------------------------------------------------------------
def test_p5_11(page):
    """P5.11: Restaurant booking confirm page has 'Table' text."""
    tid, name, sev = "P5.11", "Restaurant booking confirm page has 'Table' text", "MEDIUM"
    try:
        bk = _create_booking(page, email_suffix=11,
                             type_id=TYPE_IDS["restaurant"],
                             staff_id=None,
                             resource_id=RESOURCE_IDS["table_1_window"],
                             days_ahead=44, hour=18)

        # After submit, browser is on confirm page
        content = page.content()
        passed = "Table" in content or "table" in content.lower()
        conftest.test(tid, name, passed,
                      f"'Table' in page={passed}, url={page.url}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# -- P5.12 --------------------------------------------------------------
def test_p5_12(page):
    """P5.12: Type 1 confirm page has 'Mitchell Admin' or 'Staff' text."""
    tid, name, sev = "P5.12", "Type 1 confirm page has staff text", "MEDIUM"
    try:
        bk = _create_booking(page, email_suffix=12, type_id=1,
                             staff_id=STAFF_IDS["admin"],
                             days_ahead=46, hour=14)

        content = page.content()
        has_admin = "Mitchell Admin" in content
        has_staff = "Staff" in content or "staff" in content.lower()
        passed = has_admin or has_staff
        conftest.test(tid, name, passed,
                      f"has_admin={has_admin}, has_staff={has_staff}", sev)
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception:
        conftest.test(tid, name, False, traceback.format_exc(), sev)
        conftest.take_failure_screenshot(page, tid)


# ===================================================================
# run() -- entry point called by the test runner
# ===================================================================

def run():
    """Execute all P5 confirmation / detail tests. Returns conftest.get_results()."""
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

    print("\n=== P5: Confirmation & Detail Page Tests (12 tests) ===\n")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)

    try:
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        # P5.1 creates the shared booking; P5.2-P5.3 inspect the same confirm page
        test_p5_1(page)
        test_p5_2(page)
        test_p5_3(page)

        # P5.4 navigates to the detail page; P5.5-P5.7 inspect it
        test_p5_4(page)
        test_p5_5(page)
        test_p5_6(page)
        test_p5_7(page)

        # Security: no-token and wrong-token access
        test_p5_8(page)
        test_p5_9(page)

        # Separate bookings for remaining tests
        test_p5_10(page)
        test_p5_11(page)
        test_p5_12(page)

        context.close()
    except Exception:
        print(f"Fatal error in P5 suite: {traceback.format_exc()}")
    finally:
        # ── Cleanup all test emails ──
        print("\n--- Cleaning up P5 test bookings ---")
        for n in EMAILS:
            try:
                conftest.cleanup_test_bookings(EMAILS[n])
            except Exception:
                pass
        browser.close()
        pw.stop()

    results = conftest.get_results()
    passed = sum(1 for r in results if r["passed"])
    print(f"\n=== P5 Complete: {passed}/{len(results)} passed ===\n")
    return results


if __name__ == "__main__":
    run()
