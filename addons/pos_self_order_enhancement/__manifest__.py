{
    "name": "POS Self Order Enhancement",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Enhance POS self-ordering: remove cancel button, continue ordering, pay per order mode",
    "description": """
        POS Self Order Enhancement
        ==========================

        This module enhances the Odoo POS self-ordering experience:

        Features:
        ---------
        * Remove cancel button after order is submitted (prevents customer cancellation)
        * Add "Continue Ordering" button on landing page to allow customers to add items to existing order
        * Enable "Pay per Order" mode (Enterprise feature) for Community version
          - Customers can submit multiple orders and pay at the end
          - Checkout from "My Orders" page with accumulated total

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
        "web.assets_backend": [
            "pos_self_order_enhancement/static/src/fields/**/*",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
