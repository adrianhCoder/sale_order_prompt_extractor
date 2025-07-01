# -*- coding: utf-8 -*-

import logging
import re
import json
try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_google_sheet_credentials(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        key_content = get_param('sale_order_prompt_extractor.google_service_account_key')
        if not key_content:
            raise UserError(_("Google Service Account Key is not set in settings."))
        
        try:
            return json.loads(key_content)
        except json.JSONDecodeError:
            raise UserError(_("The Google Service Account Key is not a valid JSON."))

    def _get_worksheet(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        sheet_url = get_param('sale_order_prompt_extractor.google_sheet_url')
        worksheet_name = get_param('sale_order_prompt_extractor.google_sheet_worksheet_name')

        if not sheet_url or not worksheet_name:
            raise UserError(_("Google Sheet URL or Worksheet Name are not set in settings."))
            
        if gspread is None:
            raise UserError(_("The 'gspread' library is not installed. Please install it with: pip install gspread google-auth-oauthlib"))

        creds_dict = self._get_google_sheet_credentials()
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        try:
            sheet = client.open_by_url(sheet_url)
            return sheet.worksheet(worksheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            raise UserError(_("Spreadsheet not found at the provided URL."))
        except gspread.exceptions.WorksheetNotFound:
            raise UserError(_("Worksheet '%s' not found in the spreadsheet.", worksheet_name))
        except Exception as e:
            raise UserError(_("An error occurred while accessing Google Sheets: %s", str(e)))

    def _get_dias_credito(self, payment_term):
        if not payment_term:
            return "VERIFICAR"
        
        name = payment_term.name.lower()
        if "inmediato" in name or "immediate" in name:
            return 0
        
        numbers = re.findall(r'\d+', name)
        return int(numbers[0]) if numbers else "VERIFICAR"

    def action_extract_prompt_data(self):
        try:
            worksheet = self._get_worksheet()
            existing_pids = set(worksheet.col_values(4)) # "Pedido Interno" is the 4th column
        except UserError as e:
            raise e
        except Exception as e:
             _logger.error("Error accessing Google Sheet: %s", str(e))
             raise UserError(_("Failed to connect to Google Sheets. Check logs for details."))

        rows_to_add = []
        for order in self.filtered(lambda o: o.name not in existing_pids):
            # General Info
            invoice = self.env['account.move'].search([
                ('invoice_origin', '=', order.name),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted')
            ], limit=1)

            factura = invoice.name if invoice else "VERIFICAR"
            fecha_emision_dt = invoice.invoice_date if invoice and invoice.invoice_date else order.date_order.date()
            fecha_emision = fecha_emision_dt.strftime('%Y-%m-%d')
            mes = fecha_emision_dt.month

            oc = order.client_order_ref or "VERIFICAR"
            dias_credito = self._get_dias_credito(order.payment_term_id)
            
            cred_cont = "VERIFICAR"
            if isinstance(dias_credito, int):
                cred_cont = "CRÉDITO" if dias_credito > 0 else "CONTADO"
            
            currency_map = {'MXN': 'Peso Mexicano', 'USD': 'Dólar Americano'}
            moneda = currency_map.get(order.currency_id.name, order.currency_id.name or "")

            tc_field_name = 'x_studio_tasa_de_cambio'
            tc = order[tc_field_name] if tc_field_name in order and order.currency_id.name != 'MXN' else ""
            
            # Line Info
            for line in order.order_line.filtered(lambda l: not l.display_type):
                raw_concepto = line.name.replace('\n', ' ').replace('\r', ' ')
                concepto = re.sub(r'\[.*?\]\s*', '', raw_concepto).strip()
                
                categoria = "COMERCIAL"
                if any(term.lower() in concepto.lower() for term in ["tabla", "cono", "módulo"]):
                    categoria = "FABRICACION"
                
                familia = (line.product_id.categ_id.name or '').upper()
                
                total_mxn = line.price_total
                if order.currency_id.name != 'MXN' and isinstance(tc, (int, float)) and tc > 0:
                    total_mxn = line.price_total * tc
                elif order.currency_id.name != 'MXN':
                    total_mxn = "VERIFICAR"

                rows_to_add.append([
                    factura, str(mes), fecha_emision, order.name or "VERIFICAR",
                    oc, "DOMICILIO", order.partner_id.name or "VERIFICAR",
                    line.product_id.default_code or "", concepto, str(line.product_uom_qty),
                    line.product_uom.name or "", f"{line.price_unit:.2f}", f"{line.price_subtotal:.2f}",
                    f"{line.price_tax:.2f}", f"{line.price_total:.2f}", moneda,
                    str(tc) if tc else "", f"{total_mxn:.2f}" if isinstance(total_mxn, (int, float)) else total_mxn,
                    str(dias_credito), cred_cont, categoria, familia, "PENDIENTE"
                ])

        if not rows_to_add:
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {
                    'title': _('No New Data'),
                    'message': _('All selected orders already exist in the Google Sheet.'),
                    'sticky': False,
                }
            }
        
        try:
            worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        except Exception as e:
            _logger.error("Error writing to Google Sheet: %s", str(e))
            raise UserError(_("Failed to write to Google Sheets. Check logs for details."))

        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Extraction Successful'),
                'message': _('%s row(s) added to the Google Sheet.', len(rows_to_add)),
                'sticky': False,
            }
        } 