# PRD: Online Meeting Integration + Sales Order Payment Flow

**Date:** 2026-03-31
**Module:** reservation_module (v18.0.1.4.0 → v18.0.1.5.0)
**Status:** Approved
**Principles:** Use native Odoo mechanisms exclusively — no custom implementations where Odoo already provides the feature.

---

## Feature 1: Online Meeting (Odoo Videocall) Integration

### Problem

When `location_type = 'online'`, the appointment type form shows a plain `video_link` text field requiring manual URL entry. This is disconnected from Odoo's built-in calendar videocall system.

### Solution

Use Odoo 18's native calendar videocall mechanism. When a booking is confirmed for an online appointment type, the system creates a `calendar.event` with Odoo Discuss videocall enabled — generating a unique meeting URL automatically. The `video_link` field remains as an optional override.

### Design

#### Model Changes — `appointment.type`

No field changes. Keep existing `video_link` field as optional override.

#### Model Changes — `appointment.booking`

Add computed field:
- `meeting_url` (Char, computed): Returns `video_link` override if set, otherwise returns `calendar_event_id.videocall_location`.

#### Logic Changes — `appointment_booking.py :: _create_calendar_event()`

When `appointment_type.location_type == 'online'`:

1. If `appointment_type.video_link` is set (manual override):
   - Create calendar event with `videocall_location = video_link` (custom source)
2. If `video_link` is empty:
   - Create calendar event normally
   - Call `event._set_discuss_videocall_location()` to auto-generate Odoo videocall URL
   - This generates: `{base_url}/calendar/join_videocall/{access_token}`

#### View Changes — Backend `appointment_type_views.xml`

Replace the simple `video_link` text field in the Location section:
- Show `video_link` as "Custom Video Link (optional)" with help text: "Leave blank to auto-generate Odoo meeting link for each booking"
- Only visible when `location_type == 'online'`

#### Template Changes — `appointment_templates.xml`

On the booking confirmation page and booking detail page:
- When `location_type == 'online'` and `meeting_url` exists:
  - Show a "Join Meeting" button with the meeting URL
- On the email template: include meeting link in confirmation email

#### Files Modified

| File | Change |
|------|--------|
| `models/appointment_booking.py` | Add `meeting_url` computed field; update `_create_calendar_event()` for videocall |
| `views/appointment_type_views.xml` | Update `video_link` label/help text |
| `views/appointment_templates.xml` | Add "Join Meeting" button on confirmation/detail pages |
| `data/appointment_data.xml` | Update email template to include meeting link |

---

## Feature 2: Sales Order Integration for Paid Bookings

### Problem

Currently, paid bookings create `payment.transaction` records directly. There is no Sales Order, so there's no invoice, no sales analytics, and no integration with the standard Odoo sales workflow.

### Solution

When a booking requires payment (`require_payment = True`), automatically create a `sale.order` when the booking is submitted. Then redirect the user to Odoo's native SO portal payment page (`/my/orders/{so_id}`). After payment, Odoo's standard SO flow handles: order confirmation → invoice creation → payment reconciliation.

### Design

#### New Dependency

Add `sale` to `__manifest__.py` depends list.

#### Model Changes — `appointment.booking`

New fields:
- `sale_order_id` (Many2one `sale.order`): Link to the created Sales Order.
- `sale_order_state` (Selection, related): Quick reference to SO state.

#### New Method — `appointment_booking.py :: _create_sale_order()`

```
def _create_sale_order(self):
    """Create a sale order for paid bookings."""
    SO vals:
        partner_id = self.partner_id  (already created/found by email)
        order_line:
            product_id = appointment_type.payment_product_id
            product_uom_qty = guest_count if payment_per_person else 1
            price_unit = appointment_type.payment_amount
        note: Booking reference, appointment type, date/time

    Create SO → Confirm SO (action_confirm) → Return SO
```

#### Controller Changes — `controllers/main.py :: _process_booking()`

Current flow:
```
submit form → create booking → if require_payment → redirect /appointment/booking/{id}/pay
```

