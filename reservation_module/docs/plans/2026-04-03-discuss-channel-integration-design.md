# Design: Reservation Module + cs_portal_discuss Integration

## Date
2026-04-03

## Summary
Integrate `reservation_module` online meetings with `cs_portal_discuss` by creating a `discuss.channel` per confirmed booking. The Discuss channel becomes the unified meeting room: chat, video calls, and file sharing in one place. Portal users access their meeting channels via `/my/discussions`.

---

## Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| When to create channel? | On booking confirmation (`state → confirmed`) | Draft bookings may never confirm; confirmed = committed |
| Who are the members? | Staff user + Guest partner only | Mirrors 1:1 booking nature; others can be added manually |
| Channel type? | `channel` | Each booking gets its own named, isolated channel; supported by cs_portal_discuss |
| Lifecycle on `done`? | Channel stays open | Enables post-appointment follow-up communication |
| Lifecycle on `cancelled`? | Auto-archive channel | Cleans up portal list; history preserved in DB |
| Meeting URL strategy? | Replace with Discuss channel link | Single entry point; video calls via Discuss built-in call |
| Videocall mechanism? | Discuss built-in "Start a Call" | Same underlying Odoo RTC; no separate videocall URL needed |
| Hard dependency? | No — soft-coupled via runtime check | reservation_module works standalone; cs_portal_discuss enhances it |

---

## Architecture

### Channel Creation Flow

```
Booking confirmed (action_confirm)
  │
  ├── _create_calendar_event()    [existing — modified]
  │     └── Skips videocall_location when discuss channel will be created
  │
  └── _create_discuss_channel()   [new]
        ├── Check if cs_portal_discuss is installed (runtime)
        │     └── If not installed → return (fall back to videocall URL)
        ├── Create discuss.channel
        │     ├── name: "{Appointment Type} - {Guest Name} ({Booking Ref})"
        │     ├── channel_type: 'channel'
        │     └── channel_member_ids: [staff partner, guest partner]
        ├── Post welcome message
        │     └── "Appointment scheduled for {date} at {time}.
        │          Use the call button above to start your video meeting."
        └── Set self.discuss_channel_id = channel
```

### meeting_url Computation Priority (modified)

```
1. discuss_channel_id        → /discuss/channel/{id}?discussions=1
2. appointment_type.video_link → manual URL (Zoom/Teams/etc)
3. calendar_event.videocall_location → legacy auto-generated URL
4. False
```

This ensures:
- New bookings (cs_portal_discuss installed) → Discuss channel URL
- Existing bookings (created before change) → existing videocall URL preserved
- Bookings without cs_portal_discuss → existing video_link/videocall behavior
- Manual video_link override → respected when no discuss channel

### Lifecycle State Transitions

```
                    ┌─────────────────────────────────────────┐
                    │              discuss.channel             │
                    ├─────────────────────────────────────────┤
  confirmed ───────►│  CREATED (active=True)                  │
                    │  Welcome message posted                 │
                    │  Visible in /my/discussions              │
                    ├─────────────────────────────────────────┤
  done ────────────►│  NO CHANGE (stays active)               │
                    │  Portal user can continue chatting      │
                    ├─────────────────────────────────────────┤
  cancelled ───────►│  ARCHIVED (active=False)                │
                    │  Farewell message posted                │
                    │  Hidden from /my/discussions             │
                    ├─────────────────────────────────────────┤
  draft (re-open) ─►│  UNARCHIVED (active=True)               │
                    │  Reopen message posted                  │
                    │  Visible again in /my/discussions        │
                    └─────────────────────────────────────────┘
```

---

## Code Changes

### models/appointment_booking.py

**New field:**
```python
discuss_channel_id = fields.Many2one(
    'discuss.channel', string='Discussion Channel',
    copy=False, ondelete='set null',
)
```

**New method: `_create_discuss_channel()`**
```python
def _create_discuss_channel(self):
    """Create a Discuss channel for this booking (if cs_portal_discuss is installed)."""
    self.ensure_one()
    if self.discuss_channel_id:
        return self.discuss_channel_id

    # Soft-couple: only create if cs_portal_discuss is installed
    installed = self.env['ir.module.module'].sudo().search([
        ('name', '=', 'cs_portal_discuss'),
        ('state', '=', 'installed'),
    ], limit=1)
    if not installed:
        return self.env['discuss.channel']

    # Determine members
    members = []
    staff_partner = self.staff_user_id.partner_id if self.staff_user_id else self.env.user.partner_id
    members.append(staff_partner.id)
    if self.partner_id:
        members.append(self.partner_id.id)

    channel = self.env['discuss.channel'].sudo().create({
        'name': f"{self.appointment_type_id.name} - {self.guest_name} ({self.name})",
        'channel_type': 'channel',
        'channel_member_ids': [
            (0, 0, {'partner_id': pid}) for pid in members
        ],
    })

    # Post welcome message
    start_dt = fields.Datetime.context_timestamp(self, self.start_datetime)
    channel.message_post(
        body=_(
            "Appointment scheduled for %(date)s at %(time)s.\n"
            "Use the call button above to start your video meeting.",
            date=start_dt.strftime('%Y-%m-%d'),
            time=start_dt.strftime('%H:%M'),
        ),
        message_type='notification',
        subtype_xmlid='mail.mt_comment',
    )

    self.discuss_channel_id = channel
    return channel
```

