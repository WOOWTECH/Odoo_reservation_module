#!/usr/bin/env python3
"""
商業壓力測試數據生成器
建立 6 種預約類型 + 30 種產品 + 4 個客戶 + 50-100 筆預約記錄
"""
import xmlrpc.client
import random
import secrets
from datetime import datetime, timedelta

# === Odoo Connection ===
URL = 'http://localhost:9073'
DB = 'odooreservation'
USERNAME = 'admin'
PASSWORD = 'admin'

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

def call(model, method, *args, **kwargs):
    return models.execute_kw(DB, uid, PASSWORD, model, method, *args, **kwargs)

print("=== 連接成功 ===")
print(f"UID: {uid}")

# =========================================================================
# STEP 1: 建立 5% 營業稅（已有 15%，新增 5% 用於混合稅率測試）
# =========================================================================
print("\n--- STEP 1: 建立稅率 ---")

existing_5pct = call('account.tax', 'search', [[
    ('amount', '=', 5), ('type_tax_use', '=', 'sale'), ('active', '=', True)
]])
if existing_5pct:
    tax_5_id = existing_5pct[0]
    print(f"  5% 稅率已存在: id={tax_5_id}")
else:
    tax_5_id = call('account.tax', 'create', [{
        'name': '5%',
        'amount': 5.0,
        'type_tax_use': 'sale',
        'amount_type': 'percent',
    }])
    print(f"  建立 5% 稅率: id={tax_5_id}")

tax_15_id = call('account.tax', 'search', [[
    ('amount', '=', 15), ('type_tax_use', '=', 'sale'), ('active', '=', True)
]])[0]
print(f"  15% 稅率: id={tax_15_id}")

# =========================================================================
# STEP 2: 建立 4 個客戶
# =========================================================================
print("\n--- STEP 2: 建立 4 個客戶 ---")

customers = [
    {
        'name': '李雅婷',
        'email': 'yating.li@testmail.com',
        'phone': '0912-345-678',
        'city': '台北市',
        'street': '忠孝東路四段 100 號',
        'lang': 'zh_TW',
    },
    {
        'name': '陳志偉',
        'email': 'zhiwei.chen@testmail.com',
        'phone': '0923-456-789',
        'city': '新北市',
        'street': '中山路一段 50 號',
        'lang': 'zh_TW',
    },
    {
        'name': 'Emily Watson',
        'email': 'emily.watson@testmail.com',
        'phone': '+1-555-0123',
        'city': 'San Francisco',
        'street': '123 Market St',
        'lang': 'en_US',
    },
    {
        'name': '張家豪',
        'email': 'jiahao.zhang@testmail.com',
        'phone': '0934-567-890',
        'city': '台中市',
        'street': '台灣大道三段 200 號',
        'lang': 'zh_TW',
    },
]

customer_ids = []
for c in customers:
    existing = call('res.partner', 'search', [[('email', '=', c['email'])]])
    if existing:
        cid = existing[0]
        print(f"  客戶已存在: {c['name']} (id={cid})")
    else:
        cid = call('res.partner', 'create', [{
            **c,
            'customer_rank': 1,
            'is_company': False,
        }])
        print(f"  建立客戶: {c['name']} (id={cid})")
    customer_ids.append(cid)

print(f"  客戶 IDs: {customer_ids}")

# =========================================================================
# STEP 3: 建立 30 種產品（服務類型，分六大類）
# =========================================================================
print("\n--- STEP 3: 建立 30 種產品 ---")

