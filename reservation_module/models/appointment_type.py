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
        ondelete='set null',
    )
    location_address = fields.Char(
        'Location Address',
        related='location_id.contact_address',
        readonly=True,
    )
    video_link = fields.Char(
        'Video Link',
        help='Video conference link',
    )

    # Schedule Configuration
    schedule_type = fields.Selection([
        ('recurring', 'Weekly Recurring'),
        ('custom', 'Custom'),
    ], string='Schedule Type', default='recurring')
    schedule_based_on = fields.Selection([
        ('date', 'Date'),
        ('user_resource', 'User / Resource'),
    ], string='Based On', default='date',
        help='What the appointment should be based on')

    # Assignment Configuration
    assign_staff = fields.Boolean(
        'Staff',
        default=True,
        help='Assign staff members to bookings',
    )
    assign_location = fields.Boolean(
        'Location',
        default=False,
        help='Assign a location to bookings',
    )
    allow_customer_choose_staff = fields.Boolean(
        'Allow Customer to Choose Staff',
        default=True,
        help='Let customers pick their preferred staff member',
    )
    allow_customer_choose_location = fields.Boolean(
        'Allow Customer to Choose Location',
        default=True,
        help='Let customers pick their preferred location',
    )

    # Capacity Configuration
    manage_capacity = fields.Boolean(
        'Manage Capacity',
        help='Enable resource capacity management',
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
        help='Maximum concurrent bookings per user',
    )

    # Resource/Staff Configuration
    resource_ids = fields.Many2many(
        'resource.resource',
        'appointment_type_resource_rel',
        'appointment_type_id',
        'resource_id',
        string='Locations',
        help='Resources available for this appointment type',
    )
    staff_user_ids = fields.Many2many(
        'res.users',
        'appointment_type_user_rel',
        'appointment_type_id',
        'user_id',
        string='Staff Members',
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
        'Max Booking Days',
        default=30,
        help='How many days in advance bookings can be made',
    )
    min_booking_hours = fields.Float(
        'Min Advance Booking (hours)',
        default=1.0,
        help='Minimum advance time for bookings in hours',
    )
    cancel_before_hours = fields.Float(
        'Cancellation Deadline (hours)',
        default=1.0,
        help='Cancellation deadline in hours before start',
    )

    # Auto Confirmation
    auto_confirm = fields.Boolean(
        'Auto Confirm',
        default=True,
        help='Automatically confirm bookings',
    )
    auto_confirm_capacity_percent = fields.Float(
        'Auto Confirm Capacity (%)',
        default=1.0,
        help='Auto confirm until this capacity percentage is reached',
    )

    # Payment Configuration
    require_payment = fields.Boolean(
        'Require Payment',
        help='Require payment before confirming booking',
    )
    payment_product_id = fields.Many2one(
        'product.product',
        string='Payment Product',
        help='Product used for payment',
        ondelete='set null',
    )
    payment_amount = fields.Monetary(
        'Payment Amount',
        help='Amount to be paid for the booking',
    )
    payment_per_person = fields.Boolean(
        'Per Person Pricing',
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
        help='Allow bookers to invite others',
    )

    # Communication Settings
    introduction_page = fields.Html(
        'Introduction Page',
        translate=True,
        help='Content displayed on the booking page',
    )
    confirmation_page = fields.Html(
        'Confirmation Page',
        translate=True,
        help='Content displayed after booking confirmation',
    )

    # Availability
    availability_ids = fields.One2many(
        'appointment.availability',
        'appointment_type_id',
        string='Availability Slots',
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
            if record.auto_confirm_capacity_percent < 0 or record.auto_confirm_capacity_percent > 1.0:
                raise ValidationError(_('Auto confirm capacity must be between 0 and 1.0 (0% to 100%).'))

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

    def action_view_location_bookings(self):
        """Open location bookings reservation view"""
        self.ensure_one()
        return {
            'name': _('Location Bookings'),
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

