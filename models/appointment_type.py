# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import pytz


class AppointmentType(models.Model):
    _name = 'appointment.type'
    _description = 'Appointment Type'
    _order = 'sequence, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _default_timezone(self):
        return self.env.user.tz or 'UTC'

    name = fields.Char(
        'Name',
        required=True,
        translate=True,
        tracking=True,
    )
    sequence = fields.Integer('Sequence', default=10)
    active = fields.Boolean('Active', default=True, tracking=True)

    category = fields.Selection([
        ('meeting', 'Meeting'),
        ('video_call', 'Video Call'),
        ('table', 'Table Booking'),
        ('resource', 'Resource Booking'),
        ('paid_consultation', 'Paid Consultation'),
        ('paid_seat', 'Paid Seat'),
    ], string='Category', required=True, default='meeting', tracking=True)

    description = fields.Html('Description', translate=True)

    # Location Configuration
    location_type = fields.Selection([
        ('online', 'Online Meeting'),
        ('physical', 'Physical Location'),
    ], string='Location Type', default='online')
    location_id = fields.Many2one(
        'res.partner',
        string='Location',
        help='Physical location for the appointment',
    )
    location_address = fields.Char(
        'Location Address',
        related='location_id.contact_address',
        readonly=True,
    )
    video_link = fields.Char(
        'Video Link',
        help='Link to video conference',
    )

    # Schedule Configuration
    schedule_type = fields.Selection([
        ('recurring', 'Recurring Weekly'),
        ('custom', 'Custom'),
    ], string='Schedule Type', default='recurring')
    schedule_based_on = fields.Selection([
        ('date', 'Date'),
        ('user_resource', 'User / Resource'),
    ], string='Start Based On', default='date',
        help='What the booking reservation should be based on')

    # Assignment Configuration
    booking_type = fields.Selection([
        ('user', 'Users'),
        ('resource', 'Resources'),
    ], string='Booking Type', default='user',
        help='Whether appointments are booked with users or resources')
    assignment_method = fields.Selection([
        ('automatic', 'Automatic'),
        ('customer', 'Customer Choice'),
    ], string='Assignment Method', default='automatic',
        help='How resources/staff are assigned to bookings')

    # Capacity Configuration
    manage_capacity = fields.Boolean(
        'Manage Capacity',
        help='Enable capacity management for resources',
    )
    total_capacity = fields.Integer(
        'Total Capacity',
        compute='_compute_total_capacity',
        store=True,
        help='Total capacity across all resources',
    )
    max_concurrent_bookings = fields.Integer(
        'Max Concurrent Bookings',
        default=1,
        help='Maximum number of concurrent bookings per user',
    )

    # Resource/Staff Configuration
    resource_ids = fields.Many2many(
        'resource.resource',
        'appointment_type_resource_rel',
        'appointment_type_id',
        'resource_id',
        string='Resources',
        help='Resources available for this appointment type',
    )
    staff_user_ids = fields.Many2many(
        'res.users',
        'appointment_type_user_rel',
        'appointment_type_id',
        'user_id',
        string='Staff',
        help='Staff members available for this appointment type',
    )

    # Time Configuration
    slot_duration = fields.Float(
        'Slot Duration (hours)',
        default=1.0,
        required=True,
        help='Duration of each appointment slot in hours',
    )
    slot_interval = fields.Float(
        'Slot Interval (hours)',
        default=1.0,
        help='Time interval between available slots',
    )

    # Booking Restrictions
    max_booking_days = fields.Integer(
        'Maximum Booking Days',
        default=30,
        help='How many days in advance can appointments be booked',
    )
    min_booking_hours = fields.Float(
        'Minimum Advance Booking (hours)',
        default=1.0,
        help='Minimum hours before the appointment start time that booking is allowed',
    )
    cancel_before_hours = fields.Float(
        'Cancellation Deadline (hours)',
        default=1.0,
        help='Hours before appointment start time until when cancellation is allowed',
    )

    # Auto Confirmation
    auto_confirm = fields.Boolean(
        'Auto Confirm',
        default=True,
        help='Automatically confirm bookings',
    )
    auto_confirm_capacity_percent = fields.Integer(
        'Auto Confirm Capacity (%)',
        default=100,
        help='Automatically confirm until this percentage of capacity is reached',
    )

    # Payment Configuration
    require_payment = fields.Boolean(
        'Require Payment',
        help='Require payment before confirming the appointment',
    )
    payment_product_id = fields.Many2one(
        'product.product',
        string='Payment Product',
        help='Product used for payment',
    )
    payment_amount = fields.Monetary(
        'Payment Amount',
        help='Amount to charge for the appointment',
    )
    payment_per_person = fields.Boolean(
        'Payment Per Person',
        help='Charge per person instead of per booking',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )

    # Display Settings
    show_image = fields.Boolean('Show Image')
    image = fields.Binary('Image', attachment=True)
    image_url = fields.Char('Image URL')
    icon = fields.Char('Icon', default='fa-calendar')

    # Timezone
    timezone = fields.Selection(
        '_tz_get',
        string='Timezone',
        default=_default_timezone,
        required=True,
    )

    # Allow Invitations
    allow_invitations = fields.Boolean(
        'Allow Invitations',
        help='Allow bookers to invite other people',
    )

    # Communication Settings
    introduction_page = fields.Html(
        'Introduction Page',
        translate=True,
        help='Content shown on the appointment booking page',
    )
    confirmation_page = fields.Html(
        'Confirmation Page',
        translate=True,
        help='Content shown after booking is confirmed',
    )

    # Availability
    availability_ids = fields.One2many(
        'appointment.availability',
        'appointment_type_id',
        string='Availability',
    )

    # Questions
    question_ids = fields.One2many(
        'appointment.question',
        'appointment_type_id',
        string='Questions',
    )

    # Bookings
    booking_ids = fields.One2many(
        'appointment.booking',
        'appointment_type_id',
        string='Bookings',
    )
    booking_count = fields.Integer(
        'Booking Count',
        compute='_compute_booking_count',
    )
    upcoming_booking_count = fields.Integer(
        'Upcoming Bookings',
        compute='_compute_booking_count',
    )

    # Website
    is_published = fields.Boolean('Published', default=True)
    website_url = fields.Char('Website URL', compute='_compute_website_url')

    @api.model
    def _tz_get(self):
        return [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]

    @api.depends('resource_ids', 'resource_ids.capacity')
    def _compute_total_capacity(self):
        for record in self:
            if record.manage_capacity and record.resource_ids:
                record.total_capacity = sum(record.resource_ids.mapped('capacity'))
            else:
                record.total_capacity = 0

    @api.depends('booking_ids', 'booking_ids.state', 'booking_ids.start_datetime')
    def _compute_booking_count(self):
        now = fields.Datetime.now()
        for record in self:
            bookings = record.booking_ids.filtered(lambda b: b.state not in ['cancelled'])
            record.booking_count = len(bookings)
            record.upcoming_booking_count = len(bookings.filtered(lambda b: b.start_datetime > now))

    def _compute_website_url(self):
        for record in self:
            if record.id:
                record.website_url = f'/appointment/{record.id}'
            else:
                record.website_url = False

    @api.constrains('slot_duration')
    def _check_slot_duration(self):
        for record in self:
            if record.slot_duration <= 0:
                raise ValidationError(_('Slot duration must be greater than 0.'))

    @api.constrains('max_booking_days')
    def _check_max_booking_days(self):
        for record in self:
            if record.max_booking_days < 1:
                raise ValidationError(_('Maximum booking days must be at least 1.'))

    @api.constrains('auto_confirm_capacity_percent')
    def _check_auto_confirm_capacity(self):
        for record in self:
            if record.auto_confirm_capacity_percent < 0 or record.auto_confirm_capacity_percent > 100:
                raise ValidationError(_('Auto confirm capacity must be between 0 and 100.'))

    def action_view_bookings(self):
        """Open bookings for this appointment type"""
        self.ensure_one()
        return {
            'name': _('Bookings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.booking',
            'view_mode': 'list,form,calendar',
            'domain': [('appointment_type_id', '=', self.id)],
            'context': {'default_appointment_type_id': self.id},
        }

    def action_share(self):
        """Share appointment booking link"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return {
            'type': 'ir.actions.act_url',
            'url': f'{base_url}/appointment/{self.id}',
            'target': 'new',
        }

    def action_open_settings(self):
        """Open appointment type settings"""
        self.ensure_one()
        return {
            'name': _('Settings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.type',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_view_resource_bookings(self):
        """Open resource bookings reservation view"""
        self.ensure_one()
        return {
            'name': _('Resource Bookings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.booking',
            'view_mode': 'calendar,list,form',
            'domain': [('appointment_type_id', '=', self.id), ('resource_id', '!=', False)],
            'context': {
                'default_appointment_type_id': self.id,
                'search_default_groupby_resource': 1,
            },
        }

    def action_view_staff_bookings(self):
        """Open staff bookings reservation view"""
        self.ensure_one()
        return {
            'name': _('Staff Bookings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.booking',
            'view_mode': 'calendar,list,form',
            'domain': [('appointment_type_id', '=', self.id), ('staff_user_id', '!=', False)],
            'context': {
                'default_appointment_type_id': self.id,
                'search_default_groupby_staff': 1,
            },
        }

    def action_add_closing_days(self):
        """Open wizard to add closing days"""
        self.ensure_one()
        return {
            'name': _('Add Closing Days'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.closing.day.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_appointment_type_id': self.id,
            },
        }

    @api.model
    def get_appointment_type_presets(self):
        """Return appointment type presets for selection dialog"""
        return [
            {
                'category': 'meeting',
                'name': _('Meeting'),
                'description': _('Allow others to book meetings in your reservation'),
                'icon': 'fa-user',
            },
            {
                'category': 'video_call',
                'name': _('Video Call'),
                'description': _('Schedule video meetings with one or more participants'),
                'icon': 'fa-video-camera',
            },
            {
                'category': 'table',
                'name': _('Table Booking'),
                'description': _('Let customers book tables at your restaurant or bar'),
                'icon': 'fa-cutlery',
            },
            {
                'category': 'resource',
                'name': _('Book a Resource'),
                'description': _('Allow customers to book resources like rooms, tennis courts, etc.'),
                'icon': 'fa-clock-o',
            },
            {
                'category': 'paid_consultation',
                'name': _('Paid Consultation'),
                'description': _('Let customers book a paid slot in your reservation'),
                'icon': 'fa-dollar',
            },
            {
                'category': 'paid_seat',
                'name': _('Paid Seats'),
                'description': _('Let customers book a fee per person for activities'),
                'icon': 'fa-chair',
            },
        ]
