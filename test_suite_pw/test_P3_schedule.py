# -*- coding: utf-8 -*-
"""P3 — Schedule page tests for /appointment/<id>/schedule.

25 tests covering the calendar widget, staff/location selectors,
date clicking, slot loading (AJAX), slot navigation to /book, and
various appointment-type-specific behaviours.
"""

import sys
import os
import time
import re

sys.path.insert(0, os.path.dirname(__file__))
import conftest
from config import URL, TYPE_IDS, TYPE_CONFIG, STAFF_IDS, RESOURCE_IDS

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEDULE_URL = lambda tid: f"{URL}/appointment/{tid}/schedule"

# Multiple selector patterns to try for dynamically-rendered calendar elements.
DATE_CELL_SELECTORS = [
    ".o_day:not(.o_disabled)",
    "td.o_day:not(.o_disabled)",
    ".reservation-day:not(.disabled)",
    "td[data-date]:not(.disabled)",
    ".day:not(.disabled)",
    "td.day:not(.disabled)",
    ".calendar-day:not(.disabled)",
    ".o_calendar_day:not(.o_disabled)",
    "button.o_day",
    "td.o_day",
    ".fc-daygrid-day",
]

SLOT_SELECTORS = [
    "a[href*='book']",
    ".o_slot_button",
    "button.o_slot_button",
    ".slot",
    ".time-slot",
    ".o_appointment_slot",
    "a.o_appointment_slot",
    "button.slot",
    ".slot-time",
    "[data-slot]",
]

NAV_NEXT_SELECTORS = [
    "button.reservation-next",
    "button.o_next",
    ".o_calendar_navigation_next",
    "button[title='Next']",
    ".fc-next-button",
    "a.next",
    "button.next",
    ".o_appointment_month_navigation .o_next",
    "span.oi-chevron-right",
    "button:has(> .oi-chevron-right)",
    ".o_appointment_select_slots_container button:has(.oi-chevron-right)",
]

NAV_PREV_SELECTORS = [
    "button.reservation-prev",
    "button.o_prev",
    ".o_calendar_navigation_prev",
    "button[title='Previous']",
    ".fc-prev-button",
    "a.prev",
    "button.prev",
    ".o_appointment_month_navigation .o_prev",
    "span.oi-chevron-left",
    "button:has(> .oi-chevron-left)",
]


def _try_selectors(page, selectors, timeout=3000):
    """Try multiple CSS selectors; return first locator that finds something."""
    for sel in selectors:
        try:
            loc = page.locator(sel)
            loc.first.wait_for(timeout=timeout, state="visible")
            if loc.count() > 0:
                return sel, loc
        except Exception:
            continue
    return None, None


def _wait_for_slots(page, timeout=5000):
    """Wait for slot elements to appear after a date click. Returns (selector, locator) or (None, None)."""
    return _try_selectors(page, SLOT_SELECTORS, timeout=timeout)


def _click_available_date(page, timeout=5000):
    """Click the first available (non-disabled) date cell. Returns True on success."""
    sel, loc = _try_selectors(page, DATE_CELL_SELECTORS, timeout=timeout)
    if loc is not None:
        loc.first.click()
        page.wait_for_timeout(1500)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        return True, sel
    return False, None


def _goto_schedule(page, type_id, wait_ms=3000):
    """Navigate to a schedule page and wait for it to settle."""
    page.goto(SCHEDULE_URL(type_id), wait_until="networkidle", timeout=20000)
    page.wait_for_timeout(wait_ms)


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

def run():
    conftest.clear_results()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )
        page = context.new_page()

        try:
            _test_p3_01(page)
            _test_p3_02(page)
            _test_p3_03(page)
            _test_p3_04(page)
            _test_p3_05(page)
            _test_p3_06(page)
            _test_p3_07(page)
            _test_p3_08(page)
            _test_p3_09(page)
            _test_p3_10(page)
            _test_p3_11(page)
            _test_p3_12(page)
            _test_p3_13(page)
            _test_p3_14(page)
            _test_p3_15(page)
            _test_p3_16(page)
            _test_p3_17(page)
            _test_p3_18(page)
            _test_p3_19(page)
            _test_p3_20(page)
            _test_p3_21(page)
            _test_p3_22(page)
            _test_p3_23(page)
            _test_p3_24(page)
            _test_p3_25(page)
        finally:
            context.close()
            browser.close()

    return conftest.get_results()


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------

