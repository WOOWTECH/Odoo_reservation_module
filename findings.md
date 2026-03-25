# Findings: Test Gap Analysis

## Previous Test Coverage (28 tests in v1)
- C1: Token security ✓
- C2: Past date validation ✓
- C3: Guest count cap ✓
- H1: Unpublished endpoint protection ✓
- H2: Debug endpoint removal ✓
- H3: XSS sanitization ✓
- H4: Payment token validation ✓
- M1: Demo data availability ✓
- M2: Wizard removal ✓
- M3: Field removal ✓
- M4: Cron job ✓
- M5: Timezone handling ✓
- L1: ID validation ✓
- L2: Staff availability ✓
- F1-F6: Booking lifecycle (create/confirm/done) ✓
- W1-W2: Website page accessibility ✓

## Identified Gaps (NOT yet tested)

### Frontend / Browser
- [ ] Calendar month navigation (prev/next)
- [ ] Date cell click → slot loading
- [ ] Slot selection → booking form prefill
- [ ] Staff/location dropdown functionality
- [ ] Event mode calendar (only dates with events highlighted)
- [ ] Mobile responsive layout
- [ ] CSS rendering (badges, states, colors)
- [ ] JavaScript error-free page load
- [ ] Form validation (required fields, email format)
- [ ] Bilingual switching (zh_TW / en_US)
- [ ] Breadcrumb navigation
- [ ] Loading spinner display
- [ ] Error alert display styling

### API Endpoints (JSON-RPC)
- [ ] Slots endpoint with all param combos (date + resource + staff)
- [ ] Slots for event mode vs scheduled mode
- [ ] Event dates with boundary months (Jan, Dec)
- [ ] Concurrent API requests (race conditions)
- [ ] Malformed JSON-RPC body
- [ ] Missing required params
- [ ] Oversized request body
- [ ] Session/auth edge cases on public endpoints

### Backend Business Logic
- [ ] Auto-assign staff algorithm (least bookings wins)
- [ ] Auto-assign location algorithm
- [ ] Cross-type conflict detection
- [ ] Capacity management (fill to max, then reject)
- [ ] Booking state machine (all valid/invalid transitions)
- [ ] Cancel before deadline enforcement
- [ ] Cancel after deadline rejection
- [ ] Slot subdivision accuracy (1h, 30m, 2h durations)
- [ ] Slot interval spacing
- [ ] Min booking hours enforcement
- [ ] Max booking days enforcement
- [ ] Email template rendering
- [ ] Cron reminder logic (24h window accuracy)
- [ ] Payment flow (transaction creation, validation, post-process)
- [ ] Sequence number generation (APT00001, APT00002...)
- [ ] Calendar event creation with correct attendees
- [ ] Calendar event deletion on cancel
- [ ] Computed fields (total_capacity, booking_count, duration)
- [ ] Record rules (user sees own, manager sees all)
- [ ] Multi-company isolation

### All 5 Appointment Types
- [ ] Business Meeting: scheduled, staff, no capacity
- [ ] Video Consultation: scheduled, staff, online
- [ ] Restaurant Reservation: scheduled, capacity, resources
- [ ] Tennis Court Booking: scheduled, capacity, single resource
- [ ] Expert Consultation: scheduled, staff, PAYMENT required

### Forms & Templates
- [ ] Booking form: all field validation
- [ ] Booking form: XSS in all text fields
- [ ] Confirm page: correct data display
- [ ] Cancel page: flow completion
- [ ] Payment page: provider listing
- [ ] Backend form: all tabs render
- [ ] Backend kanban: card display
- [ ] Backend calendar: event display
- [ ] Backend list: sorting/filtering

### Edge Cases
- [ ] Booking at exactly midnight
- [ ] Booking spanning DST transition
- [ ] 0-capacity resource
- [ ] Empty availability (no schedule)
- [ ] Very long guest name (1000+ chars)
- [ ] Unicode/emoji in all text fields
- [ ] Concurrent bookings (same slot, same time)
- [ ] Booking deleted resource/staff
- [ ] Deactivated appointment type
- [ ] Maximum integer guest_count
- [ ] Negative/zero duration
- [ ] Same start and end datetime
- [ ] February 29 (leap year)
- [ ] Year boundary (Dec→Jan navigation)
- [ ] 100+ bookings in same slot

### Stability
- [ ] Rapid-fire API calls (rate limit behavior)
- [ ] Large dataset performance (1000+ bookings)
- [ ] Memory usage under load
- [ ] Database connection pool behavior
- [ ] Graceful error recovery
- [ ] Module upgrade idempotency
