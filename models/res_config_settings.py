# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    google_sheet_url = fields.Char(
        string='Google Sheet URL',
        config_parameter='sale_order_prompt_extractor.google_sheet_url'
    )
    
    # Configuración de mapeo empresa -> hoja para pedidos
    company_sheet_mapping = fields.Char(
        string='Company to Sheet Mapping (Orders)',
        config_parameter='sale_order_prompt_extractor.company_sheet_mapping',
        default='{"GLOBAL HIRT SUMINISTROS Y SERVICIOS DE LA INDUSTRIA": "PED G", "FORMAS CERAMICAS": "PED F"}',
        help='JSON mapping of company names to worksheet names for orders. Format: {"Company Name": "Worksheet Name"}'
    )
    
    # Configuración de mapeo empresa -> hoja para facturas
    company_invoice_mapping = fields.Char(
        string='Company to Sheet Mapping (Invoices)',
        config_parameter='sale_order_prompt_extractor.company_invoice_mapping',
        default='{"GLOBAL HIRT SUMINISTROS Y SERVICIOS DE LA INDUSTRIA": "FACT G", "FORMAS CERAMICAS": "FACT F"}',
        help='JSON mapping of company names to worksheet names for invoices. Format: {"Company Name": "Worksheet Name"}'
    )
    
    # Configuración por defecto (para compatibilidad)
    google_sheet_worksheet_name = fields.Char(
        string='Default Worksheet Name',
        config_parameter='sale_order_prompt_extractor.google_sheet_worksheet_name',
        default='PED G'
    )
    
    google_service_account_key = fields.Char(
        string='Google Service Account JSON Key',
        config_parameter='sale_order_prompt_extractor.google_service_account_key'
    ) 