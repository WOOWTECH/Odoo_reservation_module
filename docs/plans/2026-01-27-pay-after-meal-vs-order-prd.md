# PRD: 自助點餐結帳模式 - 餐點結/整單結

## 概述

### 背景
Odoo 18 企業版提供了兩種自助點餐的付款時機選項：
- **餐點結 (Pay after each meal)**：每次送出訂單後立即付款
- **整單結 (Pay after entire order)**：可持續點餐，最後統一結帳（企業版功能）

本 PRD 規劃將「整單結」功能引入社區版，讓店家可以在後台自由選擇付款模式。

### 目標
- 在 POS 設定頁面新增「付款時機」選項
- 實作「整單結」模式的完整流程
- 保持與現有「餐點結」模式的相容性

---

## 功能需求

### 1. 後台設定 (POS Configuration)

#### 1.1 新增欄位
| 欄位名稱 | 技術名稱 | 類型 | 說明 |
|---------|---------|------|------|
| 付款時機 | `self_ordering_pay_after` | Selection | 選項：'meal' (餐點結) / 'order' (整單結) |

#### 1.2 設定位置
- 路徑：POS 營業點 > 設定 > POS 營業點 分頁 > 自助下單區塊
- 位置：在現有的「服務位置」欄位下方

#### 1.3 UI 呈現
```
付款時機
○ 餐點 (每次送出後付款)
◉ 整單 (用餐結束後統一付款)
```

---

### 2. 客戶端流程

#### 2.1 餐點結模式 (現有行為)
```
首頁 → 點餐 → 購物車 → 送出 → 付款 → 確認頁 → 結束
                                              ↓
                                         (可選) 繼續點餐
```

#### 2.2 整單結模式 (新功能)
```
首頁 → 點餐 → 購物車 → 送出 → 確認頁 → 返回首頁
  ↑                              ↓
  ←──────── 繼續點餐 ←───────────┘

最後結帳：首頁 → 我的訂單 → 查看累積項目 → 結帳付款 → 完成
```

---

### 3. 頁面變更

#### 3.1 確認頁 (Confirmation Page)

**整單結模式下的變更：**
- 隱藏付款相關按鈕
- 顯示「返回首頁」按鈕
- 顯示提示訊息：「餐點已送出，您可以繼續點餐或前往『我的訂單』結帳」

**UI 設計：**
```
┌─────────────────────────────────┐
│      訂單已送出！               │
│      訂單編號: #00003-001-0014  │
│                                 │
│   餐點已送至廚房準備中          │
│   您可以繼續點餐或前往          │
│   「我的訂單」統一結帳          │
│                                 │
│   ┌─────────────────────────┐   │
│   │       返回首頁          │   │
│   └─────────────────────────┘   │
│                                 │
│   ┌─────────────────────────┐   │
│   │       我的訂單          │   │
│   └─────────────────────────┘   │
└─────────────────────────────────┘
```

#### 3.2 我的訂單頁 (Order History Page)

**整單結模式下的變更：**
- 顯示本次用餐所有已送出的訂單項目
- 顯示累積總金額
- 新增「結帳」按鈕

**UI 設計：**
```
┌─────────────────────────────────┐
│  我的訂單                       │
│                                 │
│  ── 第一次點餐 ──               │
│  乳酪漢堡 x1          NT$ 14    │
│  可口可樂 x2          NT$ 4     │
│                                 │
│  ── 第二次點餐 ──               │
│  培根漢堡 x1          NT$ 17    │
│  冰茶 x1              NT$ 2     │
│                                 │
│  ─────────────────────────────  │
│  總計                 NT$ 37    │
│                                 │
│   ┌─────────────────────────┐   │
│   │       結帳付款          │   │
│   └─────────────────────────┘   │
│                                 │
│   ┌─────────────────────────┐   │
│   │       繼續點餐          │   │
│   └─────────────────────────┘   │
└─────────────────────────────────┘
```

#### 3.3 首頁 (Landing Page)

**整單結模式下的變更：**
- 「繼續點餐」按鈕邏輯維持不變（有未結帳訂單時顯示）
- 「我的訂單」按鈕維持不變

---

### 4. 技術規格

#### 4.1 後端模型 (Python)

**檔案：** `models/pos_config.py`

```python
from odoo import fields, models

class PosConfig(models.Model):
    _inherit = 'pos.config'

    self_ordering_pay_after = fields.Selection(
        selection=[
            ('meal', 'Per Meal'),
            ('order', 'Per Order'),
        ],
        string='Pay After',
        default='meal',
        help='When customers should pay in self-ordering mode'
    )
```

#### 4.2 後端視圖 (XML)

**檔案：** `views/pos_config_views.xml`

```xml
<record id="pos_config_view_form_inherit" model="ir.ui.view">
    <field name="name">pos.config.form.inherit.pay.after</field>
    <field name="model">pos.config</field>
    <field name="inherit_id" ref="pos_self_order.pos_config_view_form"/>
    <field name="arch" type="xml">
        <xpath expr="//field[@name='self_ordering_service_mode']" position="after">
            <field name="self_ordering_pay_after" widget="radio"
                   invisible="self_ordering_mode == 'nothing'"/>
        </xpath>
    </field>
</record>
```

#### 4.3 前端 JavaScript

**檔案：** `static/src/app/pages/confirmation_page/confirmation_page.js`

```javascript
patch(ConfirmationPage.prototype, {
    get isPayPerOrder() {
        return this.selfOrder.config.self_ordering_pay_after === 'order';
    },

    goToLanding() {
        this.router.navigate("landing");
    },

    goToMyOrders() {
        this.router.navigate("order_history");
    },
});
```

