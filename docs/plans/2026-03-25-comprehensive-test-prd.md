# PRD: reservation_module 商用上線前全面測試計畫

**版本**: v18.0.1.5.0
**日期**: 2026-03-25
**目標**: 確保模組達到商用正式上線 (production-ready) 的品質標準
**方法**: 多輪迴圈迭代測試 (multi-loop iterative testing)

---

## 1. 測試概觀

### 1.1 範圍

| 層級 | 涵蓋範圍 |
|------|----------|
| **前端瀏覽器** | 9 個 Website 模板頁面、JS 日曆元件、CSS 樣式、表單驗證、RWD |
| **中間 API** | 4 個 JSON-RPC 端點 + 8 個 HTTP 路由、CSRF、Session 安全 |
| **後端邏輯** | 7 個模型的所有方法、約束、狀態機、自動排程、衝突偵測 |
| **軟體穩定度** | 併發、大量資料、錯誤恢復、模組升級冪等性 |

### 1.2 5 種預約類型全覆蓋

| # | 類型 | 模式 | 特殊功能 |
|---|------|------|----------|
| 1 | Business Meeting | 排程制、員工 | assign_staff, 無容量管理 |
| 2 | Video Consultation | 排程制、線上 | 30 分鐘時段、14 天預訂窗口 |
| 3 | Restaurant Reservation | 排程制、容量 | 3 桌位 (4/6/8 容量)、manage_capacity |
| 4 | Tennis Court Booking | 排程制、單資源 | 7 天窗口、容量 4 |
| 5 | Expert Consultation | 排程制、付款 | require_payment、100 USD |

### 1.3 多輪迴圈測試方法

每個測試類別使用參數化迴圈 (parameterized loops) 執行：

```
for appointment_type in ALL_5_TYPES:
    for test_scenario in SCENARIOS:
        for edge_value in EDGE_VALUES:
            execute_test(appointment_type, test_scenario, edge_value)
            assert_result()
            cleanup()
```

---

## 2. 測試類別 A：前端瀏覽器測試 (Frontend Browser)

### A1. 頁面可訪問性 (Page Accessibility)

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| A1.1 | `/appointment` 列表頁載入 | HTTP GET | status=200, 含所有 published 類型卡片 |
| A1.2 | `/appointment/{id}` 詳情頁 (x5 類型) | HTTP GET loop | 每個類型 status=200, 含正確名稱 |
| A1.3 | `/appointment/{id}/schedule` 排程頁 (x5) | HTTP GET loop | status=200, 含日曆 HTML |
| A1.4 | `/appointment/{id}/book` 表單頁 (x5) | HTTP GET with params | status=200, 含表單元素 |
| A1.5 | 未發佈類型頁面重導向 | HTTP GET | status=302 → `/appointment` |
| A1.6 | 不存在的類型 ID | HTTP GET /appointment/99999 | status=404 或 302 |
| A1.7 | 確認頁面需要 token | HTTP GET without token | 不顯示預約資訊 |
| A1.8 | 取消頁面需要 token | HTTP GET without token | 不顯示取消按鈕 |
| A1.9 | 付款頁面 (Expert Consultation) | HTTP GET with token | status=200, 含金額 |

### A2. JavaScript 日曆元件

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| A2.1 | 日曆初始渲染 | Browser snapshot | 月份名稱、日名稱、日期格 |
| A2.2 | 前月導航按鈕 | Click `.reservation-prev` | 月份切換正確 |
| A2.3 | 後月導航按鈕 | Click `.reservation-next` | 月份切換正確 |
| A2.4 | 過去日期標記 disabled | Snapshot check | `.disabled` class 存在 |
| A2.5 | 超出 max_booking_days 日期 disabled | Snapshot check | `.disabled` class 存在 |
| A2.6 | 日期選擇 → slots 載入 | Click date cell | `#slots-container` 顯示 |
| A2.7 | Event 模式只標記有活動日期 | Browser snapshot | `.has-event` class 只在有活動日期 |
| A2.8 | 員工下拉切換重新載入 slots | Select change | API 重新呼叫 |
| A2.9 | 場地下拉切換重新載入 slots | Select change | API 重新呼叫 |
| A2.10 | 年份邊界 (12月→1月) | Navigate forward | 正確顯示下年一月 |
| A2.11 | 年份邊界 (1月→12月) | Navigate backward | 正確顯示上年十二月 |

