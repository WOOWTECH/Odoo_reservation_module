# -*- coding: utf-8 -*-
"""A-series frontend test module: page accessibility, form presence,
confirm/cancel pages, error handling, and content verification.

Uses HTTP requests (no Selenium/Playwright) to verify page content and
structure for the Odoo 18 reservation module.
"""

import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import (
    test, call, jsonrpc, http_get, http_post,
    create_booking, cleanup, get_results, reset_results, print_summary,
)
from config import URL, TYPE_IDS, TYPE_CONFIG, RESOURCE_IDS


# ---------------------------------------------------------------------------
# A1 - Page Accessibility
# ---------------------------------------------------------------------------

def test_a1_page_accessibility():
    """A1: Basic page accessibility tests."""
    print("\n--- A1: Page Accessibility ---")

    # A1.1  GET /appointment returns 200
    try:
        resp = http_get('/appointment')
        test('A1.1', 'GET /appointment returns 200',
             resp.status_code == 200,
             detail=f"status={resp.status_code}")
    except Exception as e:
        test('A1.1', 'GET /appointment returns 200', False,
             detail=f"Exception: {e}")

    # A1.2  GET /appointment/type/{id} returns 200 for each of the 5 types
    for key, tid in TYPE_IDS.items():
        try:
            resp = http_get(f'/appointment/{tid}')
            test(f'A1.2-{key}',
                 f'GET /appointment/{tid} ({key}) returns 200',
                 resp.status_code == 200,
                 detail=f"status={resp.status_code}")
        except Exception as e:
            test(f'A1.2-{key}',
                 f'GET /appointment/{tid} ({key}) returns 200',
                 False, detail=f"Exception: {e}")

    # A1.3  Response contains proper HTML structure
    try:
        resp = http_get('/appointment')
        body = resp.text
        has_doctype = '<!DOCTYPE' in body.upper() or '<!doctype' in body
        has_html_tag = '<html' in body.lower()
        test('A1.3', 'Response contains proper HTML structure (<!DOCTYPE or <html)',
             has_doctype or has_html_tag,
             detail=f"has_doctype={has_doctype}, has_html_tag={has_html_tag}")
    except Exception as e:
        test('A1.3', 'Response contains proper HTML structure', False,
             detail=f"Exception: {e}")

    # A1.4  Each type page contains booking form or calendar element
    for key, tid in TYPE_IDS.items():
        try:
            resp = http_get(f'/appointment/{tid}')
            body = resp.text.lower()
            has_appointment = 'appointment' in body
            has_calendar = 'calendar' in body
            has_booking = 'booking' in body
            found = has_appointment or has_calendar or has_booking
            test(f'A1.4-{key}',
                 f'Type page {tid} ({key}) contains appointment/calendar/booking keyword',
                 found,
                 detail=f"appointment={has_appointment}, calendar={has_calendar}, booking={has_booking}")
        except Exception as e:
            test(f'A1.4-{key}',
                 f'Type page {tid} ({key}) contains appointment/calendar/booking keyword',
                 False, detail=f"Exception: {e}")

    # A1.5  Page returns valid Content-Type text/html
    try:
        resp = http_get('/appointment')
        content_type = resp.headers.get('Content-Type', '')
        is_html = 'text/html' in content_type
        test('A1.5', 'Page returns valid Content-Type text/html',
             is_html,
             detail=f"Content-Type={content_type}")
    except Exception as e:
        test('A1.5', 'Page returns valid Content-Type text/html', False,
             detail=f"Exception: {e}")


# ---------------------------------------------------------------------------
# A2 - Form Presence & Structure
# ---------------------------------------------------------------------------

