# PRD: Portal Booking Features - Enterprise E2E Test Plan

**Date:** 2026-04-02
**Module:** reservation_module (Odoo 18)
**Version:** 18.0.1.6.0
**Target:** Enterprise deployment-grade validation

---

## 1. Scope

Comprehensive testing of newly implemented portal booking features:

| Feature | Route/Component | Auth |
|---------|----------------|------|
| Portal Home Card | `/my/home` (booking_count) | user |
| Bookings List | `/my/bookings` (sort/filter/page) | user |
| Booking Detail | `/my/bookings/<id>` | user |
| Confirmation Page | `/appointment/booking/<id>/confirm?token=` | public |
| Email Templates | 3 mail.template records | N/A |

---

## 2. Test Rounds

### Round 1: Backend API Tests
- Portal route HTTP status codes (200/302/403/404)
- Sorting (date/name/state) correctness
- Filtering (all/upcoming/completed/cancelled) domain logic
- Pagination boundary (0/1/many pages)
- Partner ownership enforcement
- `_prepare_home_portal_values` booking_count accuracy

### Round 2: Browser E2E Tests
- Portal home card visibility and count
- Bookings list rendering (columns, badges, links)
- Sort/filter dropdown interactions
- Detail page card layout and fields
- Cancel button presence/absence by state
- Confirmation page email notice + View My Bookings button
- Meeting URL conditional rendering

### Round 3: Security & Access Control
- Unauthenticated access → login redirect
- Cross-user booking access (partner_id mismatch)
- SQL injection in sort/filter params
- XSS in booking data display
- Token validation on confirmation page
- Invalid booking_id handling

### Round 4: Edge Cases
- Zero bookings (empty state)
- Bookings in all 4 states (draft/confirmed/done/cancelled)
- Booking with/without meeting_url
- Booking with/without staff/resource
- Booking with/without payment
- Long names / special characters in fields
- Pagination with exactly 10, 11, 20 items

### Round 5: Email Template Validation
- Confirmed email renders with all fields
- Confirmed email renders meeting URL button conditionally
- Cancelled email renders correctly
- Reminder email renders with meeting URL
- get_portal_url() generates valid URLs in emails
- Email subject lines contain booking reference

### Round 6: Cross-Module Integration
- Portal breadcrumbs navigation
- Cancel booking from portal detail → state change
- Booking list updates after state changes
- Email sending triggers on confirmation/cancellation
- Portal URL in email navigates to correct booking

---

## 3. Pass Criteria

- **Enterprise Grade:** ≥ 95% pass rate across all rounds
- **Zero Critical:** No security or data access failures
- **Zero P1:** No functional blocking issues
