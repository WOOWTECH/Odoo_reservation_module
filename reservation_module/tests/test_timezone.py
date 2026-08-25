# -*- coding: utf-8 -*-
"""時區契約測試（18.0.3.0.0 起）。

儲存契約：appointment.booking.start_datetime / end_datetime 一律是
naive UTC；appointment.availability.hour_from / hour_to 則是
appointment_type.timezone 的牆上小時。這裡把兩者的邊界釘死：

  * DB 存的是 UTC（台北 10:00 -> 02:00）
  * /slots API 回傳 UTC 的 start、當地時間的 start_time
  * 已確認的預約會讓同一時段從可預約清單消失（防重複）
  * min_booking_hours 以 UTC now 為基準，正確擋掉近期時段
"""

import re
from datetime import date, datetime, timedelta

import pytz

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged

try:
    from freezegun import freeze_time
except ImportError:  # pragma: no cover - freezegun ships with Odoo's test deps
    freeze_time = None

TAIPEI = pytz.timezone('Asia/Taipei')


class TimezoneCommon:
    """共用的測試資料：Asia/Taipei、每天 08:00-17:00、一小時一格。"""

    def _setup_appointment_type(self, **overrides):
        vals = {
            'name': 'TZ Test Appointment',
            'timezone': 'Asia/Taipei',
            'slot_duration': 1.0,
            'slot_interval': 1.0,
            'min_booking_hours': 0,
            'max_booking_days': 60,
            'is_scheduled': True,
            'location_type': 'physical',
            'assign_staff': False,
            'assign_location': False,
            'auto_confirm': True,
            'require_payment': False,
            'is_published': True,
        }
        vals.update(overrides)
        appointment_type = self.env['appointment.type'].create(vals)
        # 每個星期幾都開，測試就不必在意當天是星期幾
        self.env['appointment.availability'].create([{
            'appointment_type_id': appointment_type.id,
            'dayofweek': str(day),
            'hour_from': 8.0,
            'hour_to': 17.0,
        } for day in range(7)])
        return appointment_type

    @staticmethod
    def _taipei_wall_to_utc(wall):
        """台北牆上時間 -> naive UTC，測試裡的期望值都由此產生。"""
        return TAIPEI.localize(wall).astimezone(pytz.utc).replace(tzinfo=None)


