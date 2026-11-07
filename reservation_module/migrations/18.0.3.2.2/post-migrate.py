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
   且訂單是自己的預約重算一次，舊規則下被同一購物車其他品項的已付發票標成
   paid 的會回到 pending（並在預約上留記事）；真的已付款的維持 paid。
   已確認／完成／取消的預約不重算，歷史紀錄不變；訂單不是自己的預約也不重算
   （見第 5 段），付款狀態維持原樣（_recompute_open_payment_status）。

5. 指向別人訂單的預約（最先做，只報告、不改資料）：升級前 portal 可經 RPC
   建立預約並帶任意 sale_order_id，員工也可能手動連過別的客戶的訂單。
   _check_sale_order_owner 只擋新的連結；這類舊列會讓該訂單付款失敗時把訂單的
   access_token 寄到這筆預約的訪客信箱，也會因這筆預約的時段被訂走而擋下訂單
   本人的付款。執行期已經把這類列當成「不是本預約的訂單」處理
   （_is_own_sale_order：不給連結與 token、訂單的付款不保留／確認／回報、取消
   預約時不動那張訂單），所以升級不需要、也不可以動資料：舊版匿名訪客每筆預約
   都建一個新的訪客聯絡人，購物車模式又把共用購物車改指向最新那筆的訪客，
   同一購物車裡較早的合法預約看起來也「不是自己的」，已付款、已確認的也一樣；
   員工代付的連結同樣是合法資料。_is_own_sale_order 現在認得匿名訪客的共用
   購物車（預約的聯絡人是訪客，且購物車的聯絡人是訪客，或購物車裡有網站替
   這筆預約加的區段行）。剩下仍判為別人訂單的預約，這裡只寫 warning log、
   在預約上留內部記事，並替還要處理的預約（未取消、未完成、時間未過）排一個
   給預約管理員的待辦；連結、付款交易（payment_transaction_id）與付款狀態
   一律不動（_flag_foreign_sale_orders）。這段與其他各段沒有先後相依：付款
   失敗標記（第 3 段）以預約的 sale_order_id 找交易，連結不動，找到的交易與
   升級前相同。

6. 信件範本的翻譯：mail.template 的 body_html 是整欄翻譯（translate=True），
   升級只會覆蓋英文；資料庫裡已存的其他語言版本（例如 zh_TW）仍用
   object.sale_order_id 取付款連結與金額。改成 _get_payment_url／
   _get_payment_amount；改完仍直接讀 sale_order_id 的語言版本（客製內容）就
   刪掉，改回模組的翻譯或英文（_fix_payment_link_translations）。

