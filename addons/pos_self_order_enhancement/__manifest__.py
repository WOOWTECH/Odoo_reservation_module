{
    "name": "POS Self Order Enhancement",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Enhance POS self-ordering: remove cancel button, add continue ordering button on landing page",
    "description": """
        POS Self Order Enhancement
        ==========================

        This module enhances the Odoo POS self-ordering experience:

        Features:
        ---------
        * Remove cancel button after order is submitted (prevents customer cancellation)
        * Add "Continue Ordering" button on landing page to allow customers to add items to existing order
        * Button appears below "My Order" with same style, only when customer has unpaid orders

        Note:
        -----
        Staff can still cancel orders from the POS backend.
    """,
    "author": "WoowTech",
    "website": "https://www.woowtech.com",
    "license": "LGPL-3",
    "depends": ["pos_self_order"],
    "data": [],
    "assets": {
        "pos_self_order.assets": [
            "pos_self_order_enhancement/static/src/app/**/*",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