@tagged('post_install', '-at_install')
class TestTimezoneStorage(TimezoneCommon, TransactionCase):
    """模型層：儲存基準、防重複、行事曆匯出。"""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._setup_appointment_type()

    def _create_booking(self, wall_start, hours=1, state='confirmed', **extra):
        """以台北牆上時間建立預約（內部換算成 UTC 才寫進 DB）。"""
        start_utc = self._taipei_wall_to_utc(wall_start)
        vals = {
            'appointment_type_id': self.appointment_type.id,
            'guest_name': 'TZ Guest',
            'guest_email': 'tz@example.com',
            'start_datetime': start_utc,
            'end_datetime': start_utc + timedelta(hours=hours),
            'state': state,
        }
        vals.update(extra)
        return self.env['appointment.booking'].create(vals)

    def test_storage_is_utc(self):
        """台北 10:00 的預約，DB 必須存 02:00（而不是 10:00）。"""
        booking = self._create_booking(datetime(2026, 8, 31, 10, 0, 0))
        self.assertEqual(
            booking.start_datetime,
            datetime(2026, 8, 31, 2, 0, 0),
            '台北 10:00 應存成 UTC 02:00',
        )
        self.assertEqual(booking.end_datetime, datetime(2026, 8, 31, 3, 0, 0))

    def test_start_date_local_uses_local_day(self):
        """start_date_local 取當地日期：台北 07:00 在 UTC 是前一天 23:00。"""
        booking = self._create_booking(datetime(2026, 9, 1, 7, 0, 0))
        self.assertEqual(booking.start_datetime, datetime(2026, 8, 31, 23, 0, 0))
        self.assertEqual(
            booking.start_date_local,
            date(2026, 9, 1),
            'start_date_local 必須是當地日期，不能跟著 UTC 退回前一天',
        )

    def test_is_one_local_day_across_utc_midnight(self):
        """跨 UTC 午夜但同一個當地日，仍應視為同一天。"""
        booking = self._create_booking(datetime(2026, 9, 1, 7, 0, 0), hours=2)
        self.assertTrue(booking.is_one_local_day)

    def test_overlap_blocks_duplicate(self):
        """同一資源、同一時段的第二筆預約會被 _check_booking_conflict 擋下。"""
        resource = self.env['resource.resource'].create({
            'name': 'TZ Room',
            'resource_type': 'material',
        })
        start_utc = self._taipei_wall_to_utc(datetime(2026, 8, 31, 10, 0, 0))
        self._create_booking(
            datetime(2026, 8, 31, 10, 0, 0),
            resource_id=resource.id,
            guest_count=resource.capacity or 1,
        )
        conflict = self.env['appointment.booking']._check_booking_conflict(
            start_dt=start_utc,
            end_dt=start_utc + timedelta(hours=1),
            resource_id=resource.id,
        )
        self.assertTrue(
            conflict['resource_conflict'],
            '同一 UTC 時段的重複預約必須被偵測到',
        )

    def test_calendar_export_uses_local_wall_time(self):
        """Google / .ics 匯出的是當地牆上時間，不是把 UTC 值再加一次時差。"""
        booking = self._create_booking(datetime(2026, 8, 31, 10, 0, 0))
        google_url = booking._get_calendar_urls()['google_url']
        self.assertIn('20260831T100000', google_url,
                      'Google 行事曆連結應帶當地 10:00')
        self.assertIn('20260831T110000', google_url)
        # 舊 bug：對 naive 值呼叫 .astimezone() 會把 UTC 02:00 當成本地時間再 +8
        self.assertNotIn('20260831T180000', google_url)
        self.assertIn('ctz=Asia%2FTaipei', google_url)

    def test_display_tz_prefers_appointment_type(self):
        """display_tz 以預約類型時區為首選，公開使用者沒有 tz 也不會掉回 UTC。"""
        booking = self._create_booking(datetime(2026, 8, 31, 10, 0, 0))
        self.assertEqual(booking.display_tz, 'Asia/Taipei')

    def test_cancel_deadline_uses_utc_now(self):
        """取消截止時間以 UTC now 比對，不會被時差多放行 8 小時。"""
        self.appointment_type.cancel_before_hours = 1.0
        # 距離現在僅 30 分鐘的預約 -> 已過截止時間
        soon_utc = fields.Datetime.now() + timedelta(minutes=30)
        soon_wall = pytz.utc.localize(soon_utc).astimezone(TAIPEI).replace(tzinfo=None)
        booking = self._create_booking(soon_wall)
        with self.assertRaises(UserError):
            booking.action_cancel()


