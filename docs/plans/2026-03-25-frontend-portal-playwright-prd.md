# Frontend Portal Playwright E2E Test PRD

## Module: reservation_module v18.0.1.5.0
## Date: 2026-03-25
## Scope: Public user frontend booking flow — Playwright browser automation

---

## 1. Objective

Validate that every public-facing page, form, interactive widget, and cross-module integration works correctly from the perspective of an unauthenticated website visitor (public user). This complements the existing backend/API test suite (198 tests, 98% pass rate) by covering the actual browser experience.

---

## 2. Environment

| Item | Value |
|------|-------|
| Odoo Instance | `http://localhost:9073` |
| Database | `odooreservation` |
| Admin UID / Password | `2` / `admin` |
| Browser Engine | Chromium (headless) via Playwright 1.58.0 |
| Backend Verification | XML-RPC `xmlrpc/2/object` |

---

## 3. Live Data Inventory (from fields_get + search_read)

### 3.1 Published Appointment Types (5 active, published)

| ID | Name | Duration | Resources | Staff | Questions | Payment | Capacity |
|----|------|----------|-----------|-------|-----------|---------|----------|
| 1 | Business Meeting | 1h | — | Admin (uid=2) | — | No | No |
| 2 | Video Consultation | 0.5h | — | Admin (uid=2) | — | No | No |
| 3 | Restaurant Reservation | 2h | Table1(R3,cap4), Table2(R4,cap6), Table3(R5,cap8) | — | Q3,Q4 | No | Yes (18) |
| 4 | Tennis Court Booking | 1h | Tennis Court(R6,cap4) | — | — | No | No |
| 5 | Expert Consultation | 1h | — | Admin (uid=2) | Q1,Q2 | Yes ($100) | No |

### 3.2 Questions (appointment.question — simple: name + answer + sequence)

| ID | Name | Type ID | Sequence |
|----|------|---------|----------|
| Q1 | "What topics can I discuss during a consultation?" | 5 (Expert) | 1 |
| Q2 | "How should I prepare for my consultation?" | 5 (Expert) | 2 |
| Q3 | "Can I request a special occasion setup?" | 3 (Restaurant) | 1 |
| Q4 | "Do you accommodate dietary restrictions?" | 3 (Restaurant) | 2 |

> NOTE: Questions have `name` (the question text) and `answer` (html) fields. They appear to be **informational FAQ items**, NOT form input fields. The booking form does NOT render question input fields. This is a key finding from live browser inspection.

### 3.3 Resources (material type, linked to appointment types)

| ID | Name | Capacity | Linked Type |
|----|------|----------|-------------|
| R3 | Table 1 - Window | 4 | Restaurant (3) |
| R4 | Table 2 - Garden View | 6 | Restaurant (3) |
| R5 | Table 3 - Private Room | 8 | Restaurant (3) |
| R6 | Tennis Court | 4 | Tennis (4) |

### 3.4 Booking Form Fields (verified from live HTML)

| Field Name | Input Type | Required | Present On |
|------------|-----------|----------|------------|
| `csrf_token` | hidden | auto | all forms |
| `start_datetime` | hidden | auto | booking form |
| `resource_id` | hidden | auto | when resource selected |
| `staff_id` | hidden | auto | when staff selected |
| `guest_name` | text | Yes | booking form |
| `guest_email` | email | Yes | booking form |
| `guest_phone` | tel | No | booking form |
| `guest_count` | number (default=1) | No | booking form |
| `notes` | textarea | No | booking form |

Submit button: `button[type=submit].btn-primary.btn-lg` ("Confirm Booking" or "Continue to Payment")

### 3.5 Page Routes (public, auth='public')

| Route | Method | Page |
|-------|--------|------|
| `/appointment` | GET | Type listing grid |
| `/appointment/<id>` | GET | Type detail page |
| `/appointment/<id>/schedule` | GET | Calendar + slot selection |
| `/appointment/<id>/slots` | JSON POST | AJAX slot loader |
| `/appointment/<id>/book` | GET/POST | Booking form + submission |
| `/appointment/booking/<id>/confirm` | GET | Confirmation page (token) |
| `/appointment/booking/<id>` | GET | Booking details (token) |
| `/appointment/booking/<id>/cancel` | GET/POST | Cancel flow (token) |
| `/appointment/booking/<id>/pay` | GET | Payment page (token) |

