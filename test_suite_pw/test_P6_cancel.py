# -*- coding: utf-8 -*-
"""P6 — Cancel booking flow tests.

10 Playwright browser tests verifying the cancel page, cancel submission,
state changes, and post-cancel behaviour via XML-RPC.
"""

import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(__file__))

import conftest
from config import URL, TYPE_IDS, STAFF_IDS

# ---------------------------------------------------------------------------
# Email pattern: pw_p6_{suffix}@example.com
# ---------------------------------------------------------------------------
EMAILS = {
    "p6_1": "pw_p6_1@example.com",
    "p6_2": "pw_p6_2@example.com",
    "p6_3": "pw_p6_3@example.com",
    "p6_4": "pw_p6_4@example.com",
    "p6_5": "pw_p6_5@example.com",
    "p6_6": "pw_p6_6@example.com",
    "p6_7": "pw_p6_7@example.com",
    "p6_8": "pw_p6_8@example.com",
    "p6_9": "pw_p6_9@example.com",
    "p6_10": "pw_p6_10@example.com",
}

GUEST = "PW P6 Tester"


# ---------------------------------------------------------------------------
# Helper: create a fresh booking for each cancel test
# ---------------------------------------------------------------------------

def _create_fresh_booking(page, suffix, days_ahead, hour=10):
    """Book type 1 (Business Meeting) with staff_id=2 and return booking dict.

    Returns dict with keys: id, access_token, name  (or None on failure).
    """
    email = EMAILS[suffix]
    guest_name = f"{GUEST} {suffix}"
    date_obj = conftest.get_future_weekday(days_ahead)
    start_dt = conftest.make_start_datetime(date_obj, hour)

    conftest.goto_book_page(
        page,
        TYPE_IDS["business_meeting"],
        start_dt,
        staff_id=STAFF_IDS["admin"],
    )
    conftest.fill_booking_form(page, guest_name, email)
    conftest.submit_booking_form(page, timeout=15000)

    # Look up the booking in DB
    bookings = conftest.find_bookings_by_email(email)
    if not bookings:
        return None

    bk = conftest.read_booking(bookings[0]["id"])
    return {
        "id": bk["id"],
        "access_token": bk["access_token"],
        "name": bk["name"],
    }


def _cancel_url(booking_id, token):
    """Build the cancel page URL."""
    return f"{URL}/appointment/booking/{booking_id}/cancel?token={token}"


def _click_cancel_button(page):
    """Try several selectors to find and click the cancel submit button.

    Returns True if a button was found and clicked, False otherwise.
    """
    selectors = [
        "button[type=submit].btn-primary",
        "button.btn-primary.btn-lg",
        "form button.btn-danger",
        "form input[type=submit]",
        'button:has-text("Cancel Booking")',
        'button:has-text("Confirm Cancel")',
        'button:has-text("Cancel")',
    ]
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            return True
    return False


# ===================================================================
# Individual test functions
# ===================================================================

def test_p6_1(page):
    """P6.1: Cancel page loads with form element."""
    try:
        bk = _create_fresh_booking(page, "p6_1", days_ahead=40, hour=9)
        if not bk:
            conftest.test("P6.1", "Cancel page loads with form element", False,
                          "Failed to create fresh booking", "HIGH")
            return

        page.goto(_cancel_url(bk["id"], bk["access_token"]))
        page.wait_for_load_state("networkidle")

        # Check for a form with a method attribute or a submit button
        form_loc = page.locator("form")
        button_loc = page.locator("button[type=submit], input[type=submit]")
        has_form = form_loc.count() > 0
        has_button = button_loc.count() > 0
        passed = has_form or has_button
        detail = f"form_count={form_loc.count()}, button_count={button_loc.count()}"
        conftest.test("P6.1", "Cancel page loads with form element", passed, detail, "HIGH")
    except Exception:
        conftest.test("P6.1", "Cancel page loads with form element", False,
                      traceback.format_exc(), "HIGH")
        conftest.take_failure_screenshot(page, "P6.1")