### A3. 表單驗證 (Form Validation)

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| A3.1 | 空表單送出被阻止 | POST empty form | 錯誤訊息顯示 |
| A3.2 | 缺少 guest_name | POST without name | 錯誤：必填欄位 |
| A3.3 | 缺少 guest_email | POST without email | 錯誤：必填欄位 |
| A3.4 | 無效 email 格式 (loop 8 種) | POST each format | 全部拒絕 |
|      | - `not-email` | | |
|      | - `@domain.com` | | |
|      | - `user@` | | |
|      | - `user@.com` | | |
|      | - `user@domain` | | |
|      | - `user name@domain.com` | | |
|      | - `<script>@xss.com` | | |
|      | - 空字串 | | |
| A3.5 | guest_count = 0 | POST | 拒絕，最少 1 |
| A3.6 | guest_count = -1 | POST | 拒絕 |
| A3.7 | guest_count = 非數字 "abc" | POST | 預設為 1 或拒絕 |
| A3.8 | 極長名字 (5000 字元) | POST | 不崩潰，正常處理 |
| A3.9 | Unicode/Emoji 名字 | POST "測試🎉👍" | 正常儲存 |
| A3.10 | HTML/XSS 在所有文字欄位 | POST `<script>alert(1)</script>` x4 fields | 全部轉義 |

### A4. CSS / RWD / 視覺

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| A4.1 | 桌面版面配置 (1920x1080) | Lighthouse/Screenshot | 不破版 |
| A4.2 | 手機版面配置 (375x667) | Emulate mobile | 不破版，元素不重疊 |
| A4.3 | 狀態徽章顏色正確 | Screenshot | draft=灰/confirmed=綠/done=藍/cancelled=紅 |
| A4.4 | 載入中旋轉器 (spinner) | Trigger slot load | 出現並消失 |
| A4.5 | 錯誤提醒框樣式 | Trigger error | alert-danger 紅色左邊框 |

---

## 3. 測試類別 B：API 端點測試 (Middle Layer)

### B1. JSON-RPC 端點 - Slots

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| B1.1 | 正常取得 slots (x5 類型 loop) | JSON-RPC POST | 返回 `{slots: [...]}` |
| B1.2 | 帶 resource_id 過濾 | JSON-RPC with param | 只返回該資源的 slots |
| B1.3 | 帶 staff_id 過濾 | JSON-RPC with param | 只返回該員工的 slots |
| B1.4 | 帶兩者過濾 | JSON-RPC with both | 交叉過濾 |
| B1.5 | 無效日期格式 "2026-13-99" | JSON-RPC | `{error: "Invalid date"}` |
| B1.6 | 非字串日期 (數字 12345) | JSON-RPC | 錯誤或優雅處理 |
| B1.7 | 缺少必需參數 date | JSON-RPC | 錯誤回應 |
| B1.8 | 週末日期 (無可用性) | JSON-RPC | `{slots: []}` |
| B1.9 | 排程模式 slot 時段正確性 | 驗證數學 | 9-17 / 1h = 8 slots |
| B1.10 | 排程模式 30m duration | 驗證數學 | 10-18 / 0.5h = 16 slots |
| B1.11 | 排程模式 2h duration, 30m interval | 驗證數學 | 18-22 / 30m步進 = 特定數量 |
| B1.12 | min_booking_hours 過濾 | 查詢今日近時段 | 過近時段不出現 |
| B1.13 | 已被預約 slot 不出現 (staff) | 先建預約再查 | 衝突 slot 排除 |
| B1.14 | 已被預約 slot (resource) 容量遞減 | 建 N 預約再查 | available 數遞減 |
| B1.15 | 資源容量滿 → slot 消失 | 填滿容量再查 | slot 不出現 |
| B1.16 | 跨類型衝突偵測 | 類型 A 預約、查類型 B | 正確偵測衝突 |
| B1.17 | Event 模式 slots | 建 event mode 類型 | 整個時段一個 slot |

