# PRD: Odoo 18 日曆預約增強模組 (odoo_calendar_enhance)

## 1. 概述

### 1.1 目標
將 Odoo 18 企業版的日曆預約功能（Appointment）完整複製到 Community 版本，讓用戶無需購買企業版即可使用完整的預約系統。

### 1.2 模組名稱
- 技術名稱：`odoo_calendar_enhance`
- 顯示名稱：日曆預約增強 / Calendar Booking Enhancement

### 1.3 依賴模組
- `calendar` - Odoo 內建日曆模組
- `resource` - 資源管理模組
- `website` - 網站模組（用於公開預約頁面）
- `payment` - 付款模組（用於付費預約）
- `mail` - 郵件模組（用於通知和提醒）

### 1.4 參考來源
- Odoo 18 Enterprise demo.odoo.com (2026-01-29 實地測試)
- woowtech.odoo.com 中文介面截圖 (2026-01-29)

---

## 2. 功能規格

### 2.1 預約類型 (Appointment Types)

支援以下預約類型：

| 類型 | 說明 | 資源類型 |
|------|------|----------|
| **會議** | 允許其他人透過日曆預約會議 | 員工 (Staff) |
| **視像通話** | 安排與一位或多位參加者在虛擬會議室進行視像會議 | 員工 (Staff) |
| **訂枱** | 讓顧客向餐廳或酒吧訂枱/訂座 | 餐桌 (Table) |
| **預訂資源** | 允許客戶預訂資源，例如房間、網球場等 | 資源 (Resource) |
| **付費諮詢** | Let customers book a paid slot in your calendar with you | 員工 (Staff) + 付款 |
| **付費座位** | Let customers book a fee per person for activities such as a theater, etc. | 資源 (Resource) + 按人數付款 |

### 2.2 預約類型設定

每個預約類型包含以下設定頁籤（從 Odoo Enterprise 實測）：

#### 2.2.1 Availabilities（可用的）頁籤
- **可預約的員工/資源選擇器**
- **每週可用時間表（Weekly Schedule）**
  - 星期一到星期日的時間設定
  - 例如：Mon 8:00 AM - 12:00 PM, 2:00 PM - 5:00 PM
  - 可為每天設定多個時段
  - 「+ Add a line」按鈕新增時段

#### 2.2.2 Questions（問題）頁籤
- **問題清單**：可配置預約時需填寫的問題
- 問題欄位：
  - Question（問題內容）
  - Question Type（問題類型）
  - Placeholder（佔位符文字）
  - Required Answer（是否必填）
- **Add a line** 按鈕新增問題
- 範例問題：Phone number（電話號碼），類型為 Phone

#### 2.2.3 Communication（溝通）頁籤
- **Introduction Page（介紹頁面）**：WYSIWYG 編輯器
- **Confirmation Page（確認頁面）**：WYSIWYG 編輯器
- **Emails & SMS（郵件與簡訊）**
  - Confirmation（確認通知）
  - Cancellation（取消通知）
  - Reminder（提醒通知）

#### 2.2.4 Options（選項）頁籤
完整選項清單（從 demo.odoo.com 實測）：

| 選項 | 說明 | 類型 |
|------|------|------|
| Allow Invitations | 允許邀請其他參加者 | Boolean |
| Auto Confirm | 自動確認，直到容量達 X% | Boolean + Integer |
| Display pictures | 在預約頁面顯示圖片 | Boolean |
| Up-front Payment | 預先付款設定 | Boolean + 金額設定 |
| Create Opportunity | 創建商機 | Boolean |
| Website | 選擇發布的網站 | Many2one |
| Schedule | 預約週期：Recurring weekly / Custom | Selection |
| Allow Bookings | 未來 X 天內可預約 | Integer |
| Minimum Schedule | 最少提前 X 小時預約 | Float |
| Create slot every | 每隔 X 小時建立時段 | Float |
| Cancellation | 直到預約前 X 小時可取消 | Float |
| Timezone | 時區設定（例如 Europe/Brussels） | Selection |

---

## 3. 資料模型

### 3.1 appointment.type (預約類型)

