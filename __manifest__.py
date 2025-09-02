# -*- coding: utf-8 -*-
{
    'name': "Sales & Invoice Prompt Extractor",
    'summary': """
        Extracts sale order and invoice data in a specific format for an AI prompt with multi-company support.""",
    'description': """
        Adds server actions to Sale Orders and Invoices to extract data based on a predefined prompt format and logs it.
        
        Features:
        - Multi-company support: Automatically routes orders/invoices to different Google Sheets worksheets based on company
        - Configurable company-to-worksheet mapping
        - Intelligent data extraction and formatting
        - Google Sheets integration with automatic synchronization
        - Mexican EDI support (UUID, CFDI) for invoices
    """,
    'author': "Adriano",
    'website': "https://www.github.com/Adrianovaldes",
    'category': 'Sales/Accounting',
    'version': '17.0.1.0.0',
    'depends': ['sale_management', 'base_setup', 'account', 'l10n_mx_edi'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/sale_order_view.xml',
        'views/account_move_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
} 