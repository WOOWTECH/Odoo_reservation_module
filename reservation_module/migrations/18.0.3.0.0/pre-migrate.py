# -*- coding: utf-8 -*-
"""18.0.3.0.0 — 解除提醒信範本的 noupdate 鎖，讓時區修正套得進既有資料庫。

3.0.0 之前，email_template_booking_reminder 被放在 data/appointment_data.xml
的 <data noupdate="1"> 區塊裡。noupdate 的語意是「模組升級時不要覆寫這筆
資料」，Odoo 會把它記在 ir_model_data.noupdate 上；因此在**既有**資料庫上
執行 -u reservation_module 時，資料檔裡新加的 tz_name 修正根本不會被套用，
該範本會保留 3.0.0 之前的內容。

後果很具體：提醒信是由 cron 以 OdooBot 身分渲染的，那個使用者沒有設定時區，
QWeb 少了 tz_name 就會直接輸出 UTC——資料改存 UTC 之後，收件者看到的提醒
時間會少 8 小時（Asia/Taipei）。其餘 4 個範本本來就在 noupdate="0" 區塊，
不受影響。

必須在 **pre** 階段執行：post-migrate 跑在資料檔載入之後，那時範本早就被
跳過了，改旗標也來不及。pre-migrate 先把旗標放掉，接著載入資料檔時 Odoo
才會真的覆寫該範本。

3.0.0 起該 record 已移到 <data noupdate="0"> 區塊，所以新安裝的資料庫本來
就是對的；這支腳本只負責把既有資料庫拉齊。腳本本身是冪等的（把 false 再設
成 false 沒有副作用），重跑安全。
"""

import logging

_logger = logging.getLogger(__name__)

# 3.0.0 起改由資料檔的 noupdate="0" 管理、需要在既有 DB 上解鎖的 xmlid
UNLOCK_XMLIDS = [
    'email_template_booking_reminder',
]


def migrate(cr, version):
    if not version:
        # 全新安裝：資料檔本來就是 noupdate="0"，沒有舊旗標要清
        return

    cr.execute(
        """
        UPDATE ir_model_data
        SET noupdate = false
        WHERE module = 'reservation_module'
          AND name IN %s
          AND noupdate = true
        """,
        (tuple(UNLOCK_XMLIDS),),
    )
    _logger.info(
        "Migration 18.0.3.0.0 (pre): cleared noupdate on %s reservation_module "
        "record(s) so the timezone fix in data/appointment_data.xml is applied",
        cr.rowcount,
    )