```python
class AppointmentType(models.Model):
    _name = 'appointment.type'
    _description = '預約類型'

    name = fields.Char('名稱', required=True, translate=True)
    category = fields.Selection([
        ('meeting', '會議'),
        ('video_call', '視像通話'),
        ('table', '訂枱'),
        ('resource', '預訂資源'),
        ('paid_consultation', '付費諮詢'),
        ('paid_seat', '付費座位'),
    ], string='類別', required=True, default='meeting')

    # 資源設定
    resource_ids = fields.Many2many('resource.resource', string='資源')
    staff_user_ids = fields.Many2many('res.users', string='員工')

    # 時間設定
    slot_duration = fields.Float('時段時長', default=1.0)
    slot_interval = fields.Float('時段間隔', default=1.0)

    # 預約限制
    max_booking_days = fields.Integer('最大預約天數', default=30)
    min_booking_hours = fields.Float('最少提前預約時數', default=1.0)
    cancel_before_hours = fields.Float('取消期限（小時）', default=1.0)

    # 自動確認
    auto_confirm = fields.Boolean('自動確認', default=True)
    auto_confirm_capacity_percent = fields.Integer('自動確認容量百分比', default=100)

    # 付款設定
    require_payment = fields.Boolean('需要預先付款')
    payment_product_id = fields.Many2one('product.product', string='付款產品')
    payment_amount = fields.Monetary('付款金額')
    payment_per_person = fields.Boolean('按人數收費')
    currency_id = fields.Many2one('res.currency', string='貨幣')

    # 顯示設定
    show_image = fields.Boolean('顯示圖片')
    image = fields.Binary('圖片')

    # 時區
    timezone = fields.Selection('_tz_get', string='時區', default='Asia/Taipei')

    # 問題
    question_ids = fields.One2many('appointment.question', 'appointment_type_id', string='問題')

    # 狀態
    active = fields.Boolean('啟用', default=True)
```

### 3.2 appointment.slot (預約時段)

```python
class AppointmentSlot(models.Model):
    _name = 'appointment.slot'
    _description = '預約時段'

    appointment_type_id = fields.Many2one('appointment.type', string='預約類型', required=True)
    resource_id = fields.Many2one('resource.resource', string='資源')
    staff_user_id = fields.Many2one('res.users', string='員工')

    start_datetime = fields.Datetime('開始時間', required=True)
    end_datetime = fields.Datetime('結束時間', required=True)

    capacity = fields.Integer('容量', default=1)
    booked_count = fields.Integer('已預約數量', compute='_compute_booked_count')
    available_count = fields.Integer('可用數量', compute='_compute_available_count')

    state = fields.Selection([
        ('available', '可用'),
        ('partial', '部分預約'),
        ('full', '已滿'),
    ], string='狀態', compute='_compute_state')
```

### 3.3 appointment.booking (預約記錄)

```python
class AppointmentBooking(models.Model):
    _name = 'appointment.booking'
    _description = '預約記錄'

    name = fields.Char('預約編號', readonly=True, copy=False)
    appointment_type_id = fields.Many2one('appointment.type', string='預約類型', required=True)
    slot_id = fields.Many2one('appointment.slot', string='時段')

    # 預約者資訊
    partner_id = fields.Many2one('res.partner', string='預約者')
    guest_name = fields.Char('訪客姓名')
    guest_email = fields.Char('訪客電子郵件')
    guest_phone = fields.Char('訪客電話')
    guest_count = fields.Integer('人數', default=1)

    # 資源/員工
    resource_id = fields.Many2one('resource.resource', string='資源')
    staff_user_id = fields.Many2one('res.users', string='員工')

    # 時間
    start_datetime = fields.Datetime('開始時間', required=True)
    end_datetime = fields.Datetime('結束時間', required=True)

    # 日曆事件連結
    calendar_event_id = fields.Many2one('calendar.event', string='日曆事件')

    # 付款
    payment_status = fields.Selection([
        ('not_required', '無需付款'),
        ('pending', '待付款'),
        ('paid', '已付款'),
        ('refunded', '已退款'),
    ], string='付款狀態', default='not_required')
    payment_amount = fields.Monetary('付款金額')
    payment_transaction_id = fields.Many2one('payment.transaction', string='付款交易')

    # 狀態
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已確認'),
        ('done', '已完成'),
        ('cancelled', '已取消'),
    ], string='狀態', default='draft')

    # 問題回答
    answer_ids = fields.One2many('appointment.answer', 'booking_id', string='回答')
```

### 3.4 appointment.question (預約問題)