def test_p6_2(page):
    """P6.2: Cancel page with wrong token -> redirect or error."""
    try:
        bk = _create_fresh_booking(page, "p6_2", days_ahead=41, hour=10)
        if not bk:
            conftest.test("P6.2", "Cancel page with wrong token -> error", False,
                          "Failed to create fresh booking", "HIGH")
            return

        page.goto(_cancel_url(bk["id"], "WRONG_TOKEN"))
        page.wait_for_load_state("networkidle")

        current_url = page.url
        body_text = page.locator("body").inner_text().lower()

        # With a wrong token we expect either a redirect away from cancel page,
        # an error/403 status, or error text in the body.
        is_redirected = "/cancel" not in current_url
        has_error_text = any(
            kw in body_text
            for kw in ["error", "denied", "invalid", "not found", "unauthorized", "forbidden", "404", "403"]
        )
        passed = is_redirected or has_error_text
        detail = f"url={current_url}, error_text={has_error_text}"
        conftest.test("P6.2", "Cancel page with wrong token -> error", passed, detail, "HIGH")
    except Exception:
        conftest.test("P6.2", "Cancel page with wrong token -> error", False,
                      traceback.format_exc(), "HIGH")
        conftest.take_failure_screenshot(page, "P6.2")


def test_p6_3(page):
    """P6.3: Submit cancel -> state changes to 'cancelled' in DB."""
    try:
        bk = _create_fresh_booking(page, "p6_3", days_ahead=42, hour=11)
        if not bk:
            conftest.test("P6.3", "Submit cancel -> state=cancelled", False,
                          "Failed to create fresh booking", "CRITICAL")
            return

        page.goto(_cancel_url(bk["id"], bk["access_token"]))
        page.wait_for_load_state("networkidle")

        clicked = _click_cancel_button(page)
        if not clicked:
            conftest.test("P6.3", "Submit cancel -> state=cancelled", False,
                          "Could not find cancel submit button", "CRITICAL")
            conftest.take_failure_screenshot(page, "P6.3")
            return

        # Verify state in DB
        updated = conftest.read_booking(bk["id"])
        passed = updated and updated["state"] == "cancelled"
        detail = f"state={updated['state'] if updated else 'booking not found'}"
        conftest.test("P6.3", "Submit cancel -> state=cancelled", passed, detail, "CRITICAL")
    except Exception:
        conftest.test("P6.3", "Submit cancel -> state=cancelled", False,
                      traceback.format_exc(), "CRITICAL")
        conftest.take_failure_screenshot(page, "P6.3")


def test_p6_4(page):
    """P6.4: Cancel success page shows 'cancel' text."""
    try:
        bk = _create_fresh_booking(page, "p6_4", days_ahead=43, hour=12)
        if not bk:
            conftest.test("P6.4", "Cancel success page shows 'cancel' text", False,
                          "Failed to create fresh booking", "HIGH")
            return

        page.goto(_cancel_url(bk["id"], bk["access_token"]))
        page.wait_for_load_state("networkidle")

        clicked = _click_cancel_button(page)
        if not clicked:
            conftest.test("P6.4", "Cancel success page shows 'cancel' text", False,
                          "Could not find cancel submit button", "HIGH")
            conftest.take_failure_screenshot(page, "P6.4")
            return

        body_text = page.locator("body").inner_text().lower()
        passed = "cancel" in body_text
        detail = f"body contains 'cancel': {passed}, url={page.url}"
        conftest.test("P6.4", "Cancel success page shows 'cancel' text", passed, detail, "HIGH")
    except Exception:
        conftest.test("P6.4", "Cancel success page shows 'cancel' text", False,
                      traceback.format_exc(), "HIGH")
        conftest.take_failure_screenshot(page, "P6.4")


