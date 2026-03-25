# -*- coding: utf-8 -*-
"""Test suite configuration for reservation_module"""

URL = "http://localhost:9073"
DB = "odooreservation"
ADMIN_UID = 2
ADMIN_PWD = "admin"
XMLRPC_COMMON = f"{URL}/xmlrpc/2/common"
XMLRPC_OBJECT = f"{URL}/xmlrpc/2/object"

# Demo appointment type IDs (from appointment_demo.xml)
TYPE_IDS = {
    'business_meeting': 1,
    'video_consultation': 2,
    'restaurant': 3,
    'tennis': 4,
    'expert_consultation': 5,
}

# Demo resource IDs
RESOURCE_IDS = {
    'meeting_room_a': 1,
    'meeting_room_b': 2,
    'table_1': 3,  # capacity 4
    'table_2': 4,  # capacity 6
    'table_3': 5,  # capacity 8
    'tennis_court': 6,  # capacity 4
}

# Expected configurations per type
TYPE_CONFIG = {
    1: {'name': 'Business Meeting', 'duration': 1.0, 'interval': 1.0, 'max_days': 30,
        'min_hours': 2, 'cancel_hours': 24, 'scheduled': True, 'payment': False,
        'assign_staff': True, 'manage_capacity': False},
    2: {'name': 'Video Consultation', 'duration': 0.5, 'interval': 0.5, 'max_days': 14,
        'min_hours': 1, 'cancel_hours': 2, 'scheduled': True, 'payment': False,
        'assign_staff': True, 'manage_capacity': False},
    3: {'name': 'Restaurant Reservation', 'duration': 2.0, 'interval': 0.5, 'max_days': 60,
        'min_hours': 4, 'cancel_hours': 4, 'scheduled': True, 'payment': False,
        'assign_staff': True, 'manage_capacity': True},
    4: {'name': 'Tennis Court Booking', 'duration': 1.0, 'interval': 1.0, 'max_days': 7,
        'min_hours': 2, 'cancel_hours': 4, 'scheduled': True, 'payment': False,
        'assign_staff': True, 'manage_capacity': False},
    5: {'name': 'Expert Consultation', 'duration': 1.0, 'interval': 1.0, 'max_days': 30,
        'min_hours': 24, 'cancel_hours': 48, 'scheduled': True, 'payment': True,
        'assign_staff': True, 'manage_capacity': False},
}