### B2. JSON-RPC 端點 - Event Dates

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| B2.1 | 正常月份 event dates | JSON-RPC | 返回 `{dates: [...]}` |
| B2.2 | 1 月 (年初邊界) | JSON-RPC year=2026, month=1 | 正確日期 |
| B2.3 | 12 月 (年末邊界) | JSON-RPC year=2026, month=12 | 正確日期 |
| B2.4 | 2 月 (非閏年) | JSON-RPC year=2026, month=2 | 28 天正確 |
| B2.5 | 2 月 (閏年 2028) | JSON-RPC year=2028, month=2 | 29 天正確 |
| B2.6 | month=0 (無效) | JSON-RPC | 錯誤或空 |
| B2.7 | month=13 (無效) | JSON-RPC | 錯誤或空 |
| B2.8 | 未發佈類型 | JSON-RPC | `{error: ...}` |

### B3. HTTP 路由安全性

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| B3.1 | CSRF protection on POST | POST without CSRF | Odoo 框架阻止 |
| B3.2 | 預約表單 POST 重放 (重複提交) | 同一表單送兩次 | 不建立重複預約或正常處理 |
| B3.3 | Token 暴力破解 | 隨機 token 嘗試 | 全部拒絕 |
| B3.4 | Path traversal in appointment_type_id | `/appointment/../admin` | 404/400 |
| B3.5 | GET 送到 JSON-RPC 端點 | GET /appointment/1/slots | 400 Bad Request |
| B3.6 | 超大 JSON body (1MB) | POST oversized | 400 或 413 |
| B3.7 | 空 JSON body | POST `{}` | 錯誤回應，不崩潰 |
| B3.8 | Content-Type mismatch | POST form-data to JSON | 400 |

### B4. Payment API

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| B4.1 | 無 token 存取付款端點 | POST without token | 拒絕 |
| B4.2 | 錯誤 token 存取 | POST with wrong token | 拒絕 |
| B4.3 | 不需要付款的類型建交易 | POST for free type | `{error: ...}` |
| B4.4 | payment_per_person 計算 | 建 3 人付款預約 | amount = 100 * 3 |
| B4.5 | 付款驗證重導向 | GET /appointment/payment/validate | 正確重導 |

---

## 4. 測試類別 C：後端業務邏輯 (Backend Logic)

### C1. 預約狀態機 (State Machine)

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C1.1 | draft → confirmed | action_confirm | state='confirmed' |
| C1.2 | confirmed → done | action_done | state='done' |
| C1.3 | draft → cancelled | action_cancel | state='cancelled' |
| C1.4 | confirmed → cancelled | action_cancel | state='cancelled' |
| C1.5 | cancelled → draft | action_draft | state='draft' |
| C1.6 | done → draft | action_draft | state='draft' |
| C1.7 | ~~confirmed → draft~~ (無效) | action_draft | 無變化或拒絕 |
| C1.8 | ~~done → confirmed~~ (無效) | action_confirm | 不變 (skip) |
| C1.9 | ~~cancelled → confirmed~~ (無效) | action_confirm | 不變 (skip) |
| C1.10 | ~~draft → done~~ (無效) | action_done | 不變 (skip) |
| C1.11 | 批量確認多筆 | action_confirm on recordset | 全部確認 |

### C2. 衝突偵測 (Conflict Detection)

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C2.1 | 同員工同時段衝突 | 建兩筆同時段 | 第二筆拒絕確認 |
| C2.2 | 同資源同時段容量滿 | 建 capacity+1 筆 | 超額拒絕 |
| C2.3 | 不同員工同時段可並行 | 建兩筆不同員工 | 都可確認 |
| C2.4 | 不同資源同時段可並行 | 建兩筆不同資源 | 都可確認 |
| C2.5 | 部分時段重疊 | 10:00-11:00 vs 10:30-11:30 | 偵測衝突 |
| C2.6 | 相鄰但不重疊 | 10:00-11:00 vs 11:00-12:00 | 不衝突 |
| C2.7 | 跨類型衝突 (同員工) | 類型A→確認、類型B→確認 | 偵測衝突 |
| C2.8 | 跨類型衝突 (同資源) | 同上，資源版 | 偵測衝突 |
| C2.9 | exclude_booking_id 排除自身 | 更新自身預約 | 不誤判自身衝突 |
| C2.10 | cancelled 預約不算衝突 | 建並取消，再建同時段 | 允許 |

