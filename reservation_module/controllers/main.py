# -*- coding: utf-8 -*-

from odoo import http, fields, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from datetime import datetime, timedelta
import calendar
import json
import re


class AppointmentController(http.Controller):

    def _get_translations(self):
        """Get translated labels for templates

        Uses a simple dictionary approach for reliable bilingual support.
        Checks current language and returns appropriate translations.
        """
        # Get current language - try multiple sources for reliability
        lang = None

        # Method 1: Check request.env.lang (Odoo 18 standard)
        if hasattr(request, 'env') and request.env:
            lang = request.env.lang

        # Method 2: Check request.env.context
        if not lang and hasattr(request, 'env') and request.env:
            lang = request.env.context.get('lang')

        # Method 3: Check website's current language via frontend_lang cookie
        if not lang:
            try:
                frontend_lang = request.httprequest.cookies.get('frontend_lang')
                if frontend_lang:
                    lang = frontend_lang
            except Exception:
                pass

        # Method 4: Check website's default language
        if not lang:
            try:
                website = request.env['website'].get_current_website()
                if website and website.default_lang_id:
                    lang = website.default_lang_id.code
            except Exception:
                pass

        # Default fallback
        if not lang:
            lang = 'en_US'

        # Chinese translations (zh_TW)
        zh_tw = {
            'book_an_appointment': '預約服務',
            'book_now': '立即預約',
            'hours': '小時',
            'no_appointment_types': '目前沒有可用的預約類型。',
            'appointments': '預約',
            'select_date_time': '選擇日期與時間',
            'select_location': '選擇場地',
            'select_staff': '選擇員工',
            'seats': '座位',
            'loading_slots': '正在載入可用時段...',
            'available_times': '可用時段',
            'book': '預約',
            'complete_booking': '完成您的預約',
            'name': '姓名',
            'email': '電子郵件',
            'phone': '電話',
            'number_of_guests': '訪客人數',
            'select_option': '-- 請選擇 --',
            'notes': '備註',
            'payment_of': '付款金額',
            'per_person': '每人',
            'payment_required': '需要付款才能確認您的預約。',
            'continue_to_payment': '繼續付款',
            'confirm_booking': '確認預約',
            'booking_confirmed': '預約已確認！',
            'booking_reference': '您的預約編號是：',
            'appointment_label': '預約項目：',
            'date_time': '日期與時間：',
            'location_label': '場地：',
            'staff_label': '員工：',
            'guests_label': '訪客人數：',
            'confirmation_email_sent': '確認郵件已發送至',
            'book_another': '預約另一個時段',
            'booking': '預約',
            'appointment_details': '預約詳情',
            'type_label': '類型：',
            'guest_information': '訪客資訊',
            'name_label': '姓名：',
            'email_label': '電子郵件：',
            'phone_label': '電話：',
            'guests_count_label': '訪客人數：',
            'cancel_booking': '取消預約',
            'cancel_booking_question': '取消預約？',
            'cancel_confirm_msg': '您確定要取消您的預約嗎？',
            'booking_reference_label': '預約編號：',
            'yes_cancel': '是的，取消預約',
            'no_keep': '不，保留預約',
            'booking_cancelled': '預約已取消',
            'your_booking': '您的預約',
            'has_been_cancelled': '已被取消。',
            'book_new_appointment': '預約新時段',
            'payment': '付款',
            'booking_summary': '預約摘要',
            'amount_due': '應付金額',
            'select_payment_method': '選擇付款方式以完成預約。',
            'pay_with': '使用付款',
            'no_payment_methods': '沒有可用的付款方式。請聯繫我們完成您的預約。',
            'faq_title': '常見問題',
            'auto_assign': '自動分配',
            'special_event': '特殊活動',
            'scheduled_appointment': '排程預約',
            'join_meeting': '加入會議',
            'online_meeting': '線上會議',
            'online_meeting_label': '這是一場線上會議，請在預約時間使用以下連結加入：',
            'meeting_link_available': '會議連結將在預約確認後提供。',
            'pending_payment': '待付款',
            'pending_payment_msg': '您的預約正在等待付款確認。',
            'go_to_payment': '前往付款',
            # Portal booking list
            'my_bookings': '我的預約',
            'view_my_bookings': '查看我的預約',
            'booking_info_sent_email': '相關預約資訊已傳送到您的電子信箱',
            'meeting_link_in_email': '（會議連結已包含在郵件中）',
            'upcoming_bookings': '即將到來的預約',
            'completed_bookings': '已完成的預約',
            'all_bookings': '所有預約',
            'no_bookings_yet': '您還沒有任何預約',
            'booking_status': '狀態',
            'view_details': '查看詳情',
            'status_confirmed': '已確認',
            'status_done': '已完成',
            'status_cancelled': '已取消',
            'status_draft': '草稿',
        }

        # English translations (en_US) - default
        en_us = {
            'book_an_appointment': 'Book an Appointment',
            'book_now': 'Book Now',
            'hours': 'hour(s)',
            'no_appointment_types': 'No appointment types available at the moment.',
            'appointments': 'Appointments',
            'select_date_time': 'Select Date & Time',
            'select_location': 'Select Location',
            'select_staff': 'Select Staff',
            'seats': 'seats',
            'loading_slots': 'Loading available slots...',
            'available_times': 'Available Times',
            'book': 'Book',
            'complete_booking': 'Complete Your Booking',
            'name': 'Name',
            'email': 'Email',
            'phone': 'Phone',
            'number_of_guests': 'Number of Guests',
            'select_option': '-- Select --',
            'notes': 'Notes',
            'payment_of': 'Payment of',
            'per_person': 'per person',
            'payment_required': 'will be required to confirm your booking.',
            'continue_to_payment': 'Continue to Payment',
            'confirm_booking': 'Confirm Booking',
            'booking_confirmed': 'Booking Confirmed!',
            'booking_reference': 'Your booking reference is:',
            'appointment_label': 'Appointment:',
            'date_time': 'Date & Time:',
            'location_label': 'Location:',
            'staff_label': 'Staff:',
            'guests_label': 'Guests:',
            'confirmation_email_sent': 'A confirmation email has been sent to',
            'book_another': 'Book Another Appointment',
            'booking': 'Booking',
            'appointment_details': 'Appointment Details',
            'type_label': 'Type:',
            'guest_information': 'Guest Information',
            'name_label': 'Name:',
            'email_label': 'Email:',
            'phone_label': 'Phone:',
            'guests_count_label': 'Number of Guests:',
            'cancel_booking': 'Cancel Booking',
            'cancel_booking_question': 'Cancel Booking?',
            'cancel_confirm_msg': 'Are you sure you want to cancel your booking?',
            'booking_reference_label': 'Booking Reference:',
            'yes_cancel': 'Yes, Cancel Booking',
            'no_keep': 'No, Keep Booking',
            'booking_cancelled': 'Booking Cancelled',
            'your_booking': 'Your booking',
            'has_been_cancelled': 'has been cancelled.',
            'book_new_appointment': 'Book a New Appointment',
            'payment': 'Payment',
            'booking_summary': 'Booking Summary',
            'amount_due': 'Amount Due',
            'select_payment_method': 'Select a payment method to complete your booking.',
            'pay_with': 'Pay with',
            'no_payment_methods': 'No payment methods available. Please contact us to complete your booking.',
            'faq_title': 'Frequently Asked Questions',
            'auto_assign': 'Auto-Assign',
            'special_event': 'Special Event',
            'scheduled_appointment': 'Scheduled Appointment',
            'join_meeting': 'Join Meeting',
            'online_meeting': 'Online Meeting',
            'online_meeting_label': 'This is an online meeting. Use the link below to join at the scheduled time:',
            'meeting_link_available': 'Meeting link will be available after booking confirmation.',
            'pending_payment': 'Pending Payment',
            'pending_payment_msg': 'Your booking is waiting for payment confirmation.',
            'go_to_payment': 'Go to Payment',
            # Portal booking list
            'my_bookings': 'My Bookings',
            'view_my_bookings': 'View My Bookings',
            'booking_info_sent_email': 'Booking confirmation details have been sent to your email',
            'meeting_link_in_email': '(The meeting link is included in the email)',
            'upcoming_bookings': 'Upcoming Bookings',
            'completed_bookings': 'Completed Bookings',
            'all_bookings': 'All Bookings',
            'no_bookings_yet': 'You have no bookings yet',
            'booking_status': 'Status',
            'view_details': 'View Details',
            'status_confirmed': 'Confirmed',
            'status_done': 'Completed',
            'status_cancelled': 'Cancelled',
            'status_draft': 'Draft',
        }

        # Return appropriate translation based on language
        if lang and lang.startswith('zh'):
            return zh_tw
        return en_us

    @staticmethod
    def _safe_int(value, default=None):
        """Safely convert a value to int, returning default on failure."""
        if not value:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @http.route('/appointment', type='http', auth='public', website=True)
    def appointment_list(self, **kwargs):
        """Display list of available appointment types"""
        appointment_types = request.env['appointment.type'].sudo().search([
            ('is_published', '=', True),
            ('active', '=', True),
        ])
        return request.render('reservation_module.appointment_list', {
            'appointment_types': appointment_types,
            't': self._get_translations(),
        })

    @http.route('/appointment/<int:appointment_type_id>', type='http', auth='public', website=True)
    def appointment_type(self, appointment_type_id, **kwargs):
        """Display appointment type details and start booking process"""
        appointment_type = request.env['appointment.type'].sudo().browse(appointment_type_id)
        if not appointment_type.exists() or not appointment_type.is_published:
            return request.redirect('/appointment')

        return request.render('reservation_module.appointment_type_page', {
            'appointment_type': appointment_type,
            't': self._get_translations(),
        })

    @http.route('/appointment/<int:appointment_type_id>/schedule', type='http', auth='public', website=True)
    def appointment_schedule(self, appointment_type_id, resource_id=None, staff_id=None, **kwargs):
        """Display available time slots"""
        appointment_type = request.env['appointment.type'].sudo().browse(appointment_type_id)
        if not appointment_type.exists() or not appointment_type.is_published:
            return request.redirect('/appointment')

        # Determine which panels to show
        show_staff_panel = (
            appointment_type.assign_staff
            and appointment_type.allow_customer_choose_staff
            and appointment_type.staff_user_ids
        )
        show_location_panel = (
            appointment_type.assign_location
            and appointment_type.allow_customer_choose_location
            and appointment_type.resource_ids
        )

        # Get available resources/staff based on assignment flags
        resources = appointment_type.resource_ids if show_location_panel else appointment_type.resource_ids.browse()
        staff = appointment_type.staff_user_ids if show_staff_panel else appointment_type.staff_user_ids.browse()

        # Calculate date range
        start_date = fields.Date.context_today(request.env['appointment.type'])
        end_date = start_date + timedelta(days=appointment_type.max_booking_days)

        return request.render('reservation_module.appointment_schedule_page', {
            'appointment_type': appointment_type,
            'resources': resources,
            'staff': staff,
            'show_staff_panel': show_staff_panel,
            'show_location_panel': show_location_panel,
            'start_date': start_date,
            'end_date': end_date,
            'selected_resource_id': self._safe_int(resource_id),
            'selected_staff_id': self._safe_int(staff_id),
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

        if appointment_type.is_scheduled:
            return self._get_scheduled_slots(appointment_type, selected_date, resource_id, staff_id)
        else:
            return self._get_event_slots(appointment_type, selected_date, resource_id, staff_id)

    def _get_availability_and_bookings(self, appointment_type, selected_date, resource_id, staff_id):
        """Common setup for both scheduled and event slot generation"""
        start_datetime = datetime.combine(selected_date, datetime.min.time())
        end_datetime = datetime.combine(selected_date, datetime.max.time())

        # Query weekly schedule availability for this day of week
        day_of_week = str(selected_date.weekday())
        availability_domain = [
            ('appointment_type_id', '=', appointment_type.id),
            ('dayofweek', '=', day_of_week),
        ]
        if resource_id:
            availability_domain += [
                '|',
                ('resource_id', '=', int(resource_id)),
                ('resource_id', '=', False),
            ]
        if staff_id:
            availability_domain += [
                '|',
                ('user_id', '=', int(staff_id)),
                ('user_id', '=', False),
            ]
        availabilities = request.env['appointment.availability'].sudo().search(availability_domain)

        min_booking_time = fields.Datetime.now() + timedelta(hours=appointment_type.min_booking_hours)

        # Batch fetch bookings for conflict detection
        Booking = request.env['appointment.booking'].sudo()
        day_conflict_domain = [
            ('state', 'in', ['confirmed', 'done']),
            ('start_datetime', '<', end_datetime),
            ('end_datetime', '>', start_datetime),
        ]
        staff_bookings = Booking.search(day_conflict_domain + [('staff_user_id', '=', int(staff_id))]) if staff_id else Booking
        resource_bookings = Booking.search(day_conflict_domain + [('resource_id', '=', int(resource_id))]) if resource_id else Booking

        capacity = 1
        if resource_id:
            resource = request.env['resource.resource'].sudo().browse(int(resource_id))
            capacity = resource.capacity or 1

        return {
            'start_datetime': start_datetime,
            'availabilities': availabilities,
            'min_booking_time': min_booking_time,
            'staff_bookings': staff_bookings,
            'resource_bookings': resource_bookings,
            'capacity': capacity,
        }

    def _get_scheduled_slots(self, appointment_type, selected_date, resource_id, staff_id):
        """Generate subdivided time slots from availability windows"""
        ctx = self._get_availability_and_bookings(appointment_type, selected_date, resource_id, staff_id)

        if not ctx['availabilities']:
            return {'slots': []}

        slots = []
        slot_duration = timedelta(hours=appointment_type.slot_duration)
        slot_interval = timedelta(hours=appointment_type.slot_interval or appointment_type.slot_duration)
        start_datetime = ctx['start_datetime']

        for avail in ctx['availabilities']:
            hour_from_int = int(avail.hour_from)
            min_from = int(round((avail.hour_from % 1) * 60))
            hour_to_int = int(avail.hour_to)
            min_to = int(round((avail.hour_to % 1) * 60))

            current_time = start_datetime.replace(hour=hour_from_int, minute=min_from, second=0, microsecond=0)
            end_time = start_datetime.replace(hour=hour_to_int, minute=min_to, second=0, microsecond=0)

            while current_time + slot_duration <= end_time:
                if current_time >= ctx['min_booking_time']:
                    slot_end = current_time + slot_duration

                    staff_conflict = staff_id and any(
                        b.start_datetime < slot_end and b.end_datetime > current_time
                        for b in ctx['staff_bookings']
                    )
                    resource_overlap = sum(
                        1 for b in ctx['resource_bookings']
                        if b.start_datetime < slot_end and b.end_datetime > current_time
                    ) if resource_id else 0

                    if not staff_conflict and resource_overlap < ctx['capacity']:
                        slots.append({
                            'start': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'end': slot_end.strftime('%Y-%m-%d %H:%M:%S'),
                            'start_time': current_time.strftime('%H:%M'),
                            'end_time': slot_end.strftime('%H:%M'),
                            'available': ctx['capacity'] - resource_overlap if resource_id else 1,
                        })

                current_time += slot_interval

        slots.sort(key=lambda s: s['start'])
        return {'slots': slots}

    def _get_event_slots(self, appointment_type, selected_date, resource_id, staff_id):
        """Generate one slot per availability window (special event mode)"""
        ctx = self._get_availability_and_bookings(appointment_type, selected_date, resource_id, staff_id)

        if not ctx['availabilities']:
            return {'slots': []}

        slots = []
        start_datetime = ctx['start_datetime']

        for avail in ctx['availabilities']:
            hour_from_int = int(avail.hour_from)
            min_from = int(round((avail.hour_from % 1) * 60))
            hour_to_int = int(avail.hour_to)
            min_to = int(round((avail.hour_to % 1) * 60))

            slot_start = start_datetime.replace(hour=hour_from_int, minute=min_from, second=0, microsecond=0)
            slot_end = start_datetime.replace(hour=hour_to_int, minute=min_to, second=0, microsecond=0)

            if slot_start < ctx['min_booking_time']:
                continue

            staff_conflict = staff_id and any(
                b.start_datetime < slot_end and b.end_datetime > slot_start
                for b in ctx['staff_bookings']
            )
            resource_overlap = sum(
                1 for b in ctx['resource_bookings']
                if b.start_datetime < slot_end and b.end_datetime > slot_start
            ) if resource_id else 0

            if not staff_conflict and resource_overlap < ctx['capacity']:
                slots.append({
                    'start': slot_start.strftime('%Y-%m-%d %H:%M:%S'),
                    'end': slot_end.strftime('%Y-%m-%d %H:%M:%S'),
                    'start_time': slot_start.strftime('%H:%M'),
                    'end_time': slot_end.strftime('%H:%M'),
                    'available': ctx['capacity'] - resource_overlap if resource_id else 1,
                })

        slots.sort(key=lambda s: s['start'])
        return {'slots': slots}

    @http.route('/appointment/<int:appointment_type_id>/event_dates', type='json', auth='public')
    def get_event_dates(self, appointment_type_id, year, month, **kwargs):
        """Get dates with events for a given month (special event mode)"""
        appointment_type = request.env['appointment.type'].sudo().browse(appointment_type_id)
        if not appointment_type.exists():
            return {'dates': []}

        year = int(year)
        month = int(month)
        _, num_days = calendar.monthrange(year, month)

        # Get all availability dayofweek values for this appointment type
        availabilities = request.env['appointment.availability'].sudo().search([
            ('appointment_type_id', '=', appointment_type_id),
        ])
        available_days = set(int(a.dayofweek) for a in availabilities)

        dates = []
        today = fields.Date.context_today(request.env['appointment.type'])
        for day in range(1, num_days + 1):
            d = datetime(year, month, day).date()
            if d >= today and d.weekday() in available_days:
                dates.append(d.strftime('%Y-%m-%d'))

        return {'dates': dates}

    @http.route('/appointment/<int:appointment_type_id>/book', type='http', auth='public', website=True, methods=['GET', 'POST'])
    def appointment_book(self, appointment_type_id, start_datetime=None, end_datetime=None, resource_id=None, staff_id=None, **kwargs):
        """Display booking form and handle submission"""
        appointment_type = request.env['appointment.type'].sudo().browse(appointment_type_id)
        if not appointment_type.exists() or not appointment_type.is_published:
            return request.redirect('/appointment')

        if request.httprequest.method == 'POST':
            # Include explicitly captured params in data dict
            data = dict(kwargs)
            data['start_datetime'] = start_datetime
            data['end_datetime'] = end_datetime
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

        # For event mode, use explicit end_datetime; for scheduled, compute from slot_duration
        if not appointment_type.is_scheduled and end_datetime:
            try:
                end_dt = datetime.strptime(end_datetime, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                end_dt = start_dt + timedelta(hours=appointment_type.slot_duration)
        else:
            end_dt = start_dt + timedelta(hours=appointment_type.slot_duration)

        resource = None
        rid = self._safe_int(resource_id)
        if rid:
            resource = request.env['resource.resource'].sudo().browse(rid)

        staff = None
        sid = self._safe_int(staff_id)
        if sid:
            staff = request.env['res.users'].sudo().browse(sid)

        # Pre-fill form for logged-in portal users
        portal_partner = None
        if not request.env.user._is_public():
            portal_partner = request.env.user.partner_id

        return request.render('reservation_module.appointment_book_page', {
            'appointment_type': appointment_type,
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'resource': resource,
            'staff': staff,
            'portal_partner': portal_partner,
            't': self._get_translations(),
        })

    def _render_booking_form_error(self, appointment_type, data, error_msg):
        """Re-render booking form with validation error, preserving all user input"""
        start_dt = None
        end_dt = None
        if data.get('start_datetime'):
            try:
                start_dt = datetime.strptime(data['start_datetime'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        # Preserve explicit end_datetime from form (important for event mode)
        if data.get('end_datetime'):
            try:
                end_dt = datetime.strptime(data['end_datetime'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        # Fallback: compute from slot_duration if end_datetime not available
        if not end_dt and start_dt:
            end_dt = start_dt + timedelta(hours=appointment_type.slot_duration)

        resource = None
        rid = self._safe_int(data.get('resource_id'))
        if rid:
            resource = request.env['resource.resource'].sudo().browse(rid)

        staff = None
        sid = self._safe_int(data.get('staff_id'))
        if sid:
            staff = request.env['res.users'].sudo().browse(sid)

        return request.render('reservation_module.appointment_book_page', {
            'appointment_type': appointment_type,
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'resource': resource,
            'staff': staff,
            'error': error_msg,
            'guest_name': data.get('guest_name', ''),
            'guest_email': data.get('guest_email', ''),
            'guest_phone': data.get('guest_phone', ''),
            'guest_count': data.get('guest_count', 1),
            'notes': data.get('notes', ''),
            't': self._get_translations(),
        })

    def _process_booking(self, appointment_type, data):
        """Process the booking form submission"""
        # Validate required fields
        required_fields = ['guest_name', 'guest_email', 'start_datetime']
        for field in required_fields:
            if not data.get(field):
                return self._render_booking_form_error(
                    appointment_type, data, _('Please fill in all required fields.'))

        # Validate & sanitize guest_name (strip HTML tags)
        guest_name = re.sub(r'<[^>]+>', '', data.get('guest_name', '')).strip()
        if not guest_name or len(guest_name) > 256:
            return self._render_booking_form_error(
                appointment_type, data, _('Please enter a valid name.'))

        # Validate email format
        email = data.get('guest_email', '').strip()
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return self._render_booking_form_error(
                appointment_type, data, _('Please enter a valid email address.'))

        # Validate phone (if provided): only digits, spaces, +, -, ()
        guest_phone = (data.get('guest_phone') or '').strip()
        if guest_phone and not re.match(r'^[0-9+\-() ]{0,30}$', guest_phone):
            return self._render_booking_form_error(
                appointment_type, data, _('Please enter a valid phone number.'))

        # Safe int() casts for guest_count (H2 + H3)
        try:
            guest_count = int(data.get('guest_count', 1))
        except (ValueError, TypeError):
            guest_count = 1
        if guest_count < 1:
            guest_count = 1
        # Enforce upper bound from appointment type capacity
        max_guests = appointment_type.max_guests if hasattr(appointment_type, 'max_guests') and appointment_type.max_guests else 100
        if guest_count > max_guests:
            return self._render_booking_form_error(
                appointment_type, data, _('Maximum %d guests allowed.', max_guests))

        try:
            start_dt = datetime.strptime(data['start_datetime'], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return request.redirect(f'/appointment/{appointment_type.id}/schedule')

        # For event mode, use explicit end_datetime; for scheduled, compute from slot_duration
        if not appointment_type.is_scheduled and data.get('end_datetime'):
            try:
                end_dt = datetime.strptime(data['end_datetime'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                end_dt = start_dt + timedelta(hours=appointment_type.slot_duration)
        else:
            end_dt = start_dt + timedelta(hours=appointment_type.slot_duration)

        # M8: Server-side max_booking_days validation
        max_date = fields.Date.today() + timedelta(days=appointment_type.max_booking_days)
        if start_dt.date() > max_date:
            return self._render_booking_form_error(
                appointment_type, data, _('Cannot book beyond %d days in advance.', appointment_type.max_booking_days))

        # Prevent booking in the past
        if start_dt < datetime.now():
            return self._render_booking_form_error(
                appointment_type, data, _('Cannot book a time slot in the past.'))

        # Safe int() casts for resource_id and staff_id (H3)
        resource_id = None
        if data.get('resource_id'):
            try:
                resource_id = int(data['resource_id'])
            except (ValueError, TypeError):
                resource_id = None

        staff_id = None
        if data.get('staff_id'):
            try:
                staff_id = int(data['staff_id'])
            except (ValueError, TypeError):
                staff_id = None

        # C4: Server-side slot conflict check before creating booking
        Booking = request.env['appointment.booking'].sudo()
        conflict = Booking._check_booking_conflict(
            start_dt=start_dt,
            end_dt=end_dt,
            staff_user_id=staff_id or False,
            resource_id=resource_id or False,
        )
        if conflict.get('staff_conflict'):
            return self._render_booking_form_error(
                appointment_type, data, _('This staff member is no longer available for the selected time. Please choose another time.'))
        if conflict.get('resource_conflict'):
            return self._render_booking_form_error(
                appointment_type, data, _('This location is no longer available for the selected time. Please choose another time.'))

        # M1: Basic rate limiting — max 5 bookings per email per hour
        one_hour_ago = fields.Datetime.now() - timedelta(hours=1)
        recent_count = Booking.search_count([
            ('guest_email', '=', email),
            ('create_date', '>=', one_hour_ago),
        ])
        if recent_count >= 5:
            return self._render_booking_form_error(
                appointment_type, data, _('Too many booking attempts. Please try again later.'))

        # Build booking values
        booking_vals = {
            'appointment_type_id': appointment_type.id,
            'guest_name': guest_name,
            'guest_phone': guest_phone,
            'guest_count': guest_count,
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'notes': (data.get('notes') or '')[:2000],  # L3: limit notes length
        }

        if resource_id:
            booking_vals['resource_id'] = resource_id
        if staff_id:
            booking_vals['staff_user_id'] = staff_id

        # M4: For logged-in users, always use partner email instead of form input
        if not request.env.user._is_public():
            partner = request.env.user.partner_id
            booking_vals['guest_email'] = partner.email or email
        else:
            booking_vals['guest_email'] = email
            partner = request.env['res.partner'].sudo().search([
                ('email', '=', email)
            ], limit=1)
            if not partner:
                partner = request.env['res.partner'].sudo().create({
                    'name': guest_name,
                    'email': email,
                    'phone': guest_phone,
                })
        booking_vals['partner_id'] = partner.id

        # Set payment status
        if appointment_type.require_payment:
            booking_vals['payment_status'] = 'pending'
            booking_vals['payment_amount'] = appointment_type.payment_amount
            if appointment_type.payment_per_person:
                booking_vals['payment_amount'] *= guest_count

        booking = Booking.create(booking_vals)

        # Auto-assign staff/location if not customer-chosen
        if appointment_type.assign_staff and not booking.staff_user_id:
            booking._auto_assign_staff()
        if appointment_type.assign_location and not booking.resource_id:
            booking._auto_assign_location()

        # Auto confirm if enabled and no payment required
        if appointment_type.auto_confirm and not appointment_type.require_payment:
            booking.action_confirm()
            # action_confirm already sends confirmation email
        else:
            # Send "booking created" email for:
            # 1. Payment-required bookings (draft + payment pending)
            # 2. Non-auto-confirm bookings (draft, awaiting manual confirmation)
            booking._send_booking_created_email()

        # Redirect to appropriate page
        if appointment_type.require_payment:
            # Create Sales Order and redirect to Odoo's native SO portal payment page
            sale_order = booking._create_sale_order()
            if sale_order:
                # Use access_token so public/anonymous users can view the SO portal page
                return request.redirect(
                    f'/my/orders/{sale_order.id}?access_token={sale_order.access_token}'
                )
            # SO creation failed — show error on booking form
            return self._render_booking_form_error(
                appointment_type, data,
                _('Payment configuration error. Please contact support.')
            )

        return request.redirect(f'/appointment/booking/{booking.id}/confirm?token={booking.access_token}')

    @http.route('/appointment/booking/<int:booking_id>/confirm', type='http', auth='public', website=True)
    def appointment_confirm(self, booking_id, token=None, **kwargs):
        """Display booking confirmation page"""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or not token or booking.access_token != token:
            return request.redirect('/appointment')

        return request.render('reservation_module.appointment_confirm_page', {
            'booking': booking,
            't': self._get_translations(),
        })

    @http.route('/appointment/booking/<int:booking_id>', type='http', auth='public', website=True)
    def appointment_booking_details(self, booking_id, token=None, **kwargs):
        """Display booking details"""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or not token or booking.access_token != token:
            return request.redirect('/appointment')

        return request.render('reservation_module.appointment_booking_page', {
            'booking': booking,
            't': self._get_translations(),
        })

    @http.route('/appointment/booking/<int:booking_id>/cancel', type='http', auth='public', website=True, methods=['GET', 'POST'])
    def appointment_cancel(self, booking_id, token=None, **kwargs):
        """Cancel a booking"""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or not token or booking.access_token != token:
            return request.redirect('/appointment')

        if request.httprequest.method == 'POST':
            try:
                booking.action_cancel()
                return request.render('reservation_module.appointment_cancelled_page', {
                    'booking': booking,
                    't': self._get_translations(),
                })
            except Exception as e:
                return request.render('reservation_module.appointment_booking_page', {
                    'booking': booking,
                    'error': str(e),
                    't': self._get_translations(),
                })

        return request.render('reservation_module.appointment_cancel_page', {
            'booking': booking,
            't': self._get_translations(),
        })

    def _render_payment_page(self, booking, error=None):
        """Render payment page with full payment context (reusable for error retries)"""
        # Get partner (create if needed)
        partner = booking.partner_id
        if not partner:
            partner = request.env['res.partner'].sudo().create({
                'name': booking.guest_name,
                'email': booking.guest_email,
                'phone': booking.guest_phone,
            })
            booking.partner_id = partner

        # Get payment context
        amount = booking.payment_amount
        currency = booking.currency_id
        company = request.env.company

        # Get compatible payment providers and methods
        availability_report = {}
        providers_sudo = request.env['payment.provider'].sudo()._get_compatible_providers(
            company.id,
            partner.id,
            amount,
            currency_id=currency.id,
            report=availability_report,
        )
        payment_methods_sudo = request.env['payment.method'].sudo()._get_compatible_payment_methods(
            providers_sudo.ids,
            partner.id,
            currency_id=currency.id,
            report=availability_report,
        )
        tokens_sudo = request.env['payment.token'].sudo()._get_available_tokens(
            providers_sudo.ids, partner.id
        )

        access_token = booking.access_token

        vals = {
            'booking': booking,
            'amount': amount,
            'currency': currency,
            'partner_id': partner.id,
            'providers_sudo': providers_sudo,
            'payment_methods_sudo': payment_methods_sudo,
            'tokens_sudo': tokens_sudo,
            'reference_prefix': f'APPT-{booking.id}',
            'transaction_route': f'/appointment/payment/transaction/{booking.id}',
            'landing_route': f'/appointment/payment/validate?booking_id={booking.id}&token={access_token}',
            'access_token': access_token,
            't': self._get_translations(),
        }
        if error:
            vals['error'] = error
        return request.render('reservation_module.appointment_payment_page', vals)

    @http.route('/appointment/booking/<int:booking_id>/pay', type='http', auth='public', website=True)
    def appointment_payment(self, booking_id, token=None, **kwargs):
        """Legacy payment page — redirects to SO portal if SO exists."""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or not token or booking.access_token != token:
            return request.redirect('/appointment')

        if booking.payment_status == 'paid':
            return request.redirect(f'/appointment/booking/{booking_id}/confirm?token={token}')

        # Redirect to SO portal payment page (Odoo standard e-commerce flow)
        if booking.sale_order_id:
            so = booking.sale_order_id
            return request.redirect(
                f'/my/orders/{so.id}?access_token={so.access_token}'
            )

        # No SO yet — try to create one now
        sale_order = booking._create_sale_order()
        if sale_order:
            return request.redirect(
                f'/my/orders/{sale_order.id}?access_token={sale_order.access_token}'
            )

        # Truly broken configuration — show error
        return request.render('reservation_module.appointment_payment_page', {
            'booking': booking,
            'error': _('Payment configuration error. Please contact support.'),
            't': self._get_translations(),
        })

    @http.route('/appointment/payment/transaction/<int:booking_id>', type='json', auth='public')
    def appointment_payment_transaction(self, booking_id, access_token=None, **kwargs):
        """Create payment transaction for appointment booking"""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists():
            return {'error': 'Booking not found'}

        # Validate access token
        if not access_token or booking.access_token != access_token:
            return {'error': 'Invalid access token'}

        # Get partner
        partner = booking.partner_id
        if not partner:
            return {'error': 'Partner not found'}

        # Create transaction using Odoo payment flow — only pass known safe kwargs
        tx_kwargs = {}
        for key in ('provider_id', 'payment_method_id', 'token_id', 'flow', 'tokenization_requested', 'landing_route'):
            if key in kwargs:
                tx_kwargs[key] = kwargs[key]

        tx_sudo = request.env['payment.transaction'].sudo()._create_transaction(
            amount=booking.payment_amount,
            currency_id=booking.currency_id.id,
            partner_id=partner.id,
            reference_prefix=f'APPT-{booking.id}',
            **tx_kwargs,
        )

        # Link transaction to booking
        tx_sudo.appointment_booking_id = booking.id
        booking.payment_transaction_id = tx_sudo.id

        # Render the payment processing template
        return tx_sudo._get_processing_values()

    @http.route('/appointment/payment/validate', type='http', auth='public', website=True)
    def appointment_payment_validate(self, booking_id=None, token=None, **kwargs):
        """Validate payment and redirect to confirmation page"""
        if not booking_id:
            return request.redirect('/appointment')

        try:
            booking_id = int(booking_id)
        except (ValueError, TypeError):
            return request.redirect('/appointment')

        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or not token or booking.access_token != token:
            return request.redirect('/appointment')

        # Check transaction status
        tx_sudo = booking.payment_transaction_id
        if tx_sudo and tx_sudo.state == 'done':
            # Payment successful
            return request.redirect(f'/appointment/booking/{booking.id}/confirm?token={token}')
        elif tx_sudo and tx_sudo.state in ('pending', 'authorized'):
            # Payment pending (e.g., wire transfer)
            return request.redirect(f'/appointment/booking/{booking.id}/confirm?token={token}&pending=1')
        else:
            # Payment failed or cancelled — re-render full payment page with error
            return self._render_payment_page(booking, error=_('Payment was not completed. Please try again.'))


class AppointmentPortal(CustomerPortal):
    """Portal controller for /my/bookings pages"""

    def _prepare_home_portal_values(self, counters):
        """Add booking count to the portal home page"""
        values = super()._prepare_home_portal_values(counters)
        if 'booking_count' in counters:
            partner = request.env.user.partner_id
            values['booking_count'] = request.env['appointment.booking'].sudo().search_count([
                ('partner_id', '=', partner.id),
                ('state', 'in', ['draft', 'confirmed', 'done']),
            ])
        return values

    @http.route(['/my/bookings', '/my/bookings/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_bookings(self, page=1, sortby=None, filterby=None, **kw):
        """Portal page listing user's bookings"""
        partner = request.env.user.partner_id
        BookingSudo = request.env['appointment.booking'].sudo()

        domain = [('partner_id', '=', partner.id)]

        # Sorting
        searchbar_sortings = {
            'date': {'label': _('Date'), 'order': 'start_datetime desc'},
            'name': {'label': _('Reference'), 'order': 'name desc'},
            'state': {'label': _('Status'), 'order': 'state asc'},
        }
        if not sortby or sortby not in searchbar_sortings:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        # Filtering
        now = fields.Datetime.now()
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': [('state', '!=', 'cancelled')]},
            'upcoming': {'label': _('Upcoming'), 'domain': [
                ('state', '=', 'confirmed'),
                ('start_datetime', '>=', now),
            ]},
            'completed': {'label': _('Completed'), 'domain': [
                ('state', '=', 'done'),
            ]},
            'cancelled': {'label': _('Cancelled'), 'domain': [
                ('state', '=', 'cancelled'),
            ]},
        }
        if not filterby or filterby not in searchbar_filters:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        # Count and pagination
        booking_count = BookingSudo.search_count(domain)
        pager_values = portal_pager(
            url="/my/bookings",
            total=booking_count,
            page=page,
            step=10,
            url_args={'sortby': sortby, 'filterby': filterby},
        )

        bookings = BookingSudo.search(
            domain, order=order, limit=10, offset=pager_values['offset']
        )

        # Get translations
        t = AppointmentController()._get_translations()

        values = {
            'bookings': bookings,
            'page_name': 'my_bookings',
            'pager': pager_values,
            'default_url': '/my/bookings',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': searchbar_filters,
            'filterby': filterby,
            't': t,
        }
        return request.render('reservation_module.portal_my_bookings', values)

    @http.route('/my/bookings/<int:booking_id>', type='http', auth='user', website=True)
    def portal_my_booking_detail(self, booking_id, **kw):
        """Portal page showing single booking details"""
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        partner = request.env.user.partner_id

        if not booking.exists() or booking.partner_id != partner:
            return request.redirect('/my/bookings')

        t = AppointmentController()._get_translations()

        values = {
            'booking': booking,
            'page_name': 'my_booking_detail',
            't': t,
        }
        return request.render('reservation_module.portal_my_booking_detail', values)