**檔案：** `static/src/app/pages/order_history_page/order_history_page.js`

```javascript
patch(OrderHistoryPage.prototype, {
    get isPayPerOrder() {
        return this.selfOrder.config.self_ordering_pay_after === 'order';
    },

    get totalAmount() {
        // 計算所有未付款訂單的總金額
        return this.unpaidOrders.reduce((sum, order) => sum + order.amount_total, 0);
    },

    get unpaidOrders() {
        // 獲取所有未付款的訂單
        return this.orders.filter(order => order.state !== 'paid');
    },

    async checkout() {
        // 導航到付款頁面，合併所有未付款訂單
        this.router.navigate("payment");
    },
});
```

#### 4.4 前端模板 (XML)

**檔案：** `static/src/app/pages/confirmation_page/confirmation_page.xml`

```xml
<!-- 整單結模式：顯示返回首頁和我的訂單按鈕 -->
<t t-if="isPayPerOrder">
    <div class="d-flex flex-column gap-3 mt-4">
        <p class="text-center text-muted">
            餐點已送至廚房準備中<br/>
            您可以繼續點餐或前往「我的訂單」統一結帳
        </p>
        <button class="btn btn-lg btn-primary" t-on-click="goToLanding">
            返回首頁
        </button>
        <button class="btn btn-lg btn-secondary" t-on-click="goToMyOrders">
            我的訂單
        </button>
    </div>
</t>
```

**檔案：** `static/src/app/pages/order_history_page/order_history_page.xml`

```xml
<!-- 整單結模式：顯示結帳按鈕 -->
<t t-if="isPayPerOrder and unpaidOrders.length > 0">
    <div class="checkout-section">
        <div class="total-amount">
            總計: <t t-esc="formatCurrency(totalAmount)"/>
        </div>
        <button class="btn btn-lg btn-primary w-100" t-on-click="checkout">
            結帳付款
        </button>
    </div>
</t>
```

---

### 5. 檔案結構

```
addons/pos_self_order_enhancement/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── pos_config.py                    # 新增
├── views/
│   └── pos_config_views.xml             # 新增
├── i18n/
│   ├── pos_self_order_enhancement.pot
│   └── zh_TW.po
└── static/src/app/pages/
    ├── cart_page/
    │   └── cart_page.js
    ├── landing_page/
    │   ├── landing_page.js
    │   └── landing_page.xml
    ├── confirmation_page/
    │   ├── confirmation_page.js         # 新增
    │   └── confirmation_page.xml        # 新增
    └── order_history_page/
        ├── order_history_page.js        # 新增
        └── order_history_page.xml       # 新增
```

---

### 6. 翻譯字串

| 英文 | 繁體中文 |
|------|---------|
| Pay After | 付款時機 |
| Per Meal | 餐點 |
| Per Order | 整單 |
| Go to Home | 返回首頁 |
| My Orders | 我的訂單 |
| Checkout | 結帳付款 |
| Continue Ordering | 繼續點餐 |
| Total | 總計 |
| Your order has been sent to kitchen | 餐點已送至廚房準備中 |
| You can continue ordering or go to "My Orders" to checkout | 您可以繼續點餐或前往「我的訂單」統一結帳 |

---

## 實作步驟

### 階段一：後端設定
1. 建立 `models/pos_config.py` 新增 `self_ordering_pay_after` 欄位
2. 建立 `views/pos_config_views.xml` 新增設定介面
3. 更新 `__manifest__.py` 註冊新檔案
4. 測試後台設定功能

### 階段二：確認頁修改
1. 建立 `confirmation_page.js` 新增邏輯判斷
2. 建立 `confirmation_page.xml` 新增 UI 模板
3. 測試整單結模式下的確認頁行為

### 階段三：我的訂單頁修改
1. 建立 `order_history_page.js` 新增結帳邏輯
2. 建立 `order_history_page.xml` 新增結帳 UI
3. 測試訂單累積和結帳流程

### 階段四：整合測試
1. 測試餐點結模式（確保現有功能正常）
2. 測試整單結模式完整流程
3. 測試模式切換
4. 更新翻譯檔案

---

## 風險與考量

### 技術風險
| 風險 | 影響 | 緩解措施 |
|------|------|---------|
| 企業版欄位已存在 | 可能與企業版衝突 | 檢查欄位是否已存在，若存在則不重複建立 |
| 訂單合併邏輯複雜 | 付款時可能出錯 | 詳細測試多訂單合併場景 |
| 前端狀態管理 | 頁面切換時狀態丟失 | 使用 selfOrder service 維護狀態 |

### 業務考量
| 考量 | 說明 |
|------|------|
| 客戶跑單風險 | 整單結模式下客戶可能未付款就離開，建議搭配桌號管理 |
| 廚房出餐順序 | 多次點餐可能造成廚房混亂，建議顯示訂單批次 |

---

## 成功指標

1. **功能完整性**：兩種模式都能正常運作
2. **向後相容**：不影響現有「餐點結」模式的使用者
3. **使用者體驗**：流程清晰，客戶能理解如何操作
4. **設定簡易**：店家能輕鬆在後台切換模式

---

## 附錄

### A. 參考資料
- Odoo 18 企業版 POS Self Order 模組
- 現有 `pos_self_order_enhancement` 模組程式碼

### B. 相關截圖
- 企業版設定頁面截圖（見 `.vibe-images/4e5f388c-...`）