### C3. 自動排程演算法

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C3.1 | auto_assign_staff 選最少預約者 | 建多筆不同員工 | 新預約分給最少者 |
| C3.2 | auto_assign_staff 跳過衝突員工 | 員工 A 已滿，員工 B 空 | 分給 B |
| C3.3 | auto_assign_staff 全部衝突 | 所有員工已滿 | staff_user_id 仍空 |
| C3.4 | auto_assign_location 選最少預約場地 | 類似 C3.1 | 場地版 |
| C3.5 | auto_assign_location 跳過滿容量 | 場地 A 滿、B 空 | 分給 B |
| C3.6 | auto_assign_location 全滿 | 所有場地滿 | resource_id 仍空 |
| C3.7 | 月份邊界 (12月→1月) | 12月31日預約 | 計算不跨月 |

### C4. 容量管理 (Capacity)

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C4.1 | 餐廳桌位 capacity=4 填滿 | 建 4 筆 guest_count=1 | 全部確認 |
| C4.2 | 第 5 筆拒絕 | 建第 5 筆 | UserError |
| C4.3 | guest_count=3 佔 3 容量 | 建 1 筆 count=3，再 1 筆 count=2 | 第二筆拒絕 |
| C4.4 | 取消後容量釋放 | 取消 1 筆，再建 | 可建立 |
| C4.5 | total_capacity 計算 | 3桌 4+6+8 | total=18 |
| C4.6 | max_concurrent_bookings 限制 | 設定限制 | 超過拒絕 |

### C5. 時間規則

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C5.1 | min_booking_hours (2h) | 預約 1.5h 後時段 | 拒絕 |
| C5.2 | min_booking_hours (2h) | 預約 2.5h 後時段 | 允許 |
| C5.3 | max_booking_days (30) | 預約 31 天後 | 拒絕或不出現 |
| C5.4 | max_booking_days (30) | 預約 29 天後 | 允許 |
| C5.5 | cancel_before_hours (24h) | 取消 23h 前預約 | UserError |
| C5.6 | cancel_before_hours (24h) | 取消 25h 前預約 | 允許 |
| C5.7 | cancel_before_hours = 0 | 隨時取消 | 允許 |
| C5.8 | 過去日期預約 | submit 過去日期 | 拒絕 |
| C5.9 | 端午假日 (無可用性) | 查無排程日 | 空 slots |
| C5.10 | timezone 正確轉換 | Europe/Brussels vs UTC | 時段數量不同 |

### C6. 日曆事件整合

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C6.1 | 確認建立 calendar.event | action_confirm | calendar_event_id 非空 |
| C6.2 | 取消刪除 calendar.event | action_cancel | calendar.event 被刪 |
| C6.3 | 事件名稱 XSS 安全 | 含 `<script>` 名字 | 轉義後存儲 |
| C6.4 | 事件描述包含所有欄位 | 確認後讀 description | 含 Guest/Email/Phone |
| C6.5 | 有員工時 user_id 正確 | 有 staff 的預約 | event.user_id = staff |
| C6.6 | 無員工時 user_id 為當前用戶 | 無 staff 的預約 | event.user_id = env.user |
| C6.7 | 有 partner 時加入 attendees | 有 partner 的預約 | partner_ids 含 partner |
| C6.8 | 重複確認不重複建事件 | 確認→ 再確認 | 只有一個 event |

### C7. Email 通知

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C7.1 | 確認寄送確認信 | action_confirm | mail.mail 建立 |
| C7.2 | 取消寄送取消信 | action_cancel | mail.mail 建立 |
| C7.3 | cron 提醒信 (24h window) | 建 23h 後預約，呼叫 cron | 有寄信 |
| C7.4 | cron 不提醒 25h 後預約 | 建 25h 後預約，呼叫 cron | 無寄信 |
| C7.5 | cron 不提醒已過期預約 | 建過去預約，呼叫 cron | 無寄信 |
| C7.6 | 無 email 不崩潰 | guest_email 空 | 跳過不報錯 |
| C7.7 | email template 不存在不崩潰 | 刪除 template ref | 跳過不報錯 |

