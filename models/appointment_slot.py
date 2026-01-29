# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class AppointmentSlot(models.Model):
    _name = 'appointment.slot'
    _description = 'Appointment Slot'
    _order = 'start_datetime'

    appointment_type_id = fields.Many2one(
        'appointment.type',
        string='Appointment Type',
        required=True,
        ondelete='cascade',
    )
    resource_id = fields.Many2one(
        'resource.resource',
        string='Resource',
        ondelete='cascade',
    )
    staff_user_id = fields.Many2one(
        'res.users',
        string='Staff',
        ondelete='cascade',
    )

    start_datetime = fields.Datetime('Start Time', required=True)
    end_datetime = fields.Datetime('End Time', required=True)

    capacity = fields.Integer('Capacity', default=1, required=True)
    booked_count = fields.Integer(
        'Booked Count',
        compute='_compute_booking_info',
        store=True,
    )
    available_count = fields.Integer(
        'Available Count',
        compute='_compute_booking_info',
        store=True,
    )

    state = fields.Selection([
        ('available', 'Available'),
        ('partial', 'Partially Booked'),
        ('full', 'Fully Booked'),
        ('closed', 'Closed'),
    ], string='State', compute='_compute_booking_info', store=True)

    booking_ids = fields.One2many(
        'appointment.booking',
        'slot_id',
        string='Bookings',
    )

    @api.depends('booking_ids', 'booking_ids.state', 'booking_ids.guest_count', 'capacity')
    def _compute_booking_info(self):
        for slot in self:
            confirmed_bookings = slot.booking_ids.filtered(
                lambda b: b.state in ['confirmed', 'done']
            )
            slot.booked_count = sum(confirmed_bookings.mapped('guest_count'))
            slot.available_count = max(0, slot.capacity - slot.booked_count)

            if slot.available_count == 0:
                slot.state = 'full'
            elif slot.booked_count > 0:
                slot.state = 'partial'
            else:
                slot.state = 'available'

    @api.constrains('start_datetime', 'end_datetime')
    def _check_dates(self):
        for slot in self:
            if slot.end_datetime <= slot.start_datetime:
                raise ValidationError(_('End time must be after start time.'))

    @api.constrains('capacity')
    def _check_capacity(self):
        for slot in self:
            if slot.capacity < 1:
                raise ValidationError(_('Capacity must be at least 1.'))

    def is_available(self, guest_count=1):
        """Check if slot has enough availability for the requested guest count"""
        self.ensure_one()
        return self.available_count >= guest_count

    @api.model
    def generate_slots(self, appointment_type, start_date, end_date, resource=None, staff=None):
        """
        Generate available slots for an appointment type within a date range.
        Returns a list of slot data dictionaries.
        """
        slots = []
        slot_duration = timedelta(hours=appointment_type.slot_duration)
        slot_interval = timedelta(hours=appointment_type.slot_interval or appointment_type.slot_duration)

        current_datetime = fields.Datetime.to_datetime(start_date)
        end_datetime = fields.Datetime.to_datetime(end_date)

        # Get working hours from resource calendar if available
        if resource and resource.calendar_id:
            calendar = resource.calendar_id
        elif staff and staff.resource_id and staff.resource_id.calendar_id:
            calendar = staff.resource_id.calendar_id
        else:
            calendar = self.env.company.resource_calendar_id

        while current_datetime < end_datetime:
            slot_end = current_datetime + slot_duration

            # Check if this time is within working hours
            if calendar:
                intervals = calendar._work_intervals_batch(
                    current_datetime,
                    slot_end,
                    resources=resource or (staff.resource_id if staff else None),
                )
                # Check if slot falls within work intervals
                is_working = any(intervals.values())
            else:
                is_working = True

            if is_working:
                slot_data = {
                    'appointment_type_id': appointment_type.id,
                    'start_datetime': current_datetime,
                    'end_datetime': slot_end,
                    'capacity': 1,  # Default capacity
                }
                if resource:
                    slot_data['resource_id'] = resource.id
                    slot_data['capacity'] = resource.capacity if hasattr(resource, 'capacity') else 1
                if staff:
                    slot_data['staff_user_id'] = staff.id

                slots.append(slot_data)

            current_datetime += slot_interval

        return slots

    @api.model
    def get_available_slots(self, appointment_type_id, start_date, end_date, resource_id=None, staff_user_id=None):
        """
        Get available slots for booking.
        This method can be called from the website controller.
        """
        appointment_type = self.env['appointment.type'].browse(appointment_type_id)
        if not appointment_type.exists():
            return []

        domain = [
            ('appointment_type_id', '=', appointment_type_id),
            ('start_datetime', '>=', start_date),
            ('start_datetime', '<', end_date),
            ('state', 'in', ['available', 'partial']),
        ]
        if resource_id:
            domain.append(('resource_id', '=', resource_id))
        if staff_user_id:
            domain.append(('staff_user_id', '=', staff_user_id))

        return self.search(domain)