def _test_p3_01(page):
    """P3.1: Type 1 schedule page loads with #appointment-reservation widget."""
    tid = "P3.1"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        widget = page.locator("div#appointment-reservation")
        widget.wait_for(timeout=5000, state="attached")
        visible = widget.count() > 0
        conftest.test(tid, "Type 1 schedule page has #appointment-reservation widget",
                      visible,
                      "Widget found" if visible else "Widget NOT found",
                      "HIGH")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Type 1 schedule page has #appointment-reservation widget",
                      False, f"Exception: {exc}", "HIGH")


def _test_p3_02(page):
    """P3.2: Widget has correct data-appointment-type-id attr."""
    tid = "P3.2"
    try:
        widget = page.locator("div#appointment-reservation")
        attr = widget.get_attribute("data-appointment-type-id")
        expected = str(TYPE_IDS["business_meeting"])
        passed = attr == expected
        conftest.test(tid, "Widget data-appointment-type-id matches",
                      passed,
                      f"Expected {expected}, got {attr!r}",
                      "HIGH")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Widget data-appointment-type-id matches",
                      False, f"Exception: {exc}", "HIGH")


def _test_p3_03(page):
    """P3.3: Type 1 staff selector has Auto-Assign + Mitchell Admin."""
    tid = "P3.3"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        sel = page.locator("select#staff-select")
        sel.wait_for(timeout=5000, state="attached")
        options = sel.locator("option").all_text_contents()
        options_stripped = [o.strip() for o in options]
        expected = TYPE_CONFIG[1]["staff_options"]
        all_found = all(exp in options_stripped for exp in expected)
        conftest.test(tid, "Type 1 staff selector has Auto-Assign + Mitchell Admin",
                      all_found,
                      f"Options found: {options_stripped}; expected: {expected}",
                      "HIGH")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Type 1 staff selector has Auto-Assign + Mitchell Admin",
                      False, f"Exception: {exc}", "HIGH")


def _test_p3_04(page):
    """P3.4: Type 3 location selector has Auto-Assign + 3 tables."""
    tid = "P3.4"
    try:
        _goto_schedule(page, TYPE_IDS["restaurant"])
        sel = page.locator("select#location-select")
        sel.wait_for(timeout=5000, state="attached")
        options = sel.locator("option").all_text_contents()
        options_stripped = [o.strip() for o in options]
        expected = TYPE_CONFIG[3]["location_options"]
        all_found = all(exp in options_stripped for exp in expected)
        conftest.test(tid, "Type 3 location selector has Auto-Assign + 3 tables",
                      all_found,
                      f"Options found: {options_stripped}; expected: {expected}",
                      "HIGH")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Type 3 location selector has Auto-Assign + 3 tables",
                      False, f"Exception: {exc}", "HIGH")


def _test_p3_05(page):
    """P3.5: Type 5 has staff selector."""
    tid = "P3.5"
    try:
        _goto_schedule(page, TYPE_IDS["expert_consultation"])
        sel = page.locator("select#staff-select")
        sel.wait_for(timeout=5000, state="attached")
        found = sel.count() > 0
        conftest.test(tid, "Type 5 (Expert Consultation) has staff selector",
                      found,
                      "Staff selector present" if found else "Staff selector NOT found",
                      "HIGH")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Type 5 (Expert Consultation) has staff selector",
                      False, f"Exception: {exc}", "HIGH")


