# -*- coding: utf-8 -*-

import re

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.fields import Command

# A record id as RPC clients may send it: 63, 63.0 or "63".
_ID_TEXT = re.compile(r'[+-]?[0-9]{1,18}')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # res.partner.meeting_ids is the other side of calendar.event.partner_ids.
    # Many2many LINK/UNLINK/SET/CLEAR commands write the relation table
    # directly and never check access on the calendar.event records, and every
    # internal user has write on res.partner (base.group_partner_manager is in
    # the default user template). Without this guard an employee could attach
    # their partner to any booking event, receive its alarms and, through the
    # core videocall fallback, a seat in its meeting room, or detach the
    # guest. Booking events may only be (un)linked from here by someone
    # allowed to write the event itself.

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            touched = set()
            checked_vals_list = []
            for vals in vals_list:
                if 'meeting_ids' in vals:
                    commands = self._normalize_meeting_commands(vals['meeting_ids'])
                    vals = dict(vals, meeting_ids=commands)
                    touched |= self._meeting_ids_touched(commands, current=set())
                checked_vals_list.append(vals)
            vals_list = checked_vals_list
            self._check_booking_event_link(touched)
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and 'meeting_ids' in vals:
            # The checked commands are the ones written: ids normalised once.
            commands = self._normalize_meeting_commands(vals['meeting_ids'])
            vals = dict(vals, meeting_ids=commands)
            touched = set()
            # Same view of the current links as the ORM's own write
            # (archived events filtered out the same way).
            for partner in self.sudo():
                touched |= self._meeting_ids_touched(
                    commands, current=set(partner.meeting_ids.ids))
            self._check_booking_event_link(touched)
        return super().write(vals)

    @api.model
    def _meeting_relation_id(self, value):
        """The event id a LINK / UNLINK / SET command of meeting_ids refers to.

        The ORM puts these ids into the relation INSERT/DELETE as given and
        PostgreSQL casts them, so "63" and 63.0 change the rows of event 63
        just like 63. They are turned into 63 for the access check and for the
        write itself, so both see the same event. Anything that is not an
        exact integer id is refused.
        """
        if isinstance(value, bool):
            pass  # an int subclass, never an id
        elif isinstance(value, int):
            return value
        elif isinstance(value, float):
            if value.is_integer():
                return int(value)
        elif isinstance(value, str):
            text = value.strip()
            if _ID_TEXT.fullmatch(text):
                return int(text)
        raise ValidationError(_('Invalid meeting id: %s', repr(value)))

    @api.model
    def _normalize_meeting_commands(self, value):
        """``value`` (any form the ORM accepts for meeting_ids) as a list of
        commands whose relation ids are integers.

        Mirrors the value normalisation of fields._RelationalMulti.write_batch
        (a tuple or list of ids, a recordset, False/None become SET/CLEAR).
        The ids of LINK, UNLINK and SET go through _meeting_relation_id.
        CREATE, UPDATE and DELETE go through calendar.event
        create/write/unlink and their own access checks; they are left as
        given.
        """
        relation_id = self._meeting_relation_id
        if isinstance(value, tuple):
            value = [Command.set(value)]
        elif isinstance(value, models.BaseModel):
            value = [Command.set(value._ids)]
        elif value is False or value is None:
            value = [Command.clear()]
        elif isinstance(value, list) and value and not isinstance(value[0], (tuple, list)):
            value = [Command.set(tuple(value))]
        if not isinstance(value, list):
            return value  # the ORM refuses it
        commands = []
        for command in value:
            if isinstance(command, (tuple, list)) and command:
                if command[0] == Command.LINK:
                    command = Command.link(relation_id(command[1]))
                elif command[0] == Command.UNLINK:
                    command = Command.unlink(relation_id(command[1]))
                elif command[0] == Command.SET:
                    command = Command.set([relation_id(id_) for id_ in (command[2] or ())])
            commands.append(command)
        return commands

    @api.model
    def _meeting_ids_touched(self, value, current):
        """Event ids whose relation rows the given meeting_ids value may change.

        ``current`` holds the event ids linked now. The ids are normalised
        like the write does (_normalize_meeting_commands): "63" and 63.0 count
        as event 63, never as something to skip.
        """
        commands = self._normalize_meeting_commands(value)
        touched = set()
        if not isinstance(commands, list):
            return touched
        for command in commands:
            if not isinstance(command, (tuple, list)) or not command:
                continue
            if command[0] in (Command.LINK, Command.UNLINK):
                touched.add(command[1])
            elif command[0] == Command.CLEAR:
                touched |= current
            elif command[0] == Command.SET:
                touched |= set(command[2]) ^ current
        return touched

    @api.model
    def _check_booking_event_link(self, event_ids):
        if not event_ids:
            return
        booking_events = self.env['calendar.event'].sudo().with_context(
            active_test=False).browse(event_ids).exists().filtered('is_appointment_booking')
        if booking_events:
            # Raises AccessError unless the record rules let this user write
            # every one of these events (organizer, guest, appointment manager).
            booking_events.with_env(self.env).check_access('write')
