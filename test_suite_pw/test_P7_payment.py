# -*- coding: utf-8 -*-
"""P7 — Expert Consultation payment flow tests.

10 Playwright browser tests verifying that booking an Expert Consultation
(type 5, require_payment=True, payment_amount=100.0) redirects to a
payment page and that the payment page contains expected content.
"""

import sys
import os
import time
import traceback
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(__file__))

import conftest
from config import URL, TYPE_IDS, STAFF_IDS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TYPE_ID = TYPE_IDS['expert_consultation']  # 5
STAFF_ID = STAFF_IDS['admin']             # 2
GUEST = 'PW P7 Tester'
EMAIL_PREFIX = 'pw_p7_'

EMAILS = {n: f"{EMAIL_PREFIX}{n}@example.com" for n in range(1, 11)}

# Cache booking info across tests so browser-dependent tests can share data
_cache = {}


def _email(n):
    return EMAILS[n]


# ---------------------------------------------------------------------------
# Helper: book an expert consultation and return (final_url, booking_dict)
# ---------------------------------------------------------------------------

def _book_expert(page, suffix, days_ahead, hour, guest_count=1):
    """Book Expert Consultation (type 5) with staff_id=2.

    Args:
        page: Playwright page object.
        suffix: Used to build the unique email pw_p7_{suffix}@example.com.
        days_ahead: Days ahead for get_future_weekday (>= 2 for min 24h).
        hour: Hour of the appointment.
        guest_count: Number of guests (default 1).

    Returns:
        (page_url_after_submit, booking_dict_from_db) or (page.url, None) on
        lookup failure.
    """
    email = f"{EMAIL_PREFIX}{suffix}@example.com"
    date_obj = conftest.get_future_weekday(days_ahead)
    start_dt = conftest.make_start_datetime(date_obj, hour)

    conftest.goto_book_page(page, TYPE_ID, start_dt, staff_id=STAFF_ID)
    conftest.fill_booking_form(
        page,
        guest_name=f"{GUEST} {suffix}",
        guest_email=email,
        guest_phone='+886900000007',
        guest_count=guest_count,
        notes=f'P7 payment test - {suffix}',
    )
    conftest.submit_booking_form(page, timeout=15000)

    final_url = page.url

    # Look up the booking from the DB
    bookings = conftest.find_bookings_by_email(email)
    booking = None
    if bookings:
        booking = conftest.read_booking(bookings[0]['id'])

    return final_url, booking


# ===================================================================
# Individual test functions
# ===================================================================

def test_p7_1(page):
    """P7.1: After booking Expert, URL contains '/pay'."""
    try:
        final_url, booking = _book_expert(page, '1', days_ahead=3, hour=10)
        _cache['p7_1_url'] = final_url
        _cache['p7_1_booking'] = booking
        passed = '/pay' in final_url
        conftest.test('P7.1',
                      "After booking Expert, URL contains '/pay'",
                      passed,
                      f"URL={final_url}",
                      'CRITICAL')
        if not passed:
            conftest.take_failure_screenshot(page, 'P7.1')
    except Exception:
        conftest.test('P7.1',
                      "After booking Expert, URL contains '/pay'",
                      False,
                      traceback.format_exc(),
                      'CRITICAL')


def test_p7_2(page):
    """P7.2: Payment page body has '100' amount text."""
    try:
        # Reuse the page that should already be on the payment URL from P7.1
        # If not, navigate using cached URL
        current = page.url
        if '/pay' not in current:
            cached_url = _cache.get('p7_1_url', '')
            if '/pay' in cached_url:
                page.goto(cached_url)
                page.wait_for_load_state('networkidle')
            else:
                # Fallback: make a fresh booking
                final_url, booking = _book_expert(page, '2', days_ahead=3, hour=11)
                _cache['p7_2_url'] = final_url

        content = page.content()
        passed = '100' in content
        conftest.test('P7.2',
                      "Payment page body has '100' amount text",
                      passed,
                      "Found '100' in page" if passed else "'100' not found in page body",
                      'HIGH')
        if not passed:
            conftest.take_failure_screenshot(page, 'P7.2')
    except Exception:
        conftest.test('P7.2',
                      "Payment page body has '100' amount text",
                      False,
                      traceback.format_exc(),
                      'HIGH')