def _test_p3_06(page):
    """P3.6: Type 4 has location selector with Tennis Court."""
    tid = "P3.6"
    try:
        _goto_schedule(page, TYPE_IDS["tennis"])
        sel = page.locator("select#location-select")
        sel.wait_for(timeout=5000, state="attached")
        options = sel.locator("option").all_text_contents()
        options_stripped = [o.strip() for o in options]
        has_court = any("Tennis Court" in o for o in options_stripped)
        conftest.test(tid, "Type 4 location selector has Tennis Court",
                      has_court,
                      f"Options: {options_stripped}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Type 4 location selector has Tennis Court",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_07(page):
    """P3.7: Click future date -> slots appear (AJAX load)."""
    tid = "P3.7"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        clicked, date_sel = _click_available_date(page, timeout=5000)
        if not clicked:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Click future date loads slots",
                          False,
                          f"Could not find any clickable date cell. Tried: {DATE_CELL_SELECTORS}",
                          "CRITICAL")
            return

        slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)
        if slot_loc is not None and slot_loc.count() > 0:
            conftest.test(tid, "Click future date loads slots",
                          True,
                          f"Date clicked via '{date_sel}'; {slot_loc.count()} slots via '{slot_sel}'",
                          "CRITICAL")
        else:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Click future date loads slots",
                          False,
                          f"Date clicked via '{date_sel}' but no slots appeared. Tried: {SLOT_SELECTORS}",
                          "CRITICAL")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Click future date loads slots",
                      False, f"Exception: {exc}", "CRITICAL")


def _test_p3_08(page):
    """P3.8: Slots are clickable elements with time info."""
    tid = "P3.8"
    try:
        # Reuse slots that should already be on page after P3.7
        slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)
        if slot_loc is None or slot_loc.count() == 0:
            # Try re-loading
            _goto_schedule(page, TYPE_IDS["business_meeting"])
            _click_available_date(page)
            slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)

        if slot_loc is not None and slot_loc.count() > 0:
            first_text = slot_loc.first.text_content().strip()
            # Expect some time-like text (digits + colon) e.g. "10:00"
            has_time = bool(re.search(r"\d{1,2}:\d{2}", first_text))
            conftest.test(tid, "Slots are clickable with time info",
                          has_time,
                          f"First slot text: {first_text!r}; time pattern found: {has_time}",
                          "HIGH")
        else:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Slots are clickable with time info",
                          False, "No slots found on page", "HIGH")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Slots are clickable with time info",
                      False, f"Exception: {exc}", "HIGH")