products_def = [
    # === 醫美診所類 (5 items) ===
    {'name': '微整形諮詢費', 'price': 800, 'code': 'BIZ-MED-01', 'tax': tax_5_id},
    {'name': '肉毒桿菌注射（單區）', 'price': 6000, 'code': 'BIZ-MED-02', 'tax': tax_5_id},
    {'name': '雷射除斑療程', 'price': 12000, 'code': 'BIZ-MED-03', 'tax': tax_5_id},
    {'name': '皮秒雷射（全臉）', 'price': 18000, 'code': 'BIZ-MED-04', 'tax': tax_5_id},
    {'name': '術前抽血檢查', 'price': 1500, 'code': 'BIZ-MED-05', 'tax': None},  # 免稅-醫療

    # === 法律諮詢類 (5 items) ===
    {'name': '法律諮詢費（30分鐘）', 'price': 3000, 'code': 'BIZ-LAW-01', 'tax': tax_5_id},
    {'name': '合約審閱服務', 'price': 8000, 'code': 'BIZ-LAW-02', 'tax': tax_5_id},
    {'name': '訴訟案件評估', 'price': 5000, 'code': 'BIZ-LAW-03', 'tax': tax_5_id},
    {'name': '企業法務顧問（月費）', 'price': 25000, 'code': 'BIZ-LAW-04', 'tax': tax_5_id},
    {'name': '公證服務', 'price': 2000, 'code': 'BIZ-LAW-05', 'tax': None},  # 免稅

    # === 健身教練類 (5 items) ===
    {'name': '體適能評估', 'price': 500, 'code': 'BIZ-FIT-01', 'tax': tax_5_id},
    {'name': '私人教練課程（1hr）', 'price': 2000, 'code': 'BIZ-FIT-02', 'tax': tax_5_id},
    {'name': '團體飛輪課程', 'price': 600, 'code': 'BIZ-FIT-03', 'tax': tax_5_id},
    {'name': '營養師諮詢', 'price': 1500, 'code': 'BIZ-FIT-04', 'tax': tax_5_id},
    {'name': '運動按摩放鬆', 'price': 1200, 'code': 'BIZ-FIT-05', 'tax': tax_5_id},

    # === 攝影工作室類 (5 items) ===
    {'name': '個人形象照（基本組）', 'price': 3500, 'code': 'BIZ-PHO-01', 'tax': tax_15_id},
    {'name': '全家福拍攝', 'price': 6000, 'code': 'BIZ-PHO-02', 'tax': tax_15_id},
    {'name': '商品攝影（10件）', 'price': 8000, 'code': 'BIZ-PHO-03', 'tax': tax_15_id},
    {'name': '婚紗外拍（半天）', 'price': 25000, 'code': 'BIZ-PHO-04', 'tax': tax_15_id},
    {'name': '證件照（6張）', 'price': 300, 'code': 'BIZ-PHO-05', 'tax': tax_15_id},

    # === 寵物服務類 (5 items) ===
    {'name': '寵物健康檢查', 'price': 800, 'code': 'BIZ-PET-01', 'tax': tax_5_id},
    {'name': '寵物美容（小型犬）', 'price': 1200, 'code': 'BIZ-PET-02', 'tax': tax_5_id},
    {'name': '寵物美容（大型犬）', 'price': 2000, 'code': 'BIZ-PET-03', 'tax': tax_5_id},
    {'name': '寵物疫苗注射', 'price': 600, 'code': 'BIZ-PET-04', 'tax': None},  # 免稅-醫療
    {'name': '寵物行為訓練（4堂）', 'price': 6000, 'code': 'BIZ-PET-05', 'tax': tax_5_id},

    # === 共用/雜項 (5 items) ===
    {'name': '場地清潔費', 'price': 500, 'code': 'BIZ-GEN-01', 'tax': tax_5_id},
    {'name': '延時服務費（30分鐘）', 'price': 800, 'code': 'BIZ-GEN-02', 'tax': tax_5_id},
    {'name': '交通接駁服務', 'price': 1000, 'code': 'BIZ-GEN-03', 'tax': tax_5_id},
    {'name': 'VIP 會員年費', 'price': 30000, 'code': 'BIZ-GEN-04', 'tax': tax_15_id},
    {'name': '保險附加費', 'price': 200, 'code': 'BIZ-GEN-05', 'tax': None},  # 免稅
]

product_ids = []
for p in products_def:
    existing = call('product.template', 'search', [[('default_code', '=', p['code'])]])
    if existing:
        tmpl_id = existing[0]
        pp = call('product.product', 'search', [[('product_tmpl_id', '=', tmpl_id)]])
        pid = pp[0] if pp else None
        print(f"  已存在: {p['name']} (tmpl={tmpl_id}, product={pid})")
    else:
        vals = {
            'name': p['name'],
            'default_code': p['code'],
            'list_price': p['price'],
            'type': 'service',
            'sale_ok': True,
            'purchase_ok': False,
        }
        if p['tax'] is not None:
            vals['taxes_id'] = [(6, 0, [p['tax']])]
        else:
            vals['taxes_id'] = [(5, 0, 0)]  # clear taxes

        tmpl_id = call('product.template', 'create', [vals])
        pp = call('product.product', 'search', [[('product_tmpl_id', '=', tmpl_id)]])
        pid = pp[0]
        print(f"  建立: {p['name']} ${p['price']} (tmpl={tmpl_id}, product={pid})")
    product_ids.append(pid)

print(f"  產品數量: {len(product_ids)}")

