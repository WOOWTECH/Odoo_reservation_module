# -*- coding: utf-8 -*-
{
    "name": "Reservation Booking Enhancement",
    "summary": "Complete appointment booking system for Odoo Community",
    "description": """
        This module provides a complete appointment booking system similar to
        Odoo Enterprise's Appointment module.

        Features:
        - Multiple appointment types (Meeting, Video Call, Table, Resource, etc.)
        - Resource and staff scheduling
        - Online booking portal
        - Payment integration
        - Automatic confirmation
        - FAQ / Q&A for appointment types
        - Email notifications and reminders
    """,
    "version": "18.0.2.1.0",
    "category": "Services/Appointment",
    "author": "WoowTech",
    "website": "https://aiot.woowtech.io/",
    "license": "LGPL-3",
    "depends": [
        "calendar",
        "resource",
        "website",
        "portal",
        "payment",
        "product",
        "mail",
        "sale",
    ],
    "data": [
        # Security
        "security/appointment_security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/appointment_data.xml",
        # Views
        "views/appointment_type_views.xml",
        "views/appointment_booking_views.xml",
        "views/resource_views.xml",
        "views/appointment_menus.xml",
        # Website
        "views/appointment_templates.xml",
        # Portal
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "reservation_module/static/src/css/appointment_backend.css",
            "reservation_module/static/src/js/appointment_kanban.js",
        ],
        "web.assets_frontend": [
            "reservation_module/static/src/css/appointment_frontend.css",
            "reservation_module/static/src/js/appointment_booking.js",
        ],
    },
    "demo": [
        "demo/appointment_demo.xml",
    ],
    "post_init_hook": "_post_init_hook",
    "installable": True,
    "auto_install": False,
    "application": True,
    "sequence": 10,
}
