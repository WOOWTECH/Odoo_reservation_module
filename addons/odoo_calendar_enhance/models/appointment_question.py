# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class AppointmentQuestion(models.Model):
    _name = 'appointment.question'
    _description = 'Appointment Question'
    _order = 'sequence, id'

    appointment_type_id = fields.Many2one(
        'appointment.type',
        string='Appointment Type',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char('Question', required=True, translate=True)
    question_type = fields.Selection([
        ('text', 'Single Line Text'),
        ('textarea', 'Multi-Line Text'),
        ('select', 'Selection'),
        ('radio', 'Radio Buttons'),
        ('checkbox', 'Checkboxes'),
        ('date', 'Date'),
        ('datetime', 'Date & Time'),
        ('number', 'Number'),
        ('email', 'Email'),
        ('phone', 'Phone'),
    ], string='Question Type', default='text', required=True)

    required = fields.Boolean('Required', default=False)
    sequence = fields.Integer('Sequence', default=10)

    placeholder = fields.Char('Placeholder', translate=True)
    help_text = fields.Text('Help Text', translate=True)

    option_ids = fields.One2many(
        'appointment.question.option',
        'question_id',
        string='Options',
    )

    @api.onchange('question_type')
    def _onchange_question_type(self):
        if self.question_type not in ['select', 'radio', 'checkbox']:
            self.option_ids = [(5, 0, 0)]


class AppointmentQuestionOption(models.Model):
    _name = 'appointment.question.option'
    _description = 'Appointment Question Option'
    _order = 'sequence, id'

    question_id = fields.Many2one(
        'appointment.question',
        string='Question',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char('Option', required=True, translate=True)
    sequence = fields.Integer('Sequence', default=10)
