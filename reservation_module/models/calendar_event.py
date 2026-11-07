# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .appointment_booking import BOOKING_MANAGER_GROUP


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    # Marks the event a booking created (_create_calendar_event). The record
    # rules in security/appointment_calendar_security.xml key on it: a booking
    # event, and its attendee rows, are visible only to its organizer, its
    # attendees and appointment managers. Core privacy masking alone is not
    # enough: calendar.attendee rows (guest name, email, phone), the
    # res.partner <-> event relation and domain searches are not masked.
    is_appointment_booking = fields.Boolean(
        'Appointment Booking Event', readonly=True, copy=False, index=True)

    @api.model
    def _get_public_fields(self):
        return super()._get_public_fields() | {'is_appointment_booking'}

    def _check_private_event_conditions(self):
        """Let appointment managers see private booking events in full.

        Organizer and attendees already see them (core). Writes stay guarded
        by the core "Private events" record rule (organizer/attendees only);
        changes go through the booking.
        """
        hidden = super()._check_private_event_conditions()
        if (hidden and self.is_appointment_booking
                and self.env.user.has_group(BOOKING_MANAGER_GROUP)):
            return False
        return hidden
