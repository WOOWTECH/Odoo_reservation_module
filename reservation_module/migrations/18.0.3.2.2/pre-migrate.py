# -*- coding: utf-8 -*-
"""18.0.3.2.2 — 預約行事曆規則改成跟著程式更新（可重跑）。

security/appointment_calendar_security.xml 的兩條規則改看
appointment_guest_partner_id，不再看 partner_ids（員工能從 res.partner 那一側
把自己加進 partner_ids）。早期版本把這兩條規則載成 noupdate，升級時 XML
不會覆蓋，舊的 partner_ids 寫法會留著；先把 noupdate 拿掉，讓這次載入的
XML（noupdate="0"）蓋過去。只改還是 noupdate 的列，重跑不會再變動。
"""

RULE_XMLIDS = (
    'calendar_event_rule_appointment_booking',
    'calendar_attendee_rule_appointment_booking',
)


def release_calendar_rules(cr):
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = FALSE
         WHERE module = 'reservation_module'
           AND model = 'ir.rule'
           AND name IN %s
           AND noupdate IS TRUE
    """, [RULE_XMLIDS])
    return cr.rowcount


def migrate(cr, version):
    if not version:
        return
    release_calendar_rules(cr)