### C8. Sequence & Token

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C8.1 | 序號遞增 | 建連續 3 筆 | APT00001 → APT00002 → APT00003 |
| C8.2 | Token 唯一性 | 建 20 筆 | 所有 token 不重複 |
| C8.3 | Token 長度 | 建 1 筆 | len >= 32 |
| C8.4 | Token 字元集 | 建 1 筆 | URL-safe chars only |
| C8.5 | Token 不可預測 | 連續 2 筆 | 無模式可預測 |

### C9. 約束驗證 (Constraints)

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C9.1 | end_datetime <= start_datetime | create with bad dates | ValidationError |
| C9.2 | guest_count = 0 | create with 0 | ValidationError |
| C9.3 | guest_count = -5 | create with -5 | ValidationError |
| C9.4 | slot_duration = 0 (scheduled) | write to type | ValidationError |
| C9.5 | max_booking_days = 0 | write to type | ValidationError |
| C9.6 | availability hour_from >= hour_to | create avail | ValidationError |
| C9.7 | availability hour > 24 | create avail | ValidationError |
| C9.8 | slot capacity = 0 | create slot | ValidationError |

### C10. Partner/Contact 管理

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| C10.1 | 新 email 建立新 partner | submit 新 email | res.partner 新建 |
| C10.2 | 重複 email 複用既有 partner | submit 已有 email | 不重複建立 |
| C10.3 | partner 資料正確 | 查新建 partner | name/email/phone 正確 |

---

## 5. 測試類別 D：全類型迴圈極限測試 (Per-Type Loop)

對所有 5 種預約類型各執行一整套預約流程：

### D1. 完整流程迴圈 (x5 類型)

```
for each of 5 appointment types:
    D1.1: GET listing page → 該類型出現
    D1.2: GET detail page → 正確資訊
    D1.3: GET schedule page → 日曆渲染
    D1.4: JSON-RPC get slots → 返回正確數量
    D1.5: POST booking form → 預約建立
    D1.6: 驗證 state=draft 或 confirmed (auto_confirm)
    D1.7: 驗證 token/name/partner
    D1.8: GET confirm page → 正確資訊
    D1.9: 取消預約 → 狀態變更
    D1.10: GET cancelled page → 確認顯示
    cleanup: 刪除測試預約
```

### D2. 特定類型專屬測試

| ID | 類型 | 測試 | 通過標準 |
|----|------|------|----------|
| D2.1 | Restaurant | 填滿 Table 1 (cap=4)，驗 slot available 遞減 | available: 4→3→2→1→0 |
| D2.2 | Restaurant | Table 1 滿後，Table 2 仍可用 | 不同資源不影響 |
| D2.3 | Restaurant | FAQ 問題在 schedule 頁顯示 | 含 "dietary" 和 "occasion" |
| D2.4 | Tennis | 7 天窗口限制 | 第 8 天不出現 |
| D2.5 | Tennis | 週末時段不同 (Sat 8-20) | slot 數量正確 |
| D2.6 | Business Meeting | auto_assign_staff | 員工自動分配 |
| D2.7 | Business Meeting | 24h cancel deadline | 驗時限 |
| D2.8 | Video Consultation | 30m slots | 10-18 = 16 slots |
| D2.9 | Video Consultation | 14 天限制 | 第 15 天不出現 |
| D2.10 | Expert Consultation | require_payment flow | payment_status=pending |
| D2.11 | Expert Consultation | 付款金額計算 (per_person) | 3 人 = 300 USD |
| D2.12 | Expert Consultation | 未付款不可確認 | UserError |

---

## 6. 測試類別 E：邊緣極限測試 (Edge Cases)

### E1. 數值邊界

| ID | 測試案例 | 輸入 | 通過標準 |
|----|----------|------|----------|
| E1.1 | guest_count = 1 (最小值) | 1 | 允許 |
| E1.2 | guest_count = 100 (上限) | 100 | 允許 |
| E1.3 | guest_count = 101 | 101 | 拒絕 |
| E1.4 | guest_count = MAX_INT | 2147483647 | 拒絕 |
| E1.5 | guest_count = 浮點數 1.5 | 1.5 | 截斷為 1 或拒絕 |
| E1.6 | duration = 0.25 (15min) | slot_duration=0.25 | 正確 slot 數 |
| E1.7 | duration = 8.0 (整天) | slot_duration=8.0 | 1 slot per window |