def test_p6_5(page):
    """P6.5: After cancel, calendar_event_id is False/empty."""
    try:
        bk = _create_fresh_booking(page, "p6_5", days_ahead=44, hour=13)
        if not bk:
            conftest.test("P6.5", "After cancel, calendar_event_id is False", False,
                          "Failed to create fresh booking", "HIGH")
            return

        # Read before cancel to note the calendar_event_id
        before = conftest.read_booking(bk["id"])
        cal_before = before.get("calendar_event_id") if before else None

        # Cancel
        page.goto(_cancel_url(bk["id"], bk["access_token"]))
        page.wait_for_load_state("networkidle")
        clicked = _click_cancel_button(page)
        if not clicked:
            conftest.test("P6.5", "After cancel, calendar_event_id is False", False,
                          "Could not find cancel submit button", "HIGH")
            conftest.take_failure_screenshot(page, "P6.5")
            return

        # Re-read after cancel
        after = conftest.read_booking(bk["id"])
        cal_after = after.get("calendar_event_id") if after else None
        passed = not cal_after  # Should be False/empty/None
        detail = f"before={cal_before}, after={cal_after}"
        conftest.test("P6.5", "After cancel, calendar_event_id is False", passed, detail, "HIGH")
    except Exception:
        conftest.test("P6.5", "After cancel, calendar_event_id is False", False,
                      traceback.format_exc(), "HIGH")
        conftest.take_failure_screenshot(page, "P6.5")


def test_p6_6(page):
    """P6.6: Cancel for future booking succeeds (cancel_hours=24, booking is days ahead)."""
    try:
        bk = _create_fresh_booking(page, "p6_6", days_ahead=45, hour=14)
        if not bk:
            conftest.test("P6.6", "Cancel for future booking succeeds", False,
                          "Failed to create fresh booking", "HIGH")
            return

        page.goto(_cancel_url(bk["id"], bk["access_token"]))
        page.wait_for_load_state("networkidle")

        clicked = _click_cancel_button(page)
        if not clicked:
            conftest.test("P6.6", "Cancel for future booking succeeds", False,
                          "Could not find cancel submit button", "HIGH")
            conftest.take_failure_screenshot(page, "P6.6")
            return

        updated = conftest.read_booking(bk["id"])
        passed = updated and updated["state"] == "cancelled"
        detail = f"state={updated['state'] if updated else 'not found'}, days_ahead=45"
        conftest.test("P6.6", "Cancel for future booking succeeds", passed, detail, "HIGH")
    except Exception:
        conftest.test("P6.6", "Cancel for future booking succeeds", False,
                      traceback.format_exc(), "HIGH")
        conftest.take_failure_screenshot(page, "P6.6")


def test_p6_7(page):
    """P6.7: Visit cancelled booking detail -> shows 'cancelled'."""
    try:
        bk = _create_fresh_booking(page, "p6_7", days_ahead=46, hour=15)
        if not bk:
            conftest.test("P6.7", "Cancelled booking detail shows 'cancelled'", False,
                          "Failed to create fresh booking", "MEDIUM")
            return

        # Cancel the booking first
        page.goto(_cancel_url(bk["id"], bk["access_token"]))
        page.wait_for_load_state("networkidle")
        _click_cancel_button(page)

        # Visit the booking detail page
        detail_url = f"{URL}/appointment/booking/{bk['id']}?token={bk['access_token']}"
        page.goto(detail_url)
        page.wait_for_load_state("networkidle")

        body_text = page.locator("body").inner_text().lower()
        passed = "cancel" in body_text
        detail = f"body contains 'cancel': {passed}, url={page.url}"
        conftest.test("P6.7", "Cancelled booking detail shows 'cancelled'", passed, detail, "MEDIUM")
    except Exception:
        conftest.test("P6.7", "Cancelled booking detail shows 'cancelled'", False,
                      traceback.format_exc(), "MEDIUM")
        conftest.take_failure_screenshot(page, "P6.7")


def test_p6_8(page):
    """P6.8: Cancel page shows booking info before confirming."""
    try:
        bk = _create_fresh_booking(page, "p6_8", days_ahead=47, hour=16)
        if not bk:
            conftest.test("P6.8", "Cancel page shows booking info", False,
                          "Failed to create fresh booking", "MEDIUM")
            return

        page.goto(_cancel_url(bk["id"], bk["access_token"]))
        page.wait_for_load_state("networkidle")

        body_text = page.locator("body").inner_text()
        body_lower = body_text.lower()

        # The cancel page should show the booking reference or the type name
        has_ref = bk["name"].lower() in body_lower if bk["name"] else False
        has_type = "business meeting" in body_lower or "meeting" in body_lower
        has_booking_info = has_ref or has_type
        passed = has_booking_info
        detail = f"has_ref={has_ref}, has_type={has_type}, booking_name={bk['name']}"
        conftest.test("P6.8", "Cancel page shows booking info", passed, detail, "MEDIUM")
    except Exception:
        conftest.test("P6.8", "Cancel page shows booking info", False,
                      traceback.format_exc(), "MEDIUM")
        conftest.take_failure_screenshot(page, "P6.8")