### 3.6 Frontend Widgets (JavaScript)

- **Calendar Widget**: `#appointment-reservation` with `data-appointment-type-id`, `data-start-date`, `data-end-date`, `data-is-scheduled`
- **Staff Selector**: `select[name=staff-select]` (types 1,2,5 — staff-based)
- **Location Selector**: `select[name=location-select]` (types 3,4 — resource-based)
- **Form Validation**: Bootstrap `needs-validation` class with `was-validated` on submit

---

## 4. Test Design

### 4.1 Architecture

```
test_suite_pw/
├── conftest.py          # Playwright fixtures, XML-RPC helpers, cleanup
├── config.py            # URLs, credentials, type configs
├── test_P1_listing.py   # P1: Type listing page
├── test_P2_detail.py    # P2: Type detail pages
├── test_P3_schedule.py  # P3: Calendar + slot selection
├── test_P4_booking.py   # P4: Booking form submission (all 5 types)
├── test_P5_confirm.py   # P5: Confirmation + booking detail pages
├── test_P6_cancel.py    # P6: Cancel flow
├── test_P7_payment.py   # P7: Payment flow (Expert Consultation)
├── test_P8_integration.py # P8: Cross-module (partner, calendar, payment_tx)
├── test_P9_validation.py  # P9: Form validation + error handling
├── test_P10_edge.py     # P10: Edge cases + security
├── pw_runner.py         # Orchestrator with GO/NO-GO
└── screenshots/         # Failure screenshots
```

### 4.2 Test Framework

- **pytest + playwright** (`pytest-playwright` plugin) for test structure
- **XML-RPC** backend verification after each browser action
- **Screenshot on failure** for debugging
- **Automatic cleanup** of test bookings via XML-RPC after each test

---

## 5. Test Cases (150+ cases across 10 modules)

### P1: Type Listing Page (8 tests)

| ID | Test | Severity | Method |
|----|------|----------|--------|
| P1.1 | `/appointment` returns 200 with proper HTML | HIGH | GET, check status + DOCTYPE |
| P1.2 | All 5 published types visible as cards | HIGH | Count cards, verify names |
| P1.3 | Unpublished type (ID=6) NOT visible | HIGH | Verify absence |
| P1.4 | Each card has "Book Now" link to `/appointment/<id>` | MEDIUM | Check hrefs |
| P1.5 | Each card shows type name correctly | MEDIUM | Text match |
| P1.6 | Page has proper navigation (breadcrumb, header, footer) | LOW | DOM check |
| P1.7 | Page is responsive (mobile viewport 375px) | LOW | Viewport resize, check layout |
| P1.8 | Deactivated types (ID=9,12) behavior | MEDIUM | Verify visibility rules |

### P2: Type Detail Pages (15 tests)

| ID | Test | Severity |
|----|------|----------|
| P2.1 | Business Meeting detail shows name, duration "1.0 hour(s)" | MEDIUM |
| P2.2 | Video Consultation detail shows "online" location info | MEDIUM |
| P2.3 | Restaurant detail shows duration, capacity info | MEDIUM |
| P2.4 | Tennis Court detail shows duration, resource info | MEDIUM |
| P2.5 | Expert Consultation shows payment "$100.0" and payment warning | HIGH |
| P2.6 | "Select Date & Time" button links to `/appointment/<id>/schedule` | HIGH |
| P2.7 | Each type page has unique content (not generic template) | MEDIUM |
| P2.8 | Non-existent type `/appointment/999` returns 404 or error | MEDIUM |
| P2.9 | Unpublished type `/appointment/6` returns 404 or redirect | HIGH |
| P2.10 | Page loads within 3 seconds | LOW |
| P2.11 | Business Meeting detail shows FAQ questions if any | LOW |
| P2.12 | Restaurant detail shows available resources/tables | MEDIUM |
| P2.13 | Expert Consultation detail shows FAQ questions (Q1, Q2) | MEDIUM |
| P2.14 | Type pages have consistent layout structure | LOW |
| P2.15 | Back button / breadcrumb navigates to listing | LOW |

### P3: Schedule Page — Calendar & Slot Selection (25 tests)

