# -*- coding: utf-8 -*-

from odoo import http, fields, _
from odoo.http import request
from datetime import datetime, timedelta
import json


class AppointmentController(http.Controller):

    def _get_translations(self):
        """Get translated labels for templates"""
        return {
            'book_an_appointment': _('Book an Appointment'),
            'book_now': _('Book Now'),
            'hours': _('hour(s)'),
            'no_appointment_types': _('No appointment types available at the moment.'),
            'appointments': _('Appointments'),
            'select_date_time': _('Select Date & Time'),
            'select_resource': _('Select Resource'),
            'select_staff': _('Select Staff'),
            'seats': _('seats'),
            'loading_slots': _('Loading available slots...'),
            'available_times': _('Available Times'),
            'book': _('Book'),
            'complete_booking': _('Complete Your Booking'),
            'name': _('Name'),
            'email': _('Email'),
            'phone': _('Phone'),
            'number_of_guests': _('Number of Guests'),
            'select_option': _('-- Select --'),
            'notes': _('Notes'),
            'payment_of': _('Payment of'),
            'per_person': _('per person'),
            'payment_required': _('will be required to confirm your booking.'),
            'continue_to_payment': _('Continue to Payment'),
            'confirm_booking': _('Confirm Booking'),
            'booking_confirmed': _('Booking Confirmed!'),
            'booking_reference': _('Your booking reference is:'),
            'appointment_label': _('Appointment:'),
            'date_time': _('Date & Time:'),
            'resource_label': _('Resource:'),
            'staff_label': _('Staff:'),
            'guests_label': _('Guests:'),
            'confirmation_email_sent': _('A confirmation email has been sent to'),
            'book_another': _('Book Another Appointment'),
            'booking': _('Booking'),
            'appointment_details': _('Appointment Details'),
            'type_label': _('Type:'),
            'guest_information': _('Guest Information'),
            'name_label': _('Name:'),
            'email_label': _('Email:'),
            'phone_label': _('Phone:'),
            'guests_count_label': _('Number of Guests:'),
            'cancel_booking': _('Cancel Booking'),
            'cancel_booking_question': _('Cancel Booking?'),
            'cancel_confirm_msg': _('Are you sure you want to cancel your booking?'),
            'booking_reference_label': _('Booking Reference:'),
            'yes_cancel': _('Yes, Cancel Booking'),
            'no_keep': _('No, Keep Booking'),
            'booking_cancelled': _('Booking Cancelled'),
            'your_booking': _('Your booking'),
            'has_been_cancelled': _('has been cancelled.'),
            'book_new_appointment': _('Book a New Appointment'),
            'payment': _('Payment'),
            'booking_summary': _('Booking Summary'),
            'amount_due': _('Amount Due'),
            'select_payment_method': _('Select a payment method to complete your booking.'),
            'pay_with': _('Pay with'),
            'no_payment_methods': _('No payment methods available. Please contact us to complete your booking.'),
        }

    @http.route('/appointment', type='http', auth='public', website=True)
    def appointment_list(self, **kwargs):
        """Display list of available appointment types"""
        appointment_types = request.env['appointment.type'].sudo().search([
            ('is_published', '=', True),
            ('active', '=', True),
        ])
        return request.render('odoo_calendar_enhance.appointment_list', {
            'appointment_types': appointment_types,
            't': self._get_translations(),
        })

    @http.route('/appointment/<int:appointment_type_id>', type='http', auth='public', website=True)
    def appointment_type(self, appointment_type_id, **kwargs):
        """Display appointment type details and start booking process"""
        appointment_type = request.env['appointment.type'].sudo().browse(appointment_type_id)
        if not appointment_type.exists() or not appointment_type.is_published:
            return request.redirect('/appointment')

        return request.render('odoo_calendar_enhance.appointment_type_page', {
            'appointment_type': appointment_type,
            't': self._get_translations(),
        })

    @http.route('/appointment/<int:appointment_type_id>/schedule', type='http', auth='public', website=True)
    def appointment_schedule(self, appointment_type_id, resource_id=None, staff_id=None, **kwargs):
        """Display available time slots"""
        appointment_type = request.env['appointment.type'].sudo().browse(appointment_type_id)
        if not appointment_type.exists() or not appointment_type.is_published:
            return request.redirect('/appointment')

        # Get available resources/staff
        resources = appointment_type.resource_ids
        staff = appointment_type.staff_user_ids

        # Calculate date range
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=appointment_type.max_booking_days)

        return request.render('odoo_calendar_enhance.appointment_schedule_page', {
            'appointment_type': appointment_type,
            'resources': resources,
            'staff': staff,
            'start_date': start_date,
            'end_date': end_date,
            'selected_resource_id': int(resource_id) if resource_id else None,
            'selected_staff_id': int(staff_id) if staff_id else None,
            't': self._get_translations(),
        })

    @http.route('/appointment/<int:appointment_type_id>/slots', type='json', auth='public')
    def get_slots(self, appointment_type_id, date, resource_id=None, staff_id=None, **kwargs):
        """Get available slots for a specific date (AJAX endpoint)"""
        appointment_type = request.env['appointment.type'].sudo().browse(appointment_type_id)
        if not appointment_type.exists():
            return {'error': 'Appointment type not found'}

        try:
            selected_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            return {'error': 'Invalid date format'}

        # Get or generate slots for this date
        start_datetime = datetime.combine(selected_date, datetime.min.time())
        end_datetime = datetime.combine(selected_date, datetime.max.time())

        slots = []
        slot_duration = timedelta(hours=appointment_type.slot_duration)
        slot_interval = timedelta(hours=appointment_type.slot_interval or appointment_type.slot_duration)

        # Working hours (default 9:00 - 18:00)
        current_time = start_datetime.replace(hour=9, minute=0)
        end_time = start_datetime.replace(hour=18, minute=0)

        # Minimum booking time check
        min_booking_time = datetime.now() + timedelta(hours=appointment_type.min_booking_hours)

        while current_time + slot_duration <= end_time:
            if current_time >= min_booking_time:
                # Check existing bookings
                existing = request.env['appointment.booking'].sudo().search_count([
                    ('appointment_type_id', '=', appointment_type_id),
                    ('start_datetime', '=', current_time),
                    ('state', 'in', ['confirmed', 'done']),
                    ('resource_id', '=', int(resource_id) if resource_id else False),
                    ('staff_user_id', '=', int(staff_id) if staff_id else False),
                ])

                capacity = 1
                if resource_id:
                    resource = request.env['resource.resource'].sudo().browse(int(resource_id))
                    capacity = resource.capacity or 1

                if existing < capacity:
                    slots.append({
                        'start': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'end': (current_time + slot_duration).strftime('%Y-%m-%d %H:%M:%S'),
                        'start_time': current_time.strftime('%H:%M'),
                        'end_time': (current_time + slot_duration).strftime('%H:%M'),
                        'available': capacity - existing,
                    })

            current_time += slot_interval

        return {'slots': slots}

    @http.route('/appointment/<int:appointment_type_id>/book', type='http', auth='public', website=True, methods=['GET', 'POST'])
    def appointment_book(self, appointment_type_id, start_datetime=None, resource_id=None, staff_id=None, **kwargs):
        """Display booking form and handle submission"""
        appointment_type = request.env['appointment.type'].sudo().browse(appointment_type_id)
        if not appointment_type.exists() or not appointment_type.is_published:
            return request.redirect('/appointment')

        if request.httprequest.method == 'POST':
            # Include explicitly captured params in data dict
            data = dict(kwargs)
            data['start_datetime'] = start_datetime
            data['resource_id'] = resource_id
            data['staff_id'] = staff_id
            return self._process_booking(appointment_type, data)

        # Validate start_datetime
        if not start_datetime:
            return request.redirect(f'/appointment/{appointment_type_id}/schedule')

        try:
            start_dt = datetime.strptime(start_datetime, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return request.redirect(f'/appointment/{appointment_type_id}/schedule')

        end_dt = start_dt + timedelta(hours=appointment_type.slot_duration)

        resource = None
        if resource_id:
            resource = request.env['resource.resource'].sudo().browse(int(resource_id))

        staff = None
        if staff_id:
            staff = request.env['res.users'].sudo().browse(int(staff_id))

        return request.render('odoo_calendar_enhance.appointment_book_page', {
            'appointment_type': appointment_type,
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'resource': resource,
            'staff': staff,
            'questions': appointment_type.question_ids,
            't': self._get_translations(),
        })

    def _process_booking(self, appointment_type, data):
        """Process the booking form submission"""
        # Validate required fields
        required_fields = ['guest_name', 'guest_email', 'start_datetime']
        for field in required_fields:
            if not data.get(field):
                # Need to reconstruct template context properly
                start_dt = None
                end_dt = None
                if data.get('start_datetime'):
                    try:
                        start_dt = datetime.strptime(data['start_datetime'], '%Y-%m-%d %H:%M:%S')
                        end_dt = start_dt + timedelta(hours=appointment_type.slot_duration)
                    except ValueError:
                        pass

                resource = None
                if data.get('resource_id'):
                    resource = request.env['resource.resource'].sudo().browse(int(data['resource_id']))

                staff = None
                if data.get('staff_id'):
                    staff = request.env['res.users'].sudo().browse(int(data['staff_id']))

                return request.render('odoo_calendar_enhance.appointment_book_page', {
                    'appointment_type': appointment_type,
                    'start_datetime': start_dt,
                    'end_datetime': end_dt,
                    'resource': resource,
                    'staff': staff,
                    'questions': appointment_type.question_ids,
                    'error': _('Please fill in all required fields.'),
                    'guest_name': data.get('guest_name', ''),
                    'guest_email': data.get('guest_email', ''),
                    'guest_phone': data.get('guest_phone', ''),
                    'guest_count': data.get('guest_count', 1),
                    'notes': data.get('notes', ''),
                    't': self._get_translations(),
                })

        try:
            start_dt = datetime.strptime(data['start_datetime'], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return request.redirect(f'/appointment/{appointment_type.id}/schedule')

        end_dt = start_dt + timedelta(hours=appointment_type.slot_duration)

        # Create booking
        booking_vals = {
            'appointment_type_id': appointment_type.id,
            'guest_name': data.get('guest_name'),
            'guest_email': data.get('guest_email'),
            'guest_phone': data.get('guest_phone'),
            'guest_count': int(data.get('guest_count', 1)),
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'notes': data.get('notes'),
        }

        if data.get('resource_id'):
            booking_vals['resource_id'] = int(data['resource_id'])
        if data.get('staff_id'):
            booking_vals['staff_user_id'] = int(data['staff_id'])

        # Set payment status
        if appointment_type.require_payment:
            booking_vals['payment_status'] = 'pending'
            booking_vals['payment_amount'] = appointment_type.payment_amount
            if appointment_type.payment_per_person:
                booking_vals['payment_amount'] *= int(data.get('guest_count', 1))

        # Create partner if email provided
        partner = request.env['res.partner'].sudo().search([
            ('email', '=', data.get('guest_email'))
        ], limit=1)
        if not partner:
            partner = request.env['res.partner'].sudo().create({
                'name': data.get('guest_name'),
                'email': data.get('guest_email'),
                'phone': data.get('guest_phone'),
            })
        booking_vals['partner_id'] = partner.id

        booking = request.env['appointment.booking'].sudo().create(booking_vals)

        # Save question answers
        for question in appointment_type.question_ids:
            answer_key = f'question_{question.id}'
            if answer_key in data:
                answer_vals = {
                    'booking_id': booking.id,
                    'question_id': question.id,
                }
                answer = request.env['appointment.answer'].sudo().create(answer_vals)
                answer.set_value(data[answer_key])

        # Auto confirm if enabled and no payment required
        if appointment_type.auto_confirm and not appointment_type.require_payment:
            booking.action_confirm()

        # Redirect to appropriate page
        if appointment_type.require_payment:
            return request.redirect(f'/appointment/booking/{booking.id}/pay?token={booking.access_token}')

        return request.redirect(f'/appointment/booking/{booking.id}/confirm?token={booking.access_token}')

    @http.route('/appointment/booking/<int:booking_id>/confirm', type='http', auth='public', website=True)
    def appointment_confirm(self, booking_id, token=None, **kwargs):
        """Display booking confirmation page"""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or (token and booking.access_token != token):
            return request.redirect('/appointment')

        return request.render('odoo_calendar_enhance.appointment_confirm_page', {
            'booking': booking,
            't': self._get_translations(),
        })

    @http.route('/appointment/booking/<int:booking_id>', type='http', auth='public', website=True)
    def appointment_booking_details(self, booking_id, token=None, **kwargs):
        """Display booking details"""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or (token and booking.access_token != token):
            return request.redirect('/appointment')

        return request.render('odoo_calendar_enhance.appointment_booking_page', {
            'booking': booking,
            't': self._get_translations(),
        })

    @http.route('/appointment/booking/<int:booking_id>/cancel', type='http', auth='public', website=True, methods=['GET', 'POST'])
    def appointment_cancel(self, booking_id, token=None, **kwargs):
        """Cancel a booking"""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or (token and booking.access_token != token):
            return request.redirect('/appointment')

        if request.httprequest.method == 'POST':
            try:
                booking.action_cancel()
                return request.render('odoo_calendar_enhance.appointment_cancelled_page', {
                    'booking': booking,
                    't': self._get_translations(),
                })
            except Exception as e:
                return request.render('odoo_calendar_enhance.appointment_booking_page', {
                    'booking': booking,
                    'error': str(e),
                    't': self._get_translations(),
                })

        return request.render('odoo_calendar_enhance.appointment_cancel_page', {
            'booking': booking,
            't': self._get_translations(),
        })

    @http.route('/appointment/booking/<int:booking_id>/pay', type='http', auth='public', website=True)
    def appointment_payment(self, booking_id, token=None, **kwargs):
        """Display payment page"""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or (token and booking.access_token != token):
            return request.redirect('/appointment')

        if booking.payment_status == 'paid':
            return request.redirect(f'/appointment/booking/{booking_id}/confirm?token={token}')

        # Get available payment providers
        payment_providers = request.env['payment.provider'].sudo().search([
            ('state', '=', 'enabled'),
        ])

        return request.render('odoo_calendar_enhance.appointment_payment_page', {
            'booking': booking,
            'payment_providers': payment_providers,
            't': self._get_translations(),
        })