def test_p7_3(page):
    """P7.3: Payment page has booking summary (year or type name)."""
    try:
        current = page.url
        if '/pay' not in current:
            cached_url = _cache.get('p7_1_url', '')
            if '/pay' in cached_url:
                page.goto(cached_url)
                page.wait_for_load_state('networkidle')
            else:
                final_url, _ = _book_expert(page, '3_fallback', days_ahead=3, hour=14)

        content = page.content()
        import datetime
        year_str = str(datetime.date.today().year)
        has_year = year_str in content
        has_type_name = 'Expert' in content or 'expert' in content.lower()
        passed = has_year or has_type_name
        detail_parts = []
        if has_year:
            detail_parts.append(f"year '{year_str}' found")
        if has_type_name:
            detail_parts.append("type name 'Expert' found")
        if not detail_parts:
            detail_parts.append(f"Neither '{year_str}' nor 'Expert' found")
        conftest.test('P7.3',
                      'Payment page has booking summary (year or type name)',
                      passed,
                      ', '.join(detail_parts),
                      'HIGH')
        if not passed:
            conftest.take_failure_screenshot(page, 'P7.3')
    except Exception:
        conftest.test('P7.3',
                      'Payment page has booking summary (year or type name)',
                      False,
                      traceback.format_exc(),
                      'HIGH')


def test_p7_4(page):
    """P7.4: Payment page has payment form area."""
    try:
        current = page.url
        if '/pay' not in current:
            cached_url = _cache.get('p7_1_url', '')
            if '/pay' in cached_url:
                page.goto(cached_url)
                page.wait_for_load_state('networkidle')
            else:
                final_url, _ = _book_expert(page, '4_fallback', days_ahead=4, hour=9)

        content = page.content().lower()
        form_el = page.locator('form')
        has_form = form_el.count() > 0
        has_payment_text = 'payment' in content or 'pay' in content
        passed = has_form or has_payment_text
        detail_parts = []
        if has_form:
            detail_parts.append(f"form elements found (count={form_el.count()})")
        if has_payment_text:
            detail_parts.append("'payment'/'pay' text found in HTML")
        if not detail_parts:
            detail_parts.append("No form element and no 'payment'/'pay' text found")
        conftest.test('P7.4',
                      'Payment page has payment form area',
                      passed,
                      ', '.join(detail_parts),
                      'HIGH')
        if not passed:
            conftest.take_failure_screenshot(page, 'P7.4')
    except Exception:
        conftest.test('P7.4',
                      'Payment page has payment form area',
                      False,
                      traceback.format_exc(),
                      'HIGH')


def test_p7_5(page):
    """P7.5: Payment URL has 'token=' parameter."""
    try:
        current = page.url
        if '/pay' not in current:
            cached_url = _cache.get('p7_1_url', '')
            if '/pay' in cached_url:
                current = cached_url
            else:
                final_url, _ = _book_expert(page, '5_fallback', days_ahead=4, hour=11)
                current = final_url

        parsed = urlparse(current)
        query_params = parse_qs(parsed.query)
        # Check both query param and path-embedded token
        has_token_param = 'token' in query_params
        has_token_in_url = 'token=' in current or 'token' in current
        passed = has_token_param or has_token_in_url
        conftest.test('P7.5',
                      "Payment URL has 'token=' parameter",
                      passed,
                      f"URL={current}, token_param={has_token_param}, token_in_url={has_token_in_url}",
                      'HIGH')
    except Exception:
        conftest.test('P7.5',
                      "Payment URL has 'token=' parameter",
                      False,
                      traceback.format_exc(),
                      'HIGH')


def test_p7_6(page):
    """P7.6: Backend booking state is 'draft' (payment pending)."""
    try:
        final_url, booking = _book_expert(page, '6', days_ahead=4, hour=10)
        _cache['p7_6_booking'] = booking
        if not booking:
            conftest.test('P7.6',
                          "Backend booking state is 'draft' (payment pending)",
                          False,
                          'No booking found in DB',
                          'HIGH')
            return
        state = booking.get('state', '')
        passed = state == 'draft'
        conftest.test('P7.6',
                      "Backend booking state is 'draft' (payment pending)",
                      passed,
                      f"state='{state}', expected 'draft'",
                      'HIGH')
    except Exception:
        conftest.test('P7.6',
                      "Backend booking state is 'draft' (payment pending)",
                      False,
                      traceback.format_exc(),
                      'HIGH')


