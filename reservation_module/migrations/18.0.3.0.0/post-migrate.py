# -*- coding: utf-8 -*-
"""18.0.3.0.0 — 把預約時間從「牆上時間」改存標準 UTC。

3.0.0 之前，appointment.booking.start_datetime / end_datetime 存的是
appointment_type.timezone 的牆上時間（例如台北 10:00 就直接存 10:00），
而不是 Odoo 慣例的 naive UTC。本腳本把既有資料一次性換算成 UTC：

    (start_datetime AT TIME ZONE <type tz>) AT TIME ZONE 'UTC'

Postgres 語意：第一個 AT TIME ZONE 把 timestamp 視為該時區的時間並回傳
timestamptz，第二個再轉回 naive UTC。台北無日光節約，但寫成通用式，
其他時區（含歷史 DST 規則）也會被正確處理。

同時處理：
  * 由預約建立的 calendar.event（_create_calendar_event 直接把牆上時間
    寫進 Odoo 核心模型，同樣被污染）
  * appointment_slot（已 deprecated，有資料才處理）
  * start_date_local（3.0.0 新增的預存欄位，ORM 會在本腳本之前用「換算前」
    的值算好，必須在位移之後重算）

冪等保護：完成後寫入 ir_config_parameter 旗標，重跑會直接跳過——這點很重要，
重複執行會再減 8 小時。
"""

import logging

_logger = logging.getLogger(__name__)

FLAG = 'reservation_module.utc_storage_migrated'


def _already_migrated(cr):
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (FLAG,))
    row = cr.fetchone()
    return bool(row and row[0])


def _mark_migrated(cr, version):
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date)
        VALUES (%s, %s, 1, 1, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = EXCLUDED.write_date
        """,
        (FLAG, version or '18.0.3.0.0'),
    )


def _check_timezones(cr):
    """所有 appointment_type.timezone 必須是 Postgres 認得的時區名稱。

    換算的正確性完全建立在這個欄位上；有任何一筆是空的或拼錯，
    寧可中止整個升級，也不要產生一批偏移錯誤且無法分辨的資料。
    """
    cr.execute("SELECT id, name, timezone FROM appointment_type")
    rows = cr.fetchall()
    if not rows:
        return

    cr.execute("SELECT name FROM pg_timezone_names")
    known = {r[0] for r in cr.fetchall()}

    bad = [(r[0], r[1], r[2]) for r in rows if not r[2] or r[2] not in known]
    if bad:
        raise ValueError(
            "reservation_module 18.0.3.0.0 migration aborted: appointment_type "
            "records with a missing or unknown timezone: %s. Fix the Timezone "
            "field on those records, then re-run the update." % (bad,)
        )

    for type_id, name, tz in rows:
        _logger.info("Migration 18.0.3.0.0: appointment.type %s (%s) -> tz %s", type_id, name, tz)


def _table_exists(cr, table):
    cr.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        # 全新安裝，沒有舊資料要換算
        return

    if _already_migrated(cr):
        _logger.info("Migration 18.0.3.0.0: already applied (flag %s set), skipping", FLAG)
        return

    _check_timezones(cr)

    # ---- 1. appointment_booking：牆上時間 -> UTC ----
    cr.execute(
        """
        UPDATE appointment_booking b
        SET start_datetime = (b.start_datetime AT TIME ZONE t.timezone) AT TIME ZONE 'UTC',
            end_datetime   = (b.end_datetime   AT TIME ZONE t.timezone) AT TIME ZONE 'UTC'
        FROM appointment_type t
        WHERE b.appointment_type_id = t.id
          AND (b.start_datetime IS NOT NULL OR b.end_datetime IS NOT NULL)
        """
    )
    _logger.info("Migration 18.0.3.0.0: converted %s bookings to UTC", cr.rowcount)

    # ---- 2. 由預約建立的 calendar.event ----
    # 只動被 appointment_booking 引用的事件，其他來源的行事曆事件本來就是 UTC。
    cr.execute(
        """
        UPDATE calendar_event e
        SET start = (e.start AT TIME ZONE t.timezone) AT TIME ZONE 'UTC',
            stop  = (e.stop  AT TIME ZONE t.timezone) AT TIME ZONE 'UTC'
        FROM appointment_booking b
        JOIN appointment_type t ON t.id = b.appointment_type_id
        WHERE b.calendar_event_id = e.id
        """
    )
    _logger.info("Migration 18.0.3.0.0: converted %s calendar events to UTC", cr.rowcount)

    # calendar.event 另有 start_date / stop_date（全天事件）與 duration，
    # 本模組不會建立全天事件，duration 是差值、不受平移影響，故不處理。

    # ---- 3. appointment_slot（deprecated，有資料才處理）----
    if _table_exists(cr, 'appointment_slot'):
        cr.execute(
            """
            UPDATE appointment_slot s
            SET start_datetime = (s.start_datetime AT TIME ZONE t.timezone) AT TIME ZONE 'UTC',
                end_datetime   = (s.end_datetime   AT TIME ZONE t.timezone) AT TIME ZONE 'UTC'
            FROM appointment_type t
            WHERE s.appointment_type_id = t.id
            """
        )
        if cr.rowcount:
            _logger.info("Migration 18.0.3.0.0: converted %s slots to UTC", cr.rowcount)

    # ---- 4. 重算 start_date_local ----
    # 這個預存欄位在本腳本執行前就由 ORM 算過了，但當時讀到的是換算前的值。
    cr.execute(
        """
        UPDATE appointment_booking b
        SET start_date_local = ((b.start_datetime AT TIME ZONE 'UTC') AT TIME ZONE t.timezone)::date
        FROM appointment_type t
        WHERE b.appointment_type_id = t.id
          AND b.start_datetime IS NOT NULL
        """
    )
    _logger.info("Migration 18.0.3.0.0: recomputed start_date_local for %s bookings", cr.rowcount)

    _mark_migrated(cr, version)
    _logger.info("Migration 18.0.3.0.0: UTC storage migration completed")
