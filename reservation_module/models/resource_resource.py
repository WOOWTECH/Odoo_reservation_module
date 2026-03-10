# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    # Additional fields for appointment booking
    capacity = fields.Integer(
        'Capacity',
        default=1,
        help='Maximum number of concurrent bookings for this resource',
    )
    appointment_type_ids = fields.Many2many(
        'appointment.type',
        'appointment_type_resource_rel',
        'resource_id',
        'appointment_type_id',
        string='Appointment Types',
    )

    # Display settings
    icon = fields.Char('Icon', default='fa-chair')
    image = fields.Binary('Image', attachment=True)

    # Booking statistics
    booking_count = fields.Integer(
        'Booking Count',
        compute='_compute_booking_count',
    )
    upcoming_booking_count = fields.Integer(
        'Upcoming Bookings',
        compute='_compute_booking_count',
    )

    @api.depends('appointment_type_ids')
    def _compute_booking_count(self):
        now = fields.Datetime.now()
        for resource in self:
            bookings = self.env['appointment.booking'].search([
                ('resource_id', '=', resource.id),
                ('state', 'not in', ['cancelled']),
            ])
            resource.booking_count = len(bookings)
            resource.upcoming_booking_count = len(bookings.filtered(lambda b: b.start_datetime > now))

    def action_view_bookings(self):
        """Open bookings for this resource"""
        self.ensure_one()
        return {
            'name': _('Bookings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.booking',
            'view_mode': 'list,form,calendar',
            'domain': [('resource_id', '=', self.id)],
            'context': {'default_resource_id': self.id},
        }
