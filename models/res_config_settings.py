# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    google_sheet_url = fields.Char(
        string='Google Sheet URL',
        config_parameter='sale_order_prompt_extractor.google_sheet_url'
    )
    google_sheet_worksheet_name = fields.Char(
        string='Worksheet Name',
        config_parameter='sale_order_prompt_extractor.google_sheet_worksheet_name',
        default='PED G'
    )
    google_service_account_key = fields.Char(
        string='Google Service Account JSON Key',
        config_parameter='sale_order_prompt_extractor.google_service_account_key'
    ) 