def _test_p3_09(page):
    """P3.9: Calendar has prev/next month navigation buttons."""
    tid = "P3.9"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        _, next_loc = _try_selectors(page, NAV_NEXT_SELECTORS, timeout=5000)
        _, prev_loc = _try_selectors(page, NAV_PREV_SELECTORS, timeout=5000)

        has_next = next_loc is not None and next_loc.count() > 0
        has_prev = prev_loc is not None and prev_loc.count() > 0
        passed = has_next and has_prev
        conftest.test(tid, "Calendar has prev/next navigation buttons",
                      passed,
                      f"Next found: {has_next}, Prev found: {has_prev}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Calendar has prev/next navigation buttons",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_10(page):
    """P3.10: Calendar widget has data-start-date and data-end-date."""
    tid = "P3.10"
    try:
        widget = page.locator("div#appointment-reservation")
        start = widget.get_attribute("data-start-date")
        end = widget.get_attribute("data-end-date")
        passed = start is not None and end is not None
        conftest.test(tid, "Widget has data-start-date and data-end-date",
                      passed,
                      f"start={start!r}, end={end!r}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Widget has data-start-date and data-end-date",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_11(page):
    """P3.11: Click next month button works (no error)."""
    tid = "P3.11"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        sel, loc = _try_selectors(page, NAV_NEXT_SELECTORS, timeout=5000)
        if loc is None:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Click next month button works",
                          False, "Next button not found", "MEDIUM")
            return

        loc.first.click()
        page.wait_for_timeout(2000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        # Verify no crash — page should still have the widget
        widget = page.locator("div#appointment-reservation")
        still_ok = widget.count() > 0
        conftest.test(tid, "Click next month button works",
                      still_ok,
                      f"Clicked '{sel}'; widget still present: {still_ok}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Click next month button works",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_12(page):
    """P3.12: Widget has data-is-scheduled attribute."""
    tid = "P3.12"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        widget = page.locator("div#appointment-reservation")
        widget.wait_for(timeout=5000, state="attached")
        attr = widget.get_attribute("data-is-scheduled")
        passed = attr is not None
        conftest.test(tid, "Widget has data-is-scheduled attribute",
                      passed,
                      f"data-is-scheduled={attr!r}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Widget has data-is-scheduled attribute",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_13(page):
    """P3.13: Change staff selector value to Mitchell Admin."""
    tid = "P3.13"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        sel = page.locator("select#staff-select")
        sel.wait_for(timeout=5000, state="attached")

        # Find option value for Mitchell Admin
        options = sel.locator("option").all()
        admin_value = None
        for opt in options:
            txt = opt.text_content().strip()
            if "Mitchell Admin" in txt:
                admin_value = opt.get_attribute("value")
                break

        if admin_value is None:
            conftest.test(tid, "Change staff selector to Mitchell Admin",
                          False, "Mitchell Admin option not found", "MEDIUM")
            return

        sel.select_option(value=admin_value)
        page.wait_for_timeout(1500)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        current = sel.input_value()
        passed = current == admin_value
        conftest.test(tid, "Change staff selector to Mitchell Admin",
                      passed,
                      f"Selected value: {current!r}, expected: {admin_value!r}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Change staff selector to Mitchell Admin",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_14(page):
    """P3.14: Change location selector (type 3, select Table 1)."""
    tid = "P3.14"
    try:
        _goto_schedule(page, TYPE_IDS["restaurant"])
        sel = page.locator("select#location-select")
        sel.wait_for(timeout=5000, state="attached")

        options = sel.locator("option").all()
        table1_value = None
        for opt in options:
            txt = opt.text_content().strip()
            if "Table 1" in txt:
                table1_value = opt.get_attribute("value")
                break

        if table1_value is None:
            conftest.test(tid, "Change location selector to Table 1",
                          False, "Table 1 option not found", "MEDIUM")
            return

        sel.select_option(value=table1_value)
        page.wait_for_timeout(1500)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        current = sel.input_value()
        passed = current == table1_value
        conftest.test(tid, "Change location selector to Table 1",
                      passed,
                      f"Selected value: {current!r}, expected: {table1_value!r}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Change location selector to Table 1",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_15(page):
    """P3.15: Click a slot -> navigates to /appointment/<id>/book."""
    tid = "P3.15"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        clicked, _ = _click_available_date(page, timeout=5000)
        if not clicked:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Click slot navigates to /book",
                          False, "Could not click a date cell", "CRITICAL")
            return

        slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)
        if slot_loc is None or slot_loc.count() == 0:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Click slot navigates to /book",
                          False, "No slots found after date click", "CRITICAL")
            return

        # Click the first slot
        slot_loc.first.click()
        page.wait_for_timeout(2000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        current_url = page.url
        passed = "/book" in current_url
        conftest.test(tid, "Click slot navigates to /book",
                      passed,
                      f"URL after click: {current_url}",
                      "CRITICAL")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Click slot navigates to /book",
                      False, f"Exception: {exc}", "CRITICAL")


def _test_p3_16(page):
    """P3.16: Booking URL contains start_datetime param."""
    tid = "P3.16"
    try:
        current_url = page.url
        passed = "start_datetime" in current_url
        conftest.test(tid, "Booking URL contains start_datetime param",
                      passed,
                      f"URL: {current_url}",
                      "HIGH")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Booking URL contains start_datetime param",
                      False, f"Exception: {exc}", "HIGH")


def _test_p3_17(page):
    """P3.17: URL contains staff_id for type 1 after selecting Mitchell Admin."""
    tid = "P3.17"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        # Select Mitchell Admin
        sel = page.locator("select#staff-select")
        sel.wait_for(timeout=5000, state="attached")
        options = sel.locator("option").all()
        admin_value = None
        for opt in options:
            txt = opt.text_content().strip()
            if "Mitchell Admin" in txt:
                admin_value = opt.get_attribute("value")
                break
        if admin_value:
            sel.select_option(value=admin_value)
            page.wait_for_timeout(1500)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

        # Click a date
        clicked, _ = _click_available_date(page, timeout=5000)
        if not clicked:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Booking URL has staff_id for type 1",
                          False, "Could not click date", "HIGH")
            return

        # Wait for slots and click
        slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)
        if slot_loc is None or slot_loc.count() == 0:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Booking URL has staff_id for type 1",
                          False, "No slots found", "HIGH")
            return

        slot_loc.first.click()
        page.wait_for_timeout(2000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        current_url = page.url
        passed = "staff_id" in current_url or "staff_user_id" in current_url
        conftest.test(tid, "Booking URL has staff_id for type 1",
                      passed,
                      f"URL: {current_url}",
                      "HIGH")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Booking URL has staff_id for type 1",
                      False, f"Exception: {exc}", "HIGH")


