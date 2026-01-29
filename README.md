# Reservation Booking Enhancement / 預約管理系統

## English

### Overview

A complete appointment booking system for Odoo 18 Community Edition, providing enterprise-level reservation management capabilities.

### Features

- **Multiple Appointment Types**: Meetings, video calls, table bookings, resource reservations, and paid consultations
- **Resource & Staff Management**: Manage availability of rooms, tables, equipment, and staff members
- **Online Booking Portal**: Beautiful public-facing booking pages for customers
- **Payment Integration**: Collect payments upfront with Odoo's payment providers
- **Auto Confirmation**: Automatically confirm bookings based on capacity rules
- **Email Notifications**: Automatic confirmation and reminder emails
- **Multi-language Support**: English, Traditional Chinese (zh_TW), Simplified Chinese (zh_CN)

### Appointment Types

| Type | Description | Use Case |
|------|-------------|----------|
| Meeting | Book time with staff members | Consultations, interviews |
| Video Call | Virtual meeting scheduling | Remote consultations |
| Table Booking | Reserve tables at restaurants | Restaurants, bars |
| Resource Booking | Book rooms, courts, equipment | Meeting rooms, sports facilities |
| Paid Consultation | Paid time slots with professionals | Legal, medical consultations |
| Paid Seat | Per-person booking with payment | Events, theaters, tours |

### Installation

1. Copy the `odoo_calendar_enhance` folder to your Odoo addons directory
2. Update the apps list in Odoo
3. Install "Reservation Booking Enhancement" from the Apps menu

### Dependencies

- `calendar` (Odoo core)
- `resource` (Odoo core)
- `website` (Odoo core)
- `payment` (Odoo core)
- `mail` (Odoo core)

### Configuration

1. Go to **Reservation > Appointments** to create appointment types
2. Configure availability schedules for each appointment type
3. Add resources or staff members as needed
4. Set up payment options if required
5. Publish appointment types to make them available on the website

### Usage

#### Backend
- Access the module via the **Reservation** menu
- Manage appointment types, bookings, resources, and staff
- View bookings in list, calendar, or kanban views

#### Frontend
- Customers can access the booking portal at `/appointment`
- Select appointment type, date/time, and complete booking form
- Receive confirmation email after booking

### License

LGPL-3

### Support

For support, please contact us at support@woowtech.com or visit https://woowtech.com

---

## 繁體中文

### 概述

適用於 Odoo 18 社群版的完整預約管理系統，提供企業級的預約管理功能。

### 功能特色

- **多種預約類型**：會議、視訊通話、餐桌預訂、資源預約、付費諮詢
- **資源與員工管理**：管理房間、桌位、設備和員工的可用時間
- **線上預約入口**：為客戶提供美觀的公開預約頁面
- **付款整合**：透過 Odoo 的付款服務商預先收取款項
- **自動確認**：根據容量規則自動確認預約
- **電子郵件通知**：自動發送確認和提醒郵件
- **多語言支援**：英文、繁體中文（zh_TW）、簡體中文（zh_CN）

### 預約類型

| 類型 | 說明 | 使用情境 |
|------|------|----------|
| 會議 | 與員工預約時間 | 諮詢、面試 |
| 視訊通話 | 虛擬會議排程 | 遠端諮詢 |
| 餐桌預訂 | 預訂餐廳桌位 | 餐廳、酒吧 |
| 資源預訂 | 預訂房間、場地、設備 | 會議室、運動設施 |
| 付費諮詢 | 與專業人士的付費時段 | 法律、醫療諮詢 |
| 付費座位 | 按人數收費的預約 | 活動、劇院、旅遊 |

### 安裝方式

1. 將 `odoo_calendar_enhance` 資料夾複製到您的 Odoo 附加模組目錄
2. 在 Odoo 中更新應用程式列表
3. 從應用程式選單安裝「預約管理系統」

### 相依模組

- `calendar`（Odoo 核心）
- `resource`（Odoo 核心）
- `website`（Odoo 核心）
- `payment`（Odoo 核心）
- `mail`（Odoo 核心）

### 設定

1. 前往 **預約 > 預約類型** 建立預約類型
2. 為每種預約類型設定可用時間表
3. 根據需要新增資源或員工
4. 如需要，設定付款選項
5. 發佈預約類型使其在網站上可用

### 使用方式

#### 後台
- 透過 **預約** 選單存取模組
- 管理預約類型、預約訂單、資源和員工
- 以列表、日曆或看板檢視預約

#### 前台
- 客戶可在 `/appointment` 存取預約入口
- 選擇預約類型、日期/時間，並填寫預約表單
- 預約後收到確認電子郵件

### 授權條款

LGPL-3

### 技術支援

如需支援，請聯繫 support@woowtech.com 或訪問 https://woowtech.com

---

© 2026 WoowTech. All rights reserved.
