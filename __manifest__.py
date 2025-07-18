# -*- coding: utf-8 -*-
{
    'name': "Sale Order Prompt Extractor",
    'summary': """
        Extracts sale order data in a specific format for an AI prompt.""",
    'description': """
        Adds a server action to Sale Orders to extract data based on a predefined prompt format and logs it.
    """,
    'author': "Adriano",
    'website': "https://www.github.com/Adrianovaldes",
    'category': 'Sales',
    'version': '17.0.1.0.0',
    'depends': ['sale_management', 'base_setup'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/sale_order_view.xml',
        'views/account_move_actions.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
} 