```python
class AppointmentQuestion(models.Model):
    _name = 'appointment.question'
    _description = '預約問題'

    appointment_type_id = fields.Many2one('appointment.type', string='預約類型', required=True)
    name = fields.Char('問題', required=True, translate=True)
    question_type = fields.Selection([
        ('text', '文字'),
        ('textarea', '多行文字'),
        ('select', '選擇'),
        ('checkbox', '核取方塊'),
        ('date', '日期'),
    ], string='類型', default='text')
    required = fields.Boolean('必填')
    sequence = fields.Integer('排序')
    option_ids = fields.One2many('appointment.question.option', 'question_id', string='選項')
```

### 3.5 appointment.answer (預約回答)

```python
class AppointmentAnswer(models.Model):
    _name = 'appointment.answer'
    _description = '預約回答'

    booking_id = fields.Many2one('appointment.booking', string='預約', required=True)
    question_id = fields.Many2one('appointment.question', string='問題', required=True)
    value_text = fields.Text('回答')
```

---

## 4. 視圖規格

### 4.1 後台視圖

#### 4.1.1 預約應用主頁面 (Kanban)
URL: `/odoo/appointments`

- 顯示所有預約類型卡片
- 每個卡片顯示：
  - **PUBLISHED** 狀態標籤（左上角綠色）
  - 預約類型名稱（例如：Dental Care, Tennis Court）
  - 時段時長（例如：30 min Duration, 1 hour Duration）
  - 關聯的資源/員工頭像（可顯示多個，+N 表示更多）
  - **X Meetings/Bookings Upcoming**（即將舉行）
  - **X Meetings/Bookings Total**（總計）
  - **Share** 按鈕
  - **Configure** 按鈕
- 頂部工具列：
  - **New** 按鈕（建立新預約類型）
  - 分頁導航

#### 4.1.2 資源預訂視圖 (Gantt/Calendar)
URL: `/odoo/appointments/{type_id}/action-344`
標題: **Resource Bookings**

- **Gantt 甘特圖視圖**
- 工具列控件：
  - 返回按鈕
  - **New** 按鈕
  - **Actions menu**
  - 時間範圍選擇器（Day / Week / Month / Quarter / Year / 自訂日期範圍）
  - **Add Closing Day(s)** 按鈕
  - **Today** 按鈕
  - Toolbar menu
- 左側列：**Resources** 資源列表（例如：Court 1, Court 2, Court 3, Court 4）
- 頂部：時間刻度（12am, 1am, 2am... 依選擇的時間範圍）
- 預約顯示為橫條，顯示："{預約者姓名} - {預約類型名稱} Booking"
- 日期顯示（例如：January 29, 2026）

#### 4.1.2.1 Add Closing Day(s) 對話框
- **Resources** 欄位：選擇要關閉的資源
- **Dates** 欄位：日期範圍選擇器
- **Reason** 欄位：關閉原因文字輸入
- **Create Closing Day(s)** 按鈕
- **Cancel** 按鈕

#### 4.1.3 員工預訂視圖 (Gantt/Calendar)
- 類似資源預訂視圖
- 左側列出員工（顯示頭像和姓名）
- 時間軸顯示可用時段

#### 4.1.4 預約類型表單視圖
- 四個頁籤：Availabilities、Questions、Communication、Options
- 完整的設定選項（詳見 2.2 節）

#### 4.1.5 新增預約類型對話框
建立新預約時會顯示預設類型選擇：
- **Meeting** - 會議
- **Video Call** - 視像通話
- **Table Booking** - 訂枱
- **Book a Resource** - 預訂資源
- **Paid Consultation** - 付費諮詢
- **Paid Seats** - 付費座位

### 4.2 前台預約頁面（Website Portal）

#### 4.2.1 預約類型頁面
URL: `/appointment/{type_id}`

佈局（左右兩欄）：
- **左側主區域**：
  - **Select a date** 標題
  - 月曆選擇器（顯示月份和年份，如 "January 2026"）
  - 左右導航按鈕切換月份
  - 星期標題（Sun Mon Tue Wed Thu Fri Sat）
  - 日期格子（可點擊選擇）
  - **Timezone** 下拉選擇器（完整時區列表）
  - **Time** 標題
  - 時間按鈕列表（例如：9:00 AM, 10:00 AM, 11:00 AM, 2:00 PM, 3:00 PM, 4:00 PM）
  - **Make your choice** 資源選擇下拉（例如：Court 1, Court 2, Court 3, Court 4）
  - **Confirm** 按鈕

