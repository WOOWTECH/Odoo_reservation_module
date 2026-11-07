# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .appointment_booking import BOOKING_MANAGER_GROUP

_logger = logging.getLogger(__name__)

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


class CalendarAttendee(models.Model):
    _inherit = 'calendar.attendee'

    def _appointment_guest_mail_blocked(self):
        """Guest rows of booking events whose booking is past the mail cap.

        The public booking form takes any address; the per-inbox cap
        (appointment.booking._guest_mail_over_cap) must also hold for the
        mails core sends to the event's attendees: invitation on a new
        attendee, date change, e-mail reminders, "send by mail".
        """
        attendees = self.sudo()
        events = attendees.event_id.filtered('is_appointment_booking')
        if not events:
            return self.browse()
        bookings = self.env['appointment.booking'].sudo().search(
            [('calendar_event_id', 'in', events.ids)])
        booking_by_event = {booking.calendar_event_id.id: booking for booking in bookings}
        blocked = self.browse()
        for attendee in attendees:
            event = attendee.event_id
            if not event.is_appointment_booking or not attendee.partner_id:
                continue
            if attendee.partner_id != event.appointment_guest_partner_id:
                continue
            booking = booking_by_event.get(event.id)
            if booking and booking._guest_mail_over_cap():
                blocked |= self.browse(attendee.id)
        return blocked

    def _send_mail_to_attendees(self, mail_template, force_send=False):
        blocked = self._appointment_guest_mail_blocked()
        if blocked:
            _logger.warning("Calendar mail to booking guests suppressed (per-address limit): attendees %s",
                            blocked.ids)
            remaining = self - blocked
            if not remaining:
                return False
            return super(CalendarAttendee, remaining)._send_mail_to_attendees(
                mail_template, force_send=force_send)
        return super()._send_mail_to_attendees(mail_template, force_send=force_send)
