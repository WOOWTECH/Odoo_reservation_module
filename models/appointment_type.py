# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import pytz


class AppointmentType(models.Model):
    _name = 'appointment.type'
    _description = 'Appointment Type'
    _order = 'sequence, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _default_timezone(self):
        return self.env.user.tz or 'UTC'

    name = fields.Char(
        '名稱',
        required=True,
        translate=True,
        tracking=True,
    )
    sequence = fields.Integer('順序', default=10)
    active = fields.Boolean('啟用', default=True, tracking=True)

    category = fields.Selection([
        ('meeting', '會議'),
        ('video_call', '視訊通話'),
        ('table', '桌位預訂'),
        ('resource', '資源預訂'),
        ('paid_consultation', '付費諮詢'),
        ('paid_seat', '付費座位'),
    ], string='類別', required=True, default='meeting', tracking=True)

    description = fields.Html('說明', translate=True)

    # Location Configuration
    location_type = fields.Selection([
        ('online', '線上會議'),
        ('physical', '實體地點'),
    ], string='地點類型', default='online')
    location_id = fields.Many2one(
        'res.partner',
        string='地點',
        help='預約的實體地點',
        ondelete='set null',
    )
    location_address = fields.Char(
        '地點地址',
        related='location_id.contact_address',
        readonly=True,
    )
    video_link = fields.Char(
        '視訊連結',
        help='視訊會議連結',
    )

    # Schedule Configuration
    schedule_type = fields.Selection([
        ('recurring', '每週循環'),
        ('custom', '自訂'),
    ], string='排程類型', default='recurring')
    schedule_based_on = fields.Selection([
        ('date', '日期'),
        ('user_resource', '使用者 / 資源'),
    ], string='開始依據', default='date',
        help='預約應基於什麼')

    # Assignment Configuration
    booking_type = fields.Selection([
        ('user', '使用者'),
        ('resource', '資源'),
    ], string='預約類型', default='user',
        help='預約是與使用者還是資源進行')
    assignment_method = fields.Selection([
        ('automatic', '自動'),
        ('customer', '客戶選擇'),
    ], string='分配方式', default='automatic',
        help='資源/員工如何分配給預約')

    # Capacity Configuration
    manage_capacity = fields.Boolean(
        '管理容量',
        help='啟用資源容量管理',
    )
    total_capacity = fields.Integer(
        '總容量',
        compute='_compute_total_capacity',
        store=True,
        help='所有資源的總容量',
    )
    max_concurrent_bookings = fields.Integer(
        '最大同時預約數',
        default=1,
        help='每位使用者的最大同時預約數',
    )

    # Resource/Staff Configuration
    resource_ids = fields.Many2many(
        'resource.resource',
        'appointment_type_resource_rel',
        'appointment_type_id',
        'resource_id',
        string='資源',
        help='此預約類型可用的資源',
    )
    staff_user_ids = fields.Many2many(
        'res.users',
        'appointment_type_user_rel',
        'appointment_type_id',
        'user_id',
        string='服務人員',
        help='此預約類型可用的服務人員',
    )

    # Time Configuration
    slot_duration = fields.Float(
        '時段長度（小時）',
        default=1.0,
        required=True,
        help='每個預約時段的持續時間（小時）',
    )
    slot_interval = fields.Float(
        '時段間隔（小時）',
        default=1.0,
        help='可用時段之間的時間間隔',
    )

    # Booking Restrictions
    max_booking_days = fields.Integer(
        '最大預約天數',
        default=30,
        help='可以提前多少天預約',
    )
    min_booking_hours = fields.Float(
        '最短提前預約時間（小時）',
        default=1.0,
        help='允許預約的最短提前時間（小時）',
    )
    cancel_before_hours = fields.Float(
        '取消截止時間（小時）',
        default=1.0,
        help='允許取消的截止時間（開始前幾小時）',
    )

    # Auto Confirmation
    auto_confirm = fields.Boolean(
        '自動確認',
        default=True,
        help='自動確認預約',
    )
    auto_confirm_capacity_percent = fields.Integer(
        '自動確認容量（%）',
        default=100,
        help='達到此容量百分比前自動確認',
    )

    # Payment Configuration
    require_payment = fields.Boolean(
        '需要付款',
        help='確認預約前需要付款',
    )
    payment_product_id = fields.Many2one(
        'product.product',
        string='付款產品',
        help='用於付款的產品',
        ondelete='set null',
    )
    payment_amount = fields.Monetary(
        '付款金額',
        help='預約需支付的金額',
    )
    payment_per_person = fields.Boolean(
        '按人數收費',
        help='按人數收費而非按預約收費',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='貨幣',
        default=lambda self: self.env.company.currency_id,
    )

    # Display Settings
    show_image = fields.Boolean('顯示圖片')
    image = fields.Binary('圖片', attachment=True)
    image_url = fields.Char('圖片網址')
    icon = fields.Char('圖示', default='fa-calendar')

    # Timezone
    timezone = fields.Selection(
        '_tz_get',
        string='時區',
        default=_default_timezone,
        required=True,
    )

    # Allow Invitations
    allow_invitations = fields.Boolean(
        '允許邀請',
        help='允許預約者邀請其他人',
    )

    # Communication Settings
    introduction_page = fields.Html(
        '簡介頁面',
        translate=True,
        help='預約頁面上顯示的內容',
    )
    confirmation_page = fields.Html(
        '確認頁面',
        translate=True,
        help='預約確認後顯示的內容',
    )

    # Availability
    availability_ids = fields.One2many(
        'appointment.availability',
        'appointment_type_id',
        string='可用時段',
    )

    # Questions
    question_ids = fields.One2many(
        'appointment.question',
        'appointment_type_id',
        string='問題',
    )

    # Bookings
    booking_ids = fields.One2many(
        'appointment.booking',
        'appointment_type_id',
        string='預約',
    )
    booking_count = fields.Integer(
        '預約數',
        compute='_compute_booking_count',
    )
    upcoming_booking_count = fields.Integer(
        '即將到來的預約',
        compute='_compute_booking_count',
    )

    # Website
    is_published = fields.Boolean('已發布', default=True)
    website_url = fields.Char('網站網址', compute='_compute_website_url')

    @api.model
    def _tz_get(self):
        return [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]

    @api.depends('resource_ids', 'resource_ids.capacity')
    def _compute_total_capacity(self):
        for record in self:
            if record.manage_capacity and record.resource_ids:
                record.total_capacity = sum(record.resource_ids.mapped('capacity'))
            else:
                record.total_capacity = 0

    @api.depends('booking_ids', 'booking_ids.state', 'booking_ids.start_datetime')
    def _compute_booking_count(self):
        now = fields.Datetime.now()
        for record in self:
            bookings = record.booking_ids.filtered(lambda b: b.state not in ['cancelled'])
            record.booking_count = len(bookings)
            record.upcoming_booking_count = len(bookings.filtered(lambda b: b.start_datetime > now))

    def _compute_website_url(self):
        for record in self:
            if record.id:
                record.website_url = f'/appointment/{record.id}'
            else:
                record.website_url = False

    @api.constrains('slot_duration')
    def _check_slot_duration(self):
        for record in self:
            if record.slot_duration <= 0:
                raise ValidationError(_('Slot duration must be greater than 0.'))

    @api.constrains('max_booking_days')
    def _check_max_booking_days(self):
        for record in self:
            if record.max_booking_days < 1:
                raise ValidationError(_('Maximum booking days must be at least 1.'))

    @api.constrains('auto_confirm_capacity_percent')
    def _check_auto_confirm_capacity(self):
        for record in self:
            if record.auto_confirm_capacity_percent < 0 or record.auto_confirm_capacity_percent > 100:
                raise ValidationError(_('Auto confirm capacity must be between 0 and 100.'))

    def action_view_bookings(self):
        """Open bookings for this appointment type"""
        self.ensure_one()
        return {
            'name': _('Bookings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.booking',
            'view_mode': 'list,form,calendar',
            'domain': [('appointment_type_id', '=', self.id)],
            'context': {'default_appointment_type_id': self.id},
        }

    def action_share(self):
        """Share appointment booking link"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return {
            'type': 'ir.actions.act_url',
            'url': f'{base_url}/appointment/{self.id}',
            'target': 'new',
        }

    def action_open_settings(self):
        """Open appointment type settings"""
        self.ensure_one()
        return {
            'name': _('Settings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.type',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_view_resource_bookings(self):
        """Open resource bookings reservation view"""
        self.ensure_one()
        return {
            'name': _('Resource Bookings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.booking',
            'view_mode': 'calendar,list,form',
            'domain': [('appointment_type_id', '=', self.id), ('resource_id', '!=', False)],
            'context': {
                'default_appointment_type_id': self.id,
                'search_default_groupby_resource': 1,
            },
        }

    def action_view_staff_bookings(self):
        """Open staff bookings reservation view"""
        self.ensure_one()
        return {
            'name': _('Staff Bookings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.booking',
            'view_mode': 'calendar,list,form',
            'domain': [('appointment_type_id', '=', self.id), ('staff_user_id', '!=', False)],
            'context': {
                'default_appointment_type_id': self.id,
                'search_default_groupby_staff': 1,
            },
        }

    def action_add_closing_days(self):
        """Open wizard to add closing days"""
        self.ensure_one()
        return {
            'name': _('Add Closing Days'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.closing.day.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_appointment_type_id': self.id,
            },
        }

    @api.model
    def get_appointment_type_presets(self):
        """Return appointment type presets for selection dialog"""
        return [
            {
                'category': 'meeting',
                'name': _('Meeting'),
                'description': _('Allow others to book meetings in your reservation'),
                'icon': 'fa-user',
            },
            {
                'category': 'video_call',
                'name': _('Video Call'),
                'description': _('Schedule video meetings with one or more participants'),
                'icon': 'fa-video-camera',
            },
            {
                'category': 'table',
                'name': _('Table Booking'),
                'description': _('Let customers book tables at your restaurant or bar'),
                'icon': 'fa-cutlery',
            },
            {
                'category': 'resource',
                'name': _('Book a Resource'),
                'description': _('Allow customers to book resources like rooms, tennis courts, etc.'),
                'icon': 'fa-clock-o',
            },
            {
                'category': 'paid_consultation',
                'name': _('Paid Consultation'),
                'description': _('Let customers book a paid slot in your reservation'),
                'icon': 'fa-dollar',
            },
            {
                'category': 'paid_seat',
                'name': _('Paid Seats'),
                'description': _('Let customers book a fee per person for activities'),
                'icon': 'fa-chair',
            },
        ]