# Map by category
med_products = product_ids[0:5]    # 醫美
law_products = product_ids[5:10]   # 法律
fit_products = product_ids[10:15]  # 健身
pho_products = product_ids[15:20]  # 攝影
pet_products = product_ids[20:25]  # 寵物
gen_products = product_ids[25:30]  # 雜項

# =========================================================================
# STEP 4: 建立 6 種預約類型
# =========================================================================
print("\n--- STEP 4: 建立 6 種預約類型 ---")

# Resources for staff assignment
staff_resources = call('resource.resource', 'search', [[
    ('resource_type', '=', 'user'), ('active', '=', True)
]], {'limit': 6})

location_resources = call('resource.resource', 'search', [[
    ('resource_type', '=', 'material'), ('active', '=', True)
]], {'limit': 4})

appointment_types_def = [
    {
        'name': '醫美微整形門診',
        'description': '專業醫美微整形諮詢與療程預約。含諮詢、注射、雷射等項目。',
        'location_type': 'physical',
        'require_payment': True,
        'payment_per_person': False,
        'slot_duration': 1.0,
        'auto_confirm': False,
        'assign_staff': True,
        'assign_location': True,
        'products': [med_products[0], med_products[1], med_products[2]],  # 諮詢+肉毒+雷射
        'is_published': True,
    },
    {
        'name': '線上法律諮詢',
        'description': '由執業律師提供的專業法律諮詢服務。支援視訊會議。',
        'location_type': 'online',
        'require_payment': True,
        'payment_per_person': False,
        'slot_duration': 0.5,
        'auto_confirm': True,
        'assign_staff': True,
        'assign_location': False,
        'products': [law_products[0], law_products[2]],  # 諮詢+評估
        'is_published': True,
    },
    {
        'name': '私人健身教練課',
        'description': '一對一私人教練課程。包含體適能評估與個人化訓練計畫。',
        'location_type': 'physical',
        'require_payment': True,
        'payment_per_person': True,  # 按人數收費
        'slot_duration': 1.0,
        'auto_confirm': True,
        'assign_staff': True,
        'assign_location': False,
        'products': [fit_products[0], fit_products[1]],  # 評估+私教
        'is_published': True,
    },
    {
        'name': '婚紗攝影預約',
        'description': '專業婚紗及個人形象攝影服務。含造型、場地、後製。',
        'location_type': 'physical',
        'require_payment': True,
        'payment_per_person': False,
        'slot_duration': 2.0,
        'auto_confirm': False,
        'assign_staff': True,
        'assign_location': True,
        'products': [pho_products[0], pho_products[3], gen_products[0]],  # 形象照+婚紗+場地清潔
        'is_published': True,
    },
    {
        'name': '寵物健檢美容',
        'description': '寵物健康檢查與美容服務。專業獸醫師及美容師駐點。',
        'location_type': 'physical',
        'require_payment': True,
        'payment_per_person': False,
        'slot_duration': 1.5,
        'auto_confirm': True,
        'assign_staff': True,
        'assign_location': False,
        'products': [pet_products[0], pet_products[1]],  # 健檢+美容小型犬
        'is_published': True,
    },
    {
        'name': '免費團體飛輪體驗',
        'description': '免費飛輪體驗課，歡迎新會員體驗。無需付費即可預約。',
        'location_type': 'physical',
        'require_payment': False,
        'payment_per_person': False,
        'slot_duration': 1.0,
        'auto_confirm': True,
        'manage_capacity': True,
        'total_capacity': 12,
        'assign_staff': True,
        'assign_location': False,
        'products': [],
        'is_published': True,
    },
]

apt_type_ids = []
for i, apt in enumerate(appointment_types_def):
    existing = call('appointment.type', 'search', [[
        ('name', 'like', apt['name'])
    ]])
    if existing:
        at_id = existing[0]
        print(f"  已存在: {apt['name']} (id={at_id})")
    else:
        vals = {
            'name': apt['name'],
            'description': apt['description'],
            'location_type': apt['location_type'],
            'require_payment': apt['require_payment'],
            'payment_per_person': apt.get('payment_per_person', False),
            'slot_duration': apt['slot_duration'],
            'auto_confirm': apt['auto_confirm'],
            'assign_staff': apt.get('assign_staff', False),
            'assign_location': apt.get('assign_location', False),
            'is_published': apt.get('is_published', True),
            'active': True,
            'manage_capacity': apt.get('manage_capacity', False),
            'total_capacity': apt.get('total_capacity', 0),
            'max_booking_days': 90,
            'min_booking_hours': 2,
            'cancel_before_hours': 24,
        }
        if apt['products']:
            vals['payment_product_ids'] = [(6, 0, apt['products'])]

        at_id = call('appointment.type', 'create', [vals])
        print(f"  建立: {apt['name']} (id={at_id})")

        # 建立 Mon-Sat 排班 (9:00-18:00)
        for dow in ['0', '1', '2', '3', '4', '5']:  # Mon-Sat
            call('appointment.availability', 'create', [{
                'appointment_type_id': at_id,
                'dayofweek': dow,
                'hour_from': 9.0,
                'hour_to': 18.0,
            }])
        print(f"    排班: Mon-Sat 09:00-18:00")

    apt_type_ids.append(at_id)