| ID | Test | Severity |
|----|------|----------|
| P3.1 | Schedule page loads with calendar widget for type 1 | HIGH |
| P3.2 | Calendar widget has `data-appointment-type-id` matching type | HIGH |
| P3.3 | Staff selector visible for type 1 (Business Meeting) with "Auto-Assign" + "Mitchell Admin" | HIGH |
| P3.4 | Location selector visible for type 3 (Restaurant) with 3 tables + "Auto-Assign" | HIGH |
| P3.5 | Staff selector visible for type 5 (Expert) | HIGH |
| P3.6 | No staff/location selector for type 4 (Tennis) if only 1 resource | MEDIUM |
| P3.7 | Click a future date → AJAX loads time slots | CRITICAL |
| P3.8 | Slots displayed as clickable buttons with time ranges | HIGH |
| P3.9 | Past dates are disabled/unclickable in calendar | HIGH |
| P3.10 | Dates beyond max_booking_days are disabled (type 4: 7 days) | HIGH |
| P3.11 | Navigate to next month via arrow button | MEDIUM |
| P3.12 | Navigate to previous month (if current month) stays on today | MEDIUM |
| P3.13 | Select staff → calendar updates (may reload slots) | MEDIUM |
| P3.14 | Select location/resource → calendar updates | MEDIUM |
| P3.15 | Click slot → redirects to booking form with correct params | CRITICAL |
| P3.16 | Slot redirect URL contains `start_datetime` param | HIGH |
| P3.17 | Slot redirect URL contains `staff_id` when staff selected | HIGH |
| P3.18 | Slot redirect URL contains `resource_id` when resource selected | HIGH |
| P3.19 | Weekend dates follow availability rules (Restaurant has Sat/Sun) | MEDIUM |
| P3.20 | Weekday dates follow availability rules (Tennis: Mon-Fri 7-21) | MEDIUM |
| P3.21 | Slot duration matches type config (Restaurant: 2h slots) | MEDIUM |
| P3.22 | Slot interval matches type config (Restaurant: 30min interval) | MEDIUM |
| P3.23 | Empty day shows "no slots available" message | MEDIUM |
| P3.24 | Multiple date clicks update slot display correctly | LOW |
| P3.25 | Calendar shows correct month/year in header | LOW |

### P4: Booking Form Submission — All 5 Types (30 tests)

| ID | Test | Severity | Type |
|----|------|----------|------|
| P4.1 | Business Meeting: fill form → submit → confirm page | CRITICAL | 1 |
| P4.2 | Business Meeting: booking created in DB with correct state | CRITICAL | 1 |
| P4.3 | Video Consultation: fill form → submit → confirm page | CRITICAL | 2 |
| P4.4 | Restaurant: fill form with resource → submit → confirm | CRITICAL | 3 |
| P4.5 | Restaurant: guest_count field works (set to 3) | HIGH | 3 |
| P4.6 | Tennis Court: fill form with resource → submit → confirm | CRITICAL | 4 |
| P4.7 | Expert Consultation: fill form → redirects to payment page | CRITICAL | 5 |
| P4.8 | Booking form shows correct date/time summary | HIGH | all |
| P4.9 | Booking form shows selected staff name | HIGH | 1 |
| P4.10 | Booking form shows selected resource/table name | HIGH | 3 |
| P4.11 | CSRF token present in form | HIGH | all |
| P4.12 | Hidden fields (start_datetime, resource_id, staff_id) populated | HIGH | all |
| P4.13 | guest_name is required (HTML validation) | HIGH | all |
| P4.14 | guest_email is required (HTML validation) | HIGH | all |
| P4.15 | guest_phone is optional | MEDIUM | all |
| P4.16 | guest_count defaults to 1 | MEDIUM | all |
| P4.17 | notes field is optional textarea | LOW | all |
| P4.18 | Expert Consultation form shows "Continue to Payment" button | HIGH | 5 |
| P4.19 | Expert Consultation form shows payment amount info | HIGH | 5 |
| P4.20 | Booking with all fields filled (name, email, phone, count, notes) | HIGH | 1 |
| P4.21 | Booking with minimal fields (name + email only) | HIGH | 1 |
| P4.22 | Multiple bookings same type different times | MEDIUM | 1 |
| P4.23 | Booking creates partner (res.partner) with matching email | HIGH | 1 |
| P4.24 | Booking creates calendar event (calendar.event) | HIGH | 1 |
| P4.25 | Booking state is "confirmed" (auto_confirm=True for all types) | HIGH | 1 |
| P4.26 | Booking access_token is generated (non-empty) | HIGH | 1 |
| P4.27 | Booking start_datetime matches form selection | HIGH | all |
| P4.28 | Booking staff_user_id matches selected staff | HIGH | 1 |
| P4.29 | Booking resource_id matches selected resource | HIGH | 3 |
| P4.30 | Booking duration matches type config | MEDIUM | all |