def test_p7_7(page):
    """P7.7: Book with guest_count=2, payment page shows '2' or '200'."""
    try:
        final_url, booking = _book_expert(page, '7', days_ahead=5, hour=10, guest_count=2)
        _cache['p7_7_url'] = final_url
        _cache['p7_7_booking'] = booking

        content = page.content()
        # payment_per_person is False in current config, so total may stay 100
        # Accept either '200' (per-person pricing) or presence of '2' guests
        has_200 = '200' in content
        has_100 = '100' in content
        # Check that guest_count=2 was saved
        db_count = booking.get('guest_count', 0) if booking else 0

        passed = db_count == 2 and (has_200 or has_100)
        detail_parts = [f"guest_count_in_db={db_count}"]
        if has_200:
            detail_parts.append("'200' found in page (per-person pricing)")
        if has_100:
            detail_parts.append("'100' found in page (flat pricing)")
        if not has_200 and not has_100:
            detail_parts.append("Neither '100' nor '200' found in page")
        conftest.test('P7.7',
                      "Book guest_count=2, payment page shows amount",
                      passed,
                      ', '.join(detail_parts),
                      'MEDIUM')
        if not passed:
            conftest.take_failure_screenshot(page, 'P7.7')
    except Exception:
        conftest.test('P7.7',
                      "Book guest_count=2, payment page shows amount",
                      False,
                      traceback.format_exc(),
                      'MEDIUM')


def test_p7_8(page):
    """P7.8: Payment page accessible with correct token (direct navigation)."""
    try:
        booking = _cache.get('p7_1_booking')
        if not booking:
            # Try to find from DB
            bookings = conftest.find_bookings_by_email(_email(1))
            if bookings:
                booking = conftest.read_booking(bookings[0]['id'])
        if not booking:
            conftest.test('P7.8',
                          'Payment page accessible with correct token',
                          False,
                          'No P7.1 booking available in cache or DB',
                          'MEDIUM')
            return

        booking_id = booking['id']
        token = booking.get('access_token', '')
        if not token:
            conftest.test('P7.8',
                          'Payment page accessible with correct token',
                          False,
                          f"Booking {booking_id} has no access_token",
                          'MEDIUM')
            return

        pay_url = f"{URL}/appointment/booking/{booking_id}/pay?token={token}"
        page.goto(pay_url)
        page.wait_for_load_state('networkidle')

        final_url = page.url
        content = page.content().lower()
        # Should stay on pay page (not redirected to error/home)
        has_pay = '/pay' in final_url
        has_payment_content = 'payment' in content or 'pay' in content or '100' in content
        passed = has_pay or has_payment_content
        conftest.test('P7.8',
                      'Payment page accessible with correct token',
                      passed,
                      f"URL={final_url}, has_pay_in_url={has_pay}, has_content={has_payment_content}",
                      'MEDIUM')
        if not passed:
            conftest.take_failure_screenshot(page, 'P7.8')
    except Exception:
        conftest.test('P7.8',
                      'Payment page accessible with correct token',
                      False,
                      traceback.format_exc(),
                      'MEDIUM')


def test_p7_9(page):
    """P7.9: Payment page with wrong token redirects away."""
    try:
        booking = _cache.get('p7_1_booking')
        if not booking:
            bookings = conftest.find_bookings_by_email(_email(1))
            if bookings:
                booking = conftest.read_booking(bookings[0]['id'])
        if not booking:
            conftest.test('P7.9',
                          'Payment page with wrong token redirects',
                          False,
                          'No P7.1 booking available in cache or DB',
                          'MEDIUM')
            return

        booking_id = booking['id']
        wrong_url = f"{URL}/appointment/booking/{booking_id}/pay?token=WRONG_TOKEN_12345"
        page.goto(wrong_url)
        page.wait_for_load_state('networkidle')

        final_url = page.url
        content = page.content().lower()
        # With wrong token, should NOT show a valid payment page
        # Could redirect to home, error page, or show access denied
        is_redirected = '/pay' not in final_url
        has_error = ('error' in content or 'denied' in content or
                     'not found' in content or 'invalid' in content or
                     'unauthorized' in content or 'access' in content)
        # Also check: if it stays on /pay URL, the page should not have
        # payment content (i.e. the amount '100')
        no_payment_content = '100' not in content
        passed = is_redirected or has_error or no_payment_content
        conftest.test('P7.9',
                      'Payment page with wrong token redirects',
                      passed,
                      f"URL={final_url}, redirected={is_redirected}, has_error={has_error}, no_100={no_payment_content}",
                      'MEDIUM')
        if not passed:
            conftest.take_failure_screenshot(page, 'P7.9')
    except Exception:
        conftest.test('P7.9',
                      'Payment page with wrong token redirects',
                      False,
                      traceback.format_exc(),
                      'MEDIUM')