print(f"  預約類型 IDs: {apt_type_ids}")

# =========================================================================
# STEP 5: 建立 80 筆預約記錄（覆蓋各狀態和場景）
# =========================================================================
print("\n--- STEP 5: 建立 80 筆預約記錄 ---")

# Time ranges
now = datetime.now()
base_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

# Define booking scenarios
# State distribution: 15 draft, 20 pending_payment, 25 confirmed, 10 done, 10 cancelled
booking_count = 0
bookings_created = []

def make_token():
    return secrets.token_urlsafe(32)

def create_booking(apt_type_id, partner_id, state, days_offset, hour, guest_count=1, notes=''):
    global booking_count
    booking_count += 1

    start_dt = base_date + timedelta(days=days_offset, hours=hour)
    # Get slot duration from appointment type
    apt_info = call('appointment.type', 'read', [apt_type_id], {'fields': ['slot_duration', 'name']})
    duration = apt_info[0]['slot_duration']
    apt_name = apt_info[0]['name']
    end_dt = start_dt + timedelta(hours=duration)

    partner_info = call('res.partner', 'read', [partner_id], {'fields': ['name', 'email', 'phone']})
    partner = partner_info[0]

    vals = {
        'appointment_type_id': apt_type_id,
        'partner_id': partner_id,
        'guest_name': partner['name'],
        'guest_email': partner['email'] or '',
        'guest_phone': partner.get('phone', '') or '',
        'guest_count': guest_count,
        'start_datetime': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'end_datetime': end_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'state': 'draft',
        'access_token': make_token(),
        'notes': notes,
        'company_id': 1,
    }

    booking_id = call('appointment.booking', 'create', [vals])

    # Transition state as needed
    if state == 'pending_payment':
        # Create SO to trigger pending_payment
        try:
            call('appointment.booking', 'action_create_sale_order', [[booking_id]])
        except Exception as e:
            # If action_create_sale_order doesn't exist as public method, set state directly
            call('appointment.booking', 'write', [[booking_id], {'state': 'pending_payment'}])
    elif state == 'confirmed':
        call('appointment.booking', 'write', [[booking_id], {'state': 'confirmed'}])
    elif state == 'done':
        call('appointment.booking', 'write', [[booking_id], {'state': 'confirmed'}])
        call('appointment.booking', 'write', [[booking_id], {'state': 'done'}])
    elif state == 'cancelled':
        call('appointment.booking', 'write', [[booking_id], {'state': 'cancelled'}])

    print(f"  #{booking_count:02d} 預約 id={booking_id} | {apt_name} | {partner['name']} | {state} | {start_dt.strftime('%m/%d %H:%M')}")
    return booking_id

# --- 醫美微整形門診 (apt_type_ids[0]) - 15 bookings ---
print("\n  === 醫美微整形門診 ===")
for i in range(15):
    cust = customer_ids[i % 4]
    state = ['draft', 'pending_payment', 'confirmed', 'confirmed', 'done',
             'cancelled', 'pending_payment', 'confirmed', 'draft', 'confirmed',
             'pending_payment', 'confirmed', 'done', 'cancelled', 'confirmed'][i]
    days = 3 + i * 2  # spread over next 30 days
    hour = 9 + (i % 8)  # 9-16 o'clock
    notes_options = [
        '初次就診，需要詳細評估',
        '回診患者，追蹤上次療程效果',
        '對麻醉過敏，請注意',
        '希望了解價格方案',
        '',
    ]
    create_booking(apt_type_ids[0], cust, state, days, hour,
                   notes=notes_options[i % 5])