### E2. 字串邊界

| ID | 測試案例 | 輸入 | 通過標準 |
|----|----------|------|----------|
| E2.1 | 空白名字 " " | spaces only | 拒絕或修剪 |
| E2.2 | 1 字元名字 "A" | single char | 允許 |
| E2.3 | 5000 字元名字 | "A" * 5000 | 不崩潰 |
| E2.4 | SQL injection in name | `'; DROP TABLE--` | 安全處理 |
| E2.5 | Unicode 全字集 | 中文/日文/韓文/阿拉伯文/emoji | 正確存儲 |
| E2.6 | NULL bytes in string | `\x00` embedded | 不崩潰 |
| E2.7 | HTML in notes | `<b>bold</b><img onerror=...>` | 安全 |
| E2.8 | 超長 email (254 chars) | RFC 5321 max | 允許或拒絕 |

### E3. 時間邊界

| ID | 測試案例 | 時間 | 通過標準 |
|----|----------|------|----------|
| E3.1 | 預約在午夜 00:00 | 00:00-01:00 | 正確處理 |
| E3.2 | 預約跨午夜 23:00-01:00 | 跨日 | 正確或拒絕 |
| E3.3 | 整日預約 0:00-23:59 | full day | 正確處理 |
| E3.4 | start = end (零時長) | same datetime | ValidationError |
| E3.5 | 1 分鐘預約 | 10:00-10:01 | 允許 |
| E3.6 | 遠未來預約 (2099年) | 2099-12-31 | 可能拒絕 (max_booking_days) |
| E3.7 | DST 轉換日 (Spring forward) | 2026-03-29 02:30 CET | 不崩潰 |
| E3.8 | DST 轉換日 (Fall back) | 2026-10-25 02:30 CET | 不崩潰 |
| E3.9 | Feb 29 2028 (閏年) | 2028-02-29 | 正確處理 |
| E3.10 | Feb 29 2026 (非閏年) | 2026-02-29 | 拒絕無效日期 |

### E4. 併發與競態

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| E4.1 | 2 人同時搶同 slot | 並行 POST | 只有 1 人成功確認 |
| E4.2 | 100 筆快速建立 | 迴圈建立 | 全部成功，序號正確 |
| E4.3 | 同 email 同時提交 | 並行 POST same email | 不建重複 partner |
| E4.4 | 建立→立刻取消→立刻重建 | 連續操作 | 狀態一致 |
| E4.5 | 10 個 API 請求同時呼叫 slots | 並行 JSON-RPC | 全部返回，不超時 |

---

## 7. 測試類別 F：資料完整性與安全 (Security & Integrity)

### F1. Access Control

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| F1.1 | Public 用戶只能讀 appointment.type | XML-RPC as public | 無 write 權限 |
| F1.2 | Public 用戶可建立 booking | XML-RPC as public | create 允許 |
| F1.3 | Public 不能 write 他人 booking | XML-RPC as public | AccessError |
| F1.4 | Public 不能 unlink booking | XML-RPC as public | AccessError |
| F1.5 | User 只看到自己的 bookings | 建 2 user 各有預約 | 各只看到自己 |
| F1.6 | Manager 看到所有 bookings | Manager 查詢 | 全部返回 |

### F2. Token 安全

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| F2.1 | 正確 token 存取確認頁 | GET with correct token | 200, 顯示資料 |
| F2.2 | 錯誤 token 存取確認頁 | GET with wrong token | 不顯示資料 |
| F2.3 | 空 token 存取確認頁 | GET without token | 不顯示資料 |
| F2.4 | 其他預約的 token | GET with other booking's token | 不顯示資料 |
| F2.5 | Token 枚舉保護 | 嘗試 100 random tokens | 全部失敗 |

### F3. Record Rules

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| F3.1 | 未發佈類型對 public 不可見 | search with public user | 不返回 |
| F3.2 | 已發佈類型對 public 可讀 | search with public user | 返回 |
| F3.3 | User 看不到他人建的 booking | search as user B | 不返回 user A 的 |

---

## 8. 測試類別 G：穩定度與效能 (Stability & Performance)