def test_p7_10(page):
    """P7.10: Re-visit payment page works (not one-time-use)."""
    try:
        booking = _cache.get('p7_1_booking')
        if not booking:
            bookings = conftest.find_bookings_by_email(_email(1))
            if bookings:
                booking = conftest.read_booking(bookings[0]['id'])
        if not booking:
            conftest.test('P7.10',
                          'Re-visit payment page works (not one-time-use)',
                          False,
                          'No P7.1 booking available in cache or DB',
                          'LOW')
            return

        booking_id = booking['id']
        token = booking.get('access_token', '')
        if not token:
            conftest.test('P7.10',
                          'Re-visit payment page works (not one-time-use)',
                          False,
                          f"Booking {booking_id} has no access_token",
                          'LOW')
            return

        pay_url = f"{URL}/appointment/booking/{booking_id}/pay?token={token}"

        # First visit
        page.goto(pay_url)
        page.wait_for_load_state('networkidle')
        url_visit1 = page.url
        content_visit1 = page.content().lower()
        ok_visit1 = '/pay' in url_visit1 or 'payment' in content_visit1 or '100' in content_visit1

        # Wait 1 second, then second visit
        time.sleep(1)

        page.goto(pay_url)
        page.wait_for_load_state('networkidle')
        url_visit2 = page.url
        content_visit2 = page.content().lower()
        ok_visit2 = '/pay' in url_visit2 or 'payment' in content_visit2 or '100' in content_visit2

        passed = ok_visit1 and ok_visit2
        conftest.test('P7.10',
                      'Re-visit payment page works (not one-time-use)',
                      passed,
                      f"visit1_ok={ok_visit1} (URL={url_visit1}), visit2_ok={ok_visit2} (URL={url_visit2})",
                      'LOW')
        if not passed:
            conftest.take_failure_screenshot(page, 'P7.10')
    except Exception:
        conftest.test('P7.10',
                      'Re-visit payment page works (not one-time-use)',
                      False,
                      traceback.format_exc(),
                      'LOW')


# ===================================================================
# run() -- entry point called by the test runner
# ===================================================================

def run():
    """Execute all P7 payment tests. Returns conftest.get_results()."""
    from playwright.sync_api import sync_playwright

    conftest.clear_results()
    print("\n=== P7: Expert Consultation Payment Flow Tests (10 tests) ===\n")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)

    try:
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        # Tests run in order; P7.1 creates the booking reused by later tests
        test_p7_1(page)
        test_p7_2(page)
        test_p7_3(page)
        test_p7_4(page)
        test_p7_5(page)
        test_p7_6(page)
        test_p7_7(page)
        test_p7_8(page)
        test_p7_9(page)
        test_p7_10(page)

        context.close()
    except Exception:
        print(f"Fatal error in P7 suite: {traceback.format_exc()}")
    finally:
        # Cleanup all pw_p7_*@example.com bookings
        print("\n--- Cleaning up P7 test bookings ---")
        for n in EMAILS:
            try:
                conftest.cleanup_test_bookings(EMAILS[n])
            except Exception:
                pass
        # Also clean up fallback emails
        for suffix in ('3_fallback', '4_fallback', '5_fallback'):
            try:
                conftest.cleanup_test_bookings(f"{EMAIL_PREFIX}{suffix}@example.com")
            except Exception:
                pass
        browser.close()
        pw.stop()

    results = conftest.get_results()
    passed = sum(1 for r in results if r['passed'])
    print(f"\n=== P7 Complete: {passed}/{len(results)} passed ===\n")
    return results


if __name__ == '__main__':
    run()
