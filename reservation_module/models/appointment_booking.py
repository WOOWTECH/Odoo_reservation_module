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

    # Reminder tracking
    reminder_sent = fields.Boolean('Reminder Sent', default=False, copy=False)

    # Payment failure tracking
    payment_failure_count = fields.Integer('Payment Failures', default=0, copy=False)

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
    def _check_booking_conflict(self, start_dt, end_dt, staff_user_id=False, resource_id=False, exclude_booking_id=False, lock=False):
        """Check if staff or resource has conflicting bookings across ALL appointment types.

        Args:
            lock: If True, uses SELECT FOR UPDATE to prevent race conditions
                  during booking creation. Only use inside a write transaction.

        Returns dict: {'staff_conflict': bool, 'resource_conflict': bool, 'resource_remaining': int}
        """
        result = {'staff_conflict': False, 'resource_conflict': False, 'resource_remaining': 1}

        base_where = "state IN ('confirmed', 'done') AND start_datetime < %s AND end_datetime > %s"
        base_params = [end_dt, start_dt]
        if exclude_booking_id:
            base_where += " AND id != %s"
            base_params.append(exclude_booking_id)

        lock_clause = " FOR UPDATE" if lock else ""

        if staff_user_id:
            query = f"SELECT COUNT(*) FROM appointment_booking WHERE {base_where} AND staff_user_id = %s{lock_clause}"
            self.env.cr.execute(query, base_params + [staff_user_id])
            staff_count = self.env.cr.fetchone()[0]
            result['staff_conflict'] = staff_count > 0

        if resource_id:
            resource = self.env['resource.resource'].browse(resource_id)
            capacity = resource.capacity or 1
            query = f"SELECT COUNT(*) FROM appointment_booking WHERE {base_where} AND resource_id = %s{lock_clause}"
            self.env.cr.execute(query, base_params + [resource_id])
            res_count = self.env.cr.fetchone()[0]
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
                booking._send_booking_done_email()
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

                cancel_vals = {'state': 'cancelled'}
                # M3: Update payment_status on cancellation
                if booking.payment_status == 'pending':
                    cancel_vals['payment_status'] = 'not_required'
                elif booking.payment_status == 'paid':
                    cancel_vals['payment_status'] = 'refunded'
                booking.write(cancel_vals)

                # Send cancellation email
                booking._send_cancellation_email()

        return True

    def action_draft(self):
        """Reset to draft (only from cancelled state)"""
        for booking in self:
            if booking.state == 'cancelled':
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
            template.send_mail(self.id, force_send=False)

    def _send_cancellation_email(self):
        """Send cancellation email to the guest"""
        self.ensure_one()
        template = self.env.ref('reservation_module.email_template_booking_cancelled', raise_if_not_found=False)
        if template and self.guest_email:
            template.send_mail(self.id, force_send=False)

    def _send_booking_created_email(self):
        """Send booking created email (draft state) with payment info if applicable"""
        self.ensure_one()
        template = self.env.ref('reservation_module.email_template_booking_created', raise_if_not_found=False)
        if template and self.guest_email:
            template.send_mail(self.id, force_send=False)

    def _send_booking_done_email(self):
        """Send booking completed email to the guest"""
        self.ensure_one()
        template = self.env.ref('reservation_module.email_template_booking_done', raise_if_not_found=False)
        if template and self.guest_email:
            template.send_mail(self.id, force_send=False)

    def _send_reminder_email(self):
        """Send reminder email to the guest"""
        self.ensure_one()
        template = self.env.ref('reservation_module.email_template_booking_reminder', raise_if_not_found=False)
        if template and self.guest_email:
            template.send_mail(self.id, force_send=False)

    def _handle_payment_failure(self, error_message=''):
        """Track payment failure and send notifications to customer + admin."""
        self.ensure_one()
        self.payment_failure_count += 1

        # Send failure notification to customer
        template = self.env.ref('reservation_module.email_template_payment_failure', raise_if_not_found=False)
        if template and self.guest_email:
            template.send_mail(self.id, force_send=False)

        # Send admin alert via internal note on booking chatter
        admin_msg = _(
            'Payment failure #%(count)s for booking %(booking)s.\n'
            'Customer: %(name)s (%(email)s)\n'
            'Amount: %(amount)s %(currency)s',
            count=self.payment_failure_count,
            booking=self.name,
            name=self.guest_name,
            email=self.guest_email,
            amount=self.payment_amount,
            currency=self.currency_id.name if self.currency_id else '',
        )
        if error_message:
            admin_msg += _('\nError: %s', error_message)

        self.message_post(
            body=admin_msg,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

    @api.model
    def _cron_send_reminders(self):
        """Cron job: send reminder emails for upcoming confirmed bookings.

        Looks for confirmed bookings starting within the next reminder_hours window
        that haven't been reminded yet (reminder_sent=False).
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
                booking._send_reminder_email()
                booking.reminder_sent = True

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
        Falls back to a generic service product if payment_product_id is not configured.
        Handles per-person pricing by adjusting quantity.
        """
        self.ensure_one()
        if self.sale_order_id:
            return self.sale_order_id

        appointment_type = self.appointment_type_id
        if not appointment_type.require_payment:
            return False

        partner = self.partner_id
        if not partner:
            return False

        # Use configured product or fallback to generic service product
        product = appointment_type.payment_product_id
        if not product:
            product = self._get_or_create_fallback_payment_product()
        if not product:
            return False

        qty = self.guest_count if appointment_type.payment_per_person else 1

        sale_order = self.env['sale.order'].sudo().create({
            'partner_id': partner.id,
            'company_id': self.company_id.id or self.env.company.id,
            'origin': self.name,
            'note': f"Booking: {self.name} | {appointment_type.name} | "
                    f"{self.start_datetime} - {self.end_datetime}",
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': f"{appointment_type.name} - {self.name}",
                'product_uom_qty': qty,
                'price_unit': appointment_type.payment_amount,
            })],
        })

        # Mark as "sent" so the portal shows the "Pay Now" button.
        # Odoo's _has_to_be_paid() requires state in ('draft', 'sent').
        # The SO will be auto-confirmed by Odoo's payment post-processing.
        sale_order.action_quotation_sent()

        # Ensure portal access_token is generated (needed for public/anonymous access)
        sale_order._portal_ensure_token()

        self.sale_order_id = sale_order
        return sale_order

    def _get_or_create_fallback_payment_product(self):
        """Get or create a generic 'Appointment Booking' service product as fallback."""
        xmlid = 'reservation_module.product_appointment_generic'
        product = self.env.ref(xmlid, raise_if_not_found=False)
        if product and product.exists():
            return product

        # Create the generic product with default sale tax
        company = self.env.company
        default_tax = company.account_sale_tax_id
        product_vals = {
            'name': 'Appointment Booking',
            'type': 'service',
            'list_price': 0.0,
            'sale_ok': True,
            'purchase_ok': False,
            'invoice_policy': 'order',
        }
        if default_tax:
            product_vals['taxes_id'] = [(6, 0, [default_tax.id])]
        product = self.env['product.product'].sudo().create(product_vals)
        # Register as ir.model.data so env.ref() finds it next time
        self.env['ir.model.data'].sudo().create({
            'name': 'product_appointment_generic',
            'module': 'reservation_module',
            'model': 'product.product',
            'res_id': product.id,
            'noupdate': True,
        })
        return product