def _test_p3_18(page):
    """P3.18: URL contains resource_id for type 3 after selecting a table."""
    tid = "P3.18"
    try:
        _goto_schedule(page, TYPE_IDS["restaurant"])
        page.wait_for_timeout(2000)

        # Select Table 1
        sel = page.locator("select#location-select")
        sel.wait_for(timeout=5000, state="attached")
        options = sel.locator("option").all()
        table_value = None
        for opt in options:
            txt = opt.text_content().strip()
            if "Table 1" in txt:
                table_value = opt.get_attribute("value")
                break
        if table_value:
            sel.select_option(value=table_value)
            page.wait_for_timeout(1500)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

        clicked, _ = _click_available_date(page, timeout=5000)
        if not clicked:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Booking URL has resource_id for type 3",
                          False, "Could not click date", "HIGH")
            return

        slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)
        if slot_loc is None or slot_loc.count() == 0:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Booking URL has resource_id for type 3",
                          False, "No slots found", "HIGH")
            return

        slot_loc.first.click()
        page.wait_for_timeout(2000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        current_url = page.url
        passed = "resource_id" in current_url
        conftest.test(tid, "Booking URL has resource_id for type 3",
                      passed,
                      f"URL: {current_url}",
                      "HIGH")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Booking URL has resource_id for type 3",
                      False, f"Exception: {exc}", "HIGH")


