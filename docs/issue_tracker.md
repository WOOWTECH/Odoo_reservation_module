# Issue Tracker — reservation_module

| ID | Severity | Test | Summary | Status |
|----|----------|------|---------|--------|
| ISS-001 | Critical | T21-T32 | Template name mismatch causes 500 errors on all frontend pages | Fixed |
| ISS-002 | Critical | Deploy | Asset paths reference old module name `odoo_calendar_enhance` | Fixed |
| ISS-003 | High | T48 | Booking accessible without token / sequential IDs enable IDOR | Open |
| ISS-004 | Medium | T56-T57 | No server-side email format validation | Open |
| ISS-007 | Minor | T30 | Hardcoded Chinese text in payment template | Open |
| ISS-008 | Minor | T30 | Jinja2 `{{ }}` syntax used instead of QWeb `#{}` in payment template | Open |
| ISS-009 | Low | T9 | auto_confirm_capacity_percent displays 10000% instead of 100% | Open |
| ISS-010 | Medium | T33 | Booking list column headers in English while rest of UI is Chinese | Open |
| ISS-011 | Low | T1 | Menu icon path references old module name | Open |
| ISS-012 | Low | T38 | Cannot reset booking from "Done" state back to Draft | Open |

## Test Summary

- **Total tests**: 46 (of 62 planned)
- **Passed**: 42
- **Failed**: 3
- **Blocked**: 1 (payment flow — no payment provider configured)
- **Server**: `https://matt-test-254-odoo.woowtech.io/`
- **Date**: 2026-03-10

---

## Issue Details

### ISS-001: Template name mismatch causes 500 errors on all frontend pages
- **Severity**: Critical
- **Test**: T21-T32 (all frontend routes)
- **Status**: Fixed
- **Steps to Reproduce**:
  1. Navigate to `/appointment`
  2. Any frontend page returns HTTP 500
- **Expected**: Appointment listing page renders
- **Actual**: 500 Internal Server Error on every frontend route
- **Root Cause**: All `request.render()` calls in `controllers/main.py` referenced templates as `odoo_calendar_enhance.*` but templates are registered under `reservation_module.*` (the actual module technical name).
- **Fix Applied**: Global replace `odoo_calendar_enhance.` → `reservation_module.` in `controllers/main.py`

### ISS-002: Asset paths reference old module name
- **Severity**: Critical
- **Test**: Deploy
- **Status**: Fixed
- **Steps to Reproduce**:
  1. Install module on Odoo server
  2. CSS compilation fails with "Could not get content" error
- **Expected**: Module installs cleanly with assets loading
- **Actual**: CSS Style Error referencing `odoo_calendar_enhance/static/src/css/...`
- **Root Cause**: `__manifest__.py` asset declarations used `odoo_calendar_enhance/static/src/` paths instead of `reservation_module/static/src/`
- **Fix Applied**: Updated all asset paths in `__manifest__.py` to use `reservation_module/`

### ISS-003: Booking accessible without token / sequential IDs enable IDOR
- **Severity**: High (Security)
- **Test**: T48
- **Steps to Reproduce**:
  1. Complete a booking to get reference APT00001
  2. Navigate to `/appointment/booking/1` (no token parameter)
  3. Booking details are displayed without authentication
  4. Try `/appointment/booking/2`, `/appointment/booking/3`, etc.
- **Expected**: Booking should only be accessible with a valid `access_token` parameter. Without token, redirect to `/appointment`.
- **Actual**: Token validation in `controllers/main.py` (lines ~458, 470, 482, 508) uses pattern `if token and booking.access_token != token` which skips the check entirely when `token` is `None` (i.e., when no token is provided in the URL). Combined with sequential integer booking IDs, this allows enumeration of all bookings (IDOR vulnerability).
- **Recommended Fix**: Change validation to `if not token or booking.access_token != token` to require a valid token.

### ISS-004: No server-side email format validation
- **Severity**: Medium
- **Test**: T56-T57
- **Steps to Reproduce**:
  1. Navigate to booking form for any appointment type
  2. Enter an invalid email like `notanemail` in the email field
  3. Submit the form
- **Expected**: Server returns validation error for invalid email format
- **Actual**: Booking is created with invalid email. Only client-side HTML5 `type="email"` validation exists, which can be bypassed.
- **Recommended Fix**: Add server-side email regex validation in the `/book` POST handler.

### ISS-007: Hardcoded Chinese text in payment template
- **Severity**: Minor
- **Test**: T30
- **Steps to Reproduce**:
  1. Enable `require_payment` on an appointment type
  2. Set English as the UI language
  3. Navigate to the payment page
- **Expected**: All text displayed in English
- **Actual**: Some labels appear in Chinese (hardcoded in the QWeb template rather than using the translation dictionary from `_get_translations()`).

### ISS-008: Jinja2 syntax used instead of QWeb in payment template
- **Severity**: Minor
- **Test**: T30
- **Steps to Reproduce**:
  1. Review `appointment_templates.xml` payment section
  2. Look for `{{ }}` syntax
- **Expected**: All dynamic expressions use QWeb `t-esc` or `t-out` directives, or `#{expr}` inside `t-attf-*` attributes
- **Actual**: Some expressions use Jinja2 `{{ variable }}` syntax which may not render correctly in QWeb context.

### ISS-009: auto_confirm_capacity_percent displays 10000% instead of 100%
- **Severity**: Low
- **Test**: T9
- **Steps to Reproduce**:
  1. Open any appointment type in backend edit mode
  2. Look at the auto_confirm settings
- **Expected**: Capacity percentage shows as 100% (or reasonable value)
- **Actual**: Field displays 10000%, suggesting the stored value is multiplied incorrectly or the field definition uses wrong precision.

### ISS-010: Booking list column headers in English while UI is Chinese
- **Severity**: Medium
- **Test**: T33
- **Steps to Reproduce**:
  1. Login as admin (Chinese locale)
  2. Navigate to Appointment Management > All Bookings
  3. Observe column headers
- **Expected**: Column headers match the UI language (Chinese)
- **Actual**: Column headers display in English (e.g., "Reference", "Appointment Type", "Status") while menu items and other UI elements are in Chinese. This is expected for a community module without `.po` translation files, but should be addressed for production use.

### ISS-011: Menu icon path references old module name
- **Severity**: Low
- **Test**: T1
- **Steps to Reproduce**:
  1. Inspect the main menu item for Appointment Management
  2. Check the `web_icon` attribute
- **Expected**: Icon path uses `reservation_module/static/...`
- **Actual**: Icon path may reference old module name. The menu renders but the icon may not load correctly.

### ISS-012: Cannot reset booking from "Done" state
- **Severity**: Low
- **Test**: T38
- **Steps to Reproduce**:
  1. Create and confirm a booking
  2. Mark the booking as "Done"
  3. Try to reset the booking back to "Draft"
- **Expected**: A "Reset to Draft" button should be available per the user guide
- **Actual**: No state transition button is available from the "Done" state. The workflow only allows: Draft → Confirmed → Done (terminal), or Draft/Confirmed → Cancelled → Draft.
