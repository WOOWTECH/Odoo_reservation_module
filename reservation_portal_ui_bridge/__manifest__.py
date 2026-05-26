# -*- coding: utf-8 -*-
{
    'name': 'Reservation Portal × Portal UI Bridge',
    'version': '18.0.1.0.0',
    'category': 'Hidden',
    'summary': 'Bridges Reservation Portal with Portal User UI (icons & colors)',
    'author': 'WoowTech',
    'website': 'https://aiot.woowtech.io/',
    'license': 'LGPL-3',
    'depends': ['reservation_module', 'woow_portal_ui'],
    'auto_install': True,
    'data': [
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'reservation_portal_ui_bridge/static/src/css/bridge.css',
        ],
    },
    'installable': True,
    'application': False,
}
