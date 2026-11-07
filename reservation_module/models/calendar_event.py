# -*- coding: utf-8 -*-

from odoo import models

from .appointment_booking import BOOKING_MANAGER_GROUP


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    def _check_private_event_conditions(self):
        """Let appointment managers see private booking events in full.

        Booking events are created private so other employees only see
        'Busy'. Appointment managers can read every booking anyway, so they
        keep seeing the details on the shared calendar. Writes stay guarded
        by the core "Private events" record rule (organizer/attendees only);
        changes go through the booking.
        """
        hidden = super()._check_private_event_conditions()
        if not hidden or not self.env.user.has_group(BOOKING_MANAGER_GROUP):
            return hidden
        return not self.env['appointment.booking'].sudo().search_count(
            [('calendar_event_id', '=', self.id)], limit=1)