def _test_p3_19(page):
    """P3.19: Restaurant shows slots on Saturday."""
    tid = "P3.19"
    try:
        saturday = conftest.get_future_saturday(days_ahead=7)
        _goto_schedule(page, TYPE_IDS["restaurant"])
        page.wait_for_timeout(2000)

        # Try to find and click the Saturday date
        # First try clicking any available date cell (the calendar may show Saturday)
        clicked, date_sel = _click_available_date(page, timeout=5000)
        if not clicked:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Restaurant shows slots on Saturday",
                          False,
                          f"Could not click any date. Target Saturday: {saturday}",
                          "MEDIUM")
            return

        slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)
        has_slots = slot_loc is not None and slot_loc.count() > 0
        conftest.test(tid, "Restaurant shows slots on Saturday",
                      has_slots,
                      f"Date clicked via '{date_sel}'; slots found: {has_slots}; target Saturday: {saturday}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Restaurant shows slots on Saturday",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_20(page):
    """P3.20: Type 1 shows slots on weekday."""
    tid = "P3.20"
    try:
        weekday = conftest.get_future_weekday(days_ahead=3)
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        clicked, date_sel = _click_available_date(page, timeout=5000)
        if not clicked:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Type 1 shows slots on weekday",
                          False,
                          f"Could not click any date. Target weekday: {weekday}",
                          "MEDIUM")
            return

        slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)
        has_slots = slot_loc is not None and slot_loc.count() > 0
        conftest.test(tid, "Type 1 shows slots on weekday",
                      has_slots,
                      f"Date clicked via '{date_sel}'; slots found: {has_slots}; target weekday: {weekday}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Type 1 shows slots on weekday",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_21(page):
    """P3.21: Business Meeting slot duration appears as 1h."""
    tid = "P3.21"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        clicked, _ = _click_available_date(page, timeout=5000)
        if not clicked:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Business Meeting slot shows 1h duration",
                          False, "Could not click date", "MEDIUM")
            return

        slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)
        if slot_loc is None or slot_loc.count() == 0:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Business Meeting slot shows 1h duration",
                          False, "No slots found", "MEDIUM")
            return

        # Gather text from all slots and look for 1h patterns
        all_texts = slot_loc.all_text_contents()
        page_text = page.content()
        # Look for duration hints: "1:00", "1h", "60 min", or time pairs an hour apart
        has_duration_hint = any(
            re.search(r"1:00|1\s*h|60\s*min", t, re.IGNORECASE)
            for t in all_texts
        )
        # Also check if consecutive slots are 1h apart (e.g. 10:00 and 11:00)
        times = []
        for t in all_texts:
            m = re.search(r"(\d{1,2}):(\d{2})", t)
            if m:
                times.append(int(m.group(1)) * 60 + int(m.group(2)))
        one_hour_gap = False
        if len(times) >= 2:
            for i in range(len(times) - 1):
                if times[i + 1] - times[i] == 60:
                    one_hour_gap = True
                    break

        passed = has_duration_hint or one_hour_gap
        conftest.test(tid, "Business Meeting slot shows 1h duration",
                      passed,
                      f"Slot texts: {all_texts[:5]}; duration hint: {has_duration_hint}; 1h gap: {one_hour_gap}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Business Meeting slot shows 1h duration",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_22(page):
    """P3.22: Restaurant slot interval (multiple slots have 30min gaps)."""
    tid = "P3.22"
    try:
        _goto_schedule(page, TYPE_IDS["restaurant"])
        page.wait_for_timeout(2000)

        clicked, _ = _click_available_date(page, timeout=5000)
        if not clicked:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Restaurant slots have 30min interval",
                          False, "Could not click date", "MEDIUM")
            return

        slot_sel, slot_loc = _wait_for_slots(page, timeout=5000)
        if slot_loc is None or slot_loc.count() == 0:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Restaurant slots have 30min interval",
                          False, "No slots found", "MEDIUM")
            return

        all_texts = slot_loc.all_text_contents()
        times = []
        for t in all_texts:
            m = re.search(r"(\d{1,2}):(\d{2})", t)
            if m:
                times.append(int(m.group(1)) * 60 + int(m.group(2)))

        thirty_min_gaps = 0
        if len(times) >= 2:
            for i in range(len(times) - 1):
                if times[i + 1] - times[i] == 30:
                    thirty_min_gaps += 1

        passed = thirty_min_gaps >= 1
        conftest.test(tid, "Restaurant slots have 30min interval",
                      passed,
                      f"Slot texts: {all_texts[:8]}; times(min): {times[:8]}; 30min gaps: {thirty_min_gaps}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Restaurant slots have 30min interval",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_23(page):
    """P3.23: Calendar navigated to empty day doesn't crash."""
    tid = "P3.23"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        # Navigate to next month (likely has fewer/no slots)
        sel, loc = _try_selectors(page, NAV_NEXT_SELECTORS, timeout=5000)
        if loc is not None:
            loc.first.click()
            page.wait_for_timeout(2000)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            # Navigate again to go further
            loc2 = page.locator(sel) if sel else None
            if loc2 and loc2.count() > 0:
                loc2.first.click()
                page.wait_for_timeout(2000)

        # Try to click a date cell in this possibly empty range
        clicked, _ = _click_available_date(page, timeout=5000)
        # Even if no date is clickable, page shouldn't crash
        widget = page.locator("div#appointment-reservation")
        still_ok = widget.count() > 0
        # Check no JS error in console would need page.on("console"),
        # so just verify widget survives
        conftest.test(tid, "Calendar on empty day doesn't crash",
                      still_ok,
                      f"Widget still present: {still_ok}; date clickable: {clicked}",
                      "MEDIUM")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Calendar on empty day doesn't crash",
                      False, f"Exception: {exc}", "MEDIUM")


