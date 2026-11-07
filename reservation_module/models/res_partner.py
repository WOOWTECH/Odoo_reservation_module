# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.fields import Command


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # res.partner.meeting_ids is the other side of calendar.event.partner_ids.
    # Many2many LINK/UNLINK/SET/CLEAR commands write the relation table
    # directly and never check access on the calendar.event records, and every
    # internal user has write on res.partner (base.group_partner_manager is in
    # the default user template). Without this guard an employee could attach
    # their partner to any booking event, pass the core "Private events" write
    # rule (partner_ids) and receive its alarms. Booking events may only be
    # (un)linked from here by someone allowed to write the event itself.

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            touched = set()
            for vals in vals_list:
                if 'meeting_ids' in vals:
                    touched |= self._meeting_ids_touched(vals['meeting_ids'], current=set())
            self._check_booking_event_link(touched)
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and 'meeting_ids' in vals:
            touched = set()
            for partner in self.sudo():
                touched |= self._meeting_ids_touched(
                    vals['meeting_ids'], current=set(partner.meeting_ids.ids))
            self._check_booking_event_link(touched)
        return super().write(vals)

    @api.model
    def _meeting_ids_touched(self, value, current):
        """Event ids whose relation rows the given meeting_ids value changes.

        Mirrors the value normalisation of fields._RelationalMulti.write_batch.
        CREATE/UPDATE/DELETE go through calendar.event create/write/unlink and
        their own access checks, so only the raw relation commands count.
        """
        if isinstance(value, tuple):
            value = [Command.set(value)]
        elif isinstance(value, models.BaseModel):
            value = [Command.set(value._ids)]
        elif value is False or value is None:
            value = [Command.clear()]
        elif isinstance(value, list) and value and not isinstance(value[0], (tuple, list)):
            value = [Command.set(tuple(value))]
        touched = set()
        for command in value or ():
            if not isinstance(command, (tuple, list)) or not command:
                continue
            if command[0] in (Command.LINK, Command.UNLINK):
                touched.add(command[1])
            elif command[0] == Command.CLEAR:
                touched |= current
            elif command[0] == Command.SET:
                touched |= set(command[2] or ()) ^ current
        return {i for i in touched if isinstance(i, int)}

    @api.model
    def _check_booking_event_link(self, event_ids):
        if not event_ids:
            return
        booking_events = self.env['calendar.event'].sudo().browse(event_ids).exists().filtered(
            'is_appointment_booking')
        if booking_events:
            # Raises AccessError unless the record rules let this user write
            # every one of these events (organizer, guest, appointment manager).
            booking_events.with_env(self.env).check_access('write')
