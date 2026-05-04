# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AppointmentClosingDay(models.Model):
    _name = 'appointment.closing.day'
    _description = 'Appointment Closing Day'
    _order = 'date'

    appointment_type_id = fields.Many2one(
        'appointment.type',
        string='Appointment Type',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date('Date', required=True)
    name = fields.Char('Reason')

    _sql_constraints = [
        ('unique_closing_day',
         'UNIQUE(appointment_type_id, date)',
         'A closing day already exists for this date.'),
    ]

    @api.constrains('date')
    def _check_date(self):
        for record in self:
            if record.date < fields.Date.today():
                raise ValidationError(_('Closing day date cannot be in the past.'))