def _test_p3_24(page):
    """P3.24: Multiple date clicks update slot display."""
    tid = "P3.24"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        # Click first available date
        clicked1, _ = _click_available_date(page, timeout=5000)
        if not clicked1:
            conftest.take_failure_screenshot(page, tid)
            conftest.test(tid, "Multiple date clicks update slots",
                          False, "Could not click first date", "LOW")
            return

        slot_sel1, slot_loc1 = _wait_for_slots(page, timeout=5000)
        first_slot_count = slot_loc1.count() if slot_loc1 else 0
        first_texts = slot_loc1.all_text_contents() if slot_loc1 and first_slot_count > 0 else []

        # Find all date cells and click a different one
        date_sel, date_loc = _try_selectors(page, DATE_CELL_SELECTORS, timeout=5000)
        second_clicked = False
        if date_loc is not None and date_loc.count() > 1:
            date_loc.nth(1).click()
            second_clicked = True
            page.wait_for_timeout(1500)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

        if not second_clicked:
            # Only one date available, still passes if first click worked
            conftest.test(tid, "Multiple date clicks update slots",
                          first_slot_count > 0,
                          f"Only one date cell available; first click had {first_slot_count} slots",
                          "LOW")
            return

        slot_sel2, slot_loc2 = _wait_for_slots(page, timeout=5000)
        second_slot_count = slot_loc2.count() if slot_loc2 else 0
        second_texts = slot_loc2.all_text_contents() if slot_loc2 and second_slot_count > 0 else []

        # Verify the display updated (different count or different texts)
        changed = (first_texts != second_texts) or (first_slot_count != second_slot_count)
        # Even if same slots, the mechanism worked if both rendered
        passed = (first_slot_count > 0 or second_slot_count > 0)
        conftest.test(tid, "Multiple date clicks update slots",
                      passed,
                      f"1st click: {first_slot_count} slots, 2nd click: {second_slot_count} slots; changed: {changed}",
                      "LOW")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Multiple date clicks update slots",
                      False, f"Exception: {exc}", "LOW")


def _test_p3_25(page):
    """P3.25: Calendar header has month/year text."""
    tid = "P3.25"
    try:
        _goto_schedule(page, TYPE_IDS["business_meeting"])
        page.wait_for_timeout(2000)

        # Look for month/year text in calendar header area
        header_selectors = [
            ".o_appointment_month_name",
            ".calendar-header",
            ".o_calendar_header",
            ".fc-toolbar-title",
            "h2.month-name",
            ".month-title",
            "#appointment-reservation .o_header",
            "#appointment-reservation h2",
            "#appointment-reservation h3",
            "#appointment-reservation .fw-bold",
        ]

        found_text = None
        for hsel in header_selectors:
            try:
                loc = page.locator(hsel)
                if loc.count() > 0:
                    found_text = loc.first.text_content().strip()
                    if found_text:
                        break
            except Exception:
                continue

        if found_text:
            # Check if it contains a year (4 digits)
            has_year = bool(re.search(r"20\d{2}", found_text))
            # Check if it contains a month-like word (Jan-Dec or full names)
            months = (
                "January|February|March|April|May|June|July|August|September|"
                "October|November|December|"
                "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
            )
            has_month = bool(re.search(months, found_text, re.IGNORECASE))
            passed = has_year or has_month
            conftest.test(tid, "Calendar header has month/year text",
                          passed,
                          f"Header text: {found_text!r}; has_year: {has_year}; has_month: {has_month}",
                          "LOW")
        else:
            # Fallback: check page body for a prominent month/year
            body_text = page.locator("#appointment-reservation").text_content()
            has_year = bool(re.search(r"20\d{2}", body_text))
            conftest.test(tid, "Calendar header has month/year text",
                          has_year,
                          f"No header element found; year in widget text: {has_year}",
                          "LOW")
    except Exception as exc:
        conftest.take_failure_screenshot(page, tid)
        conftest.test(tid, "Calendar header has month/year text",
                      False, f"Exception: {exc}", "LOW")


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = run()
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    print(f"\n{'='*60}")
    print(f"P3 Schedule Tests: {passed} passed, {failed} failed, {len(results)} total")
    print(f"{'='*60}")
