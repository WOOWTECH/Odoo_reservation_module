# -*- coding: utf-8 -*-

from odoo import fields, models


class AppointmentQuestion(models.Model):
    _name = 'appointment.question'
    _description = 'Appointment FAQ'
    _order = 'sequence, id'

    appointment_type_id = fields.Many2one(
        'appointment.type',
        string='Appointment Type',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char('Question', required=True, translate=True)
    answer = fields.Html('Answer', translate=True)
    sequence = fields.Integer('Sequence', default=10)