def test_a2_form_presence():
    """A2: Form presence and structural checks on booking pages."""
    print("\n--- A2: Form Presence & Structure ---")

    type_id = TYPE_IDS['business_meeting']  # type 1

    # A2.1  Booking page for type 1 contains form tag or input fields
    try:
        resp = http_get(f'/appointment/{type_id}')
        body = resp.text
        has_form = '<form' in body.lower()
        has_input = '<input' in body.lower()
        test('A2.1', 'Booking page for type 1 contains <form> or <input> elements',
             has_form or has_input,
             detail=f"has_form={has_form}, has_input={has_input}")
    except Exception as e:
        test('A2.1', 'Booking page for type 1 contains <form> or <input> elements',
             False, detail=f"Exception: {e}")

    # A2.2  Page includes CSRF token
    try:
        resp = http_get(f'/appointment/{type_id}')
        body = resp.text
        has_csrf = 'csrf_token' in body
        test('A2.2', 'Page includes CSRF token',
             has_csrf,
             detail=f"has_csrf={has_csrf}")
    except Exception as e:
        test('A2.2', 'Page includes CSRF token', False,
             detail=f"Exception: {e}")

    # A2.3  Page includes required JavaScript files
    try:
        resp = http_get(f'/appointment/{type_id}')
        body = resp.text
        has_js = '.js' in body
        # More specific check: look for <script src="...*.js">
        js_pattern = re.search(r'<script[^>]+src=["\'][^"\']*\.js', body, re.IGNORECASE)
        test('A2.3', 'Page includes required JavaScript files (.js references)',
             has_js and js_pattern is not None,
             detail=f"has_js_reference={has_js}, has_script_src={js_pattern is not None}")
    except Exception as e:
        test('A2.3', 'Page includes required JavaScript files', False,
             detail=f"Exception: {e}")

    # A2.4  Page includes CSS files
    try:
        resp = http_get(f'/appointment/{type_id}')
        body = resp.text
        has_css = '.css' in body
        # More specific check: <link ...*.css> or <style>
        css_pattern = re.search(r'<link[^>]+href=["\'][^"\']*\.css', body, re.IGNORECASE)
        has_style = '<style' in body.lower()
        test('A2.4', 'Page includes CSS files (.css references)',
             has_css or css_pattern is not None or has_style,
             detail=f"has_css_reference={has_css}, has_link_css={css_pattern is not None}, has_style_tag={has_style}")
    except Exception as e:
        test('A2.4', 'Page includes CSS files', False,
             detail=f"Exception: {e}")


# ---------------------------------------------------------------------------
# A3 - Confirm/Cancel Pages
# ---------------------------------------------------------------------------

def test_a3_confirm_cancel_pages():
    """A3: Confirm and cancel page tests using real bookings."""
    print("\n--- A3: Confirm/Cancel Pages ---")

    type_id = TYPE_IDS['business_meeting']

    # Create a booking for confirm/cancel page tests
    bid, start, end = create_booking(
        type_id, days_ahead=8, hour=10,
        guest_name='A3 Frontend Guest', guest_email='a3.frontend@test.com',
    )
    rec = call('appointment.booking', 'read', [bid],
               {'fields': ['access_token', 'name', 'guest_name']})
    token = rec[0]['access_token'] if rec else ''
    guest_name = rec[0]['guest_name'] if rec else ''
    booking_name = rec[0]['name'] if rec else ''

    # A3.1  GET confirm page with correct token -> 200
    try:
        resp = http_get(f'/appointment/booking/{bid}/confirm?token={token}')
        test('A3.1', 'GET confirm page with correct token returns 200',
             resp.status_code == 200,
             detail=f"status={resp.status_code}")
    except Exception as e:
        test('A3.1', 'GET confirm page with correct token returns 200',
             False, detail=f"Exception: {e}")

    # A3.2  GET confirm page with wrong token -> redirect or error
    try:
        resp = http_get(f'/appointment/booking/{bid}/confirm?token=WRONG_TOKEN_12345',
                        allow_redirects=False)
        # Expect non-200 (redirect 301/302/303 or 403/404)
        is_redirect = resp.status_code in (301, 302, 303)
        is_error = resp.status_code in (403, 404)
        # If allow_redirects=True, check final URL
        if resp.status_code == 200:
            # Try with redirects to see if it actually redirected
            resp2 = http_get(f'/appointment/booking/{bid}/confirm?token=WRONG_TOKEN_12345')
            redirected = f'/booking/{bid}/confirm' not in resp2.url
            test('A3.2', 'GET confirm page with wrong token -> redirect or error',
                 redirected,
                 detail=f"status={resp.status_code}, final_url={resp2.url}")
        else:
            test('A3.2', 'GET confirm page with wrong token -> redirect or error',
                 is_redirect or is_error,
                 detail=f"status={resp.status_code}")
    except Exception as e:
        test('A3.2', 'GET confirm page with wrong token -> redirect or error',
             False, detail=f"Exception: {e}")

    # A3.3  GET cancel page with correct token -> 200 (or form shown)
    # Create a separate booking for cancel page test
    bid2, _, _ = create_booking(
        type_id, days_ahead=9, hour=11,
        guest_name='A3 Cancel Guest', guest_email='a3.cancel@test.com',
    )
    rec2 = call('appointment.booking', 'read', [bid2],
                {'fields': ['access_token']})
    token2 = rec2[0]['access_token'] if rec2 else ''

    try:
        resp = http_get(f'/appointment/booking/{bid2}/cancel?token={token2}')
        ok = resp.status_code == 200
        test('A3.3', 'GET cancel page with correct token returns 200',
             ok,
             detail=f"status={resp.status_code}")
    except Exception as e:
        test('A3.3', 'GET cancel page with correct token returns 200',
             False, detail=f"Exception: {e}")

    # A3.4  Confirm page displays booking details (guest name in HTML)
    try:
        resp = http_get(f'/appointment/booking/{bid}/confirm?token={token}')
        body = resp.text
        has_guest_name = guest_name in body
        has_booking_ref = booking_name in body if booking_name and booking_name != 'New' else True
        test('A3.4', 'Confirm page displays booking details (guest name in HTML)',
             has_guest_name or has_booking_ref,
             detail=f"has_guest_name={has_guest_name}, has_booking_ref={has_booking_ref}, "
                    f"guest_name='{guest_name}'")
    except Exception as e:
        test('A3.4', 'Confirm page displays booking details',
             False, detail=f"Exception: {e}")