- **右側側邊欄**（complementary）：
  - 預約類型標題（例如：Tennis Court）
  - **Booking details** 標題
  - 地址資訊（例如：Tennis Club, 4141 Federer Street, Saint-Louis 63116, United States）
  - 時長（例如：1 hour）
  - **Description** 標題
  - 描述文字

#### 4.2.2 預約表單頁面
URL: `/appointment/{type_id}/info?allday=0&date_time=...&duration=...&available_resource_ids=...&resource_selected_id=...&asked_capacity=...`

佈局：
- **左側主區域**：
  - **Add more details about you** 標題
  - **Full name*** 欄位（必填）
  - **Email*** 欄位（必填）
  - 自訂問題欄位（例如：**Phone number*** 必填）
  - **Guests** 欄位 + **Add** 按鈕
  - **Confirm Appointment** 按鈕

- **右側側邊欄**：
  - 預約類型標題
  - **Booking details** 標題
  - 選擇的日期（例如：Thu Jan 29, 2026）
  - 選擇的時間和時區（例如：9:00 AM Europe/Brussels）
  - 地址資訊
  - 時長
  - 選擇的資源（例如：Court 1）
  - 描述

#### 4.2.3 確認頁面
URL: `/calendar/view/{booking_uuid}?partner_id=...&state=new&...`
標題: **Website Appointment: Appointment Confirmed**

佈局：
- **Appointment Scheduled!** 標題（帶勾選圖標）
- **{預約者姓名} - {預約類型} Booking** 副標題
- 地點資訊（含資源名稱）
- 日期時間（例如：Thu Jan 29, 2026, 9:00:00 AM (1 hour)）
- 時區
- **Add to iCal/Outlook** 按鈕
- **Add to Google Agenda** 按鈕
- **Your Details** 區塊：
  - Contact Details（姓名、Email、電話）
  - Questions & Answers（問題與回答）
- **Guests** 區塊：
  - 已確認的參加者（帶勾選圖標）
  - **Add Guests** 按鈕
- **Reschedule** 按鈕
- **Cancel** 按鈕

#### 4.2.4 付款頁面（如需要）
- 顯示付款金額
- 整合付款服務商

---

## 5. 應用程式結構

### 5.1 菜單結構

```
日曆 (Calendar)
├── 日曆 (Calendar View)
├── 預約 (Appointments)
│   ├── [預約類型卡片視圖]
├── 報告 (Reports)
└── 配置 (Configuration)
    └── 設定 (Settings)
```

### 5.2 網站路由（從 Odoo Enterprise 實測）

| 路由 | 說明 |
|------|------|
| `/appointment` | 預約類型列表 |
| `/appointment/<type_id>` | 特定預約類型頁面（日曆選擇） |
| `/appointment/<type_id>/info` | 填寫預約者資訊 |
| `/appointment/<type_id>/slots` | AJAX API：取得可用時段 |
| `/calendar/view/<booking_uuid>` | 預約確認/詳情頁面 |

#### 5.2.1 URL 參數（實測）

預約資訊頁面參數：
```
/appointment/{type_id}/info
  ?allday=0                    # 是否全天
  &date_time=2026-01-29+09:00:00  # 選擇的日期時間
  &duration=1.0                # 時長（小時）
  &available_resource_ids=[1]  # 可用資源 ID 列表
  &resource_selected_id=1      # 選擇的資源 ID
  &asked_capacity=1            # 請求的容量
```

確認頁面參數：
```
/calendar/view/{booking_uuid}
  ?partner_id=3                # 預約者 Partner ID
  &state=new                   # 狀態
  &allday=0
  &date_time=...
  &duration=...
  &available_resource_ids=...
  &resource_selected_id=...
  &asked_capacity=...
```

---

## 6. 安全性

### 6.1 存取權限群組

- **appointment.group_user** - 預約用戶（可檢視和建立預約）
- **appointment.group_manager** - 預約管理員（完整存取權限）

### 6.2 記錄規則

- 用戶只能查看自己的預約
- 管理員可查看所有預約
- 公開預約頁面不需要登入

---

## 7. 實作階段

### Phase 1: 基礎架構
- [ ] 建立模組基礎結構
- [ ] 實作資料模型
- [ ] 建立基本視圖

### Phase 2: 後台功能
- [ ] 預約類型管理
- [ ] 資源/員工配置
- [ ] 時段產生邏輯
- [ ] 預約管理

### Phase 3: 前台功能
- [ ] 預約頁面控制器
- [ ] 時段選擇介面
- [ ] 預約表單
- [ ] 確認和通知