@tagged('post_install', '-at_install')
class TestTimezoneSlotsRoute(TimezoneCommon, HttpCase):
    """/slots JSON 路由：wire format 與 min_booking_hours。"""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._setup_appointment_type()

    def _slots(self, day, **params):
        payload = {'date': day.strftime('%Y-%m-%d')}
        payload.update(params)
        result = self.make_jsonrpc_request(
            '/appointment/%d/slots' % self.appointment_type.id, payload
        )
        return result.get('slots', [])

    def test_wire_format_is_utc_start_local_start_time(self):
        """start 是 UTC 字串、start_time 是當地字串，兩者相差 8 小時。"""
        if freeze_time is None:
            self.skipTest('freezegun not available')
        # 台北 2026-09-14 08:00 == UTC 00:00，所以當天所有時段都還沒過
        with freeze_time('2026-09-14 00:00:00'):
            slots = self._slots(date(2026, 9, 14))

        self.assertTrue(slots, '應該產生時段')
        first = slots[0]
        self.assertEqual(first['start_time'], '08:00', '顯示用時間是台北 08:00')
        self.assertEqual(
            first['start'], '2026-09-14 00:00:00',
            'wire format 必須是 UTC（台北 08:00 = UTC 00:00）',
        )
        self.assertEqual(first['end_time'], '09:00')
        self.assertEqual(first['end'], '2026-09-14 01:00:00')
        # 08:00~16:00 共 9 個起點（最後一格 16:00-17:00）
        self.assertEqual(len(slots), 9)

    def test_min_booking_hours_filters_near_slots(self):
        """min_booking_hours=4：台北 08:00 當下，12:00 之前的時段全部消失。"""
        if freeze_time is None:
            self.skipTest('freezegun not available')
        self.appointment_type.min_booking_hours = 4.0

        with freeze_time('2026-09-14 00:00:00'):  # 台北 08:00
            slots = self._slots(date(2026, 9, 14))

        self.assertTrue(slots)
        start_times = [s['start_time'] for s in slots]
        self.assertEqual(
            start_times[0], '12:00',
            '4 小時提前門檻應從台北 12:00 起算，而不是被時差吃掉',
        )
        for early in ('08:00', '09:00', '10:00', '11:00'):
            self.assertNotIn(early, start_times)
        self.assertEqual(slots[0]['start'], '2026-09-14 04:00:00')

    def test_confirmed_booking_removes_slot(self):
        """已確認的預約會讓同一時段從可預約清單消失（防重複）。"""
        if freeze_time is None:
            self.skipTest('freezegun not available')
        staff = self.env['res.users'].create({
            'name': 'TZ Staff',
            'login': 'tz_staff_%s' % self.appointment_type.id,
            'email': 'tz_staff@example.com',
        })
        self.appointment_type.write({
            'assign_staff': True,
            'staff_user_ids': [(6, 0, staff.ids)],
        })
        start_utc = self._taipei_wall_to_utc(datetime(2026, 9, 14, 10, 0, 0))
        self.env['appointment.booking'].create({
            'appointment_type_id': self.appointment_type.id,
            'guest_name': 'Existing',
            'guest_email': 'existing@example.com',
            'staff_user_id': staff.id,
            'start_datetime': start_utc,
            'end_datetime': start_utc + timedelta(hours=1),
            'state': 'confirmed',
        })

        with freeze_time('2026-09-14 00:00:00'):
            slots = self._slots(date(2026, 9, 14), staff_id=staff.id)

        start_times = [s['start_time'] for s in slots]
        self.assertTrue(start_times, '其他時段應仍可預約')
        self.assertNotIn(
            '10:00', start_times,
            '台北 10:00 已被佔用（DB 存 02:00 UTC），必須從清單移除',
        )
        self.assertIn('11:00', start_times)


@tagged('post_install', '-at_install')
class TestTimezoneBookingFlow(TimezoneCommon, HttpCase):
    """端到端：從前台表單送出的預約，DB 必須落在 UTC。"""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._setup_appointment_type()

    def test_frontend_post_stores_utc(self):
        if freeze_time is None:
            self.skipTest('freezegun not available')

        # wire format 是 UTC：台北 2026-09-14 14:00 -> UTC 06:00
        start_utc = '2026-09-14 06:00:00'
        end_utc = '2026-09-14 07:00:00'
        book_url = '/appointment/%d/book' % self.appointment_type.id

        with freeze_time('2026-09-14 00:00:00'):
            page = self.url_open(
                '%s?start_datetime=%s&end_datetime=%s' % (
                    book_url, start_utc.replace(' ', '%20'), end_utc.replace(' ', '%20'),
                )
            )
            self.assertEqual(page.status_code, 200)
            match = re.search(
                r'name="csrf_token"[^>]*value="([^"]+)"', page.text
            ) or re.search(
                r'value="([^"]+)"[^>]*name="csrf_token"', page.text
            )
            self.assertTrue(match, '預約表單應含 csrf_token')

            response = self.url_open(book_url, data={
                'csrf_token': match.group(1),
                'start_datetime': start_utc,
                'end_datetime': end_utc,
                'guest_name': 'Wire Format Guest',
                'guest_email': 'wire@example.com',
                'guest_count': '1',
            })
            self.assertEqual(response.status_code, 200)

        booking = self.env['appointment.booking'].search(
            [('guest_email', '=', 'wire@example.com')], limit=1)
        self.assertTrue(booking, '預約應建立成功')
        self.assertEqual(
            booking.start_datetime, datetime(2026, 9, 14, 6, 0, 0),
            'DB 必須存 UTC 06:00（= 台北 14:00），不能存 14:00',
        )
        self.assertEqual(booking.start_date_local, date(2026, 9, 14))
