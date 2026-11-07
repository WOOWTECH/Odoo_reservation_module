# -*- coding: utf-8 -*-
"""18.0.3.2.2 — 預約的 Discuss 會議室與行事曆 event 收緊權限（可重跑）。

1. 會議室：舊版建成 channel_type='channel' + group_public_id=base.group_portal，
   任何 portal 使用者都能讀、自行加入、發言。改成成員制的 'group'，並移除
   不該在裡面的成員（不是該預約的訪客、不是指派員工、也不是內部使用者的人，
   例如自行加入的其他 portal 客戶、公開使用者）。會議室底下若有子討論串，
   一併改成成員制：父頻道沒有 group_public_id 時，core 規則會把 'channel'
   型的子討論串開放給所有人。
2. 行事曆 event：補 privacy='private'、is_appointment_booking=True 與
   appointment_guest_partner_id＝預約的訪客（讓
   security/appointment_calendar_security.xml 的規則只讓主辦人（指派員工）、
   該預約的訪客、預約管理員看到 event 與參加者列；不看 partner_ids，因為員工
   能從 res.partner 那一側把自己加進去），標題改成「預約類型 - 預約編號」
   （不含訪客姓名，_get_event_name），description 改成不含訪客 email／
   電話／備註的精簡版（_get_event_description）。
3. 付款失敗：升級前已回報過的失敗交易標成已回報，預約的付款失敗信計數從
   失敗次數起算（_mark_reported_payment_failures），付款返回頁重開不會再寄信。

4. 付款狀態：payment_status 改成只看「這筆預約自己加進訂單的那幾行」是否已開票
   並付清（_compute_payment_status）。升級前就建立的預約沒有綁定的訂單行，
   改用整張訂單判斷（_legacy_order_paid）；還在等付款（draft／pending_payment）
   的預約重算一次，舊規則下被同一購物車其他品項的已付發票標成 paid 的會回到
   pending。已確認／完成／取消的預約不重算，歷史紀錄不變
   （_recompute_open_payment_status）。

各段都只改「還不是目標狀態」的資料，重跑不會再變動。
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_BOOKING_CHANNELS = """
    SELECT b.discuss_channel_id AS channel_id,
           b.partner_id AS guest_partner_id,
           su.partner_id AS staff_partner_id
      FROM appointment_booking b
 LEFT JOIN res_users su ON su.id = b.staff_user_id
     WHERE b.discuss_channel_id IS NOT NULL
 UNION ALL
    SELECT sub.id, b.partner_id, su.partner_id
      FROM appointment_booking b
      JOIN discuss_channel sub ON sub.parent_channel_id = b.discuss_channel_id
 LEFT JOIN res_users su ON su.id = b.staff_user_id