### P5: Confirmation & Booking Detail Pages (12 tests)

| ID | Test | Severity |
|----|------|----------|
| P5.1 | Confirmation page shows success message | HIGH |
| P5.2 | Confirmation page shows booking reference (APTxxxxx) | HIGH |
| P5.3 | Confirmation page shows appointment details (date, time, type) | HIGH |
| P5.4 | Booking detail page accessible via token URL | HIGH |
| P5.5 | Booking detail shows guest name, email | MEDIUM |
| P5.6 | Booking detail shows status (confirmed) | MEDIUM |
| P5.7 | Booking detail has cancel link/button | MEDIUM |
| P5.8 | Booking detail without token returns 403 or redirect | HIGH |
| P5.9 | Booking detail with wrong token returns 403 or error | HIGH |
| P5.10 | Booking detail for cancelled booking shows cancelled status | MEDIUM |
| P5.11 | Confirmation page for Restaurant shows table name | MEDIUM |
| P5.12 | Confirmation page for Business Meeting shows staff name | MEDIUM |

### P6: Cancel Flow (10 tests)

| ID | Test | Severity |
|----|------|----------|
| P6.1 | Cancel page loads with confirmation dialog | HIGH |
| P6.2 | Cancel page requires valid token | HIGH |
| P6.3 | Submit cancel → booking state changes to "cancelled" | CRITICAL |
| P6.4 | Cancel success page shows cancellation confirmation | HIGH |
| P6.5 | Cancelled booking's calendar event is deleted/cancelled | HIGH |
| P6.6 | Cancel within deadline succeeds (Business Meeting: 24h) | HIGH |
| P6.7 | Already cancelled booking shows appropriate message | MEDIUM |
| P6.8 | Cancel page shows booking details before confirming | MEDIUM |
| P6.9 | Cancel with invalid token returns error | MEDIUM |
| P6.10 | Re-book link appears after cancellation | LOW |

### P7: Payment Flow — Expert Consultation (10 tests)

| ID | Test | Severity |
|----|------|----------|
| P7.1 | After booking Expert, redirects to payment page | CRITICAL |
| P7.2 | Payment page shows correct amount ($100) | HIGH |
| P7.3 | Payment page shows booking summary | HIGH |
| P7.4 | Payment page has payment provider selection | HIGH |
| P7.5 | Payment page requires valid token | HIGH |
| P7.6 | Booking state is "draft" before payment | HIGH |
| P7.7 | Payment page shows guest_count × amount if per_person | MEDIUM |
| P7.8 | Payment page accessible via token only | MEDIUM |
| P7.9 | Payment page with wrong token returns error | MEDIUM |
| P7.10 | Back button or re-visit payment page works | LOW |

### P8: Cross-Module Integration (20 tests)

| ID | Test | Severity | Integration |
|----|------|----------|-------------|
| P8.1 | Booking creates res.partner with guest_email | HIGH | res.partner |
| P8.2 | Repeat booking with same email reuses existing partner | HIGH | res.partner |
| P8.3 | Partner has correct name from guest_name | HIGH | res.partner |
| P8.4 | Partner has correct phone from guest_phone | MEDIUM | res.partner |
| P8.5 | Booking creates calendar.event | HIGH | calendar |
| P8.6 | Calendar event has correct start/end datetime | HIGH | calendar |
| P8.7 | Calendar event name contains type name + guest name | MEDIUM | calendar |
| P8.8 | Calendar event links to booking's staff user | MEDIUM | calendar |
| P8.9 | Cancel booking deletes/cancels calendar event | HIGH | calendar |
| P8.10 | Multiple bookings create separate calendar events | MEDIUM | calendar |
| P8.11 | Resource booking (Restaurant) links resource_id correctly | HIGH | resource |
| P8.12 | Resource capacity tracked (booking_count on resource) | MEDIUM | resource |
| P8.13 | Staff booking links staff_user_id correctly | HIGH | hr/users |
| P8.14 | Staff conflict: two bookings same staff same time → second fails | HIGH | conflict |
| P8.15 | Payment booking creates payment.transaction record | HIGH | payment |
| P8.16 | Payment transaction has correct amount | HIGH | payment |
| P8.17 | Payment transaction links to booking | HIGH | payment |
| P8.18 | Booking sequence numbers (name field) auto-increment | MEDIUM | ir.sequence |
| P8.19 | Booking appears in appointment_type.booking_count | MEDIUM | computed |
| P8.20 | Partner created via booking visible in Contacts module | MEDIUM | res.partner |

