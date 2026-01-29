# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class AppointmentAnswer(models.Model):
    _name = 'appointment.answer'
    _description = 'Appointment Answer'

    booking_id = fields.Many2one(
        'appointment.booking',
        string='Booking',
        required=True,
        ondelete='cascade',
    )
    question_id = fields.Many2one(
        'appointment.question',
        string='Question',
        required=True,
        ondelete='cascade',
    )
    question_type = fields.Selection(
        related='question_id.question_type',
        string='Question Type',
    )

    # Answer values based on question type
    value_text = fields.Text('Text Answer')
    value_number = fields.Float('Number Answer')
    value_date = fields.Date('Date Answer')
    value_datetime = fields.Datetime('DateTime Answer')
    value_option_ids = fields.Many2many(
        'appointment.question.option',
        'appointment_answer_option_rel',
        'answer_id',
        'option_id',
        string='Selected Options',
    )

    @api.depends('value_text', 'value_number', 'value_date', 'value_datetime', 'value_option_ids')
    def _compute_display_value(self):
        for answer in self:
            if answer.question_type in ['text', 'textarea', 'email', 'phone']:
                answer.display_value = answer.value_text or ''
            elif answer.question_type == 'number':
                answer.display_value = str(answer.value_number) if answer.value_number else ''
            elif answer.question_type == 'date':
                answer.display_value = str(answer.value_date) if answer.value_date else ''
            elif answer.question_type == 'datetime':
                answer.display_value = str(answer.value_datetime) if answer.value_datetime else ''
            elif answer.question_type in ['select', 'radio', 'checkbox']:
                answer.display_value = ', '.join(answer.value_option_ids.mapped('name'))
            else:
                answer.display_value = ''

    display_value = fields.Char('Display Value', compute='_compute_display_value')

    def get_value(self):
        """Return the appropriate value based on question type"""
        self.ensure_one()
        if self.question_type in ['text', 'textarea', 'email', 'phone']:
            return self.value_text
        elif self.question_type == 'number':
            return self.value_number
        elif self.question_type == 'date':
            return self.value_date
        elif self.question_type == 'datetime':
            return self.value_datetime
        elif self.question_type in ['select', 'radio', 'checkbox']:
            return self.value_option_ids
        return None

    def set_value(self, value):
        """Set the appropriate value based on question type"""
        self.ensure_one()
        if self.question_type in ['text', 'textarea', 'email', 'phone']:
            self.value_text = value
        elif self.question_type == 'number':
            self.value_number = float(value) if value else 0
        elif self.question_type == 'date':
            self.value_date = value
        elif self.question_type == 'datetime':
            self.value_datetime = value
        elif self.question_type in ['select', 'radio']:
            if value:
                self.value_option_ids = [(6, 0, [int(value)])]
        elif self.question_type == 'checkbox':
            if value:
                self.value_option_ids = [(6, 0, [int(v) for v in value])]