"""


def _table_exists(cr, name):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", [name])
    return bool(cr.fetchone())


def _migrate_discuss_channels(cr):
    if not _table_exists(cr, 'discuss_channel'):
        return 0, 0
    cr.execute(f"""
        UPDATE discuss_channel c
           SET channel_type = 'group', group_public_id = NULL
         WHERE c.id IN (SELECT channel_id FROM ({_BOOKING_CHANNELS}) bc)
           AND (c.channel_type <> 'group' OR c.group_public_id IS NOT NULL)
    """)
    converted = cr.rowcount
    if _table_exists(cr, 'discuss_channel_res_groups_rel'):
        cr.execute(f"""
            DELETE FROM discuss_channel_res_groups_rel r
             WHERE r.discuss_channel_id IN (SELECT channel_id FROM ({_BOOKING_CHANNELS}) bc)
        """)
    cr.execute(f"""
        DELETE FROM discuss_channel_member m
         WHERE m.channel_id IN (SELECT channel_id FROM ({_BOOKING_CHANNELS}) bc)
           AND NOT EXISTS (
                SELECT 1 FROM ({_BOOKING_CHANNELS}) bc
                 WHERE bc.channel_id = m.channel_id
                   AND m.partner_id IN (bc.guest_partner_id, bc.staff_partner_id))
           AND NOT EXISTS (
                SELECT 1 FROM res_users u
                 WHERE u.partner_id = m.partner_id AND u.share IS NOT TRUE)
    """)
    removed = cr.rowcount
    _logger.info(
        "reservation_module 18.0.3.2.2: %s booking channel(s) made members-only, "
        "%s outsider membership(s) removed", converted, removed)
    return converted, removed


def _migrate_calendar_events(env):
    bookings = env['appointment.booking'].with_context(active_test=False).search(
        [('calendar_event_id', '!=', False)])
    updated = 0
    for booking in bookings:
        event = booking.calendar_event_id.with_context(
            dont_notify=True, mail_notrack=True, tracking_disable=True)
        description = booking._get_event_description()
        vals = {}
        if event.privacy != 'private':
            vals['privacy'] = 'private'
        if not event.is_appointment_booking:
            vals['is_appointment_booking'] = True
        if event.appointment_guest_partner_id != booking.partner_id:
            vals['appointment_guest_partner_id'] = booking.partner_id.id
        name = booking._get_event_name()
        if event.name != name:
            vals['name'] = name
        if not _same_text(event.description, description):
            vals['description'] = description
        if vals:
            event.write(vals)
            updated += 1
    _logger.info(
        "reservation_module 18.0.3.2.2: %s booking calendar event(s) made private and confined", updated)
    return updated


def _same_text(html_value, text):
    from odoo.tools import html2plaintext
    return html2plaintext(html_value or '').split() == html2plaintext(text or '').split()


def _mark_reported_payment_failures(cr):
    """舊版已經回報過（也寄過信）的失敗交易。

    18.0.3.2.2 起每筆失敗交易只回報一次（payment_transaction 的
    appointment_failure_notified）。升級前失敗的交易舊版已回報過，可能還不止
    一次：先標記，避免訪客再開一次付款返回頁就又收到一封信。舊版每次回報都寄
    信給訪客，所以預約的「付款失敗信」計數從失敗次數起算。
    """
    tx_filter = "t.appointment_booking_id IS NOT NULL"
    if _table_exists(cr, 'sale_order_transaction_rel'):
        tx_filter += """
            OR EXISTS (SELECT 1 FROM sale_order_transaction_rel r
                         JOIN appointment_booking b ON b.sale_order_id = r.sale_order_id
                        WHERE r.transaction_id = t.id)"""
    cr.execute(f"""
        UPDATE payment_transaction t
           SET appointment_failure_notified = TRUE
         WHERE t.state IN ('error', 'cancel')
           AND t.appointment_failure_notified IS NOT TRUE
           AND ({tx_filter})
    """)
    marked = cr.rowcount
    cr.execute("""
        UPDATE appointment_booking
           SET payment_failure_mail_count = payment_failure_count
         WHERE COALESCE(payment_failure_count, 0) > COALESCE(payment_failure_mail_count, 0)
    """)
    _logger.info('reservation_module 18.0.3.2.2: %s failed transactions marked as reported, '
                 '%s bookings got their payment failure mail counter', marked, cr.rowcount)
    return marked


def _recompute_open_payment_status(env):
    bookings = env['appointment.booking'].with_context(active_test=False).search([
        ('state', 'in', ('draft', 'pending_payment')),
        ('sale_order_id', '!=', False),
    ])
    before = {booking.id: booking.payment_status for booking in bookings}
    env.add_to_compute(bookings._fields['payment_status'], bookings)
    bookings.flush_recordset(['payment_status'])
    changed = [booking.id for booking in bookings if booking.payment_status != before[booking.id]]
    _logger.info("reservation_module 18.0.3.2.2: payment status recomputed for %s open booking(s), "
                 "%s changed", len(bookings), len(changed))
    return changed


def migrate(cr, version):
    if not version:
        return
    _migrate_discuss_channels(cr)
    _mark_reported_payment_failures(cr)
    env = api.Environment(cr, SUPERUSER_ID, {})
    _migrate_calendar_events(env)
    _recompute_open_payment_status(env)
