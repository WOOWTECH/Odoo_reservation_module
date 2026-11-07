# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from .. import tz_utils
from .booking_identity import normalize_booking_email
from datetime import timedelta, datetime
import logging
import pytz
import secrets
import textwrap
import uuid
import werkzeug.urls

try:
    import vobject
except ImportError:
    vobject = None

_logger = logging.getLogger(__name__)

GOOGLE_CALENDAR_URL = 'https://www.google.com/calendar/render?'

BOOKING_STAFF_GROUP = 'reservation_module.group_appointment_user'
BOOKING_MANAGER_GROUP = 'reservation_module.group_appointment_manager'

# 佔用名額的狀態；draft／pending_payment 只有在付款保留期間
# （payment_hold_until 未過）才佔位。
OCCUPYING_STATES = ('confirmed', 'done')
HOLDING_STATES = ('draft', 'pending_payment')

# Discuss 會議室的軟耦合：舊名 cs_portal_discuss 與改名後的
# woow_odoo_portal_discuss 都算（兩者互斥，只會裝其中一個）。
PORTAL_DISCUSS_MODULES = ('cs_portal_discuss', 'woow_odoo_portal_discuss')


class AppointmentBooking(models.Model):
    _name = 'appointment.booking'
    _description = 'Appointment Booking'
    _order = 'start_datetime desc'
    _rec_name = 'appointment_type_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        'Booking Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    appointment_type_id = fields.Many2one(
        'appointment.type',
        string='Appointment Type',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    slot_id = fields.Many2one(
        'appointment.slot',
        string='Slot',
        ondelete='set null',
    )

    # Booker Information
    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        tracking=True,
        ondelete='set null',
    )
    # 必填與否依預約類型的 require_guest_* 設定，由 controller 檢查；
    # model 層不設 required，既有 DB 升級時才不會因舊資料加不上 NOT NULL。
    guest_name = fields.Char('Guest Name', tracking=True)
    guest_email = fields.Char('Guest Email')
    # Rate-limit / mail-throttle key: Foo@x.com and foo+1@x.com are one inbox.
    guest_email_normalized = fields.Char(
        'Normalized Guest Email', compute='_compute_guest_email_normalized',
        store=True, index=True)
    guest_phone = fields.Char('Guest Phone')
    guest_count = fields.Integer('Number of Guests', default=1, required=True)

    # Resource/Staff Assignment
    resource_id = fields.Many2one(
        'resource.resource',
        string='Location',
        tracking=True,
        ondelete='set null',
    )
    staff_user_id = fields.Many2one(
        'res.users',
        string='Staff',
        tracking=True,
        ondelete='set null',
    )

    # Date/Time
    # Storage contract (Odoo standard): naive datetimes expressed in UTC.
    # Anything that needs wall-clock time (availability windows, closing days,
    # emails, .ics) converts through appointment_type_id.timezone.
    start_datetime = fields.Datetime('Start Time', required=True, tracking=True)
    end_datetime = fields.Datetime('End Time', required=True, tracking=True)
    duration = fields.Float('Duration (hours)', compute='_compute_duration', store=True)
    start_date_local = fields.Date(
        'Booking Date',
        compute='_compute_start_date_local',
        store=True,
        index=True,
        help='Local (appointment type timezone) date of the booking. '
             'Stored so backend "Today"/"This Week" filters stay timezone-correct.',
    )
    display_tz = fields.Char(
        'Display Timezone',
        compute='_compute_display_tz',
        help='Timezone used to render this booking to the customer.',
    )
    is_one_local_day = fields.Boolean(
        'Same Local Day',
        compute='_compute_display_tz',
        help='True when start and end fall on the same calendar day in display_tz.',
    )

    # Calendar Integration
    calendar_event_id = fields.Many2one(
        'calendar.event',
        string='Reservation Event',
        ondelete='set null',
    )
    meeting_url = fields.Char(
        'Meeting URL',
        compute='_compute_meeting_url',
        # The linked event is private and the room members-only; whoever may
        # read the booking still gets its meeting link.
        compute_sudo=True,
    )

    # Sales Order Integration
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        ondelete='set null',
        copy=False,
    )

    # Payment
    payment_status = fields.Selection([
        ('not_required', 'Not Required'),
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
    ], string='Payment Status', compute='_compute_payment_status',
       store=True, tracking=True, default='not_required')
    sale_order_count = fields.Integer(
        'Sales Order Count',
        compute='_compute_sale_order_count',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='appointment_type_id.currency_id',
    )
    payment_transaction_id = fields.Many2one(
        'payment.transaction',
        string='Payment Transaction',
        ondelete='set null',
    )

    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending_payment', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Notes
    notes = fields.Text('Notes')
    # 員工內部欄位：portal 對自己的預約有 read ACL，沒有 groups 的欄位
    # 會經 RPC 原樣回傳。前台頁面都用 sudo 的預約渲染，不受 groups 影響。
    internal_notes = fields.Text('Internal Notes', groups=BOOKING_STAFF_GROUP)

    # Access Token for website
    access_token = fields.Char('Access Token', copy=False, groups=BOOKING_STAFF_GROUP)

    # Reminder tracking
    reminder_sent = fields.Boolean(
        'Reminder Sent', default=False, copy=False, groups=BOOKING_STAFF_GROUP)

    # Payment failure tracking
    payment_failure_count = fields.Integer(
        'Payment Failures', default=0, copy=False, groups=BOOKING_STAFF_GROUP)
    # The "payment failed" mail goes to an address the visitor typed: one
    # booking may send it at most once a day and a few times in total, however
    # many failed transactions (or reloads of the return page) it gets.
    payment_failure_mail_count = fields.Integer(
        'Payment Failure Mails Sent', default=0, copy=False, readonly=True,
        groups=BOOKING_STAFF_GROUP)
    payment_failure_mailed_at = fields.Datetime(
        'Last Payment Failure Mail', copy=False, readonly=True,
        groups=BOOKING_STAFF_GROUP)

    # Slot hold for a payment-required booking: while it waits for the
    # payment (draft / pending_payment) it occupies its staff member and its
    # seats until this time, so a second visitor cannot buy the same slot.
    payment_hold_until = fields.Datetime(
        'Slot Held Until', copy=False, readonly=True,
        help='A booking waiting for payment keeps its slot until this time.')
    # The payment window opens once per booking and is never renewed by
    # viewing the pay page or starting another transaction; otherwise the
    # token holder could keep the slot blocked without ever paying.
    payment_hold_started_at = fields.Datetime(
        'Payment Window Opened', copy=False, readonly=True,
        groups=BOOKING_STAFF_GROUP)
    # The longer hold for a started, unsettled payment (wire transfer) is
    # granted at most once per booking.
    payment_pending_hold_granted = fields.Boolean(
        'Pending Payment Hold Granted', copy=False, readonly=True,
        groups=BOOKING_STAFF_GROUP)
    # Paid, but the automatic confirmation failed (slot taken, payment not
    # reconciled, ...): staff must confirm by hand or refund.
    payment_confirm_failed = fields.Boolean(
        'Paid, Not Confirmed', copy=False, readonly=True, tracking=True,
        help='The payment was received but the booking could not be confirmed '
             'automatically. Confirm it manually or refund the customer.')
    # Keyed hash of the client address of a public booking-form submission
    # (empty for backend bookings). Used for rate limits and mail throttling.
    client_ip_hash = fields.Char(
        'Booking Source', copy=False, index=True, readonly=True,
        groups=BOOKING_STAFF_GROUP)

    # Discuss channel integration
    discuss_channel_id = fields.Many2one(
        'discuss.channel', string='Discussion Channel',
        copy=False, ondelete='set null',
    )

    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    # ------------------------------------------------------------------
    # Timezone helpers
    # ------------------------------------------------------------------

    def _tz(self):
        """pytz timezone the booking should be displayed in."""
        self.ensure_one()
        return tz_utils.get_tz(self._get_calendar_tz())

    def _to_local(self, value):
        """Naive UTC (as stored) -> aware datetime in the booking's timezone."""
        self.ensure_one()
        if not value:
            return False
        return pytz.utc.localize(value).astimezone(self._tz())

    def _local_month_bounds_utc(self):
        """[start, end) UTC bounds of the booking's *local* calendar month.

        Used for the "fewest bookings this month" balancing: a UTC month edge
        would put the first/last 8 hours of a month in the wrong bucket.
        """
        self.ensure_one()
        return tz_utils.local_month_bounds_utc(self._tz(), self.start_datetime)

    @api.depends('start_datetime', 'appointment_type_id.timezone')
    def _compute_start_date_local(self):
        """Local booking date, in the appointment type's timezone.

        Reads appointment_type_id.timezone directly rather than going through
        _get_calendar_tz(): this field is stored, so its value must be a pure
        function of the declared depends. The two resolve to the same timezone
        by construction, and both have to match the 18.0.3.0.0 migration,
        which fills the column with
        `(start_datetime AT TIME ZONE 'UTC') AT TIME ZONE appointment_type.timezone`.
        """
        for booking in self:
            if not booking.start_datetime:
                booking.start_date_local = False
                continue
            tz = tz_utils.get_tz(booking.appointment_type_id.timezone)
            booking.start_date_local = tz_utils.utc_to_local(
                tz, booking.start_datetime).date()

    @api.depends('start_datetime', 'end_datetime', 'appointment_type_id.timezone')
    def _compute_display_tz(self):
        for booking in self:
            booking.display_tz = booking._get_calendar_tz()
            if booking.start_datetime and booking.end_datetime:
                booking.is_one_local_day = (
                    booking._to_local(booking.start_datetime).date()
                    == booking._to_local(booking.end_datetime).date()
                )
            else:
                booking.is_one_local_day = False

    @api.depends('guest_email')
    def _compute_guest_email_normalized(self):
        for booking in self:
            booking.guest_email_normalized = normalize_booking_email(booking.guest_email)

    @api.depends('start_datetime', 'end_datetime')
    def _compute_duration(self):
        for booking in self:
            if booking.start_datetime and booking.end_datetime:
                delta = booking.end_datetime - booking.start_datetime
                booking.duration = delta.total_seconds() / 3600
            else:
                booking.duration = 0

    @api.depends('discuss_channel_id', 'appointment_type_id.video_link',
                 'appointment_type_id.location_type', 'calendar_event_id.videocall_location')
    def _compute_meeting_url(self):
        for booking in self:
            if booking.appointment_type_id.location_type != 'online':
                booking.meeting_url = False
            elif booking.discuss_channel_id:
                # Discuss channel = unified meeting room (chat + video)
                booking.meeting_url = f"/discuss/channel/{booking.discuss_channel_id.id}?discussions=1"
            elif booking.appointment_type_id.video_link:
                # Manual override from appointment type
                booking.meeting_url = booking.appointment_type_id.video_link
            elif booking.calendar_event_id and booking.calendar_event_id.videocall_location:
                # Auto-generated Odoo videocall URL (legacy fallback)
                booking.meeting_url = booking.calendar_event_id.videocall_location
            else:
                booking.meeting_url = False

    @api.depends(
        'appointment_type_id.require_payment',
        'state',
        'sale_order_id',
        'sale_order_id.state',
        'sale_order_id.invoice_ids.payment_state',
    )
    def _compute_payment_status(self):
        for booking in self:
            if not booking.appointment_type_id.require_payment or (booking.state == 'cancelled' and not booking.sale_order_id):
                booking.payment_status = 'not_required'
            elif not booking.sale_order_id:
                booking.payment_status = 'pending'
            elif booking.sale_order_id.state == 'cancel':
                booking.payment_status = 'refunded'
            elif any(inv.payment_state in ('paid', 'in_payment')
                     for inv in booking.sale_order_id.invoice_ids):
                booking.payment_status = 'paid'
            else:
                # SO signed but not yet paid → still pending
                booking.payment_status = 'pending'

    @api.depends('sale_order_id')
    def _compute_sale_order_count(self):
        for booking in self:
            booking.sale_order_count = 1 if booking.sale_order_id else 0

    def action_view_sale_order(self):
        """Open the linked sales order"""
        self.ensure_one()
        return {
            'name': _('Sales Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    @api.model_create_multi
    def create(self, vals_list):
        # 前台流程（匿名、portal、付款回呼）都經 controller 以 sudo 建立，
        # 那裡才有時段、名額、付款與人工核准的檢查。非 sudo 的直接建立只給
        # 預約群組的員工；ACL 之外再擋一次，避免租戶另加 ACL 時重新打開
        # portal 經 RPC 建出 confirmed 預約的路。
        if not self.env.su and not self.env.user.has_group(BOOKING_STAFF_GROUP):
            raise AccessError(_('Bookings can only be created through the booking form.'))
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('appointment.booking') or 'New'
            if not vals.get('access_token'):
                vals['access_token'] = secrets.token_urlsafe(32)
        return super().create(vals_list)

    @api.model
    def _check_booking_conflict(self, start_dt, end_dt, staff_user_id=False, resource_id=False, exclude_booking_id=False, lock=False):
        """Check staff/resource conflicts across all appointment types.

        With ``lock=True``, mutable technical guard rows are acquired before
        the aggregates. PostgreSQL forbids ``FOR UPDATE`` with ``COUNT``/``SUM``;
        more importantly, a guard *update* makes a stale REPEATABLE READ writer
        fail with ``SerializationFailure`` so Odoo retries the whole request.
        That exception must propagate—do not catch it here.

        Returns ``staff_conflict``, ``resource_conflict``, and remaining
        resource capacity. ``exclude_booking_id`` keeps edit/confirm semantics.
        Confirmed/done bookings occupy their slot; draft/pending-payment ones
        only while their payment hold runs (``payment_hold_until``). A
        resource capacity of 0/empty counts as 1. The requested party size is
        not known here: use ``_check_booking_capacity`` to compare it.
        """
        result = {'staff_conflict': False, 'resource_conflict': False, 'resource_remaining': 1}

        if lock:
            guard_keys = []
            if staff_user_id:
                guard_keys.append(f'staff:{int(staff_user_id)}')
            if resource_id:
                guard_keys.append(f'resource:{int(resource_id)}')
            if guard_keys:
                self.env['appointment.booking.conflict.guard'].sudo()._acquire_keys(guard_keys)

        # SQL must see state/guest changes still pending in the ORM cache.
        self.flush_model(['state', 'start_datetime', 'end_datetime', 'staff_user_id',
                          'resource_id', 'guest_count', 'payment_hold_until'])
        base_where = (
            "(state IN %s OR (state IN %s AND payment_hold_until > %s)) "
            "AND start_datetime < %s AND end_datetime > %s"
        )
        base_params = [OCCUPYING_STATES, HOLDING_STATES, fields.Datetime.now(), end_dt, start_dt]
        if exclude_booking_id:
            base_where += " AND id != %s"
            base_params.append(exclude_booking_id)

        if staff_user_id:
            query = f"SELECT COUNT(*) FROM appointment_booking WHERE {base_where} AND staff_user_id = %s"
            self.env.cr.execute(query, base_params + [staff_user_id])
            staff_count = self.env.cr.fetchone()[0]
            result['staff_conflict'] = staff_count > 0

        if resource_id:
            resource = self.env['resource.resource'].sudo().browse(resource_id)
            capacity = resource._get_booking_capacity()
            # SUM preserves resource capacity semantics without invalid FOR UPDATE.
            query = (
                f"SELECT COALESCE(SUM(guest_count), 0) "
                f"FROM appointment_booking WHERE {base_where} AND resource_id = %s"
            )
            self.env.cr.execute(query, base_params + [resource_id])
            total_guests = self.env.cr.fetchone()[0]
            result['resource_conflict'] = total_guests >= capacity
            result['resource_remaining'] = max(0, capacity - total_guests)

        return result

    @api.model
    def _check_booking_capacity(self, start_dt, end_dt, staff_user_id=False, resource_id=False,
                                guest_count=1, exclude_booking_id=False, lock=False):
        """``_check_booking_conflict`` plus the requested party size.

        Adds ``resource_full``: the resource cannot take ``guest_count`` more
        guests (existing guests + requested > capacity). A wrapper rather than
        a new parameter, so overrides of ``_check_booking_conflict`` (e.g.
        wassa_reservation) keep working with their signature.
        """
        try:
            guest_count = max(int(guest_count or 1), 1)
        except (TypeError, ValueError):
            guest_count = 1
        result = self._check_booking_conflict(
            start_dt, end_dt, staff_user_id=staff_user_id, resource_id=resource_id,
            exclude_booking_id=exclude_booking_id, lock=lock)
        result['resource_full'] = bool(resource_id) and (
            bool(result.get('resource_conflict'))
            or result.get('resource_remaining', 0) < guest_count)
        return result

    @api.model
    def _occupying_domain(self):
        """ORM twin of the SQL occupancy rule in _check_booking_conflict."""
        return [
            '|', ('state', 'in', list(OCCUPYING_STATES)),
            '&', ('state', 'in', list(HOLDING_STATES)),
            ('payment_hold_until', '>', fields.Datetime.now()),
        ]

    # ------------------------------------------------------------------
    # Payment hold (slot kept while a payment-required booking is paid)
    # ------------------------------------------------------------------

    @api.model
    def _get_int_param(self, key, default):
        value = self.env['ir.config_parameter'].sudo().get_param(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _payment_hold_deadline(self):
        """End of a fresh payment window (``payment_hold_minutes``, 0 = no hold)."""
        minutes = self._get_int_param('reservation_module.payment_hold_minutes', 30)
        if minutes <= 0:
            return False
        return fields.Datetime.now() + timedelta(minutes=minutes)

    @api.model
    def _new_payment_hold_vals(self):
        """Values that open the payment window of a new booking."""
        return {
            'payment_hold_started_at': fields.Datetime.now(),
            'payment_hold_until': self._payment_hold_deadline(),
        }

    def _start_payment_hold(self):
        """Open the payment window, once per booking.

        A window that was already opened is never moved forward, whether it
        is still running or has expired: reloading the pay page or starting
        another transaction must not keep the slot blocked indefinitely.
        """
        for booking in self.sudo():
            if booking.state not in HOLDING_STATES or booking.payment_hold_started_at:
                continue
            vals = self._new_payment_hold_vals()
            if booking.payment_hold_until and (
                    not vals['payment_hold_until'] or booking.payment_hold_until > vals['payment_hold_until']):
                vals.pop('payment_hold_until')
            booking.write(vals)

    def _extend_payment_hold(self, until):
        """Hold the slot at least until ``until`` (never shortens a hold)."""
        for booking in self.sudo():
            if not until or booking.state not in HOLDING_STATES:
                continue
            if not booking.payment_hold_until or booking.payment_hold_until < until:
                booking.payment_hold_until = until

    def _ensure_payment_hold(self):
        """Before money moves: the slot must still be free.

        A hold expires after the payment window; the slot may have been sold
        meanwhile. Raises UserError then, so no payment is taken for a slot
        that cannot be confirmed. A free slot can still be paid for after the
        window, but the window itself is opened only once
        (_start_payment_hold) and never renewed here.
        """
        Booking = self.env['appointment.booking'].sudo()
        for booking in self.sudo():
            if booking.state not in HOLDING_STATES or not booking.appointment_type_id.require_payment:
                continue
            conflict = Booking._check_booking_capacity(
                booking.start_datetime, booking.end_datetime,
                staff_user_id=booking.staff_user_id.id or False,
                resource_id=booking.resource_id.id or False,
                guest_count=booking.guest_count,
                exclude_booking_id=booking.id,
                lock=True,
            )
            if conflict['staff_conflict'] or conflict['resource_full']:
                raise UserError(_(
                    'The time slot of booking %s is no longer available. '
                    'Please choose another time.', booking.name))
            # Legacy bookings (created before the hold existed) get their one
            # window now; any other booking keeps its original deadline.
            booking._start_payment_hold()
        return True

    def _hold_for_pending_payment(self):
        """A payment was started but is not settled (e.g. wire transfer).

        The longer hold is granted once per booking, only while the slot is
        still free, and never past the appointment's end: starting one wire
        transfer after another must not keep the slot blocked.
        """
        hours = self._get_int_param('reservation_module.payment_pending_hold_hours', 48)
        if hours <= 0:
            return
        Booking = self.env['appointment.booking'].sudo()
        for booking in self.sudo():
            if booking.state not in HOLDING_STATES or booking.payment_pending_hold_granted:
                continue
            conflict = Booking._check_booking_capacity(
                booking.start_datetime, booking.end_datetime,
                staff_user_id=booking.staff_user_id.id or False,
                resource_id=booking.resource_id.id or False,
                guest_count=booking.guest_count,
                exclude_booking_id=booking.id,
                lock=True,
            )
            if conflict['staff_conflict'] or conflict['resource_full']:
                # Sold meanwhile: no hold; a later confirmation is flagged.
                continue
            booking.payment_pending_hold_granted = True
            booking._extend_payment_hold(
                min(fields.Datetime.now() + timedelta(hours=hours), booking.end_datetime))

    def _confirm_after_payment(self, tx):
        """Auto-confirm paid bookings; a failure is recorded, never swallowed.

        Only business errors are caught: a SerializationFailure from the
        conflict guard must reach Odoo's retry loop.
        """
        for booking in self.sudo():
            if booking.state not in HOLDING_STATES:
                continue
            if not booking.appointment_type_id.auto_confirm:
                # Paid; staff confirms by hand. Keep the slot meanwhile.
                booking._extend_payment_hold(booking.end_datetime)
                continue
            try:
                with self.env.cr.savepoint():
                    booking.action_confirm()
            except (UserError, ValidationError) as error:
                _logger.warning(
                    "Booking %s: automatic confirmation after payment tx %s failed: %s",
                    booking.name, tx.reference if tx else '-', error)
                booking._flag_payment_confirm_failure(tx, error)

    def _get_payment_followup_user(self):
        """Who gets the "paid but not confirmed" activity."""
        self.ensure_one()
        staff = self.staff_user_id
        if staff and staff.active and staff._is_internal():
            return staff
        managers = self.env.ref(BOOKING_MANAGER_GROUP, raise_if_not_found=False)
        for user in (managers.sudo().users if managers else self.env['res.users']):
            if user.active and user._is_internal() and not user._is_superuser():
                return user
        return self.env.ref('base.user_admin', raise_if_not_found=False) or self.env['res.users']

    def _flag_payment_confirm_failure(self, tx, error):
        """Mark a paid booking that could not be confirmed, for staff to act on."""
        for booking in self.sudo():
            # Keep the seats: the customer has paid, staff decides.
            booking.write({'payment_confirm_failed': True})
            booking._extend_payment_hold(booking.end_datetime)
            reason = (error.args[0] if getattr(error, 'args', None) else str(error)) or ''
            body = _(
                'Payment %(tx)s was received but the booking could not be confirmed '
                'automatically: %(reason)s. Confirm it manually, move it, or refund the customer.',
                tx=tx.reference if tx else '-', reason=reason)
            booking.message_post(body=body, message_type='notification',
                                 subtype_xmlid='mail.mt_note')
            user = booking._get_payment_followup_user()
            if user:
                try:
                    with self.env.cr.savepoint():
                        booking.activity_schedule(
                            'mail.mail_activity_data_todo',
                            user_id=user.id,
                            summary=_('Paid booking needs confirmation'),
                            note=body,
                        )
                except (AccessError, UserError, ValidationError):
                    _logger.warning("Booking %s: could not schedule the follow-up activity",
                                    booking.name, exc_info=True)

    def write(self, vals):
        """M6 fix: 修改預約時間（或改派員工、改訪客）時同步更新關聯的 calendar event。"""
        old_guests = {}
        if 'partner_id' in vals and not self.env.context.get('_skip_calendar_sync'):
            old_guests = {b.id: b.partner_id for b in self.sudo()}
        result = super().write(vals)
        if ({'start_datetime', 'end_datetime', 'staff_user_id', 'partner_id'} & set(vals)
                and not self.env.context.get('_skip_calendar_sync')):
            for booking in self:
                if booking.calendar_event_id:
                    event_vals = {}
                    if 'partner_id' in vals:
                        # The record rules key on appointment_guest_partner_id:
                        # move the event (and its attendee row) to the new guest.
                        event = booking.calendar_event_id.sudo()
                        old_guest = old_guests.get(booking.id)
                        if event.appointment_guest_partner_id != booking.partner_id:
                            event_vals['appointment_guest_partner_id'] = booking.partner_id.id
                        commands = []
                        if old_guest and old_guest != booking.partner_id and old_guest in event.partner_ids:
                            commands.append(Command.unlink(old_guest.id))
                        if booking.partner_id and booking.partner_id not in event.partner_ids:
                            commands.append(Command.link(booking.partner_id.id))
                        if commands:
                            event_vals['partner_ids'] = commands
                    if 'start_datetime' in vals:
                        event_vals['start'] = booking.start_datetime
                    if 'end_datetime' in vals:
                        event_vals['stop'] = booking.end_datetime
                    if 'staff_user_id' in vals and booking.staff_user_id:
                        # The event is visible only to its organizer/attendees:
                        # hand it to the newly assigned staff.
                        event_vals['user_id'] = booking.staff_user_id.id
                    if event_vals:
                        # 預約的 event 是 private：非主辦人的員工（例如建立者）
                        # 通過預約本身的權限後，由系統同步時間。
                        booking.calendar_event_id.sudo().write(event_vals)
        return result

    @api.constrains('start_datetime', 'end_datetime')
    def _check_dates(self):
        for booking in self:
            if booking.end_datetime <= booking.start_datetime:
                raise ValidationError(_('End time must be after start time.'))

    @api.constrains('guest_count')
    def _check_guest_count(self):
        for booking in self:
            if booking.guest_count < 1:
                raise ValidationError(_('Number of guests must be at least 1.'))

    def action_confirm(self):
        """Confirm the booking"""
        for booking in self:
            if booking.state not in ('draft', 'pending_payment'):
                continue

            # Check payment if required
            appointment_type = booking.appointment_type_id
            if appointment_type.require_payment and booking.payment_status != 'paid':
                raise UserError(_('Payment is required before confirming this booking.'))

            # Cross-type conflict check (safety net for race conditions)
            conflict = self.env['appointment.booking']._check_booking_capacity(
                start_dt=booking.start_datetime,
                end_dt=booking.end_datetime,
                staff_user_id=booking.staff_user_id.id if booking.staff_user_id else False,
                resource_id=booking.resource_id.id if booking.resource_id else False,
                guest_count=booking.guest_count,
                exclude_booking_id=booking.id,
                lock=True,
            )
            if conflict['staff_conflict']:
                raise UserError(_('Staff member is already booked for this time slot.'))
            if conflict['resource_full']:
                raise UserError(_('Location is fully booked for this time slot.'))

            # Create Discuss channel (soft-coupled: only if a portal Discuss module is installed)
            booking._create_discuss_channel()

            # Create calendar event
            booking._create_calendar_event()

            booking.write({'state': 'confirmed', 'payment_confirm_failed': False})

            # Send confirmation email
            booking._send_confirmation_email()

        return True

    def action_done(self):
        """Mark booking as done"""
        for booking in self:
            if booking.state == 'confirmed':
                booking.write({'state': 'done'})
                booking._send_booking_done_email()
        return True

    def action_cancel(self):
        """Cancel the booking"""
        for booking in self:
            if booking.state in ['draft', 'pending_payment', 'confirmed']:
                # Check cancellation deadline
                appointment_type = booking.appointment_type_id
                if appointment_type.cancel_before_hours > 0:
                    cancel_deadline = booking.start_datetime - timedelta(hours=appointment_type.cancel_before_hours)
                    if fields.Datetime.now() > cancel_deadline:
                        raise UserError(_(
                            'Cancellation is only allowed until %s hours before the appointment.',
                            appointment_type.cancel_before_hours
                        ))

                # Cancel calendar event
                if booking.calendar_event_id:
                    booking.calendar_event_id.sudo().unlink()

                # Cancel linked sale order (if no paid invoice)
                if booking.sale_order_id and booking.sale_order_id.state in ('draft', 'sent', 'sale'):
                    has_paid_invoice = any(
                        inv.payment_state in ('paid', 'in_payment')
                        for inv in booking.sale_order_id.invoice_ids
                    )
                    if not has_paid_invoice:
                        booking.sale_order_id.sudo()._action_cancel()

                # Archive Discuss channel
                # 會議室只有成員可讀寫；取消通知與封存是系統動作。
                channel_sudo = booking.discuss_channel_id.sudo()
                if channel_sudo and channel_sudo.active:
                    channel_sudo.message_post(
                        body=_("This booking has been cancelled. The discussion is now archived."),
                        message_type='notification',
                        subtype_xmlid='mail.mt_comment',
                    )
                    channel_sudo.write({'active': False})

                booking.write({'state': 'cancelled'})

                # Send cancellation email
                booking._send_cancellation_email()

        return True

    def action_draft(self):
        """Reset to draft (only from cancelled state)"""
        for booking in self:
            if booking.state == 'cancelled':
                # Unarchive Discuss channel if it was archived
                if booking.discuss_channel_id:
                    archived_channel = booking.discuss_channel_id.sudo().with_context(active_test=False).filtered(lambda c: not c.active)
                    if archived_channel:
                        archived_channel.write({'active': True})
                        archived_channel.message_post(
                            body=_("This booking has been reopened."),
                            message_type='notification',
                            subtype_xmlid='mail.mt_comment',
                        )
                booking.write({'state': 'draft'})
        return True

    @api.model
    def _portal_discuss_installed(self):
        """Whether a portal Discuss module (old or renamed) is installed."""
        return bool(self.env['ir.module.module'].sudo().search_count([
            ('name', 'in', PORTAL_DISCUSS_MODULES),
            ('state', '=', 'installed'),
        ], limit=1))

    def _get_discuss_channel_partners(self):
        """Partners allowed in this booking's meeting room: staff + guest.

        Without assigned staff, the confirming user joins only when it is a
        real internal user. The anonymous flow confirms as the shared public
        user; making its partner a member would open the room to every
        anonymous visitor.
        """
        self.ensure_one()
        partners = self.env['res.partner']
        if self.staff_user_id:
            partners |= self.staff_user_id.partner_id
        elif self.env.user._is_internal() and not self.env.user._is_superuser():
            partners |= self.env.user.partner_id
        if self.partner_id:
            partners |= self.partner_id
        return partners

    def _create_discuss_channel(self):
        """Create a Discuss channel for this booking (if a portal Discuss module is installed).

        The channel serves as a unified meeting room: chat + video (via Discuss built-in call).
        Soft-coupled — without cs_portal_discuss / woow_odoo_portal_discuss, falls back to
        the videocall URL.

        The room is a members-only ``group`` conversation (no ``group_public_id``):
        a ``channel`` open to base.group_portal let every portal user read, join and
        post in other customers' rooms. Members still see it in /my/discussions,
        which lists their pinned chats and groups.
        """
        self.ensure_one()
        if self.discuss_channel_id:
            return self.discuss_channel_id

        # Only create channels for online appointments
        if self.appointment_type_id.location_type != 'online':
            return self.env['discuss.channel']

        if not self._portal_discuss_installed():
            return self.env['discuss.channel']

        partners = self._get_discuss_channel_partners()
        channel_vals = {
            'name': f"{self.appointment_type_id.name} - {self.guest_name} ({self.name})",
            'channel_type': 'group',
            'channel_member_ids': [
                (0, 0, {'partner_id': pid}) for pid in partners.ids
            ],
        }
        channel = self.env['discuss.channel'].sudo().create(channel_vals)
        # Core create always adds the current (non-public) user. Keep that for
        # internal users (as before); drop any other outsider, e.g. a portal
        # user who is not this booking's guest.
        channel.channel_member_ids.filtered(
            lambda m: m.partner_id not in partners
            and not any(user._is_internal() for user in m.partner_id.user_ids)
        ).unlink()

        # Post welcome message.
        # Explicit tz: action_confirm often runs sudo()/public, where
        # env.user.tz is empty and context_timestamp would fall back to UTC.
        start_dt = self._to_local(self.start_datetime)
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

    def _create_calendar_event(self):
        """Create a calendar event for this booking.

        For online appointments, integrates with Odoo's native calendar videocall:
        - If video_link is set on the appointment type, uses it as a custom videocall URL.
        - If video_link is empty, auto-generates an Odoo Discuss videocall URL.
        """
        self.ensure_one()
        if self.calendar_event_id:
            return self.calendar_event_id

        # Bookings are restricted to their staff/creator (and managers), while
        # calendar.event is readable by every employee. is_appointment_booking
        # puts the event and its attendee rows (the guest) under the rules in
        # security/appointment_calendar_security.xml: only the organizer, the
        # guest (appointment_guest_partner_id, not partner_ids, which anyone
        # can join from the res.partner side) and appointment managers can
        # see them. privacy='private'
        # is the second layer (core masks name/description as 'Busy'). The
        # title and description carry no guest name or contact details; those
        # stay on the booking (see _get_event_name/_get_event_description).
        event_vals = {
            'name': self._get_event_name(),
            'start': self.start_datetime,
            'stop': self.end_datetime,
            'description': self._get_event_description(),
            'partner_ids': [(4, self.partner_id.id)] if self.partner_id else [],
            'user_id': self._get_event_organizer().id,
            'privacy': 'private',
            'is_appointment_booking': True,
            'appointment_guest_partner_id': self.partner_id.id,
        }

        # Online meeting: set videocall location only if no Discuss channel
        # (when a portal Discuss module is installed, the channel IS the meeting room)
        appointment_type = self.appointment_type_id
        if appointment_type.location_type == 'online' and not self.discuss_channel_id:
            if appointment_type.video_link:
                # Manual override — custom videocall URL
                event_vals['videocall_location'] = appointment_type.video_link
            else:
                # Auto-generate Odoo Discuss videocall URL
                access_token = uuid.uuid4().hex
                event_vals['access_token'] = access_token
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                event_vals['videocall_location'] = f"{base_url}/calendar/join_videocall/{access_token}"

        # sudo: the core "Private events" rule only lets the organizer or an
        # attendee create a private event, and the confirming user (backend
        # creator, payment callback) is often neither. Access to the booking
        # itself was already checked by the caller.
        Event = self.env['calendar.event'].sudo()
        if self._guest_mail_over_cap():
            # Core sends the invitation (with the .ics) from create(), before
            # calendar_event_id is set, so the attendee hook cannot see the
            # booking yet: decide here. The guest gets no mail at all.
            _logger.warning("Booking %s: calendar invitation suppressed (per-address limit)",
                            self.name)
            Event = Event.with_context(no_mail_to_attendees=True)
        event = Event.create(event_vals)
        self.calendar_event_id = event
        return event

    def _get_event_organizer(self):
        """Organizer of the booking's calendar event.

        The assigned staff; without one, the confirming internal user.
        Never the shared public user (anonymous / payment-callback
        confirmation) or OdooBot.
        """
        self.ensure_one()
        if self.staff_user_id:
            return self.staff_user_id
        user = self.env.user
        if user._is_internal() and not user._is_superuser():
            return user
        return self.env['res.users']

    def _get_event_name(self):
        """Event title: appointment type and booking reference, no guest name."""
        self.ensure_one()
        return f'{self.appointment_type_id.name} - {self.name}'

    def _get_event_description(self):
        """Minimal event description: no guest contact details or notes.

        The guest's name, email, phone and free-text notes live on the
        booking, which is protected by the booking ACL and record rules.
        The event only points back to the booking.
        """
        self.ensure_one()
        lines = [_("Booking: %s", self.name)]
        if self.guest_count > 1:
            lines.append(_("Number of guests: %s", self.guest_count))
        if self.resource_id:
            lines.append(_("Location: %s", self.resource_id.name))
        return '\n'.join(lines)

    def _guest_mail_allowed(self):
        """Bound the booking mails one inbox gets from public-form bookings.

        The public form takes any address, so without a bound it relays the
        tenant's mails to arbitrary third parties. Only the first
        ``guest_mail_daily_limit`` public bookings per inbox (normalized
        address) in 24 hours send mail; backend bookings are not limited.
        """
        self.ensure_one()
        return bool(self.sudo().guest_email) and not self._guest_mail_over_cap()

    def _guest_mail_over_cap(self):
        """True for a public-form booking past its inbox's daily mail cap.

        Applies to every mail the booking makes reach the guest: the module's
        templates (_send_guest_mail) and the calendar invitation, date-change
        and reminder mails of its event (calendar.attendee).
        """
        self.ensure_one()
        booking = self.sudo()
        if not booking.client_ip_hash or not booking.guest_email_normalized:
            return False
        limit = self._get_int_param('reservation_module.guest_mail_daily_limit', 10)
        if limit <= 0:
            return False
        rank = self.env['appointment.booking'].sudo().search_count([
            ('guest_email_normalized', '=', booking.guest_email_normalized),
            ('client_ip_hash', '!=', False),
            ('create_date', '>=', (booking.create_date or fields.Datetime.now()) - timedelta(days=1)),
            ('id', '<=', booking.id),
        ])
        return rank > limit

    def _send_guest_mail(self, template_xmlid):
        self.ensure_one()
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template or not self.guest_email:
            return False
        if not self._guest_mail_allowed():
            _logger.warning("Booking %s: guest mail %s suppressed (per-address limit)",
                            self.name, template_xmlid)
            self.sudo().message_post(
                body=_('The guest e-mail was not sent: too many bookings for this address today.'),
                message_type='notification', subtype_xmlid='mail.mt_note')
            return False
        template.send_mail(self.id, force_send=False)
        return True

    def _send_confirmation_email(self):
        """Send confirmation email to the guest"""
        self.ensure_one()
        self._send_guest_mail('reservation_module.email_template_booking_confirmed')

    def _send_cancellation_email(self):
        """Send cancellation email to the guest"""
        self.ensure_one()
        self._send_guest_mail('reservation_module.email_template_booking_cancelled')

    def _send_booking_created_email(self):
        """Send booking created email (draft state) with payment info if applicable"""
        self.ensure_one()
        self._send_guest_mail('reservation_module.email_template_booking_created')

    def _send_booking_done_email(self):
        """Send booking completed email to the guest"""
        self.ensure_one()
        self._send_guest_mail('reservation_module.email_template_booking_done')

    def _send_reminder_email(self):
        """Send reminder email to the guest"""
        self.ensure_one()
        self._send_guest_mail('reservation_module.email_template_booking_reminder')

    def _handle_payment_failure(self, error_message='', transaction=None):
        """Track a payment failure: count it, note it for staff, tell the guest.

        ``transaction`` is the failed payment.transaction. Each transaction is
        handled once, whichever path reports it first (the return page or the
        provider webhook); later reports of the same transaction do nothing.
        The guest mail itself is throttled per booking
        (_claim_payment_failure_mail); the counter and the internal note are
        kept even when the mail is not sent.

        Returns False when ``transaction`` was already handled, True otherwise.
        """
        self.ensure_one()
        if transaction:
            # Atomic claim: concurrent reports of one transaction serialize on
            # its row and only the first one gets it.
            self.env.cr.execute(
                "UPDATE payment_transaction SET appointment_failure_notified = TRUE "
                "WHERE id = %s AND appointment_failure_notified IS NOT TRUE RETURNING id",
                [transaction.id],
            )
            transaction.invalidate_recordset(['appointment_failure_notified'])
            if not self.env.cr.fetchone():
                return False
        # Atomic increment to avoid lost updates under concurrent requests
        self.env.cr.execute(
            "UPDATE appointment_booking SET payment_failure_count = payment_failure_count + 1 WHERE id = %s",
            [self.id],
        )
        self.invalidate_recordset(['payment_failure_count'])

        # Send failure notification to customer
        mailed = False
        if self.sudo().guest_email and self._claim_payment_failure_mail():
            mailed = self._send_guest_mail('reservation_module.email_template_payment_failure')

        # Send admin alert via internal note on booking chatter
        admin_msg = _(
            'Payment failure #%(count)s for booking %(booking)s.\n'
            'Customer: %(name)s (%(email)s)\n'
            'Amount: %(amount)s %(currency)s',
            count=self.payment_failure_count,
            booking=self.name,
            name=self.guest_name,
            email=self.guest_email,
            amount=self.sale_order_id.amount_total if self.sale_order_id else 0,
            currency=self.currency_id.name if self.currency_id else '',
        )
        if error_message:
            admin_msg += _('\nError: %s', error_message)
        if self.sudo().guest_email and not mailed:
            admin_msg += _('\nThe customer was not e-mailed about this failure '
                           '(payment failure mails for this booking are limited).')

        self.message_post(
            body=admin_msg,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        return True

    def _claim_payment_failure_mail(self):
        """Reserve the right to send one "payment failed" mail now.

        At most one per booking per 24 hours and
        ``reservation_module.payment_failure_mail_limit`` (default 3) in total;
        0 or less means no total limit. The check and the reservation are one
        conditional UPDATE, so concurrent failures cannot both pass it.
        """
        self.ensure_one()
        limit = self._get_int_param('reservation_module.payment_failure_mail_limit', 3)
        now = fields.Datetime.now()
        self.env.cr.execute(
            """
            UPDATE appointment_booking
               SET payment_failure_mail_count = COALESCE(payment_failure_mail_count, 0) + 1,
                   payment_failure_mailed_at = %(now)s
             WHERE id = %(id)s
               AND (payment_failure_mailed_at IS NULL OR payment_failure_mailed_at <= %(since)s)
               AND (%(limit)s <= 0 OR COALESCE(payment_failure_mail_count, 0) < %(limit)s)
         RETURNING id
            """,
            {'id': self.id, 'now': now, 'since': now - timedelta(days=1), 'limit': limit},
        )
        claimed = bool(self.env.cr.fetchone())
        self.invalidate_recordset(['payment_failure_mail_count', 'payment_failure_mailed_at'])
        return claimed

    @api.model
    def _cron_send_reminders(self):
        """Cron job: send reminder emails for upcoming confirmed bookings.

        Looks for confirmed bookings starting within the next reminder_hours window
        that haven't been reminded yet (reminder_sent=False).

        M7 fix: 使用 SELECT FOR UPDATE SKIP LOCKED 確保並發 cron 不會重複發送，
        並在每筆提醒後 commit 避免大批量回滾。
        """
        now = fields.Datetime.now()
        bookings = self.search([
            ('state', '=', 'confirmed'),
            ('reminder_sent', '=', False),
            ('start_datetime', '>', now),
        ])
        for booking in bookings:
            reminder_hours = booking.appointment_type_id.reminder_hours or 24
            reminder_threshold = booking.start_datetime - timedelta(hours=reminder_hours)
            if now >= reminder_threshold:
                # Atomic lock: skip if another cron worker already locked this row
                self.env.cr.execute(
                    "SELECT id FROM appointment_booking "
                    "WHERE id = %s AND reminder_sent = FALSE "
                    "FOR UPDATE SKIP LOCKED",
                    [booking.id],
                )
                if not self.env.cr.fetchone():
                    continue  # Already being processed by another worker
                booking._send_reminder_email()
                booking.reminder_sent = True

    def _auto_assign_staff(self):
        """Auto-assign staff with least bookings this month.

        Candidates are the active roster members whose availability covers
        the booking (rows for that member or for everyone) and who have no
        conflicting booking. Returns the assigned user, or an empty recordset
        when nobody fits (the caller decides whether that rejects the booking).
        """
        self.ensure_one()
        appointment_type = self.appointment_type_id
        if not appointment_type.staff_user_ids:
            return self.env['res.users']

        # Filter to staff who are scheduled and NOT conflicting at this exact
        # time slot (cross-type check)
        available_staff_ids = []
        for staff in appointment_type.staff_user_ids.filtered('active'):
            if not appointment_type._interval_in_availability(
                    self.start_datetime, self.end_datetime,
                    resource_id=self.resource_id.id or False, staff_id=staff.id):
                continue
            conflict = self.env['appointment.booking']._check_booking_conflict(
                start_dt=self.start_datetime,
                end_dt=self.end_datetime,
                staff_user_id=staff.id,
                exclude_booking_id=self.id,
                lock=True,
            )
            if not conflict['staff_conflict']:
                available_staff_ids.append(staff.id)

        if not available_staff_ids:
            _logger.warning(
                "No available staff for booking %s (type=%s, time=%s~%s). "
                "All %d staff members have conflicts.",
                self.name, appointment_type.name,
                self.start_datetime, self.end_datetime,
                len(appointment_type.staff_user_ids),
            )
            return self.env['res.users']

        # Among available staff, pick the one with fewest bookings this month
        month_start, month_end = self._local_month_bounds_utc()

        bookings = self.env['appointment.booking'].search([
            ('start_datetime', '>=', month_start),
            ('start_datetime', '<', month_end),
            ('state', 'in', ['confirmed', 'done']),
            ('staff_user_id', 'in', available_staff_ids),
        ])

        staff_counts = {uid: 0 for uid in available_staff_ids}
        for booking in bookings:
            if booking.staff_user_id:
                staff_counts[booking.staff_user_id.id] = staff_counts.get(booking.staff_user_id.id, 0) + 1

        # Pick staff with fewest bookings
        best_staff_id = min(staff_counts, key=staff_counts.get)
        self.staff_user_id = best_staff_id
        return self.staff_user_id

    def _auto_assign_location(self):
        """Auto-assign location with least bookings this month.

        Candidates are the active roster locations whose availability covers
        the booking and that still have room for this booking's whole party
        (existing guests + guest_count <= capacity). Returns the assigned
        resource, or an empty recordset when none fits.
        """
        self.ensure_one()
        appointment_type = self.appointment_type_id
        if not appointment_type.resource_ids:
            return self.env['resource.resource']

        # Filter to scheduled resources with room for the party (cross-type check)
        available_resource_ids = []
        for resource in appointment_type.resource_ids.filtered('active'):
            if not appointment_type._interval_in_availability(
                    self.start_datetime, self.end_datetime,
                    resource_id=resource.id, staff_id=self.staff_user_id.id or False):
                continue
            conflict = self.env['appointment.booking']._check_booking_capacity(
                start_dt=self.start_datetime,
                end_dt=self.end_datetime,
                resource_id=resource.id,
                guest_count=self.guest_count,
                exclude_booking_id=self.id,
                lock=True,
            )
            if not conflict['resource_full']:
                available_resource_ids.append(resource.id)

        if not available_resource_ids:
            return self.env['resource.resource']  # No location fits this party at this time

        # Among available resources, pick the one with fewest bookings this month
        month_start, month_end = self._local_month_bounds_utc()

        bookings = self.env['appointment.booking'].search([
            ('start_datetime', '>=', month_start),
            ('start_datetime', '<', month_end),
            ('state', 'in', ['confirmed', 'done']),
            ('resource_id', 'in', available_resource_ids),
        ])

        resource_counts = {rid: 0 for rid in available_resource_ids}
        for booking in bookings:
            if booking.resource_id:
                resource_counts[booking.resource_id.id] = resource_counts.get(booking.resource_id.id, 0) + 1

        # Pick resource with fewest bookings
        best_resource_id = min(resource_counts, key=resource_counts.get)
        self.resource_id = best_resource_id
        return self.resource_id

    def get_portal_url(self):
        """Get the portal URL for this booking"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f'{base_url}/appointment/booking/{self.id}?token={self.access_token}'

    def _create_sale_order(self):
        """Create a sale order for paid bookings, using the website cart when
        website_sale is installed so multiple bookings can share a cart and
        promo codes / loyalty rewards work via /shop/cart.

        Falls back to a fresh SO (directly opened via /my/orders/<id>) when
        website_sale is not installed.
        """
        self.ensure_one()
        if self.sale_order_id:
            return self.sale_order_id

        apt = self.appointment_type_id
        if not apt.require_payment or not apt.payment_product_ids:
            return False
        if not self.partner_id:
            return False

        qty = self.guest_count if apt.payment_per_person else 1

        # ---- Cart mode: append to visitor's cart if website_sale is installed ----
        # website.sale_get_order is provided by website_sale; feature-detect so
        # this code path works even if website_sale is uninstalled.
        try:
            from odoo.http import request as _req
            website = getattr(_req, 'website', None) if _req else None
        except Exception:
            website = None

        if website and hasattr(website, 'sale_get_order'):
            sale_order = website.sudo().sale_get_order(force_create=True)
            # Ensure cart is bound to the booking's partner
            if sale_order.partner_id.id != self.partner_id.id:
                sale_order.sudo().partner_id = self.partner_id.id
            # Section header — helps identify each booking's lines in cart
            self.env['sale.order.line'].sudo().create({
                'order_id': sale_order.id,
                'display_type': 'line_section',
                'name': f'{apt.name} — {self.name}',
                'sequence': 999,
            })
            # Add each product via _cart_update so promo/loyalty rules run
            for product in apt.payment_product_ids:
                sale_order.sudo()._cart_update(
                    product_id=product.id,
                    add_qty=qty,
                )
            sale_order.sudo()._portal_ensure_token()
        else:
            # ---- Fallback: create a fresh SO opened directly via SO portal ----
            order_lines = [
                (0, 0, {
                    'display_type': 'line_section',
                    'name': apt.name,
                }),
            ]
            for product in apt.payment_product_ids:
                order_lines.append((0, 0, {
                    'product_id': product.id,
                    'name': product.name,
                    'product_uom_qty': qty,
                    'price_unit': product.list_price,
                }))
            sale_order = self.env['sale.order'].sudo().create({
                'partner_id': self.partner_id.id,
                'company_id': self.company_id.id or self.env.company.id,
                'origin': self.name,
                'order_line': order_lines,
            })
            sale_order.action_quotation_sent()
            sale_order._portal_ensure_token()

        self.sale_order_id = sale_order
        if self.state == 'draft':
            self.state = 'pending_payment'
        # The slot stays reserved for the payment window (opened once).
        self._start_payment_hold()
        return sale_order

    # ------------------------------------------------------------------
    # Fix #4: Add-to-calendar (Apple / Outlook / Google) — aligned with
    # event.event._get_ics_file + website_event._get_event_resource_urls
    # ------------------------------------------------------------------

    def _get_calendar_tz(self):
        """The timezone this booking is displayed and exported in.

        Always the appointment type's timezone. That is the timezone the
        availability windows are authored in — i.e. the one the booking was
        actually agreed in — and both appointment_type_id and its `timezone`
        field are required, so it is always set.

        This used to be a fallback chain (type → partner → staff → env user →
        company → UTC), but every link after the first was unreachable. Worse,
        had one ever been reached it would have introduced a second, different
        basis alongside start_date_local and the email templates, which are
        both pinned to the appointment type — the same booking would then be
        filtered on one timezone and rendered in another. One basis only.
        """
        self.ensure_one()
        return self.appointment_type_id.timezone or 'UTC'

    def _get_calendar_location(self):
        """Location string for VEVENT LOCATION / Google URL location param."""
        self.ensure_one()
        at = self.appointment_type_id
        if self.resource_id:
            return self.resource_id.name or ''
        if at.location_id:
            return at.location_id.contact_address or at.location_id.name or ''
        return at.location_address or ''

    def _get_calendar_description(self):
        """Plain-text description with a link back to the portal detail page.

        Matches event._get_external_description shape (plain text, ≤1900 chars).
        """
        self.ensure_one()
        from odoo.tools.mail import html_to_inner_content
        at = self.appointment_type_id
        url = f'{self.get_base_url()}/my/ext-bookings/{self.id}'
        parts = [at.name or _('Booking'), url]
        if at.description:
            parts.append(html_to_inner_content(at.description))
        if self.notes:
            parts.append(self.notes)
        text = '\n\n'.join(p for p in parts if p)
        return textwrap.shorten(text, 1900, placeholder='...')

    def _get_calendar_urls(self):
        """Return {'google_url': str, 'ics_url': str} used by portal template.

        Google URL: encoded query params on GOOGLE_CALENDAR_URL, includes tz
        (ctz) so Google interprets the times in local timezone rather than UTC.
        ICS URL: token-protected route so users on iOS Mail (which cannot send
        the portal session cookie for attachment downloads) can still open it.
        """
        self.ensure_one()
        tz = self._get_calendar_tz()
        # start_datetime is a *naive* UTC value. datetime.astimezone() on a
        # naive value assumes the server's local clock (usually UTC in a
        # container, but never guaranteed), so localize explicitly first.
        start = self._to_local(self.start_datetime).strftime('%Y%m%dT%H%M%S')
        end = self._to_local(self.end_datetime).strftime('%Y%m%dT%H%M%S')
        params = {
            'action': 'TEMPLATE',
            'text': self.appointment_type_id.name or _('Booking'),
            'dates': f'{start}/{end}',
            'ctz': tz,
            'details': self._get_calendar_description(),
        }
        loc = self._get_calendar_location()
        if loc:
            params['location'] = loc
        encoded = werkzeug.urls.url_encode(params)
        return {
            'google_url': GOOGLE_CALENDAR_URL + encoded,
            'ics_url': f'/my/ext-bookings/{self.id}/ics?access_token={self.access_token or ""}',
        }

    def _get_ics_file(self):
        """Generate iCalendar (.ics) content per booking.

        Uses stable UID `ext-booking-<id>@<host>` + SEQUENCE derived from
        write_date so reschedules (which bump write_date) trigger an update
        on the calendar client instead of a duplicate event.

        Cancelled bookings include STATUS:CANCELLED so clients will remove
        the event from the calendar.

        VALARM (-15 min DISPLAY) is honoured by Apple / Outlook clients;
        Google Calendar ignores VALARM from imported .ics but uses its own
        default reminders.
        """
        result = {}
        if not vobject:
            _logger.warning('vobject not installed — cannot generate .ics')
            return result

        for booking in self:
            tz = pytz.timezone(booking._get_calendar_tz())
            cal = vobject.iCalendar()
            cal.add('prodid').value = '-//WoowTech//Reservation Booking//EN'
            cal.add('method').value = 'CANCEL' if booking.state == 'cancelled' else 'REQUEST'
            cal_event = cal.add('vevent')

            host = booking.get_base_url().split('//', 1)[-1] or 'reservation'
            cal_event.add('uid').value = f'ext-booking-{booking.id}@{host}'
            cal_event.add('sequence').value = str(int(booking.write_date.timestamp()))
            now_utc = fields.Datetime.now().replace(tzinfo=pytz.UTC)
            cal_event.add('created').value = now_utc
            cal_event.add('dtstamp').value = now_utc
            cal_event.add('last-modified').value = (
                booking.write_date.replace(tzinfo=pytz.UTC) if booking.write_date else now_utc
            )
            # Same as _get_calendar_urls: localize the naive UTC value instead
            # of calling .astimezone() on it (which would assume server-local).
            cal_event.add('dtstart').value = pytz.utc.localize(booking.start_datetime).astimezone(tz)
            cal_event.add('dtend').value = pytz.utc.localize(booking.end_datetime).astimezone(tz)
            cal_event.add('summary').value = booking.appointment_type_id.name or _('Booking')
            cal_event.add('description').value = booking._get_calendar_description()

            loc = booking._get_calendar_location()
            if loc:
                cal_event.add('location').value = loc

            if booking.state == 'cancelled':
                cal_event.add('status').value = 'CANCELLED'
            else:
                cal_event.add('status').value = 'CONFIRMED'
                alarm = cal_event.add('valarm')
                alarm.add('action').value = 'DISPLAY'
                alarm.add('trigger').value = timedelta(minutes=-15)
                alarm.add('description').value = booking.appointment_type_id.name or _('Booking')

            result[booking.id] = cal.serialize().encode('utf-8')
        return result
