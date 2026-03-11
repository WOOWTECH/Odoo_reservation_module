# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AppointmentAvailability(models.Model):
    _name = 'appointment.availability'
    _description = 'Appointment Availability'
    _order = 'dayofweek, hour_from'

    appointment_type_id = fields.Many2one(
        'appointment.type',
        string='Appointment Type',
        required=True,
        ondelete='cascade',
    )

    dayofweek = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Day of Week', required=True, default='0')

    hour_from = fields.Float(
        'From',
        required=True,
        default=8.0,
        help='Start time (24-hour format)',
    )
    hour_to = fields.Float(
        'To',
        required=True,
        default=17.0,
        help='End time (24-hour format)',
    )

    # Optional: Link to specific resource or user
    resource_id = fields.Many2one(
        'resource.resource',
        string='Resource',
        help='Leave empty to apply to all resources',
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        help='Leave empty to apply to all users',
    )

    @api.constrains('hour_from', 'hour_to')
    def _check_hours(self):
        for record in self:
            if record.hour_from < 0 or record.hour_from > 24:
                raise ValidationError(_('Start time must be between 0 and 24.'))
            if record.hour_to < 0 or record.hour_to > 24:
                raise ValidationError(_('End time must be between 0 and 24.'))
            if record.hour_from >= record.hour_to:
                raise ValidationError(_('Start time must be before end time.'))

    def name_get(self):
        result = []
        days = dict(self._fields['dayofweek'].selection)
        for record in self:
            name = f"{days.get(record.dayofweek, '')} {record.hour_from:.2f} - {record.hour_to:.2f}"
            result.append((record.id, name))
        return result
