# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta, datetime
import secrets
import uuid


class AppointmentBooking(models.Model):
    _name = 'appointment.booking'
    _description = 'Appointment Booking'
    _order = 'start_datetime desc'
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
    guest_name = fields.Char('Guest Name', required=True, tracking=True)
    guest_email = fields.Char('Guest Email', required=True)
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
    start_datetime = fields.Datetime('Start Time', required=True, tracking=True)
    end_datetime = fields.Datetime('End Time', required=True, tracking=True)
    duration = fields.Float('Duration (hours)', compute='_compute_duration', store=True)

    # Calendar Integration
    calendar_event_id = fields.Many2one(
        'calendar.event',
        string='Reservation Event',
        ondelete='set null',
    )
    meeting_url = fields.Char(
        'Meeting URL',
        compute='_compute_meeting_url',
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
    ], string='Payment Status', default='not_required', tracking=True)
    payment_amount = fields.Monetary('Payment Amount')
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
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Notes
    notes = fields.Text('Notes')
    internal_notes = fields.Text('Internal Notes')

    # Access Token for website
    access_token = fields.Char('Access Token', copy=False)

    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    @api.depends('start_datetime', 'end_datetime')
    def _compute_duration(self):
        for booking in self:
            if booking.start_datetime and booking.end_datetime:
                delta = booking.end_datetime - booking.start_datetime
                booking.duration = delta.total_seconds() / 3600
            else:
                booking.duration = 0

    @api.depends('appointment_type_id.video_link', 'appointment_type_id.location_type', 'calendar_event_id.videocall_location')
    def _compute_meeting_url(self):
        for booking in self:
            if booking.appointment_type_id.location_type != 'online':
                booking.meeting_url = False
            elif booking.appointment_type_id.video_link:
                # Manual override from appointment type
                booking.meeting_url = booking.appointment_type_id.video_link
            elif booking.calendar_event_id and booking.calendar_event_id.videocall_location:
                # Auto-generated Odoo videocall URL
                booking.meeting_url = booking.calendar_event_id.videocall_location
            else:
                booking.meeting_url = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('appointment.booking') or 'New'
            if not vals.get('access_token'):
                vals['access_token'] = secrets.token_urlsafe(32)
        return super().create(vals_list)

    @api.model
    def _check_booking_conflict(self, start_dt, end_dt, staff_user_id=False, resource_id=False, exclude_booking_id=False):
        """Check if staff or resource has conflicting bookings across ALL appointment types.

        Returns dict: {'staff_conflict': bool, 'resource_conflict': bool, 'resource_remaining': int}
        """
        domain = [
            ('state', 'in', ['confirmed', 'done']),
            ('start_datetime', '<', end_dt),
            ('end_datetime', '>', start_dt),
        ]
        if exclude_booking_id:
            domain.append(('id', '!=', exclude_booking_id))

        result = {'staff_conflict': False, 'resource_conflict': False, 'resource_remaining': 1}

        if staff_user_id:
            staff_count = self.search_count(domain + [('staff_user_id', '=', staff_user_id)])
            result['staff_conflict'] = staff_count > 0

        if resource_id:
            resource = self.env['resource.resource'].browse(resource_id)
            capacity = resource.capacity or 1
            res_count = self.search_count(domain + [('resource_id', '=', resource_id)])
            result['resource_conflict'] = res_count >= capacity
            result['resource_remaining'] = max(0, capacity - res_count)

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
            if booking.state != 'draft':
                continue

            # Check payment if required
            appointment_type = booking.appointment_type_id
            if appointment_type.require_payment and booking.payment_status != 'paid':
                raise UserError(_('Payment is required before confirming this booking.'))

            # Cross-type conflict check (safety net for race conditions)
            conflict = self.env['appointment.booking']._check_booking_conflict(
                start_dt=booking.start_datetime,
                end_dt=booking.end_datetime,
                staff_user_id=booking.staff_user_id.id if booking.staff_user_id else False,
                resource_id=booking.resource_id.id if booking.resource_id else False,
                exclude_booking_id=booking.id,
            )
            if conflict['staff_conflict']:
                raise UserError(_('Staff member is already booked for this time slot.'))
            if conflict['resource_conflict']:
                raise UserError(_('Location is fully booked for this time slot.'))

            # Create calendar event
            booking._create_calendar_event()

            booking.write({'state': 'confirmed'})

            # Send confirmation email
            booking._send_confirmation_email()

        return True

    def action_done(self):
        """Mark booking as done"""
        for booking in self:
            if booking.state == 'confirmed':
                booking.write({'state': 'done'})
        return True

    def action_cancel(self):
        """Cancel the booking"""
        for booking in self:
            if booking.state in ['draft', 'confirmed']:
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
                    booking.calendar_event_id.unlink()

                # Cancel linked sale order (if no paid invoice)
                if booking.sale_order_id and booking.sale_order_id.state in ('draft', 'sent', 'sale'):
                    has_paid_invoice = any(
                        inv.payment_state in ('paid', 'in_payment')
                        for inv in booking.sale_order_id.invoice_ids
                    )
                    if not has_paid_invoice:
                        booking.sale_order_id.sudo()._action_cancel()

                booking.write({'state': 'cancelled'})

                # Send cancellation email
                booking._send_cancellation_email()

        return True

    def action_draft(self):
        """Reset to draft"""
        for booking in self:
            if booking.state in ('cancelled', 'done'):
                booking.write({'state': 'draft'})
        return True

    def _create_calendar_event(self):
        """Create a calendar event for this booking.

        For online appointments, integrates with Odoo's native calendar videocall:
        - If video_link is set on the appointment type, uses it as a custom videocall URL.
        - If video_link is empty, auto-generates an Odoo Discuss videocall URL.
        """
        self.ensure_one()
        if self.calendar_event_id:
            return self.calendar_event_id

        event_vals = {
            'name': f'{self.appointment_type_id.name} - {self.guest_name}',
            'start': self.start_datetime,
            'stop': self.end_datetime,
            'description': self._get_event_description(),
            'partner_ids': [(4, self.partner_id.id)] if self.partner_id else [],
            'user_id': self.staff_user_id.id if self.staff_user_id else self.env.user.id,
        }

        # Add resource info to description (resource.resource is tracked via booking linkage)
        # Online meeting: set videocall location using Odoo native mechanism
        appointment_type = self.appointment_type_id
        if appointment_type.location_type == 'online':
            if appointment_type.video_link:
                # Manual override — custom videocall URL
                event_vals['videocall_location'] = appointment_type.video_link
            else:
                # Auto-generate Odoo Discuss videocall URL
                access_token = uuid.uuid4().hex
                event_vals['access_token'] = access_token
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                event_vals['videocall_location'] = f"{base_url}/calendar/join_videocall/{access_token}"

        event = self.env['calendar.event'].create(event_vals)
        self.calendar_event_id = event
        return event

    def _get_event_description(self):
        """Generate event description"""
        lines = []
        lines.append(f"Guest: {self.guest_name}")
        if self.guest_email:
            lines.append(f"Email: {self.guest_email}")
        if self.guest_phone:
            lines.append(f"Phone: {self.guest_phone}")
        if self.guest_count > 1:
            lines.append(f"Number of guests: {self.guest_count}")
        if self.resource_id:
            lines.append(f"Location: {self.resource_id.name}")
        if self.notes:
            lines.append(f"\nNotes: {self.notes}")
        return '\n'.join(lines)

    def _send_confirmation_email(self):
        """Send confirmation email to the guest"""
        self.ensure_one()
        template = self.env.ref('reservation_module.email_template_booking_confirmed', raise_if_not_found=False)
        if template and self.guest_email:
            template.send_mail(self.id, force_send=True)

    def _send_cancellation_email(self):
        """Send cancellation email to the guest"""
        self.ensure_one()
        template = self.env.ref('reservation_module.email_template_booking_cancelled', raise_if_not_found=False)
        if template and self.guest_email:
            template.send_mail(self.id, force_send=True)

    def _auto_assign_staff(self):
        """Auto-assign staff with least bookings this month, filtering out conflicting staff first"""
        self.ensure_one()
        appointment_type = self.appointment_type_id
        if not appointment_type.staff_user_ids:
            return

        # Filter to staff who are NOT conflicting at this exact time slot (cross-type check)
        available_staff_ids = []
        for staff in appointment_type.staff_user_ids:
            conflict = self.env['appointment.booking']._check_booking_conflict(
                start_dt=self.start_datetime,
                end_dt=self.end_datetime,
                staff_user_id=staff.id,
                exclude_booking_id=self.id,
            )
            if not conflict['staff_conflict']:
                available_staff_ids.append(staff.id)

        if not available_staff_ids:
            return  # No available staff for this time slot

        # Among available staff, pick the one with fewest bookings this month
        month_start = self.start_datetime.replace(day=1, hour=0, minute=0, second=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)

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

    def _auto_assign_location(self):
        """Auto-assign location with least bookings this month, filtering out full locations first"""
        self.ensure_one()
        appointment_type = self.appointment_type_id
        if not appointment_type.resource_ids:
            return

        # Filter to resources with remaining capacity at this time slot (cross-type check)
        available_resource_ids = []
        for resource in appointment_type.resource_ids:
            conflict = self.env['appointment.booking']._check_booking_conflict(
                start_dt=self.start_datetime,
                end_dt=self.end_datetime,
                resource_id=resource.id,
                exclude_booking_id=self.id,
            )
            if not conflict['resource_conflict']:
                available_resource_ids.append(resource.id)

        if not available_resource_ids:
            return  # No available locations for this time slot

        # Among available resources, pick the one with fewest bookings this month
        month_start = self.start_datetime.replace(day=1, hour=0, minute=0, second=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)

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

    def get_portal_url(self):
        """Get the portal URL for this booking"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f'{base_url}/appointment/booking/{self.id}?token={self.access_token}'

    def _create_sale_order(self):
        """Create a sale order for paid bookings using the native Odoo sales flow.

        Uses the payment_product_id from the appointment type as the SO line product.
        Handles per-person pricing by adjusting quantity.
        """
        self.ensure_one()
        if self.sale_order_id:
            return self.sale_order_id

        appointment_type = self.appointment_type_id
        if not appointment_type.require_payment or not appointment_type.payment_product_id:
            return False

        partner = self.partner_id
        if not partner:
            return False

        qty = self.guest_count if appointment_type.payment_per_person else 1

        sale_order = self.env['sale.order'].sudo().create({
            'partner_id': partner.id,
            'origin': self.name,
            'note': f"Booking: {self.name} | {appointment_type.name} | "
                    f"{self.start_datetime} - {self.end_datetime}",
            'order_line': [(0, 0, {
                'product_id': appointment_type.payment_product_id.id,
                'name': f"{appointment_type.name} - {self.name}",
                'product_uom_qty': qty,
                'price_unit': appointment_type.payment_amount,
            })],
        })

        # Confirm the SO so it becomes payable on portal
        sale_order.action_confirm()

        # Ensure portal access_token is generated (needed for public/anonymous access)
        sale_order._portal_ensure_token()

        self.sale_order_id = sale_order
        return sale_order
