# Recommended Priority Improvements

Competitive analysis of Calendly, Acuity Scheduling, Cal.com, SimplyBook.me, and Setmore identified the following feature gaps in our reservation module. Items are ordered by priority based on customer impact and implementation complexity.

---

## 1. Automated Booking Reminders (High Priority)

**Gap:** The reminder email template (`mail_template_appointment_reminder`) exists but no scheduled action (cron job) triggers it automatically.

**What competitors do:** All major platforms (Calendly, Acuity, Cal.com, SimplyBook.me, Setmore) send automated reminders via email and SMS at configurable intervals before the appointment (e.g., 24 hours, 1 hour before).

**Proposed implementation:**
- Add an `ir.cron` scheduled action that runs hourly
- Query confirmed bookings where `start_datetime` is within the configured reminder window
- Add a `reminder_sent` boolean field on `appointment.booking` to prevent duplicate sends
- Add configurable reminder timing on `appointment.type` (e.g., `reminder_hours` field, default 24)
- Send the existing reminder template to matching bookings

**Estimated scope:** Small — leverages existing template and mail infrastructure.

---

## 2. Buffer Times Between Appointments (High Priority)

**Gap:** No padding time between consecutive bookings. Back-to-back slots can be generated without breaks for staff or resource preparation.

**What competitors do:** Calendly and Cal.com allow configuring buffer time before and/or after each appointment. This prevents bookings from being scheduled too close together.

**Proposed implementation:**
- Add `buffer_before` and `buffer_after` float fields (in minutes) on `appointment.type`
- Modify slot generation logic to exclude slots that would overlap with existing bookings plus their buffer windows
- Display effective availability (accounting for buffers) on the booking portal

**Estimated scope:** Medium — requires changes to slot generation algorithm.

---

## 3. Round-Robin Staff Assignment (High Priority)

**Gap:** Current assignment methods are "automatic" (not clearly distributed) and "customer choice." There is no fair distribution mechanism that balances bookings across staff members.

**What competitors do:** Calendly's round-robin distributes meetings evenly across team members based on availability and booking count. Cal.com offers similar functionality.

**Proposed implementation:**
- Add `round_robin` as an `assignment_method` selection option
- When a customer books without choosing a specific staff member, assign to the staff member with the fewest upcoming bookings who is available at the requested time
- Track assignment counts per staff member per appointment type
- Optionally support weighted distribution (e.g., senior staff gets 2x bookings)

**Estimated scope:** Medium — extends existing assignment logic with booking count queries.

---

## 4. Recurring / Repeating Bookings (Medium Priority)

**Gap:** Customers can only book one-time appointments. There is no way to book a repeating series (e.g., "every Tuesday at 3 PM for 8 weeks").

**What competitors do:** Acuity, Calendly, and Setmore (Pro) support recurring appointments. Customers can set a repeat pattern and book multiple sessions at once.

**Proposed implementation:**
- Add recurrence fields on `appointment.booking`: `is_recurring`, `recurrence_pattern` (weekly/biweekly/monthly), `recurrence_count`
- On booking creation, generate linked child bookings for each occurrence
- Link all bookings in a series via a `recurrence_id` field
- Allow cancellation of single occurrence or entire series
- Validate capacity/availability for all occurrences before confirming
- Handle payment for the full series or per-session

**Estimated scope:** Large — new booking creation flow, UI changes, and payment handling.

---

## 5. Embeddable Booking Widget (Medium Priority)

**Gap:** The booking portal is only accessible as a full page on the Odoo website. It cannot be embedded on external websites.

**What competitors do:** All competitors offer JavaScript embed snippets. Cal.com provides inline, popup, and button embed modes. Calendly offers similar inline and popup embeds.

**Proposed implementation:**
- Create a standalone JavaScript widget (`reservation_widget.js`) that can be included via `<script>` tag
- Widget loads appointment type selector and booking flow in an iframe or shadow DOM
- Support configuration options: appointment type ID, theme color, language, embed mode (inline/popup/button)
- Add a "Get Embed Code" button in the appointment type form view
- Handle cross-origin communication for payment flow

**Estimated scope:** Large — new frontend asset, cross-origin considerations, and standalone rendering.

---

## 6. SMS / WhatsApp Notifications (Medium Priority)

**Gap:** Only email notifications are supported. No SMS or messaging app integration exists.

**What competitors do:** All major platforms support SMS reminders. SimplyBook.me also supports WhatsApp. Calendly and Cal.com support SMS confirmations and reminders.

**Proposed implementation:**
- Integrate with Odoo's SMS module (`sms`) for SMS notifications
- Add `notification_channel` selection on `appointment.type`: email, SMS, or both
- Create SMS templates for confirmation, cancellation, and reminder
- For WhatsApp: integrate via Odoo's WhatsApp module or third-party provider
- Add phone number validation on booking form (already collected but not used for notifications)

**Estimated scope:** Medium — depends on Odoo SMS module availability and provider setup.

---

## 7. Routing Forms / Pre-Booking Qualification (Low Priority)

**Gap:** All visitors go directly to the booking flow. There is no way to screen or route visitors to different appointment types based on their answers.

**What competitors do:** Calendly and Cal.com offer routing forms that ask qualifying questions and direct visitors to the appropriate event type, staff member, or external URL.

**Proposed implementation:**
- Create a `appointment.routing.form` model with configurable questions and routing rules
- Each rule maps answer combinations to a target appointment type or URL
- Add a `/appointment/route/<form_id>` controller endpoint
- Render a multi-step form that evaluates rules and redirects accordingly

**Estimated scope:** Medium — new model, controller, and template.

---

## 8. Packages and Memberships (Low Priority)

**Gap:** Each booking is a standalone transaction. There is no way to sell bundles of sessions or recurring memberships.

**What competitors do:** Acuity and SimplyBook.me sell session packages (e.g., "10 yoga classes"), gift certificates, and monthly memberships with automated billing.

**Proposed implementation:**
- Create an `appointment.package` model: name, appointment type, session count, price, validity period
- Track remaining sessions per customer via `appointment.package.usage`
- Allow customers to purchase packages through the website portal
- On booking, deduct from package balance instead of collecting payment
- Add package management views in backend and customer portal

**Estimated scope:** Large — new models, payment flow changes, and portal views.

---

## Summary Matrix

| # | Feature | Priority | Scope | Dependencies |
|---|---------|----------|-------|-------------|
| 1 | Automated Reminders | High | Small | Existing mail template |
| 2 | Buffer Times | High | Medium | Slot generation logic |
| 3 | Round-Robin Assignment | High | Medium | Staff assignment logic |
| 4 | Recurring Bookings | Medium | Large | Booking creation flow |
| 5 | Embeddable Widget | Medium | Large | Frontend JS, iframe |
| 6 | SMS/WhatsApp Notifications | Medium | Medium | Odoo SMS module |
| 7 | Routing Forms | Low | Medium | New model + controller |
| 8 | Packages & Memberships | Low | Large | New models + payment |
