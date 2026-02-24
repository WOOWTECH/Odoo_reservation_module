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
        - Custom questions and forms
        - Email notifications and reminders
    """,
    "version": "18.0.1.0.9",
    "category": "Services/Appointment",
    "author": "WoowTech",
    "website": "https://woowtech.com",
    "license": "LGPL-3",
    "depends": [
        "calendar",
        "resource",
        "website",
        "payment",
        "product",
        "mail",
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
        "views/appointment_menus.xml",
        # Website
        "views/appointment_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "odoo_calendar_enhance/static/src/css/appointment_backend.css",
            "odoo_calendar_enhance/static/src/js/appointment_kanban.js",
        ],
        "web.assets_frontend": [
            "odoo_calendar_enhance/static/src/css/appointment_frontend.css",
            "odoo_calendar_enhance/static/src/js/appointment_booking.js",
        ],
    },
    "demo": [
        "demo/appointment_demo.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
    "sequence": 10,
}
