# -*- coding: utf-8 -*-
"""P1 — /appointment listing page tests (8 tests)."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import conftest
from config import URL, TYPE_IDS, TYPE_CONFIG, UNPUBLISHED_TYPE_ID

from playwright.sync_api import sync_playwright


def run():
    conftest.clear_results()
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    listing_url = f"{URL}/appointment"

    # ── P1.1  GET returns 200 with DOCTYPE + html tag ────────────────
    tid = "P1.1"
    try:
        resp = page.goto(listing_url)
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        body = page.content()
        has_doctype = "<!DOCTYPE" in body.upper() or "<!doctype" in body.lower()
        has_html = "<html" in body.lower()
        passed = status == 200 and has_doctype and has_html
        conftest.test(
            tid,
            "GET /appointment returns 200 with DOCTYPE + html",
            passed,
            f"status={status} doctype={has_doctype} html={has_html}",
            severity="HIGH",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "GET /appointment returns 200 with DOCTYPE + html", False, str(exc), severity="HIGH")
        conftest.take_failure_screenshot(page, tid)

    # ── P1.2  All 5 published types visible ──────────────────────────
    tid = "P1.2"
    try:
        page.goto(listing_url)
        page.wait_for_load_state("networkidle")
        text = page.content().lower()
        expected_names = [
            "Business Meeting",
            "Video Consultation",
            "Restaurant Reservation",
            "Tennis Court Booking",
            "Expert Consultation",
        ]
        missing = [n for n in expected_names if n.lower() not in text]
        passed = len(missing) == 0
        conftest.test(
            tid,
            "All 5 published types visible on listing page",
            passed,
            f"missing={missing}" if missing else "all 5 found",
            severity="HIGH",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "All 5 published types visible on listing page", False, str(exc), severity="HIGH")
        conftest.take_failure_screenshot(page, tid)

    # ── P1.3  Unpublished type ID=6 NOT visible ──────────────────────
    tid = "P1.3"
    try:
        page.goto(listing_url)
        page.wait_for_load_state("networkidle")
        text = page.content().lower()
        has_unpublished_name = "test unpublished" in text
        has_unpublished_link = f"/appointment/{UNPUBLISHED_TYPE_ID}" in page.content()
        passed = not has_unpublished_name and not has_unpublished_link
        conftest.test(
            tid,
            "Unpublished type ID=6 NOT visible on listing",
            passed,
            f"name_found={has_unpublished_name} link_found={has_unpublished_link}",
            severity="HIGH",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Unpublished type ID=6 NOT visible on listing", False, str(exc), severity="HIGH")
        conftest.take_failure_screenshot(page, tid)

    # ── P1.4  Each type has "Book Now" link to /appointment/<id> ─────
    tid = "P1.4"
    try:
        page.goto(listing_url)
        page.wait_for_load_state("networkidle")
        missing_links = []
        for key, type_id in TYPE_IDS.items():
            link = page.locator(f'a[href*="/appointment/{type_id}"]')
            if link.count() == 0:
                missing_links.append(f"{key}(id={type_id})")
        passed = len(missing_links) == 0
        conftest.test(
            tid,
            "Each type has link to /appointment/<id>",
            passed,
            f"missing={missing_links}" if missing_links else "all links present",
            severity="MEDIUM",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Each type has link to /appointment/<id>", False, str(exc), severity="MEDIUM")
        conftest.take_failure_screenshot(page, tid)

    # ── P1.5  Each type name matches config ──────────────────────────
    tid = "P1.5"
    try:
        page.goto(listing_url)
        page.wait_for_load_state("networkidle")
        text = page.content().lower()
        mismatched = []
        for type_id, cfg in TYPE_CONFIG.items():
            expected_name = cfg["name"]
            if expected_name.lower() not in text:
                mismatched.append(f"id={type_id} name='{expected_name}'")
        passed = len(mismatched) == 0
        conftest.test(
            tid,
            "Each type name on page matches config",
            passed,
            f"mismatched={mismatched}" if mismatched else "all names match",
            severity="MEDIUM",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Each type name on page matches config", False, str(exc), severity="MEDIUM")
        conftest.take_failure_screenshot(page, tid)

    # ── P1.6  Page has header/nav and footer ─────────────────────────
    tid = "P1.6"
    try:
        page.goto(listing_url)
        page.wait_for_load_state("networkidle")
        has_header = (
            page.locator("header").count() > 0
            or page.locator("nav").count() > 0
        )
        has_footer = page.locator("footer").count() > 0
        passed = has_header and has_footer
        conftest.test(
            tid,
            "Page has header/nav and footer",
            passed,
            f"header/nav={has_header} footer={has_footer}",
            severity="LOW",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Page has header/nav and footer", False, str(exc), severity="LOW")
        conftest.take_failure_screenshot(page, tid)

    # ── P1.7  Mobile responsive at 375px ─────────────────────────────
    tid = "P1.7"
    try:
        mobile_context = browser.new_context(viewport={"width": 375, "height": 812})
        mobile_page = mobile_context.new_page()
        resp = mobile_page.goto(listing_url)
        mobile_page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        # Check no horizontal overflow — body scroll width should be <= viewport
        scroll_width = mobile_page.evaluate("document.body.scrollWidth")
        no_overflow = scroll_width <= 400  # small tolerance
        # At least one type name visible
        text = mobile_page.content().lower()
        has_content = "business meeting" in text or "restaurant" in text
        passed = status == 200 and no_overflow and has_content
        conftest.test(
            tid,
            "Mobile responsive at 375px viewport",
            passed,
            f"status={status} scrollW={scroll_width} overflow={not no_overflow} content={has_content}",
            severity="LOW",
        )
        if not passed:
            conftest.take_failure_screenshot(mobile_page, tid)
        mobile_page.close()
        mobile_context.close()
    except Exception as exc:
        conftest.test(tid, "Mobile responsive at 375px viewport", False, str(exc), severity="LOW")
        try:
            conftest.take_failure_screenshot(mobile_page, tid)
            mobile_page.close()
            mobile_context.close()
        except Exception:
            pass

    # ── P1.8  Unpublished type 6 not visible (published types 9,12 are OK) ──
    tid = "P1.8"
    try:
        page.goto(listing_url)
        page.wait_for_load_state("networkidle")
        html = page.content()
        # Type 6 is unpublished and should NOT appear
        unpub_visible = f"/appointment/{UNPUBLISHED_TYPE_ID}" in html
        # All 5 main published types (1-5) should be present
        main_types_present = all(f"/appointment/{i}" in html for i in range(1, 6))
        passed = not unpub_visible and main_types_present
        conftest.test(
            tid,
            "Unpublished type hidden, all 5 main types present",
            passed,
            f"unpub_visible={unpub_visible} main_types={main_types_present}",
            severity="MEDIUM",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Unpublished type hidden, all 5 main types present", False, str(exc), severity="MEDIUM")
        conftest.take_failure_screenshot(page, tid)

    # ── cleanup ──────────────────────────────────────────────────────
    page.close()
    browser.close()
    p.stop()
    return conftest.get_results()


if __name__ == "__main__":
    results = run()
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    print(f"\n{'='*60}")
    print(f"P1 Listing: {passed} passed, {failed} failed, {len(results)} total")