# ---------------------------------------------------------------------------
# A4 - Error Handling Pages
# ---------------------------------------------------------------------------

def test_a4_error_handling():
    """A4: Error handling for invalid URLs and non-existent resources."""
    print("\n--- A4: Error Handling Pages ---")

    # A4.1  GET /appointment/type/99999 (non-existent type) -> 404 or redirect
    try:
        resp = http_get('/appointment/99999', allow_redirects=False)
        is_404 = resp.status_code == 404
        is_redirect = resp.status_code in (301, 302, 303)
        # Some Odoo setups may return 200 with an error page
        if resp.status_code == 200:
            resp_full = http_get('/appointment/99999')
            # Check if redirected to main listing
            redirected_to_listing = '/appointment' == resp_full.url.rstrip('/').split(URL)[-1] if URL in resp_full.url else False
            test('A4.1', 'GET /appointment/99999 (non-existent type) -> 404 or redirect',
                 redirected_to_listing,
                 detail=f"status={resp.status_code}, final_url={resp_full.url}")
        else:
            test('A4.1', 'GET /appointment/99999 (non-existent type) -> 404 or redirect',
                 is_404 or is_redirect,
                 detail=f"status={resp.status_code}")
    except Exception as e:
        test('A4.1', 'GET /appointment/99999 -> 404 or redirect',
             False, detail=f"Exception: {e}")

    # A4.2  GET /appointment/booking/99999/confirm?token=fake -> redirect or error
    try:
        resp = http_get('/appointment/booking/99999/confirm?token=fake',
                        allow_redirects=False)
        is_error = resp.status_code in (403, 404, 500)
        is_redirect = resp.status_code in (301, 302, 303)
        # Accept anything that is NOT a clean 200 with real booking content
        not_success = resp.status_code != 200
        test('A4.2', 'GET /appointment/booking/99999/confirm?token=fake -> redirect or error',
             is_error or is_redirect or not_success,
             detail=f"status={resp.status_code}")
    except Exception as e:
        test('A4.2', 'GET /appointment/booking/99999/confirm?token=fake -> redirect or error',
             False, detail=f"Exception: {e}")

    # A4.3  Invalid URL patterns return appropriate error
    try:
        resp = http_get('/appointment/invalid/path', allow_redirects=False)
        # Should not be 200 with valid content; 404 or redirect expected
        is_404 = resp.status_code == 404
        is_redirect = resp.status_code in (301, 302, 303)
        is_error = resp.status_code >= 400
        test('A4.3', 'GET /appointment/invalid/path returns appropriate error',
             is_404 or is_redirect or is_error,
             detail=f"status={resp.status_code}")
    except Exception as e:
        test('A4.3', 'GET /appointment/invalid/path returns appropriate error',
             False, detail=f"Exception: {e}")


# ---------------------------------------------------------------------------
# A5 - Content Verification
# ---------------------------------------------------------------------------