**Modified: `action_confirm()`** — add `_create_discuss_channel()` call after `_create_calendar_event()`

**Modified: `action_cancel()`** — archive channel:
```python
if self.discuss_channel_id and self.discuss_channel_id.active:
    self.discuss_channel_id.message_post(
        body=_("This booking has been cancelled. The discussion is now archived."),
        message_type='notification',
        subtype_xmlid='mail.mt_comment',
    )
    self.discuss_channel_id.sudo().write({'active': False})
```

**Modified: `action_draft()`** — unarchive channel:
```python
if self.discuss_channel_id and not self.discuss_channel_id.active:
    self.discuss_channel_id.sudo().write({'active': True})
    self.discuss_channel_id.message_post(
        body=_("This booking has been reopened."),
        message_type='notification',
        subtype_xmlid='mail.mt_comment',
    )
```

**Modified: `_compute_meeting_url()`** — new priority:
```python
@api.depends('discuss_channel_id', 'appointment_type_id.video_link',
             'appointment_type_id.location_type', 'calendar_event_id.videocall_location')
def _compute_meeting_url(self):
    base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
    for booking in self:
        if booking.discuss_channel_id:
            booking.meeting_url = f"/discuss/channel/{booking.discuss_channel_id.id}?discussions=1"
        elif booking.appointment_type_id.video_link:
            booking.meeting_url = booking.appointment_type_id.video_link
        elif booking.calendar_event_id.videocall_location:
            booking.meeting_url = booking.calendar_event_id.videocall_location
        else:
            booking.meeting_url = False
```

**Modified: `_create_calendar_event()`** — skip videocall_location when discuss channel exists:
```python
if appointment_type.location_type == 'online' and not self.discuss_channel_id:
    # Only generate videocall URL if no discuss channel (fallback path)
    if appointment_type.video_link:
        event_vals['videocall_location'] = appointment_type.video_link
    else:
        access_token = uuid.uuid4().hex
        event_vals['access_token'] = access_token
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        event_vals['videocall_location'] = f"{base_url}/calendar/join_videocall/{access_token}"
```

### views/portal_templates.xml

Change "Join Meeting" button label when URL points to discuss channel:
```xml
<a t-att-href="booking.meeting_url" class="btn btn-primary" target="_blank">
    <t t-if="booking.discuss_channel_id">Open Meeting Room</t>
    <t t-else="">Join Meeting</t>
</a>
```

### __manifest__.py

No changes. No hard dependency on `cs_portal_discuss`.

### cs_portal_discuss module

Zero modifications needed. It already:
- Lists all `channel` type records where portal user is a member
- Handles `/discuss/channel/<id>?discussions=1` routing
- Supports video calls within channels via Discuss built-in call

---

## What Does NOT Change

- `cs_portal_discuss` — no modifications
- Email templates — they use `booking.meeting_url` which auto-resolves
- `appointment_templates.xml` — confirmation page uses `meeting_url`
- Existing bookings — their videocall URLs are preserved via fallback logic
- `calendar.event` creation — still created for calendar sync, just without videocall_location

---

## Scope

- ~60-80 lines new/modified Python in `appointment_booking.py`
- ~2 lines template change in `portal_templates.xml`
- 0 lines changed in `cs_portal_discuss`
- Backward compatible — existing bookings unaffected
- Soft-coupled — works with or without `cs_portal_discuss`

---

## Portal User Experience

1. User books an online appointment
2. Booking is confirmed (by payment or admin)
3. A Discuss channel is automatically created
4. User sees "Open Meeting Room" on their booking detail page
5. User finds the channel in `/my/discussions` list
6. Before the meeting: user can chat with staff in the channel
7. At meeting time: user clicks "Start a Call" in the channel for video
8. After meeting: channel stays open for follow-up
9. If cancelled: channel disappears from `/my/discussions`