### Phase 4: 付款整合
- [ ] 付款流程
- [ ] 付款狀態追蹤
- [ ] 退款處理

### Phase 5: 進階功能
- [ ] 日曆整合
- [ ] 提醒通知
- [ ] 報告統計

---

## 8. 參考資料

- Odoo 18 Enterprise Appointment 模組
- 實測來源：demo.odoo.com (demo4.odoo.com)
- 測試日期：2026-01-29

---

## 9. 附錄：Odoo Enterprise 實測記錄

### 9.1 測試的預約類型

| 名稱 | 類型 | 時長 | 資源/員工 |
|------|------|------|----------|
| Dental Care | Meeting | 30 min | Mitchell Admin, Marc Demo |
| Tennis Court | Resource | 1 hour | Court 1, Court 2, Court 3, Court 4 |
| Online Cooking Lesson | Meeting | 1 hour | Mitchell Admin, Marc Demo |
| Interviews availabilities | Meeting | 30 min | Mitchell Admin, Marc Demo |

### 9.2 完整預約流程測試

1. 訪問 `/appointment/2`（Tennis Court）
2. 選擇日期（January 29, 2026）
3. 選擇時區（Europe/Brussels）
4. 選擇時間（9:00 AM）
5. 選擇資源（Court 1）
6. 點擊 Confirm
7. 填寫個人資訊（Full name, Email, Phone number）
8. 點擊 Confirm Appointment
9. 顯示確認頁面，提供：
   - 加入 iCal/Outlook 日曆
   - 加入 Google Agenda
   - Reschedule 重新排程
   - Cancel 取消預約
   - Add Guests 新增參加者

### 9.3 woowtech.odoo.com 中文介面記錄

#### 9.3.1 預約類型選擇對話框（選擇預約預設設定）
六種預約類型（含圖示）：
| 類型 | 中文名稱 | 說明 |
|------|----------|------|
| Meeting | 會議 | 允許其他人透過你的日曆預約會議 |
| Video Call | 視像通話 | 安排與一位或多位參加者在虛擬會議室進行視像會議 |
| Table Booking | 訂枱 | 讓顧客向你的餐廳或酒吧訂枱/訂座 |
| Book a Resource | 預訂資源 | 允許客戶預訂資源，例如房間、網球場等 |
| Paid Consultation | 付費諮詢 | Let customers book a paid slot in your calendar with you |
| Paid Seats | 付費座位 | Let customers book a fee per person for activities such as a theater, etc. |

#### 9.3.2 預約類型主頁面（Kanban）
顯示多個預約類型卡片：
- **會議**：1 小時時長、渥屋科技股份有限公司、0 會議 即將舉行、0 會議 總計
- **餐桌**：2 小時時長、4 號桌(🪑6)、3 號桌(🪑4) +2、0 預訂 即將舉行、0 預訂 總計
- **預訂資源**：1 小時時長、資源 4、資源 3 +2、1 預訂 即將舉行、1 預訂 總計
- **付費座位**：1 小時時長、4 號房(🪑20)、3 號房(🪑15) +2、0 預訂 即將舉行、0 預訂 總計

每個卡片都有 **分享** 和 **設定** 按鈕

#### 9.3.3 會議類型表單視圖

**基本資訊：**
- 預約標題：會議
- 時長：01:00 小時
- 地點：網上會議（下拉選擇）
- 影片連結：無
- 預訂：使用者 / 資源（單選）
- 使用者：渥屋科技股份有限公司
- 管理容納人數：允許 1 項同時預約：每名使用者可同時預訂的預約數目

**四個頁籤：可用的、問題、溝通、選項**

**問題頁籤：**
- 提問 | 回覆類型 | 答案 | 強...
- 電話號碼 | 電話號碼 | ✓ | 📊
- 「加入資料行」按鈕

**溝通頁籤：**
- 介紹頁面：例如:"會議期間，我們將..."（WYSIWYG 編輯器）
- 確認頁面：例如 "感謝您的信任，期待與您見面!"（WYSIWYG 編輯器）
- 電郵及短訊

**選項頁籤：**
- 允許邀請：□
- 自動確認：☑ 直至 100 % 佔總容量
- 顯示圖片：☑
- 預先付款：□
- 預約：⚫ 每週 ○ 靈活
- 允許預訂：未來 15 天，最少 01:00 小時（開始時間前）
- 建立時段每隔：01:00 小時
- 取消：直至 01:00 小時（預約時段前）
- 時區：Asia/Taipei