各段都只改「還不是目標狀態」的資料，重跑不會再變動。
"""

import json
import logging
import re

from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)

# Stored body_html translations: read the payment link and amount from the
# booking's own order (appointment.booking._get_payment_url /
# _get_payment_amount), never from whatever order sale_order_id points at.
# object.payment_amount (a field that no longer exists) is repaired as well.
_PAYMENT_LINK_FIXES = (
    (re.compile(r't-attf-href="\{\{\s*object\.sale_order_id\.get_portal_url\(\)\s*\}\}"'),
     't-att-href="object._get_payment_url()"'),
    (re.compile(r'"\s*object\.sale_order_id\.amount_total\s+if\s+object\.sale_order_id\s+else\s+0\s*"'),
     '"object._get_payment_amount()"'),
    (re.compile(r'"\s*object\.sale_order_id\.amount_total\s*"'), '"object._get_payment_amount()"'),
    (re.compile(r't-if="\s*object\.sale_order_id\s*"'), 't-if="object._get_payment_url()"'),
    (re.compile(r'"\s*object\.payment_amount\s*"'), '"object._get_payment_amount()"'),
)
_RAW_ORDER_ACCESS = re.compile(r'\bsale_order_id\b')
_OLD_DATETIME_WIDGET = re.compile(
    r'(<t\s+t-out="object\.(?:start|end)_datetime"\s+t-options=")'
    r'\{&quot;widget&quot;: &quot;datetime&quot;\}("/>)')

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


_STATUS_MARKER = 'payment status check 18.0.3.2.2'


def _recompute_open_payment_status(env):
    """Recompute the payment status of the open bookings on their own order.

    Only draft／pending_payment bookings whose order is their own: confirmed,
    done and cancelled ones keep the status they have, and so do the ones
    reported by _flag_foreign_sale_orders (their order is not the one that
    could tell whether they are paid). A booking that really is paid stays
    paid; the one status this lowers is a "paid" that the old rule gave for
    a paid invoice of other items in the shared cart (f94e04013795), and
    that is noted on the booking.
    """
    bookings = env['appointment.booking'].with_context(active_test=False).search([
        ('state', 'in', ('draft', 'pending_payment')),
        ('sale_order_id', '!=', False),
    ])
    bookings = bookings.filtered(lambda booking: booking._is_own_sale_order(booking.sale_order_id))
    before = {booking.id: booking.payment_status for booking in bookings}
    env.add_to_compute(bookings._fields['payment_status'], bookings)
    bookings.flush_recordset(['payment_status'])
    changed = [booking.id for booking in bookings if booking.payment_status != before[booking.id]]
    for booking in bookings.filtered(
            lambda b: before[b.id] == 'paid' and b.payment_status != 'paid'):
        _logger.warning(
            "reservation_module 18.0.3.2.2: booking %s (id %s) was marked paid by a paid invoice that "
            "does not cover its own lines (sales order %s); its payment status is %s now",
            booking.name, booking.id, booking.sale_order_id.name, booking.payment_status)
        booking.message_post(
            body=Markup('<p>%s</p><p>%s</p>') % (
                '[%s] The payment status was set back from Paid to Pending: the paid invoice of '
                'sales order %s does not cover the lines of this booking (a paid invoice for other '
                'items of a shared cart used to make a booking Paid). If it really was paid, '
                'register the payment against its own lines.' % (_STATUS_MARKER, booking.sale_order_id.name),
                '[%s] 付款狀態已從「已付款」改回「待付款」：銷售訂單 %s 的已付發票沒有涵蓋這筆'
                '預約自己的行（舊規則下，同一購物車其他品項的已付發票會讓預約變成已付款）。'
                '若確實已付款，請對這筆預約自己的行登錄付款。' % (_STATUS_MARKER, booking.sale_order_id.name)),
            message_type='notification', subtype_xmlid='mail.mt_note')
    _logger.info("reservation_module 18.0.3.2.2: payment status recomputed for %s open booking(s), "
                 "%s changed", len(bookings), len(changed))
    return changed


# Read-only. Run it BEFORE the upgrade (psql) to list the bookings that
# _flag_foreign_sale_orders will report: the rule of appointment.booking
# _is_own_sale_order, without its first ground (bound lines do not exist
# before this version). A guest contact is an active contact with no res.users
# row (archived ones included) on any contact of its commercial partner.
# tests/test_legacy_order_links keeps this query in line with the code.
PRE_UPGRADE_CHECK_SQL = """
    SELECT b.id, b.name, b.state, b.payment_status, so.name AS sale_order,
           bp.name AS booking_contact, sp.name AS order_contact
      FROM appointment_booking b
      JOIN sale_order so ON so.id = b.sale_order_id
      JOIN res_partner sp ON sp.id = so.partner_id
 LEFT JOIN res_partner bp ON bp.id = b.partner_id
     WHERE bp.commercial_partner_id IS DISTINCT FROM sp.commercial_partner_id
       AND NOT (
            COALESCE(bp.active, FALSE)
        AND NOT EXISTS (
                SELECT 1 FROM res_users u
                  JOIN res_partner up ON up.id = u.partner_id
                 WHERE up.commercial_partner_id = bp.commercial_partner_id)
        AND (
                (sp.active AND NOT EXISTS (
                    SELECT 1 FROM res_users u
                      JOIN res_partner up ON up.id = u.partner_id
                     WHERE up.commercial_partner_id = sp.commercial_partner_id))
             OR EXISTS (
                    SELECT 1 FROM sale_order_line l
                     WHERE l.order_id = so.id AND l.display_type = 'line_section'
                       AND right(l.name, length(' — ' || b.name)) = ' — ' || b.name)))
  ORDER BY b.id
