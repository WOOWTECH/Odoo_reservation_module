# -*- coding: utf-8 -*-
"""純 Python 時區轉換測試（不需要 Odoo runtime）。

這一支釘住 18.0.3.0.0 UTC 儲存改造的核心算術。它只依賴 pytz，
所以可以直接跑：

    python -m pytest reservation_module/tests/test_timezone_pure.py

同一支檔案也會被 Odoo 的 test loader 殬kup到（unittest.TestCase），
在 `-u reservation_module --test-enable` 時一併執行。
"""

import importlib.util
import os
import sys
import unittest
from datetime import date, datetime, timedelta

import pytz


def _load_tz_utils():
    """載入 ../tz_utils.py。

    在 Odoo 裡跑時走正常的套件相對匯入；用純 pytest 跑時 odoo.addons
    根本不存在，改用檔案路徑直接載入——tz_utils 沒有任何 Odoo 相依，
    所以這樣載入是安全的。
    """
    try:
        from odoo.addons.reservation_module import tz_utils  # noqa: WPS433
        return tz_utils
    except ImportError:
        pass

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tz_utils.py')
    spec = importlib.util.spec_from_file_location('reservation_module_tz_utils', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tz_utils = _load_tz_utils()

TAIPEI = pytz.timezone('Asia/Taipei')
UTC = pytz.UTC


class TestLocalToUtc(unittest.TestCase):
    """本地牆上時間 -> 儲存用的 naive UTC。"""

    def test_taipei_10am_is_2am_utc(self):
        self.assertEqual(
            tz_utils.local_to_utc(TAIPEI, datetime(2026, 8, 29, 10, 0, 0)),
            datetime(2026, 8, 29, 2, 0, 0),
        )

    def test_result_is_naive(self):
        """存進 Datetime 欄位的值必須是 naive，帶 tzinfo 會被 ORM 拒絕。"""
        self.assertIsNone(
            tz_utils.local_to_utc(TAIPEI, datetime(2026, 8, 29, 10, 0, 0)).tzinfo
        )

    def test_midnight_crosses_to_previous_utc_day(self):
        """台北 00:30 是前一天的 UTC 16:30。"""
        self.assertEqual(
            tz_utils.local_to_utc(TAIPEI, datetime(2026, 8, 29, 0, 30, 0)),
            datetime(2026, 8, 28, 16, 30, 0),
        )

    def test_half_hour_zone(self):
        """半小時偏移的時區（India +05:30）也要正確。"""
        kolkata = pytz.timezone('Asia/Kolkata')
        self.assertEqual(
            tz_utils.local_to_utc(kolkata, datetime(2026, 8, 29, 10, 0, 0)),
            datetime(2026, 8, 29, 4, 30, 0),
        )

    def test_dst_zone_uses_offset_of_the_day(self):
        """有 DST 的時區：同一個牆上時間，夏令與冬令要換出不同 UTC。"""
        nyc = pytz.timezone('America/New_York')
        summer = tz_utils.local_to_utc(nyc, datetime(2026, 7, 1, 12, 0, 0))
        winter = tz_utils.local_to_utc(nyc, datetime(2026, 1, 1, 12, 0, 0))
        self.assertEqual(summer, datetime(2026, 7, 1, 16, 0, 0))  # EDT -4
        self.assertEqual(winter, datetime(2026, 1, 1, 17, 0, 0))  # EST -5


class TestUtcToLocal(unittest.TestCase):
    """儲存用的 naive UTC -> 顯示用的本地牆上時間。"""

    def test_2am_utc_is_taipei_10am(self):
        self.assertEqual(
            tz_utils.utc_to_local(TAIPEI, datetime(2026, 8, 29, 2, 0, 0)),
            datetime(2026, 8, 29, 10, 0, 0),
        )

    def test_round_trip(self):
        """local -> UTC -> local 必須回到原值。"""
        for wall in (
            datetime(2026, 1, 1, 0, 0, 0),
            datetime(2026, 8, 29, 10, 0, 0),
            datetime(2026, 12, 31, 23, 59, 0),
        ):
            self.assertEqual(
                tz_utils.utc_to_local(TAIPEI, tz_utils.local_to_utc(TAIPEI, wall)),
                wall,
            )

    def test_local_date_differs_from_utc_date(self):
        """UTC 23:00 在台北已經是隔天 07:00——後台日期篩選就是栽在這裡。"""
        local = tz_utils.utc_to_local(TAIPEI, datetime(2026, 8, 31, 23, 0, 0))
        self.assertEqual(local.date(), date(2026, 9, 1))


class TestLocalizeVsReplace(unittest.TestCase):
    """tz.localize() 與 .replace(tzinfo=tz) 的差異（LMT 陷阱）。"""

    def test_replace_tzinfo_yields_lmt_offset(self):
        """.replace(tzinfo=) 會拿到 Asia/Taipei 的歷史 LMT 偏移 +08:06。"""
        wrong = datetime(2026, 8, 29, 10, 0, 0).replace(tzinfo=TAIPEI)
        self.assertEqual(wrong.utcoffset(), timedelta(hours=8, minutes=6))

    def test_localize_yields_modern_offset(self):
        right = TAIPEI.localize(datetime(2026, 8, 29, 10, 0, 0))
        self.assertEqual(right.utcoffset(), timedelta(hours=8))

    def test_helper_does_not_use_lmt(self):
        """轉換後的 UTC 值不可以出現 LMT 造成的 6 分鐘殘留。"""
        result = tz_utils.local_to_utc(TAIPEI, datetime(2026, 8, 29, 10, 0, 0))
        self.assertEqual(result.minute, 0)
        self.assertNotEqual(result, datetime(2026, 8, 29, 1, 54, 0))


class TestHourToLocalDt(unittest.TestCase):
    """availability 的 Float 小時 -> 本地 datetime。"""

    def setUp(self):
        self.day_start = datetime(2026, 8, 29, 0, 0, 0)

    def test_whole_hour(self):
        self.assertEqual(
            tz_utils.hour_to_local_dt(self.day_start, 8.0),
            datetime(2026, 8, 29, 8, 0, 0),
        )

    def test_half_hour(self):
        self.assertEqual(
            tz_utils.hour_to_local_dt(self.day_start, 17.5),
            datetime(2026, 8, 29, 17, 30, 0),
        )

    def test_hour_24_is_next_midnight(self):
        """hour_to == 24.0 必須是隔天 00:00（舊的 .replace(hour=24) 會直接爆掉）。"""
        self.assertEqual(
            tz_utils.hour_to_local_dt(self.day_start, 24.0),
            datetime(2026, 8, 30, 0, 0, 0),
        )


class TestSlotGenerationOverlap(unittest.TestCase):
    """以 UTC 為基準做 overlap 比對：重複時段必須被擋下。"""

    def _generate_slots(self, day, hour_from, hour_to, duration_h, bookings_utc):
        """複刻 _get_scheduled_slots 的核心：本地端遞增、UTC 端比對。"""
        day_start_local = datetime.combine(day, datetime.min.time())
        current_local = tz_utils.hour_to_local_dt(day_start_local, hour_from)
        end_local = tz_utils.hour_to_local_dt(day_start_local, hour_to)
        duration = timedelta(hours=duration_h)

        slots = []
        while current_local + duration <= end_local:
            slot_end_local = current_local + duration
            current_utc = tz_utils.local_to_utc(TAIPEI, current_local)
            slot_end_utc = tz_utils.local_to_utc(TAIPEI, slot_end_local)
            taken = any(
                b_start < slot_end_utc and b_end > current_utc
                for b_start, b_end in bookings_utc
            )
            if not taken:
                slots.append({
                    'start': current_utc.strftime('%Y-%m-%d %H:%M:%S'),
                    'start_time': current_local.strftime('%H:%M'),
                })
            current_local += duration
        return slots

    def test_wire_format_is_utc_display_is_local(self):
        slots = self._generate_slots(date(2026, 8, 29), 8.0, 12.0, 1.0, [])
        self.assertEqual([s['start_time'] for s in slots],
                         ['08:00', '09:00', '10:00', '11:00'])
        self.assertEqual(slots[0]['start'], '2026-08-29 00:00:00')
        self.assertEqual(slots[-1]['start'], '2026-08-29 03:00:00')

    def test_existing_utc_booking_removes_that_slot(self):
        """DB 裡存的是 UTC 02:00，要擋掉顯示為台北 10:00 的那一格。"""
        booking = (datetime(2026, 8, 29, 2, 0, 0), datetime(2026, 8, 29, 3, 0, 0))
        slots = self._generate_slots(date(2026, 8, 29), 8.0, 12.0, 1.0, [booking])
        start_times = [s['start_time'] for s in slots]
        self.assertNotIn('10:00', start_times)
        self.assertEqual(start_times, ['08:00', '09:00', '11:00'])

    def test_wall_time_booking_would_block_the_wrong_slot(self):
        """對照組：若沿用舊的牆上時間儲存（10:00），擋掉的會是錯的那一格。

        這正是改造前的行為——擋掉台北 18:00，真正被預約的 10:00 仍可重複預約。
        """
        stale = (datetime(2026, 8, 29, 10, 0, 0), datetime(2026, 8, 29, 11, 0, 0))
        slots = self._generate_slots(date(2026, 8, 29), 8.0, 20.0, 1.0, [stale])
        start_times = [s['start_time'] for s in slots]
        self.assertIn('10:00', start_times)   # 真正該擋的沒擋到
        self.assertNotIn('18:00', start_times)  # 擋錯了別格


class TestLocalMonthBounds(unittest.TestCase):
    """本地月份邊界（自動指派的當月統計用）。"""

    def test_bounds_are_local_month_expressed_in_utc(self):
        start, end = tz_utils.local_month_bounds_utc(
            TAIPEI, datetime(2026, 8, 15, 2, 0, 0))
        # 台北 2026-08-01 00:00 == UTC 2026-07-31 16:00
        self.assertEqual(start, datetime(2026, 7, 31, 16, 0, 0))
        self.assertEqual(end, datetime(2026, 8, 31, 16, 0, 0))

    def test_december_rolls_over_to_next_year(self):
        start, end = tz_utils.local_month_bounds_utc(
            TAIPEI, datetime(2026, 12, 15, 2, 0, 0))
        self.assertEqual(start, datetime(2026, 11, 30, 16, 0, 0))
        self.assertEqual(end, datetime(2026, 12, 31, 16, 0, 0))

    def test_first_local_day_lands_in_the_right_month(self):
        """台北 9/1 07:00（UTC 8/31 23:00）必須算進 9 月，不能算進 8 月。"""
        booking_utc = datetime(2026, 8, 31, 23, 0, 0)
        start, end = tz_utils.local_month_bounds_utc(TAIPEI, booking_utc)
        self.assertLessEqual(start, booking_utc)
        self.assertLess(booking_utc, end)
        self.assertEqual(start, datetime(2026, 8, 31, 16, 0, 0))  # = 台北 9/1 00:00


class TestGetTz(unittest.TestCase):

    def test_known_zone(self):
        self.assertEqual(str(tz_utils.get_tz('Asia/Taipei')), 'Asia/Taipei')

    def test_empty_falls_back_to_utc(self):
        self.assertEqual(tz_utils.get_tz(''), pytz.UTC)
        self.assertEqual(tz_utils.get_tz(False), pytz.UTC)

    def test_unknown_zone_falls_back_to_utc(self):
        self.assertEqual(tz_utils.get_tz('Mars/Olympus_Mons'), pytz.UTC)


class TestMigrationArithmetic(unittest.TestCase):
    """驗證 18.0.3.0.0 遷移的換算方向與 SQL AT TIME ZONE 語意一致。

    SQL:
        (start_datetime AT TIME ZONE 'Asia/Taipei') AT TIME ZONE 'UTC'

    第一個 AT TIME ZONE 把 naive timestamp 解讀成該時區的時間、回傳
    timestamptz；第二個把它投影回 naive UTC。等價於 local_to_utc()。
    """

    def test_migration_shifts_wall_time_to_utc(self):
        stored_before = datetime(2026, 8, 29, 12, 0, 0)  # 舊：台北牆上 12:00
        stored_after = tz_utils.local_to_utc(TAIPEI, stored_before)
        self.assertEqual(stored_after, datetime(2026, 8, 29, 4, 0, 0))

    def test_migrated_value_displays_as_the_original_wall_time(self):
        """遷移後再依 display tz 顯示，使用者看到的時間必須不變。"""
        stored_before = datetime(2026, 8, 29, 12, 0, 0)
        stored_after = tz_utils.local_to_utc(TAIPEI, stored_before)
        self.assertEqual(tz_utils.utc_to_local(TAIPEI, stored_after), stored_before)

    def test_migration_is_not_idempotent(self):
        """跑第二次會再減 8 小時——所以 post-migrate 才需要 ir_config_parameter 旗標。"""
        once = tz_utils.local_to_utc(TAIPEI, datetime(2026, 8, 29, 12, 0, 0))
        twice = tz_utils.local_to_utc(TAIPEI, once)
        self.assertEqual(twice, datetime(2026, 8, 28, 20, 0, 0))
        self.assertNotEqual(once, twice)


if __name__ == '__main__':
    unittest.main()