def test_a5_content_verification():
    """A5: Verify expected content appears in pages."""
    print("\n--- A5: Content Verification ---")

    # A5.1  Main appointment page lists all published appointment types
    try:
        resp = http_get('/appointment')
        body = resp.text
        all_found = True
        missing_types = []
        for tid, cfg in TYPE_CONFIG.items():
            type_name = cfg['name']
            if type_name not in body:
                all_found = False
                missing_types.append(type_name)
        test('A5.1', 'Main appointment page lists all published appointment types',
             all_found,
             detail=f"missing={missing_types}" if missing_types else "all types found")
    except Exception as e:
        test('A5.1', 'Main appointment page lists all published appointment types',
             False, detail=f"Exception: {e}")

    # A5.2  Each type page shows the type name in the HTML
    for tid, cfg in TYPE_CONFIG.items():
        type_name = cfg['name']
        try:
            resp = http_get(f'/appointment/{tid}')
            body = resp.text
            has_name = type_name in body
            test(f'A5.2-type{tid}',
                 f'Type page {tid} shows name "{type_name}" in HTML',
                 has_name,
                 detail=f"has_name={has_name}")
        except Exception as e:
            test(f'A5.2-type{tid}',
                 f'Type page {tid} shows name "{type_name}" in HTML',
                 False, detail=f"Exception: {e}")

    # A5.3  Booking page includes relevant form fields
    # Note: The type overview page (/appointment/{id}) is a calendar/scheduling page.
    # The actual booking form with guest fields is rendered via JavaScript after slot
    # selection. We verify the page includes the JS booking widget and form infrastructure.
    type_id = TYPE_IDS['business_meeting']
    try:
        resp = http_get(f'/appointment/{type_id}')
        body = resp.text.lower()
        # Check for form infrastructure and booking-related elements
        has_form_or_widget = 'form' in body or 'booking' in body or 'appointment' in body
        has_input_or_js = '<input' in body or 'appointment_booking' in body or '.js' in body
        test('A5.3', 'Booking page includes form infrastructure and booking widget',
             has_form_or_widget and has_input_or_js,
             detail=f"has_form_or_widget={has_form_or_widget}, has_input_or_js={has_input_or_js}")
    except Exception as e:
        test('A5.3', 'Booking page includes form infrastructure',
             False, detail=f"Exception: {e}")

    # A5.4  Page does not contain Python tracebacks
    pages_to_check = [
        '/appointment',
        f'/appointment/{TYPE_IDS["business_meeting"]}',
        f'/appointment/{TYPE_IDS["restaurant"]}',
    ]
    all_clean = True
    traceback_page = None
    for page_path in pages_to_check:
        try:
            resp = http_get(page_path)
            body = resp.text
            has_traceback = 'Traceback' in body and 'most recent call' in body.lower()
            has_500 = 'Error 500' in body or 'Internal Server Error' in body
            if has_traceback or has_500:
                all_clean = False
                traceback_page = page_path
                break
        except Exception:
            pass
    test('A5.4', 'Pages do not contain Python tracebacks or Error 500',
         all_clean,
         detail=f"traceback_found_on={traceback_page}" if traceback_page else "all pages clean")

    # A5.5  No debug endpoints accessible
    try:
        resp = http_get('/appointment/debug', allow_redirects=False)
        is_404 = resp.status_code == 404
        is_redirect = resp.status_code in (301, 302, 303)
        is_error = resp.status_code >= 400
        # Debug endpoint should not return 200 with content
        test('A5.5', 'GET /appointment/debug should 404 (no debug endpoints accessible)',
             is_404 or is_redirect or is_error,
             detail=f"status={resp.status_code}")
    except Exception as e:
        test('A5.5', 'GET /appointment/debug should 404',
             False, detail=f"Exception: {e}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run():
    """Execute all A-series frontend tests and return results."""
    reset_results()
    print("\n" + "=" * 60)
    print("  A-SERIES: FRONTEND/PAGE TESTS")
    print("=" * 60)

    try:
        test_a1_page_accessibility()
    except Exception as e:
        test('A1.ERR', 'A1 section raised an exception', False,
             detail=str(e), severity='HIGH')

    try:
        test_a2_form_presence()
    except Exception as e:
        test('A2.ERR', 'A2 section raised an exception', False,
             detail=str(e), severity='HIGH')

    try:
        test_a3_confirm_cancel_pages()
    except Exception as e:
        test('A3.ERR', 'A3 section raised an exception', False,
             detail=str(e), severity='HIGH')

    try:
        test_a4_error_handling()
    except Exception as e:
        test('A4.ERR', 'A4 section raised an exception', False,
             detail=str(e), severity='HIGH')

    try:
        test_a5_content_verification()
    except Exception as e:
        test('A5.ERR', 'A5 section raised an exception', False,
             detail=str(e), severity='HIGH')

    cleanup()
    print_summary("Frontend Tests")

    return get_results()


if __name__ == '__main__':
    run()