def test_p6_9(page):
    """P6.9: Cancel URL without token -> error."""
    try:
        bk = _create_fresh_booking(page, "p6_9", days_ahead=48, hour=9)
        if not bk:
            conftest.test("P6.9", "Cancel URL without token -> error", False,
                          "Failed to create fresh booking", "MEDIUM")
            return

        # Visit cancel URL with no token param at all
        no_token_url = f"{URL}/appointment/booking/{bk['id']}/cancel"
        page.goto(no_token_url)
        page.wait_for_load_state("networkidle")

        current_url = page.url
        body_text = page.locator("body").inner_text().lower()

        # Expect redirect or error text
        is_redirected = "/cancel" not in current_url
        has_error_text = any(
            kw in body_text
            for kw in ["error", "denied", "invalid", "not found", "unauthorized", "forbidden", "404", "403"]
        )
        # Also check: the cancel form should NOT be present without a valid token
        form_count = page.locator("form button[type=submit], form input[type=submit]").count()
        no_cancel_form = form_count == 0

        passed = is_redirected or has_error_text or no_cancel_form
        detail = (f"url={current_url}, redirected={is_redirected}, "
                  f"error_text={has_error_text}, no_form={no_cancel_form}")
        conftest.test("P6.9", "Cancel URL without token -> error", passed, detail, "MEDIUM")
    except Exception:
        conftest.test("P6.9", "Cancel URL without token -> error", False,
                      traceback.format_exc(), "MEDIUM")
        conftest.take_failure_screenshot(page, "P6.9")


def test_p6_10(page):
    """P6.10: After cancel, page has link to rebook (/appointment)."""
    try:
        bk = _create_fresh_booking(page, "p6_10", days_ahead=49, hour=10)
        if not bk:
            conftest.test("P6.10", "After cancel, page has rebook link", False,
                          "Failed to create fresh booking", "LOW")
            return

        page.goto(_cancel_url(bk["id"], bk["access_token"]))
        page.wait_for_load_state("networkidle")

        clicked = _click_cancel_button(page)
        if not clicked:
            conftest.test("P6.10", "After cancel, page has rebook link", False,
                          "Could not find cancel submit button", "LOW")
            conftest.take_failure_screenshot(page, "P6.10")
            return

        # Check for a link to /appointment in the page
        links = page.locator('a[href*="/appointment"]')
        passed = links.count() > 0
        detail = f"appointment_link_count={links.count()}, url={page.url}"
        conftest.test("P6.10", "After cancel, page has rebook link", passed, detail, "LOW")
    except Exception:
        conftest.test("P6.10", "After cancel, page has rebook link", False,
                      traceback.format_exc(), "LOW")
        conftest.take_failure_screenshot(page, "P6.10")


# ===================================================================
# run() -- entry point called by the test runner
# ===================================================================

def run():
    """Execute all P6 cancel tests. Returns conftest.get_results()."""
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

    print("\n=== P6: Cancel Booking Flow Tests (10 tests) ===\n")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)

    try:
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        test_p6_1(page)
        test_p6_2(page)
        test_p6_3(page)
        test_p6_4(page)
        test_p6_5(page)
        test_p6_6(page)
        test_p6_7(page)
        test_p6_8(page)
        test_p6_9(page)
        test_p6_10(page)

        context.close()
    except Exception:
        print(f"Fatal error in P6 suite: {traceback.format_exc()}")
    finally:
        # Cleanup all pw_p6_*@example.com test bookings
        print("\n--- Cleaning up P6 test bookings ---")
        for email in EMAILS.values():
            try:
                conftest.cleanup_test_bookings(email)
            except Exception:
                pass
        browser.close()
        pw.stop()

    results = conftest.get_results()
    passed = sum(1 for r in results if r["passed"])
    print(f"\n=== P6 Complete: {passed}/{len(results)} passed ===\n")
    return results


if __name__ == "__main__":
    run()
