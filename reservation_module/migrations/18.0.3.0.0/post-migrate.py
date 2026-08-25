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

換算範圍只涵蓋「有預約的」appointment_type：沒有預約的類型不可能產生錯誤資料，
不應該有能力擋下升級。時區沒設（NULL）會中止升級（無從得知牆上時間的意義）；
時區有設但 Postgres 不認得（通常是 pytz 與 Postgres 的 tzdata 版本落差，
例如 Europe/Kyiv vs Europe/Kiev）則只警告並跳過該類型，並把 id 記在
ir_config_parameter，讓維運人員事後手動換算。

冪等保護：完成後寫入 ir_config_parameter 旗標，重跑會直接跳過——這點很重要，
重複執行會再減 8 小時。

另有同目錄的 pre-migrate.py，負責解除提醒信範本的 noupdate 鎖。
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


SKIPPED_PARAM = 'reservation_module.utc_migration_skipped_types'


def _classify_timezones(cr):
    """Split the appointment types that actually have bookings into
    convertible and non-convertible.

    Only types referenced by at least one booking matter: an archived or
    never-used type cannot produce wrong data, so it must not be able to
    block an upgrade.

    Two failure modes, deliberately treated differently:

    * **timezone is NULL/empty** — there is no way to know what the stored
      wall-clock time meant. Abort: a wrong shift is invisible afterwards and
      unrecoverable without a backup.
    * **timezone is set but Postgres does not recognise it** — almost always
      a tzdata skew between pytz (which validated the value in the UI) and
      the server's Postgres, e.g. pytz's `Europe/Kyiv` on a Postgres that
      still only ships `Europe/Kiev`. The configuration is legitimate, so
      refusing the whole upgrade would be wrong. Warn loudly, skip those
      types, and record them so the operator can convert them by hand.

    Returns (ok_type_ids, skipped).
    """
    cr.execute(
        """
        SELECT t.id, t.name, t.timezone
        FROM appointment_type t
        WHERE t.id IN (
            SELECT DISTINCT appointment_type_id
            FROM appointment_booking
            WHERE appointment_type_id IS NOT NULL
        )
        """
    )
    rows = cr.fetchall()
    if not rows:
        return [], []

    missing = [(r[0], r[1]) for r in rows if not r[2]]
    if missing:
        raise ValueError(
            "reservation_module 18.0.3.0.0 migration aborted: these "
            "appointment_type records have bookings but no Timezone set, so "
            "their stored times cannot be interpreted: %s. Set the Timezone "
            "field on them, then re-run the update." % (missing,)
        )

    cr.execute("SELECT name FROM pg_timezone_names")
    known = {r[0] for r in cr.fetchall()}

    ok, skipped = [], []
    for type_id, name, tz in rows:
        if tz in known:
            ok.append(type_id)
            _logger.info(
                "Migration 18.0.3.0.0: appointment.type %s (%s) -> tz %s", type_id, name, tz)
        else:
            skipped.append((type_id, name, tz))

    if skipped:
        _logger.warning(
            "Migration 18.0.3.0.0: Postgres does not know these timezones, so the "
            "bookings of these appointment types were LEFT UNCONVERTED (still "
            "wall-clock, not UTC): %s. This is usually a tzdata version skew "
            "between Python and Postgres. Convert them manually, e.g. "
            "UPDATE appointment_booking SET start_datetime = (start_datetime AT TIME "
            "ZONE '<name Postgres knows>') AT TIME ZONE 'UTC' ... , then recompute "
            "start_date_local. The affected type ids are also stored in the system "
            "parameter %s.",
            skipped, SKIPPED_PARAM,
        )
        cr.execute(
            """
            INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date)
            VALUES (%s, %s, 1, 1, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = EXCLUDED.write_date
            """,
            (SKIPPED_PARAM, ','.join(str(s[0]) for s in skipped)),
        )

    return ok, skipped


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

    ok_type_ids, _skipped = _classify_timezones(cr)
    if not ok_type_ids:
        # 沒有任何帶預約的類型可以換算（空資料庫，或全部被跳過）
        _mark_migrated(cr, version)
        _logger.info("Migration 18.0.3.0.0: nothing to convert")
        return

    ok_ids = tuple(ok_type_ids)

    # ---- 1. appointment_booking：牆上時間 -> UTC ----
    cr.execute(
        """
        UPDATE appointment_booking b
        SET start_datetime = (b.start_datetime AT TIME ZONE t.timezone) AT TIME ZONE 'UTC',
            end_datetime   = (b.end_datetime   AT TIME ZONE t.timezone) AT TIME ZONE 'UTC'
        FROM appointment_type t
        WHERE b.appointment_type_id = t.id
          AND t.id IN %s
          AND (b.start_datetime IS NOT NULL OR b.end_datetime IS NOT NULL)
        """,
        (ok_ids,),
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
          AND t.id IN %s
        """,
        (ok_ids,),
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
              AND t.id IN %s
            """,
            (ok_ids,),
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
          AND t.id IN %s
          AND b.start_datetime IS NOT NULL
        """,
        (ok_ids,),
    )
    _logger.info("Migration 18.0.3.0.0: recomputed start_date_local for %s bookings", cr.rowcount)

    _mark_migrated(cr, version)
    _logger.info("Migration 18.0.3.0.0: UTC storage migration completed")