#### 9.3.4 餐桌類型表單視圖

**基本資訊：**
- 預約標題：餐桌
- 時長：02:00 小時
- 地點：woowtechwoowtech（公司選擇器）
- 地址：6F-3, No. 4, Lane 286, Nanjing E. Rd., Sec. 5, Taipei City 105055, 台灣
- 「+ 加入影片」按鈕
- 預訂：○ 使用者 ⚫ 資源
- 資源：1 號桌(🪑2)、2 號桌(🪑2)、3 號桌(🪑4)、4 號桌(🪑6)
- 指派：⚫ 自動 ○ 來自訪客
- 管理容納人數：☑ 總計: 14 個座位（最多）

#### 9.3.5 付費座位類型表單視圖

**基本資訊：**
- 預約標題：付費座位
- 時長：01:00 小時
- 資源：1 號房(🪑5)、2 號房(🪑10)、3 號房(🪑15)、4 號房(🪑20)
- 指派：○ 自動 ⚫ 來自訪客
- 以此開始：⚫ 日期 ○ 使用者 / 資源
- 管理容納人數：☑ 總計: 50 個座位（最多）

**選項頁籤：**
- 預先付款：☑
  - 預訂費用（下拉）→ NT$ 50.00 每 個 名 額
  - 「→ 設定付款服務商」連結
- 預約：⚫ 每週 ○ 靈活
- 允許預訂：未來 30 天，最少 01:00 小時（開始時間前）
- 建立時段每隔：01:00 小時
- 取消：直至 01:00 小時（預約時段前）

#### 9.3.6 資源預訂 Gantt 視圖

標題：**資源預訂**
- 工具列：新增、← → 、星期（下拉）、加入休息日、今天、⚙
- 週視圖：Week 5, 1月25日 - 1月31日
- 左側資源列表：
  - 1 號桌 (🪑2)
  - 2 號桌 (🪑2)
  - 3 號桌 (🪑4)
  - 4 號桌 (🪑6)
  - 資源 1
  - 資源 2
  - 資源 3
  - 資源 4
  - 1 號房 (🪑5)
  - 2 號房 (🪑10)
  - 3 號房 (🪑15)
  - 4 號房 (🪑20)

#### 9.3.7 員工預訂 Gantt 視圖

標題：**員工預訂**
- 工具列：新增、← → 、日（下拉）、今天、⚙
- 日視圖：2026年1月29日
- 左側資源列表：渥屋科技股份有限...
- 時間刻度：0, 1, 2, 3, 4, 5, 6...

#### 9.3.8 新增日曆事件表單

**建立**對話框：
- 標籤欄位：例：陳大文 - 網球場預訂
- 時間：1月29日 上午12:00 → 1月30日 上午12:00  □ All day
- 訊息參與者（下拉）
- ●狀態（下拉）
- 🏷 備註

按鈕：儲存、更多選項、捨棄

**完整表單（傳送電郵）：**
- 會議主題：例如:商務午餐
- 開始：1月29日 上午12:00 → 1月30日 上午12:00
- 時長：24:00 小時 或 全天 ○
- 地點：網上會議
- 影片連結
- 「+Odoo 會議」按鈕
- 狀態：忙碌（下拉）、User default（下拉）
- 1 guests、1 Awaiting
- 電郵、電話短訊（SMS）按鈕
- 渥屋科技股份有限公司
- 選取參加者...（下拉）

**備註/選項頁籤：**
- 備註：Add notes about this meeting...
- 選項頁籤：
  - 舉辦方：渥屋科技股份有限公司
  - 標籤（下拉）
  - 預約：會議
  - 預約狀態（下拉）
  - Calendar description：加入描述

#### 9.3.9 答案細分視圖

標題：**答案細分**
- 工具列：⚙、← → 、≡、🔍
- 欄位：預約類型 | 文字答案 | 選擇的答案
- 資料：▶ 電話號碼 | 1 |

---

## 10. 版本歷史

| 版本 | 日期 | 說明 |
|------|------|------|
| 1.0 | 2026-01-29 | 初版 PRD |
| 1.1 | 2026-01-29 | 更新：加入 Odoo Enterprise demo.odoo.com 實測詳細記錄 |
| 1.2 | 2026-01-29 | 更新：加入 woowtech.odoo.com 中文介面詳細記錄 |