"""

_ORDER_LINK_MARKER = 'order link check 18.0.3.2.2'


# At most this many to-dos per upgrade; the other reported bookings only get
# the note, so a site with many such rows does not flood a manager.
_MAX_TODOS = 100


def _review_user(env):
    """Who gets the to-do: an active internal appointment manager (not OdooBot)."""
    managers = env.ref('reservation_module.group_appointment_manager', raise_if_not_found=False)
    for user in (managers.users if managers else env['res.users']):
        if user.active and user._is_internal() and not user._is_superuser():
            return user
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    return admin if admin and admin.active else env['res.users']


def _already_flagged(env, booking):
    return bool(env['mail.message'].search_count([
        ('model', '=', 'appointment.booking'), ('res_id', '=', booking.id),
        ('body', 'ilike', _ORDER_LINK_MARKER)], limit=1))


def _flag_foreign_sale_orders(env):
    """Report the bookings whose sales order is not their own; change nothing.

    Not an order of the booking (no line of it, not its customer's, not the
    shared guest cart of an anonymous visitor): the portal RPC create hole
    left such rows (an attacker's booking pointing at someone's order), and
    staff may have linked an order of another customer by hand. Nothing is
    unlinked or cleared, and the booking's payment status is left as it is:
    the row may as well be legitimate data (somebody paying for someone). The
    runtime ignores such an order anyway (appointment.booking
    _is_own_sale_order), so what is left is for a person to decide: a
    warning in the log, an internal note on the booking and, for a booking
    that is still to be served, a to-do for an appointment manager.

    A booking that already carries the note is not reported again.
    Returns the ids of the bookings reported by this run.
    """
    bookings = env['appointment.booking'].with_context(active_test=False).search(
        [('sale_order_id', '!=', False)])
    foreign = bookings.filtered(lambda booking: not booking._is_own_sale_order(booking.sale_order_id))
    now = fields.Datetime.now()
    statuses = dict(env['appointment.booking']._fields['payment_status'].selection)
    reviewer = None
    todos = 0
    reported = []
    for booking in foreign:
        if _already_flagged(env, booking):
            continue
        order = booking.sale_order_id
        status = statuses.get(booking.payment_status, booking.payment_status)
        is_paid = booking.payment_status == 'paid'
        _logger.warning(
            "reservation_module 18.0.3.2.2: booking %s (id %s) is linked to sales order %s (id %s), "
            "which is neither the booking's own nor its customer's; the link was kept "
            "(state %s, payment status %s)",
            booking.name, booking.id, order.name, order.id, booking.state, booking.payment_status)
        booking.message_post(
            body=Markup('<p>%s</p><p>%s</p>') % (
                '[%s] Sales order %s is linked to this booking, but it is not an order of this '
                'booking or of its customer. The link was kept and nothing was changed (payment '
                'status: %s). The order\'s payments and payment link are not applied to this '
                'booking. If the link is intended (for example somebody else pays), make that '
                'customer the booking\'s contact; otherwise remove the link.%s'
                % (_ORDER_LINK_MARKER, order.name, status,
                   ' The Paid status comes from the old rule (any paid invoice on the order): '
                   'do not rely on it when confirming.' if is_paid else ''),
                '[%s] 此預約連到的銷售訂單 %s 不是這筆預約或其客戶的訂單。連結已保留，沒有做任何'
                '變更（付款狀態：%s）；該訂單的付款與付款連結不會套用到這筆預約。若這是刻意的'
                '（例如由他人代付），請把該客戶設為預約的聯絡人；否則請移除連結。%s'
                % (_ORDER_LINK_MARKER, order.name, status,
                   '「已付款」是舊規則（訂單上有任一已付發票）給的，確認預約前請不要依賴它。'
                   if is_paid else '')),
            message_type='notification', subtype_xmlid='mail.mt_note')
        if (booking.state in ('draft', 'pending_payment', 'confirmed') and booking.end_datetime > now
                and todos < _MAX_TODOS):
            reviewer = reviewer or _review_user(env)
            if reviewer:
                try:
                    with env.cr.savepoint():
                        booking.with_context(mail_activity_quick_update=True).activity_schedule(
                            'mail.mail_activity_data_todo',
                            user_id=reviewer.id,
                            summary='Check the sales order of booking %s' % booking.name,
                            note='Sales order %s is not an order of this booking or of its customer '
                                 '(see the note on the booking). / 此預約連到的銷售訂單 %s 不是'
                                 '這筆預約或其客戶的訂單（見預約上的記事）。' % (order.name, order.name))
                    todos += 1
                except Exception:  # a to-do is a courtesy: it must never stop the upgrade
                    _logger.warning("reservation_module 18.0.3.2.2: no to-do could be scheduled "
                                    "for booking %s", booking.name, exc_info=True)
        reported.append(booking.id)
    _logger.info("reservation_module 18.0.3.2.2: %s booking(s) point at a sales order that is not "
                 "theirs, %s reported now (%s to-do(s)); no link was changed",
                 len(foreign), len(reported), todos)
    return reported


def _fix_template_body(value):
    for pattern, replacement in _PAYMENT_LINK_FIXES:
        value = pattern.sub(replacement, value)
    value = _OLD_DATETIME_WIDGET.sub(
        r'\1{&quot;widget&quot;: &quot;datetime&quot;, &quot;tz_name&quot;: object.display_tz}\2',
        value)
    return value


def _fix_payment_link_translations(env):
    """Repair payment links and timezones in stored template translations."""
    cr = env.cr
    env['mail.template'].flush_model(['body_html'])
    cr.execute("""
        SELECT t.id, t.body_html, d.name
          FROM mail_template t
          JOIN ir_model_data d ON d.model = 'mail.template' AND d.res_id = t.id
         WHERE d.module = 'reservation_module' AND t.body_html IS NOT NULL
         ORDER BY t.id
    """)
    changed = []
    for template_id, body, xmlid in cr.fetchall():
        new_body = {}
        for lang, value in body.items():
            fixed = _fix_template_body(value) if isinstance(value, str) else value
            if lang != 'en_US' and isinstance(fixed, str) and _RAW_ORDER_ACCESS.search(fixed):
                _logger.warning(
                    "reservation_module 18.0.3.2.2: %s translation of template %s still reads "
                    "sale_order_id; it was removed (the module's translation or English applies)",
                    lang, xmlid)
                continue
            new_body[lang] = fixed
        if new_body != body:
            cr.execute("UPDATE mail_template SET body_html = %s::jsonb WHERE id = %s",
                       [json.dumps(new_body), template_id])
            changed.append(template_id)
    if changed:
        env['mail.template'].invalidate_model(['body_html'])
    _logger.info("reservation_module 18.0.3.2.2: payment links and date widgets fixed in stored translations "
                 "of %s template(s)", len(changed))
    return changed


def _migrate_refund_activities(env):
    """Keep an old open refund to-do from becoming a second refund request.

    Older releases used the generic To Do activity type and a translated
    summary. Move only known refund summaries on appointment bookings; other
    staff to-dos must retain their type. The operation is idempotent.
    """
    todo = env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
    refund = env.ref('reservation_module.mail_activity_type_refund_due', raise_if_not_found=False)
    if not todo or not refund:
        return 0
    summaries = {'Cancelled booking was paid: refund it'}
    for lang in env['res.lang'].sudo().search([('active', '=', True)]).mapped('code'):
        summaries.add(env['appointment.booking'].with_context(lang=lang).env._(
            'Cancelled booking was paid: refund it'))
    activities = env['mail.activity'].sudo().search([
        ('res_model', '=', 'appointment.booking'),
        ('activity_type_id', '=', todo.id),
        ('summary', 'in', list(summaries)),
    ])
    if activities:
        activities.write({'activity_type_id': refund.id})
    return len(activities)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # No step changes a booking's sale_order_id or payment_transaction_id: the
    # payment-failure marking below finds transactions through the bookings'
    # sale_order_id, and the bookings whose order is not their own are only
    # reported here, before any status is recomputed.
    _flag_foreign_sale_orders(env)
    _fix_payment_link_translations(env)
    env.flush_all()
    _migrate_discuss_channels(cr)
    _mark_reported_payment_failures(cr)
    env.invalidate_all()
    _migrate_calendar_events(env)
    _recompute_open_payment_status(env)
    _migrate_refund_activities(env)