### G1. 批量操作

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| G1.1 | 建立 100 筆預約 | loop create | 全部成功，< 60s |
| G1.2 | 批量確認 50 筆 | action_confirm on 50 | 全部確認 |
| G1.3 | 批量取消 50 筆 | action_cancel on 50 | 全部取消 |
| G1.4 | 查詢 1000+ bookings | search with limit | < 5s 回應 |
| G1.5 | 有 500 筆預約時取 slots | JSON-RPC | < 3s 回應 |

### G2. 錯誤恢復

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| G2.1 | 刪除 calendar.event 後查預約 | 手動刪 event | 不崩潰 |
| G2.2 | 刪除 partner 後查預約 | unlink partner | 不崩潰 (ondelete='set null') |
| G2.3 | 停用 appointment.type 後查預約 | active=False | 預約仍可讀 |
| G2.4 | 刪除 resource 後查預約 | unlink resource | 預約仍可讀 (set null) |
| G2.5 | email template 遺失不影響確認 | 刪除 template | action_confirm 仍成功 |

### G3. 模組升級冪等性

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| G3.1 | 重複升級不報錯 | `-u reservation_module` x2 | 兩次都成功 |
| G3.2 | 升級後資料保留 | 建資料 → 升級 → 檢查 | 資料完整 |
| G3.3 | cron 不重複建立 | 升級兩次 | 只有 1 個 cron |

---

## 9. 測試類別 H：後台管理介面 (Backend Admin)

### H1. 後台表單

| ID | 測試案例 | 方法 | 通過標準 |
|----|----------|------|----------|
| H1.1 | appointment.type form 所有 tab 載入 | Browser navigate | 不報錯 |
| H1.2 | appointment.booking form 載入 | Browser navigate | 不報錯 |
| H1.3 | 預約 kanban 卡片顯示 | Browser navigate | 卡片渲染正確 |
| H1.4 | 預約日曆視圖 | Browser navigate | 事件顯示 |
| H1.5 | 資源列表 | Browser navigate | 含容量和預約數 |
| H1.6 | 搜尋過濾器 (全部) | 使用每個 filter | 結果正確 |
| H1.7 | 分組功能 | Group by type/status/date | 分組正確 |

---

## 10. 測試執行策略

### 10.1 自動化測試 (Python Script)

```
test_suite/
├── test_runner.py          # 主執行器 (multi-loop)
├── test_frontend.py        # A 類：前端 (HTTP + Browser)
├── test_api.py             # B 類：API 端點
├── test_backend.py         # C 類：後端邏輯
├── test_per_type.py        # D 類：全類型迴圈
├── test_edge_cases.py      # E 類：邊緣極限
├── test_security.py        # F 類：安全
├── test_stability.py       # G 類：穩定度
└── test_backend_admin.py   # H 類：後台管理
```

### 10.2 手動測試清單 (Manual Checklist)

需要人工操作的項目：
- [ ] 真實瀏覽器中完整預約流程 (5 類型各走一遍)
- [ ] 手機瀏覽器測試 (Safari iOS / Chrome Android)
- [ ] 中文/英文切換所有頁面
- [ ] 後台管理介面所有操作
- [ ] 真實付款流程 (如有 payment provider 配置)
- [ ] 多用戶並行操作

### 10.3 通過標準

| 等級 | 標準 |
|------|------|
| **GO** | 0 CRITICAL, 0 HIGH, ≤3 MEDIUM failures |
| **CONDITIONAL GO** | 0 CRITICAL, ≤2 HIGH (有修復計畫) |
| **NO GO** | 任何 CRITICAL，或 >2 HIGH |

### 10.4 測試案例統計

| 類別 | 自動化 | 手動 | 合計 |
|------|--------|------|------|
| A. 前端瀏覽器 | 20 | 15 | 35 |
| B. API 端點 | 30 | 0 | 30 |
| C. 後端邏輯 | 65 | 0 | 65 |
| D. 全類型迴圈 | 22 | 0 | 22 |
| E. 邊緣極限 | 30 | 0 | 30 |
| F. 安全 | 14 | 0 | 14 |
| G. 穩定度 | 13 | 0 | 13 |
| H. 後台管理 | 0 | 7 | 7 |
| **合計** | **194** | **22** | **216** |
