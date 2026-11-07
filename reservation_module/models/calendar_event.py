# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .appointment_booking import BOOKING_MANAGER_GROUP

# Set only by the booking (under sudo) and keyed on by the record rules in
# security/appointment_calendar_security.xml; see _check_booking_markers.
BOOKING_MARKER_FIELDS = frozenset({'is_appointment_booking', 'appointment_guest_partner_id'})


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    # Marks the event a booking created (_create_calendar_event). The record
    # rules in security/appointment_calendar_security.xml key on it: a booking
    # event, and its attendee rows, are visible only to its organizer (the
    # assigned staff), its guest and appointment managers. Core privacy
    # masking alone is not enough: calendar.attendee rows (guest name, email,
    # phone), the res.partner <-> event relation and domain searches are not
    # masked.
    is_appointment_booking = fields.Boolean(
        'Appointment Booking Event', readonly=True, copy=False, index=True)
    # The booking's guest. The rules use this field, not partner_ids: any
    # employee with write on res.partner can add their own partner to
    # partner_ids from the res.partner side (meeting_ids, a raw relation
    # INSERT that never checks the event), so partner_ids membership cannot
    # grant access to a booking event. Only the booking sets this field.
    appointment_guest_partner_id = fields.Many2one(
        'res.partner', 'Appointment Guest', readonly=True, copy=False,
        index='btree_not_null', ondelete='set null')

    @api.model
    def _check_booking_markers(self, vals):
        """Only the booking (sudo) or an appointment manager sets the markers.

        Without this guard the organizer could clear is_appointment_booking
        through RPC and expose the event to every employee, or point
        appointment_guest_partner_id at someone else.
        """
        if self.env.su or not (BOOKING_MARKER_FIELDS & set(vals)):
            return
        if self.env.user.has_group(BOOKING_MANAGER_GROUP):
            return
        raise AccessError(_("Only the appointment booking can change its calendar event markers."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_booking_markers(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_booking_markers(vals)
        return super().write(vals)

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
