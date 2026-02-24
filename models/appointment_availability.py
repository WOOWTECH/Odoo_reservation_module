# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AppointmentAvailability(models.Model):
    _name = 'appointment.availability'
    _description = 'Appointment Availability'
    _order = 'dayofweek, hour_from'

    appointment_type_id = fields.Many2one(
        'appointment.type',
        string='預約類型',
        required=True,
        ondelete='cascade',
    )

    dayofweek = fields.Selection([
        ('0', '星期一'),
        ('1', '星期二'),
        ('2', '星期三'),
        ('3', '星期四'),
        ('4', '星期五'),
        ('5', '星期六'),
        ('6', '星期日'),
    ], string='星期幾', required=True, default='0')

    hour_from = fields.Float(
        '從',
        required=True,
        default=8.0,
        help='開始時間（24小時制）',
    )
    hour_to = fields.Float(
        '到',
        required=True,
        default=17.0,
        help='結束時間（24小時制）',
    )

    # Optional: Link to specific resource or user
    resource_id = fields.Many2one(
        'resource.resource',
        string='資源',
        help='留空則適用於所有資源',
    )
    user_id = fields.Many2one(
        'res.users',
        string='使用者',
        help='留空則適用於所有使用者',
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