# --- 線上法律諮詢 (apt_type_ids[1]) - 15 bookings ---
print("\n  === 線上法律諮詢 ===")
for i in range(15):
    cust = customer_ids[i % 4]
    state = ['confirmed', 'confirmed', 'pending_payment', 'draft', 'confirmed',
             'done', 'cancelled', 'confirmed', 'pending_payment', 'confirmed',
             'draft', 'confirmed', 'done', 'cancelled', 'pending_payment'][i]
    days = 1 + i * 2
    hour = 10 + (i % 7)
    notes_options = [
        '關於勞資糾紛的問題',
        '需要審閱租賃合約',
        '公司設立相關諮詢',
        '繼承問題諮詢',
        '智慧財產權爭議',
    ]
    create_booking(apt_type_ids[1], cust, state, days, hour,
                   notes=notes_options[i % 5])

# --- 私人健身教練課 (apt_type_ids[2]) - 15 bookings (payment_per_person) ---
print("\n  === 私人健身教練課（按人數收費）===")
for i in range(15):
    cust = customer_ids[i % 4]
    state = ['confirmed', 'draft', 'pending_payment', 'confirmed', 'done',
             'confirmed', 'cancelled', 'pending_payment', 'confirmed', 'draft',
             'confirmed', 'done', 'cancelled', 'confirmed', 'pending_payment'][i]
    days = 2 + i * 2
    hour = 7 + (i % 10)  # 7-16 morning/afternoon
    guest_count = random.choice([1, 1, 2, 2, 3])
    notes_options = [
        f'{guest_count}人同行',
        '有膝蓋舊傷，避免深蹲',
        '備戰馬拉松，加強心肺',
        '減重目標：3個月 -10kg',
        '',
    ]
    create_booking(apt_type_ids[2], cust, state, days, hour,
                   guest_count=guest_count,
                   notes=notes_options[i % 5])

# --- 婚紗攝影預約 (apt_type_ids[3]) - 12 bookings ---
print("\n  === 婚紗攝影預約 ===")
for i in range(12):
    cust = customer_ids[i % 4]
    state = ['draft', 'pending_payment', 'confirmed', 'done',
             'confirmed', 'cancelled', 'pending_payment', 'confirmed',
             'draft', 'confirmed', 'pending_payment', 'cancelled'][i]
    days = 7 + i * 3  # spread wider (photography takes planning)
    hour = 9 + (i % 5)
    notes_options = [
        '戶外拍攝，備案室內',
        '需要妝髮造型師',
        '拍攝風格：韓系自然風',
        '帶寵物入鏡',
        '希望黃昏時段拍攝',
        '',
    ]
    create_booking(apt_type_ids[3], cust, state, days, hour,
                   guest_count=2,
                   notes=notes_options[i % 6])

# --- 寵物健檢美容 (apt_type_ids[4]) - 13 bookings ---
print("\n  === 寵物健檢美容 ===")
for i in range(13):
    cust = customer_ids[i % 4]
    state = ['confirmed', 'pending_payment', 'draft', 'confirmed', 'done',
             'cancelled', 'confirmed', 'pending_payment', 'confirmed', 'draft',
             'done', 'confirmed', 'cancelled'][i]
    days = 1 + i * 2
    hour = 10 + (i % 6)
    notes_options = [
        '柴犬，5歲，公，已結紮',
        '貴賓，3歲，母，需要修毛',
        '金毛，7歲，需要年度體檢',
        '貓咪，2歲，較怕生',
        '法鬥，4歲，有皮膚過敏史',
    ]
    create_booking(apt_type_ids[4], cust, state, days, hour,
                   notes=notes_options[i % 5])

# --- 免費團體飛輪體驗 (apt_type_ids[5]) - 10 bookings (免付費) ---
print("\n  === 免費團體飛輪體驗 ===")
for i in range(10):
    cust = customer_ids[i % 4]
    state = ['confirmed', 'confirmed', 'draft', 'confirmed', 'done',
             'cancelled', 'confirmed', 'confirmed', 'draft', 'cancelled'][i]
    days = 3 + i * 3
    hour = 18 + (i % 2)  # evening classes: 18 or 19
    guest_count = random.choice([1, 1, 2, 3])
    create_booking(apt_type_ids[5], cust, state, days, hour,
                   guest_count=guest_count,
                   notes='免費體驗課' if i < 3 else '')

# =========================================================================
# SUMMARY
# =========================================================================
print(f"\n=== 完成 ===")
print(f"  建立客戶: {len(customer_ids)} 位")
print(f"  建立產品: {len(product_ids)} 種")
print(f"  建立預約類型: {len(apt_type_ids)} 種")
print(f"  建立預約記錄: {booking_count} 筆")