New flow:
```
submit form → create booking → if require_payment:
    → create partner (existing logic)
    → call booking._create_sale_order()
    → redirect to /my/orders/{so_id} (Odoo's native SO portal page)
```

The user then uses Odoo's standard "Pay Now" button on the SO portal page.

#### Payment Callback Changes — `payment_transaction.py`

Update `_post_process_after_done()`:
- Odoo's `sale` module already handles SO → invoice flow via payment transaction
- After payment completes, check if the transaction's SO has a linked booking
- If yes: update `booking.payment_status = 'paid'` and auto-confirm

Alternative approach: Override `sale.order` write to detect state changes and trigger booking confirmation.

Simplest approach: In `_post_process_after_done()`, look up booking from SO:
```python
for tx in self:
    # Handle direct booking transactions (backward compat)
    if tx.appointment_booking_id:
        ...existing logic...
    # Handle SO-linked booking transactions
    for so in tx.sale_order_ids:
        bookings = self.env['appointment.booking'].search([
            ('sale_order_id', '=', so.id),
            ('payment_status', '=', 'pending'),
        ])
        for booking in bookings:
            booking.write({'payment_status': 'paid', 'payment_transaction_id': tx.id})
            if booking.appointment_type_id.auto_confirm:
                booking.action_confirm()
```

#### Cancellation / Refund Handling

When a booking is cancelled:
- If SO exists and is in `sale` state: cancel the SO
- If SO has an invoice paid: do NOT auto-refund (admin handles manually)
- Add warning in booking cancel if SO/invoice exists

#### View Changes — Backend

- `appointment_booking_views.xml`: Add `sale_order_id` field (smart button or field) on booking form
- Show SO state badge

#### Template Changes — Frontend

- Remove `/appointment/booking/{id}/pay` route for new bookings (keep for backward compat)
- On booking confirmation page (for pending payment): show link to SO portal page
- After payment: show standard confirmation page

#### Security

- `ir.model.access.csv`: Booking model needs read access to `sale.order` via sudo
- SO creation uses `sudo()` since website users don't have sale.order create rights
- Portal users can view their own SOs via Odoo's built-in portal access rules

#### Files Modified

| File | Change |
|------|--------|
| `__manifest__.py` | Add `sale` dependency, bump version to 18.0.1.5.0 |
| `models/__init__.py` | (no change if no new model files) |
| `models/appointment_booking.py` | Add `sale_order_id` field, `_create_sale_order()` method, update cancel |
| `models/payment_transaction.py` | Update `_post_process_after_done()` for SO-linked bookings |
| `controllers/main.py` | Update `_process_booking()` to create SO and redirect to portal |
| `views/appointment_booking_views.xml` | Add SO field/smart button |
| `views/appointment_templates.xml` | Update confirmation page for SO link |
| `security/ir.model.access.csv` | Ensure proper access for sale.order interaction |

---

## Migration Notes

- Version bump: 18.0.1.4.0 → 18.0.1.5.0
- New dependency `sale` requires module installation on existing instances
- Existing bookings with `payment_status = 'paid'` are unaffected (no SO, direct transaction)
- New bookings with `require_payment = True` will go through SO flow
- `video_link` field remains — no data migration needed

---

## Testing Plan

### Feature 1 Tests
1. Create online appointment type with empty video_link → book → confirm → verify Odoo videocall URL generated
2. Create online appointment type with custom video_link → book → confirm → verify custom URL used
3. Verify meeting URL appears on confirmation page and in email
4. Verify "Join Meeting" button links correctly

### Feature 2 Tests
1. Create paid appointment type → book as portal user → verify SO created with correct partner
2. Book as public user → verify partner auto-created → SO created
3. Complete payment on SO portal page → verify booking auto-confirmed
4. Cancel booking with pending SO → verify SO cancelled
5. Verify SO line has correct product, qty (per-person vs flat), price
6. Verify invoice generated after payment via standard SO flow
