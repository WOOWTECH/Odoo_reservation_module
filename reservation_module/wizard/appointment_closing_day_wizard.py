# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AppointmentClosingDayWizard(models.TransientModel):
    _name = 'appointment.closing.day.wizard'
    _description = 'Add Closing Days Wizard'

    appointment_type_id = fields.Many2one(
        'appointment.type',
        string='Appointment Type',
        required=True,
    )
    date_from = fields.Date('From Date', required=True, default=fields.Date.today)
    date_to = fields.Date('To Date', required=True, default=fields.Date.today)
    reason = fields.Char('Reason')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from > record.date_to:
                raise ValidationError(_('From Date must be before or equal to To Date.'))

    def action_confirm(self):
        """Create closing day records for the selected date range."""
        self.ensure_one()
        ClosingDay = self.env['appointment.closing.day']
        current_date = self.date_from
        created = 0

        while current_date <= self.date_to:
            existing = ClosingDay.search([
                ('appointment_type_id', '=', self.appointment_type_id.id),
                ('date', '=', current_date),
            ], limit=1)
            if not existing:
                ClosingDay.create({
                    'appointment_type_id': self.appointment_type_id.id,
                    'date': current_date,
                    'name': self.reason,
                })
                created += 1
            current_date += timedelta(days=1)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Closing Days Added'),
                'message': _('%d closing day(s) added.') % created,
                'sticky': False,
                'type': 'success',
            }
        }
