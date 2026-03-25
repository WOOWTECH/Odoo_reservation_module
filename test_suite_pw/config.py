# -*- coding: utf-8 -*-
"""Playwright test suite configuration — reservation_module v18.0.1.5.0"""

URL = "http://localhost:9073"
DB = "odooreservation"
ADMIN_UID = 2
ADMIN_PWD = "admin"
XMLRPC_OBJECT = f"{URL}/xmlrpc/2/object"

# Published appointment type IDs
TYPE_IDS = {
    'business_meeting': 1,
    'video_consultation': 2,
    'restaurant': 3,
    'tennis': 4,
    'expert_consultation': 5,
}

# Unpublished / test types
UNPUBLISHED_TYPE_ID = 6

# Resource IDs (material type)
RESOURCE_IDS = {
    'table_1_window': 3,      # capacity 4, Restaurant
    'table_2_garden': 4,      # capacity 6, Restaurant
    'table_3_private': 5,     # capacity 8, Restaurant
    'tennis_court': 6,        # capacity 4, Tennis
}

# Staff user IDs
STAFF_IDS = {
    'admin': 2,  # Mitchell Admin
}

# Question IDs
QUESTION_IDS = {
    'expert_q1': 1,  # "What topics can I discuss..."
    'expert_q2': 2,  # "How should I prepare..."
    'restaurant_q3': 3,  # "Can I request a special occasion..."
    'restaurant_q4': 4,  # "Do you accommodate dietary..."
}

# Expected type configurations (verified from live DB)
TYPE_CONFIG = {
    1: {
        'name': 'Business Meeting',
        'duration': 1.0, 'interval': 1.0,
        'max_days': 30, 'min_hours': 2.0, 'cancel_hours': 24.0,
        'auto_confirm': True, 'require_payment': False, 'payment_amount': 0.0,
        'assign_staff': True, 'manage_capacity': False,
        'has_staff_selector': True, 'has_location_selector': False,
        'staff_options': ['Auto-Assign', 'Mitchell Admin'],
        'location_type': 'physical',
    },
    2: {
        'name': 'Video Consultation',
        'duration': 0.5, 'interval': 0.5,
        'max_days': 14, 'min_hours': 1.0, 'cancel_hours': 2.0,
        'auto_confirm': True, 'require_payment': False, 'payment_amount': 0.0,
        'assign_staff': True, 'manage_capacity': False,
        'has_staff_selector': True, 'has_location_selector': False,
        'staff_options': ['Auto-Assign', 'Mitchell Admin'],
        'location_type': 'online',
    },
    3: {
        'name': 'Restaurant Reservation',
        'duration': 2.0, 'interval': 0.5,
        'max_days': 60, 'min_hours': 4.0, 'cancel_hours': 4.0,
        'auto_confirm': True, 'require_payment': False, 'payment_amount': 0.0,
        'assign_staff': True, 'manage_capacity': True,
        'has_staff_selector': False, 'has_location_selector': True,
        'location_options': ['Auto-Assign', 'Table 1 - Window (4 seats)',
                             'Table 2 - Garden View (6 seats)',
                             'Table 3 - Private Room (8 seats)'],
        'location_type': 'physical',
    },
    4: {
        'name': 'Tennis Court Booking',
        'duration': 1.0, 'interval': 1.0,
        'max_days': 7, 'min_hours': 2.0, 'cancel_hours': 4.0,
        'auto_confirm': True, 'require_payment': False, 'payment_amount': 0.0,
        'assign_staff': True, 'manage_capacity': False,
        'has_staff_selector': False, 'has_location_selector': True,
        'location_options': ['Auto-Assign', 'Tennis Court'],
        'location_type': 'physical',
    },
    5: {
        'name': 'Expert Consultation',
        'duration': 1.0, 'interval': 1.0,
        'max_days': 30, 'min_hours': 24.0, 'cancel_hours': 48.0,
        'auto_confirm': True, 'require_payment': True, 'payment_amount': 100.0,
        'assign_staff': True, 'manage_capacity': False,
        'has_staff_selector': True, 'has_location_selector': False,
        'staff_options': ['Auto-Assign', 'Mitchell Admin'],
        'location_type': 'online',
    },
}

# Test guest data
TEST_GUEST = {
    'name': 'PW Test User',
    'email': 'pw_e2e_test@example.com',
    'phone': '+886912345678',
    'count': 2,
    'notes': 'Playwright automated test booking',
}