### P9: Form Validation & Error Handling (15 tests)

| ID | Test | Severity |
|----|------|----------|
| P9.1 | Empty guest_name → form validation prevents submit | HIGH |
| P9.2 | Empty guest_email → form validation prevents submit | HIGH |
| P9.3 | Invalid email format → form validation rejects | HIGH |
| P9.4 | guest_count = 0 → validation or server error | MEDIUM |
| P9.5 | guest_count = -1 → validation or server error | MEDIUM |
| P9.6 | guest_count = 999 → accepted or capped | LOW |
| P9.7 | Very long guest_name (500 chars) → handled gracefully | MEDIUM |
| P9.8 | XSS in guest_name (`<script>alert(1)</script>`) → escaped in output | HIGH |
| P9.9 | XSS in notes field → escaped in confirmation page | HIGH |
| P9.10 | SQL injection in guest_email → no crash | HIGH |
| P9.11 | Missing start_datetime param → error page, not crash | HIGH |
| P9.12 | Invalid start_datetime format → error handling | MEDIUM |
| P9.13 | Past start_datetime → error or rejection | MEDIUM |
| P9.14 | start_datetime beyond max_booking_days → error | MEDIUM |
| P9.15 | Missing CSRF token (manual POST) → rejected | HIGH |

### P10: Edge Cases & Security (10 tests)

| ID | Test | Severity |
|----|------|----------|
| P10.1 | Rapid double-submit → only one booking created | HIGH |
| P10.2 | Booking unpublished type via direct URL → blocked | HIGH |
| P10.3 | Path traversal in type ID (`/appointment/../admin`) → 404 | HIGH |
| P10.4 | Non-integer type ID (`/appointment/abc`) → 404 | MEDIUM |
| P10.5 | Unicode in all text fields → saved and displayed correctly | MEDIUM |
| P10.6 | Emoji in guest_name → handled correctly | LOW |
| P10.7 | Empty notes field → booking succeeds | LOW |
| P10.8 | Concurrent bookings same time slot same resource → conflict handling | HIGH |
| P10.9 | Browser back after submit → no duplicate booking | MEDIUM |
| P10.10 | Session/cookies: public user has no auth cookies | LOW |

---

## 6. GO/NO-GO Criteria

| Severity | Threshold |
|----------|-----------|
| CRITICAL | 0 allowed |
| HIGH | 0 allowed |
| MEDIUM | ≤ 3 allowed |
| LOW | unlimited |

**GO** = 0 CRITICAL + 0 HIGH + ≤3 MEDIUM

---

## 7. Cross-Module Integration Matrix

| Module | Integration Point | Tests |
|--------|-------------------|-------|
| `res.partner` | Auto-create partner from guest email/name/phone | P8.1-P8.4, P8.20 |
| `calendar` | Auto-create calendar.event from confirmed booking | P8.5-P8.10 |
| `resource.resource` | Resource selection, capacity tracking | P8.11-P8.12 |
| `hr` / `res.users` | Staff assignment, conflict detection | P8.13-P8.14 |
| `payment` | Payment transaction, amount, status | P7.*, P8.15-P8.17 |
| `ir.sequence` | Booking reference auto-numbering | P8.18 |
| `mail` | Email templates (verified via template existence) | — |
| `website` | Published/unpublished visibility | P1.3, P2.9, P10.2 |

---

## 8. Execution Plan

1. Build test infrastructure (`conftest.py`, `config.py`, `pw_runner.py`)
2. Create all 10 test modules in parallel
3. Run Loop 1 → analyze failures → categorize as TEST FIX vs MODULE BUG
4. Fix test issues, re-run
5. Iterate until GO status achieved
6. Generate final report with screenshots
