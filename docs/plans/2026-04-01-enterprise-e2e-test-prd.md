# Enterprise E2E Test PRD: Reservation Module Payment Flow
**Date:** 2026-04-01
**Module:** reservation_module (Odoo 18)
**Version:** 18.0.1.5.0
**Target:** Commercial enterprise deployment readiness

---

## 1. Objective

Validate the complete appointment booking → sales order → payment → invoice → confirmation pipeline to enterprise deployment quality. Tests cover happy paths, edge cases, cross-module interactions, error recovery, and data integrity across Sales, Invoicing, Payment, Website, Calendar, and Contacts modules.

## 2. Test Environment

| Component | Value |
|-----------|-------|
| Container | `odoo-reservation-web` (port 9073→8069) |
| Database | `odooreservation` |
| Credentials | admin/admin |
| Payment Provider | Demo (test mode, "Successful" status) |
| Appointment Types | 9 types (5 free, 2 paid: ID=5 Expert $100, ID=13 Test Paid $50) |
| Access | XML-RPC (localhost:8069), Browser (localhost:9073) |

## 3. Test Rounds

### Round 1: Browser E2E — Happy Path (Paid + Free)

| # | Test Case | Steps | Expected |
|---|-----------|-------|----------|
| 1.1 | Paid booking full flow | Book Expert Consultation → SO portal → Sign & Pay → Demo → verify | booking=confirmed, payment_status=paid, invoice=posted+paid |
| 1.2 | Free booking full flow | Book Business Meeting → auto-confirm | booking=confirmed, payment_status=not_required, calendar_event created |
| 1.3 | Online meeting URL | Book Video Consultation → confirm → check meeting_url | meeting_url populated, "Join Meeting" button visible |
| 1.4 | Guest count pricing | Book Expert Consultation with guest_count=3 → verify SO amount | SO amount = $100 × 3 = $300 (if payment_per_person) or $100 |
| 1.5 | Confirmation page render | After booking confirm → check all elements | Booking ref, datetime, type, staff, location all displayed |

### Round 2: Backend API — XML-RPC Cross-Module Integrity

| # | Test Case | Steps | Expected |
|---|-----------|-------|----------|
| 2.1 | Booking→SO link | Create booking with payment → check sale_order_id | SO exists, SO.origin = booking.name |
| 2.2 | SO→Invoice link | After payment → check SO.invoice_ids | Invoice posted, amount matches |
| 2.3 | Invoice→Payment link | Check invoice payment_state | payment_state='paid', payment reconciled |
| 2.4 | Booking→Calendar link | Confirm booking → check calendar_event_id | Event exists, partner+staff as attendees |
| 2.5 | Partner deduplication | Book with same email twice → check partner_id | Same partner_id for both bookings |
| 2.6 | Booking field integrity | Read all booking fields after full flow | All computed fields correct (duration, meeting_url, etc.) |
| 2.7 | Access token security | Try access booking without token | Should fail or return 403 |
| 2.8 | SO portal access | Check SO access_token populated | access_token present, portal URL works |

### Round 3: Edge Cases — Payment Failures & Cancellations

| # | Test Case | Steps | Expected |
|---|-----------|-------|----------|
| 3.1 | Cancel before payment | Book paid type → cancel before paying | booking=cancelled, SO cancelled (if no paid invoice) |
| 3.2 | Cancel after payment | Book → pay → try cancel | Should cancel (or block if past deadline) |
| 3.3 | Cancellation deadline | Book slot 1 hour away, cancel_before_hours=2 | Cancellation blocked with error |
| 3.4 | Payment pending state | Book paid type → don't pay → check state | booking=draft, payment_status=pending |
| 3.5 | Orphaned SO | Book paid type → SO created but no payment | SO in 'sent' state, booking still pending |
| 3.6 | Double booking attempt | Book same slot with same guest_email | Should succeed (no unique constraint) or show conflict |
| 3.7 | Past date booking | Try to book slot in the past | Should be rejected by min_booking_hours check |

### Round 4: Concurrent Slots & Resource Conflicts

| # | Test Case | Steps | Expected |
|---|-----------|-------|----------|
| 4.1 | Staff conflict detection | Book staff A 10:00-11:00, then try same staff same time | Second booking slot unavailable |
| 4.2 | Resource capacity | Book resource to full capacity → check availability | Slot shows as full/unavailable |
| 4.3 | Cross-type conflict | Book staff on Type A 10:00, then Type B 10:00 same staff | Conflict detected across types |
| 4.4 | Slot availability API | GET /slots for a booked date → check remaining count | available_count decremented |
| 4.5 | Max concurrent bookings | Exceed max_concurrent_bookings per user | Should be enforced |

### Round 5: Error Recovery & Resilience

| # | Test Case | Steps | Expected |
|---|-----------|-------|----------|
| 5.1 | Invalid email format | Submit booking with bad email | Form error, booking not created |
| 5.2 | Missing required fields | Submit without guest_name | Form error, booking not created |
| 5.3 | Invalid datetime format | POST with malformed datetime | Graceful error handling |
| 5.4 | Unpublished type access | Navigate to /appointment/6 (unpublished) | 404 or redirect |
| 5.5 | Deactivated type access | Navigate to /appointment/9 (deactivated) | 404 or redirect |
| 5.6 | Invalid booking token | GET /appointment/booking/999?token=wrong | 404 or access denied |
| 5.7 | Payment TX post-process retry | Reset is_post_processed flag → trigger cron | Should re-process correctly |
| 5.8 | SO without matching booking | Create standalone SO → run post-process | No crash, graceful skip |

### Round 6: Cross-Module Interaction Verification

| # | Test Case | Steps | Expected |
|---|-----------|-------|----------|
| 6.1 | Sales module visibility | Check SOs in Sales → Orders | All booking SOs visible |
| 6.2 | Invoicing module visibility | Check invoices in Invoicing | All booking invoices visible |
| 6.3 | Contacts module | Check partners created from bookings | Partners exist with correct data |
| 6.4 | Calendar module | Check events from confirmed bookings | Events with correct datetime, attendees |
| 6.5 | Payment module | Check transactions in Payment → Transactions | TXs with correct state and amounts |
| 6.6 | Website module | Check appointment pages render | All published types visible |

## 4. Success Criteria

- **100% pass rate** on Round 1 (happy path)
- **100% pass rate** on Round 2 (data integrity)
- **>90% pass rate** on Rounds 3-5 (edge cases, with documented exceptions)
- **100% pass rate** on Round 6 (cross-module)
- **Zero data corruption** across all test rounds
- **Zero unhandled exceptions** in Odoo logs during testing

## 5. Test Execution Method

| Method | Tool | Purpose |
|--------|------|---------|
| Browser | Chrome DevTools MCP | Full UI E2E flows |
| Backend API | XML-RPC via podman exec | Data integrity, cross-module queries |
| Odoo Logs | podman logs | Error detection, exception monitoring |
| Screenshots | Chrome DevTools screenshots | Visual evidence of UI states |

## 6. Deliverables

1. This PRD document
2. Test execution logs (all rounds)
3. Screenshots of key UI states
4. Final pass/fail report with metrics
5. List of issues found and remediation status
