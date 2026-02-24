# 預約付款功能整合設計

## 概述

整合 Odoo 標準 payment 模組到預約系統，讓用戶可以使用電匯或綠界 ECPay 完成預約付款。

## 現況分析

### 已有的基礎設施
- `appointment.booking` 模型有 `payment_status`, `payment_amount`, `payment_transaction_id` 欄位
- `appointment.type` 模型有 `require_payment`, `payment_amount` 等設定
- 付款頁面 `/appointment/booking/<id>/pay` 已存在但按鈕無功能
- 系統已啟用兩個付款供應商：
  - 電匯 (Wire Transfer, code: `custom`)
  - 綠界 ECPay (code: `ECPay`)

### 問題
付款頁面的按鈕只是靜態 `<button>`，沒有連接到 Odoo payment 流程。

## 設計方案

### 架構：使用 Odoo 標準 Payment Form

參考 `website_sale` 模組的實作方式，整合 `payment.form` 模板：

```
用戶點擊付款按鈕
    ↓
顯示 Odoo payment.form（列出可用付款方式）
    ↓
用戶選擇付款方式並提交
    ↓
建立 payment.transaction
    ↓
[電匯] 顯示銀行資訊，等待管理員確認
[ECPay] 跳轉綠界付款頁面
    ↓
付款成功回調
    ↓
更新 booking.payment_status = 'paid'
    ↓
自動確認預約（如啟用）
```

### 需要實作的部分

#### 1. 控制器路由

```python
# 付款頁面 - 整合 payment.form
@http.route('/appointment/booking/<int:booking_id>/pay', ...)
def appointment_payment(self, booking_id, token=None, **kwargs):
    # 準備 payment form 所需的 context
    # - providers_sudo: 可用的付款供應商
    # - payment_methods_sudo: 可用的付款方式
    # - amount, currency, partner_id
    # - transaction_route, landing_route

# 建立交易
@http.route('/appointment/payment/transaction/<int:booking_id>', type='json', ...)
def appointment_payment_transaction(self, booking_id, **kwargs):
    # 建立 payment.transaction
    # 關聯到 booking

# 付款完成驗證
@http.route('/appointment/payment/validate', ...)
def appointment_payment_validate(self, **kwargs):
    # 檢查交易狀態
    # 更新 booking.payment_status
    # 重導向到確認頁面
```

#### 2. 模板修改

將 `appointment_payment_page` 模板改為呼叫 `payment.form`：

```xml
<t t-call="payment.form">
    <t t-set="reference_prefix" t-value="'APPT-%s' % booking.id"/>
    <t t-set="amount" t-value="booking.payment_amount"/>
    <t t-set="currency" t-value="booking.currency_id"/>
    <t t-set="partner_id" t-value="booking.partner_id.id"/>
    <t t-set="transaction_route" t-value="'/appointment/payment/transaction/%s' % booking.id"/>
    <t t-set="landing_route" t-value="'/appointment/payment/validate'"/>
    ...
</t>
```

#### 3. 交易回調處理

監聽 `payment.transaction` 狀態變更，自動更新預約狀態：

```python
class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    appointment_booking_id = fields.Many2one('appointment.booking')

    def _post_process_after_done(self):
        super()._post_process_after_done()
        # 更新關聯的預約付款狀態
        if self.appointment_booking_id:
            self.appointment_booking_id.payment_status = 'paid'
            if self.appointment_booking_id.appointment_type_id.auto_confirm:
                self.appointment_booking_id.action_confirm()
```

## 檔案變更清單

1. **controllers/main.py**
   - 修改 `appointment_payment()` 方法
   - 新增 `appointment_payment_transaction()` 路由
   - 新增 `appointment_payment_validate()` 路由

2. **views/appointment_templates.xml**
   - 修改 `appointment_payment_page` 模板，整合 `payment.form`

3. **models/payment_transaction.py** (新檔案)
   - 繼承 `payment.transaction`
   - 新增 `appointment_booking_id` 欄位
   - 覆寫 `_post_process_after_done()` 方法

4. **models/__init__.py**
   - 匯入新的 payment_transaction 模型

5. **__manifest__.py**
   - 確保依賴 `payment` 模組

## 測試計劃

1. 電匯流程：
   - 選擇電匯 → 顯示銀行資訊 → 後台確認收款 → 預約自動確認

2. ECPay 流程：
   - 選擇 ECPay → 跳轉綠界 → 完成付款 → 回調更新狀態 → 預約自動確認

3. 邊界情況：
   - 付款失敗處理
   - 重複付款防護
   - 過期預約不可付款
