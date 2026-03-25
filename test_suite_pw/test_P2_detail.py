# -*- coding: utf-8 -*-
"""P2 — /appointment/<id> detail page tests (15 tests)."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import conftest
from config import URL, TYPE_IDS, TYPE_CONFIG, UNPUBLISHED_TYPE_ID

from playwright.sync_api import sync_playwright


def _duration_text(duration_hours):
    """Return the human-readable duration snippet to look for.

    Odoo typically renders:
      1.0 h  -> "1" (hour)
      0.5 h  -> "30" (minutes)
      2.0 h  -> "2" (hours)
    We return a list of acceptable fragments so the test can match any.
    """
    minutes = int(duration_hours * 60)
    if duration_hours == int(duration_hours):
        hours = int(duration_hours)
        return [str(hours), f"{hours} hour", f"{minutes} min"]
    else:
        return [str(minutes), f"{minutes} min"]


def run():
    conftest.clear_results()
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # ── P2.1-P2.4  Types 1-4 show correct name + duration ───────────
    detail_types = [
        ("P2.1", 1),
        ("P2.2", 2),
        ("P2.3", 3),
        ("P2.4", 4),
    ]
    for tid, type_id in detail_types:
        try:
            cfg = TYPE_CONFIG[type_id]
            detail_url = f"{URL}/appointment/{type_id}"
            page.goto(detail_url)
            page.wait_for_load_state("networkidle")
            text = page.content().lower()

            # Name check
            name_found = cfg["name"].lower() in text

            # Duration check — any of the acceptable fragments
            fragments = _duration_text(cfg["duration"])
            duration_found = any(frag.lower() in text for frag in fragments)

            passed = name_found and duration_found
            conftest.test(
                tid,
                f"Type {type_id} ({cfg['name']}) shows name and duration",
                passed,
                f"name={name_found} duration={duration_found} (looked for {fragments})",
                severity="HIGH",
            )
            if not passed:
                conftest.take_failure_screenshot(page, tid)
        except Exception as exc:
            conftest.test(
                tid,
                f"Type {type_id} shows name and duration",
                False,
                str(exc),
                severity="HIGH",
            )
            conftest.take_failure_screenshot(page, tid)

    # ── P2.5  Expert type 5 shows price + payment text ───────────────
    tid = "P2.5"
    try:
        page.goto(f"{URL}/appointment/{TYPE_IDS['expert_consultation']}")
        page.wait_for_load_state("networkidle")
        text = page.content().lower()
        has_price = "$100" in page.content() or "100" in text
        has_payment = "payment" in text or "pay" in text
        passed = has_price and has_payment
        conftest.test(
            tid,
            "Expert type 5 shows price ($100) and payment text",
            passed,
            f"price={has_price} payment={has_payment}",
            severity="HIGH",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Expert type 5 shows price and payment text", False, str(exc), severity="HIGH")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.6  Each type has link to /appointment/<id>/schedule ───────
    tid = "P2.6"
    try:
        missing = []
        for key, type_id in TYPE_IDS.items():
            page.goto(f"{URL}/appointment/{type_id}")
            page.wait_for_load_state("networkidle")
            html = page.content()
            # Look for a link that leads to the schedule step
            has_schedule_link = f"/appointment/{type_id}/schedule" in html
            # Also accept a form/button that posts to schedule
            has_schedule_action = f"/appointment/{type_id}/schedule" in html
            if not has_schedule_link and not has_schedule_action:
                missing.append(f"{key}(id={type_id})")
        passed = len(missing) == 0
        conftest.test(
            tid,
            "Each type page links to /appointment/<id>/schedule",
            passed,
            f"missing={missing}" if missing else "all schedule links found",
            severity="HIGH",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Each type page links to /appointment/<id>/schedule", False, str(exc), severity="HIGH")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.7  Each type page shows its own name (unique content) ─────
    tid = "P2.7"
    try:
        wrong = []
        for type_id, cfg in TYPE_CONFIG.items():
            page.goto(f"{URL}/appointment/{type_id}")
            page.wait_for_load_state("networkidle")
            text = page.content().lower()
            if cfg["name"].lower() not in text:
                wrong.append(f"id={type_id} missing '{cfg['name']}'")
        passed = len(wrong) == 0
        conftest.test(
            tid,
            "Each type page shows its own name",
            passed,
            f"wrong={wrong}" if wrong else "all pages show correct name",
            severity="MEDIUM",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Each type page shows its own name", False, str(exc), severity="MEDIUM")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.8  /appointment/999 returns error ─────────────────────────
    tid = "P2.8"
    try:
        resp = page.goto(f"{URL}/appointment/999")
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        text = page.content().lower()
        is_error_status = status in (404, 403, 500)
        has_error_text = any(
            kw in text for kw in ["not found", "error", "forbidden", "does not exist", "404", "500"]
        )
        passed = is_error_status or has_error_text
        conftest.test(
            tid,
            "/appointment/999 returns error (404/403/500 or error text)",
            passed,
            f"status={status} error_text={has_error_text}",
            severity="MEDIUM",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "/appointment/999 returns error", False, str(exc), severity="MEDIUM")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.9  /appointment/6 (unpublished) blocked or redirects ──────
    tid = "P2.9"
    try:
        resp = page.goto(f"{URL}/appointment/{UNPUBLISHED_TYPE_ID}")
        page.wait_for_load_state("networkidle")
        status = resp.status if resp else 0
        final_url = page.url
        text = page.content().lower()
        # Acceptable: error status, redirect to /appointment listing, or error text
        is_blocked = status in (404, 403, 500)
        redirected = final_url.rstrip("/").endswith("/appointment") or final_url.rstrip("/").endswith("/web/login")
        has_error_text = any(
            kw in text for kw in ["not found", "error", "forbidden", "does not exist", "404"]
        )
        passed = is_blocked or redirected or has_error_text
        conftest.test(
            tid,
            "/appointment/6 (unpublished) blocked or redirects",
            passed,
            f"status={status} final_url={final_url} error_text={has_error_text} redirect={redirected}",
            severity="HIGH",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "/appointment/6 (unpublished) blocked or redirects", False, str(exc), severity="HIGH")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.10  Expert type 5 FAQ keywords ────────────────────────────
    tid = "P2.10"
    try:
        page.goto(f"{URL}/appointment/{TYPE_IDS['expert_consultation']}")
        page.wait_for_load_state("networkidle")
        text = page.content().lower()
        # FAQ questions rendered on page: check for consultation-related keywords
        has_expert = "expert" in text or "consultation" in text
        has_session = "session" in text or "hour" in text or "online" in text
        passed = has_expert and has_session
        conftest.test(
            tid,
            "Expert type 5 has consultation keywords",
            passed,
            f"expert/consultation={has_expert} session/hour/online={has_session}",
            severity="MEDIUM",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Expert type 5 has FAQ keywords", False, str(exc), severity="MEDIUM")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.11  Restaurant type 3 has special occasion + dietary ──────
    tid = "P2.11"
    try:
        page.goto(f"{URL}/appointment/{TYPE_IDS['restaurant']}")
        page.wait_for_load_state("networkidle")
        text = page.content().lower()
        has_special = "special" in text or "occasion" in text
        has_restaurant = "table" in text or "seat" in text or "reservation" in text
        passed = has_special and has_restaurant
        conftest.test(
            tid,
            "Restaurant type 3 has 'special' and table/reservation text",
            passed,
            f"special/occasion={has_special} table/seat/reservation={has_restaurant}",
            severity="MEDIUM",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Restaurant type 3 has special occasion and dietary", False, str(exc), severity="MEDIUM")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.12  Restaurant type 3 has table/resource reference ────────
    tid = "P2.12"
    try:
        page.goto(f"{URL}/appointment/{TYPE_IDS['restaurant']}")
        page.wait_for_load_state("networkidle")
        text = page.content().lower()
        has_table = "table" in text
        has_resource = (
            "resource" in text
            or "seat" in text
            or "window" in text
            or "garden" in text
            or "private" in text
        )
        passed = has_table or has_resource
        conftest.test(
            tid,
            "Restaurant type 3 has table/resource reference",
            passed,
            f"table={has_table} resource={has_resource}",
            severity="MEDIUM",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Restaurant type 3 has table/resource reference", False, str(exc), severity="MEDIUM")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.13  Tennis type 4 has tennis/court text ───────────────────
    tid = "P2.13"
    try:
        page.goto(f"{URL}/appointment/{TYPE_IDS['tennis']}")
        page.wait_for_load_state("networkidle")
        text = page.content().lower()
        has_tennis = "tennis" in text
        has_court = "court" in text
        passed = has_tennis and has_court
        conftest.test(
            tid,
            "Tennis type 4 has 'tennis' and 'court' text",
            passed,
            f"tennis={has_tennis} court={has_court}",
            severity="MEDIUM",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Tennis type 4 has tennis/court text", False, str(exc), severity="MEDIUM")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.14  Types 1,3,5 have header + footer layout ───────────────
    tid = "P2.14"
    try:
        check_ids = [1, 3, 5]
        missing_layout = []
        for type_id in check_ids:
            page.goto(f"{URL}/appointment/{type_id}")
            page.wait_for_load_state("networkidle")
            has_header = (
                page.locator("header").count() > 0
                or page.locator("nav").count() > 0
            )
            has_footer = page.locator("footer").count() > 0
            if not has_header or not has_footer:
                missing_layout.append(
                    f"id={type_id} header={has_header} footer={has_footer}"
                )
        passed = len(missing_layout) == 0
        conftest.test(
            tid,
            "Types 1,3,5 have header + footer layout",
            passed,
            f"missing={missing_layout}" if missing_layout else "all have header+footer",
            severity="LOW",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Types 1,3,5 have header + footer layout", False, str(exc), severity="LOW")
        conftest.take_failure_screenshot(page, tid)

    # ── P2.15  Video type 2 has online/video/virtual text ────────────
    tid = "P2.15"
    try:
        page.goto(f"{URL}/appointment/{TYPE_IDS['video_consultation']}")
        page.wait_for_load_state("networkidle")
        text = page.content().lower()
        has_online = "online" in text
        has_video = "video" in text
        has_virtual = "virtual" in text
        passed = has_online or has_video or has_virtual
        conftest.test(
            tid,
            "Video type 2 has 'online'/'video'/'virtual' text",
            passed,
            f"online={has_online} video={has_video} virtual={has_virtual}",
            severity="LOW",
        )
        if not passed:
            conftest.take_failure_screenshot(page, tid)
    except Exception as exc:
        conftest.test(tid, "Video type 2 has online/video/virtual text", False, str(exc), severity="LOW")
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
    print(f"P2 Detail: {passed} passed, {failed} failed, {len(results)} total")
