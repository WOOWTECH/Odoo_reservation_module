# Comprehensive Test Plan — reservation_module v18.0.1.5.0

## Objective
Enterprise-grade deployment validation covering both new features and regression testing.

## Test Scope

### Feature 1: Online Meeting Videocall Integration
- Auto-generated Odoo Discuss videocall URL on booking confirmation
- Custom video_link override
- meeting_url computed field priority logic
- Calendar event creation without res_model/res_id
- Meeting URL display in confirmation page & booking details

### Feature 2: Sales Order Payment Integration
- SO creation with payment_product_id
- Portal redirect with access_token for anonymous users
- Per-person pricing (qty = guest_count)
- SO cancellation cascade
- Payment callback (direct tx & SO-linked)

### Security
- Cryptographic access_token (secrets.token_urlsafe)
- Token-based route protection
- CSRF validation
- Invalid token rejection

### Edge Cases
- Missing payment_product_id fallback
- Guest count boundary (0, 1, large)
- Concurrent booking conflict detection
- Event mode vs scheduled mode end_datetime
- Validation error re-render preserving form data

## Test Rounds

### Round 1: Backend API (XML-RPC)
- Model CRUD operations
- Computed field verification
- Method logic (confirm, cancel, create_sale_order, create_calendar_event)

### Round 2: HTTP Flow (requests library)
- Full booking flow via form POST
- Payment redirect verification
- Token protection on all routes
- Validation error handling
- Language/translation switching

### Round 3: Browser UI (Chrome DevTools MCP)
- Visual rendering of key pages
- Button visibility/state
- Form interaction
- Responsive layout

### Round 4: Edge Cases & Stress
- Boundary values
- Concurrent bookings
- Cross-type conflict detection
- Cancellation with/without paid invoices

### Round 5: Regression
- Existing features still work after changes
- Scheduled mode booking flow
- Event mode booking flow
- Auto-assign staff/location
- Email template rendering

## Pass Criteria
- All critical paths return expected results
- No 500 errors on any public route
- Security tokens are cryptographically random
- SO portal accessible without login via access_token
- Videocall URLs generated correctly for online types
