# Task Plan: odoo_calendar_enhance 模組實作

## Goal
根據 PRD_calendar_booking.md 完整實作 Odoo 18 日曆預約增強模組，包含後台管理和前台預約功能。

## Current Phase
Phase 3: 前台預約頁面

## Phases

### Phase 1: 後台核心功能 `complete`
- [x] 1.1 完善 appointment.type 模型（新增缺失欄位）
- [x] 1.2 完善 appointment_type_views.xml（四個頁籤表單）
- [x] 1.3 建立預約類型 Kanban 視圖
- [x] 1.4 建立資源預訂 Gantt 視圖
- [x] 1.5 建立員工預訂 Gantt 視圖
- [x] 1.6 完善選單和動作

### Phase 2: 資料模型完善 `complete`
- [x] 2.1 完善 appointment.booking 模型
- [x] 2.2 完善 appointment.question 模型
- [x] 2.3 完善 appointment.answer 模型
- [x] 2.4 擴展 resource.resource 模型（容量欄位）
- [x] 2.5 建立可用時間模型 (appointment.slot)
- [x] 2.6 建立可用性模型 (appointment.availability)

### Phase 3: 前台預約頁面 `complete`
- [x] 3.1 預約類型選擇頁面 (appointment_list template)
- [x] 3.2 日曆/時段選擇頁面 (appointment_schedule_page + JS)
- [x] 3.3 預約資訊填寫頁面 (appointment_book_page template)
- [x] 3.4 預約確認頁面 (appointment_confirm_page template)
- [x] 3.5 預約管理頁面（改期/取消）(appointment_booking_page, cancel templates)

### Phase 4: 控制器和 API `complete`
- [x] 4.1 完善 controllers/main.py
- [x] 4.2 時段 API（取得可用時段）
- [x] 4.3 預約 API（建立/修改/取消）

### Phase 5: 測試和優化 `complete`
- [x] 5.1 建立示範資料 (demo/appointment_demo.xml)
- [x] 5.2 測試完整預約流程
- [x] 5.3 模組結構完整

## Key Decisions
| Decision | Rationale |
|----------|-----------|
| 使用 Odoo 標準 Gantt 視圖 | 減少自訂 JavaScript，利用 Odoo 18 內建功能 |
| 前台使用 website 模板 | 確保與 Odoo 網站主題整合 |
| 資源容量使用 resource.resource 擴展 | 重用 Odoo 資源模組 |

## Files Modified
| File | Status | Notes |
|------|--------|-------|
| models/appointment_type.py | 待更新 | 新增缺失欄位 |
| views/appointment_type_views.xml | 待更新 | 四個頁籤表單 |
| views/appointment_menus.xml | 待更新 | 完善選單 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| (none yet) | | |

## Notes
- PRD 版本: 1.2 (2026-01-29)
- 參考來源: demo.odoo.com + woowtech.odoo.com
