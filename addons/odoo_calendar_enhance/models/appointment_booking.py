# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


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
    )
    guest_name = fields.Char('Guest Name', required=True, tracking=True)
    guest_email = fields.Char('Guest Email', required=True)
    guest_phone = fields.Char('Guest Phone')
    guest_count = fields.Integer('Number of Guests', default=1, required=True)

    # Resource/Staff Assignment
    resource_id = fields.Many2one(
        'resource.resource',
        string='Resource',
        tracking=True,
    )
    staff_user_id = fields.Many2one(
        'res.users',
        string='Staff',
        tracking=True,
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
    )

    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Question Answers
    answer_ids = fields.One2many(
        'appointment.answer',
        'booking_id',
        string='Answers',
    )

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('appointment.booking') or 'New'
            if not vals.get('access_token'):
                vals['access_token'] = self.env['ir.sequence'].next_by_code('appointment.booking.token') or self._generate_token()
        return super().create(vals_list)

    def _generate_token(self):
        import secrets
        return secrets.token_urlsafe(32)

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

                booking.write({'state': 'cancelled'})

                # Send cancellation email
                booking._send_cancellation_email()

        return True

    def action_draft(self):
        """Reset to draft"""
        for booking in self:
            if booking.state == 'cancelled':
                booking.write({'state': 'draft'})
        return True

    def _create_calendar_event(self):
        """Create a calendar event for this booking"""
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

        # Add resource if available
        if self.resource_id:
            event_vals['res_model'] = 'resource.resource'
            event_vals['res_id'] = self.resource_id.id

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
            lines.append(f"Resource: {self.resource_id.name}")
        if self.notes:
            lines.append(f"\nNotes: {self.notes}")
        return '\n'.join(lines)

    def _send_confirmation_email(self):
        """Send confirmation email to the guest"""
        self.ensure_one()
        template = self.env.ref('odoo_calendar_enhance.email_template_booking_confirmed', raise_if_not_found=False)
        if template and self.guest_email:
            template.send_mail(self.id, force_send=True)

    def _send_cancellation_email(self):
        """Send cancellation email to the guest"""
        self.ensure_one()
        template = self.env.ref('odoo_calendar_enhance.email_template_booking_cancelled', raise_if_not_found=False)
        if template and self.guest_email:
            template.send_mail(self.id, force_send=True)

    def get_portal_url(self):
        """Get the portal URL for this booking"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f'{base_url}/appointment/booking/{self.id}?token={self.access_token}'
