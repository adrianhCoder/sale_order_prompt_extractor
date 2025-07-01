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
        _logger.info("Retrieving Google Sheets credentials from config parameters")
        get_param = self.env['ir.config_parameter'].sudo().get_param
        key_content = get_param('sale_order_prompt_extractor.google_service_account_key')
        if not key_content:
            _logger.error("No Google Service Account Key found in settings")
            raise UserError(_("Google Service Account Key is not set in settings."))
        try:
            return json.loads(key_content)
        except json.JSONDecodeError:
            _logger.error("Invalid JSON for Google Service Account Key")
            raise UserError(_("The Google Service Account Key is not a valid JSON."))

    def _get_worksheet(self):
        _logger.info("Connecting to Google Sheet at configured URL and worksheet")
        get_param = self.env['ir.config_parameter'].sudo().get_param
        sheet_url = get_param('sale_order_prompt_extractor.google_sheet_url')
        worksheet_name = get_param('sale_order_prompt_extractor.google_sheet_worksheet_name')

        if not sheet_url or not worksheet_name:
            _logger.error("Google Sheet URL or Worksheet Name not set in settings")
            raise UserError(_("Google Sheet URL or Worksheet Name are not set in settings."))
        if gspread is None:
            _logger.error("gspread library not installed")
            raise UserError(_("The 'gspread' library is not installed. Please install it with: pip install gspread google-auth-oauthlib"))

        creds_dict = self._get_google_sheet_credentials()
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)

        try:
            sheet = client.open_by_url(sheet_url)
            worksheet = sheet.worksheet(worksheet_name)
            _logger.info("Successfully accessed worksheet '%s'", worksheet_name)
            return worksheet
        except gspread.exceptions.SpreadsheetNotFound:
            _logger.error("Spreadsheet not found at URL: %s", sheet_url)
            raise UserError(_("Spreadsheet not found at the provided URL."))
        except gspread.exceptions.WorksheetNotFound:
            _logger.error("Worksheet '%s' not found in spreadsheet", worksheet_name)
            raise UserError(_("Worksheet '%s' not found in the spreadsheet." % worksheet_name))
        except Exception as e:
            _logger.error("Error accessing Google Sheets: %s", str(e))
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
            all_pids = worksheet.col_values(4)
            _logger.info("Existing folios in sheet: %s", all_pids)
        except UserError:
            raise
        except Exception as e:
            _logger.error("Failed to connect to Google Sheets: %s", str(e))
            raise UserError(_("Failed to connect to Google Sheets. Check logs for details."))

        rows_to_add = []
        # Delete existing rows for folios that will be updated
        for order in self:
            if order.name in all_pids:
                indices = [i+1 for i, v in enumerate(all_pids) if v == order.name]
                for idx in reversed(indices):
                    try:
                        worksheet.delete_rows(idx)
                        _logger.info("Deleted existing row %d for folio %s", idx, order.name)
                    except Exception as e:
                        _logger.error("Error deleting row %d: %s", idx, str(e))
                _logger.info("Updating data for folio %s: existing rows removed", order.name)

        # Refresh existing folios after deletion
        existing_after = worksheet.col_values(4)

        for order in self:
            if order.name in existing_after:
                _logger.warning("Folio %s still present after deletion, skipping to avoid duplicates", order.name)
                continue
            # Invoice lookup
            invoice = self.env['account.move'].search([
                ('invoice_origin', '=', order.name),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted')
            ], limit=1)
            factura = invoice.name if invoice else "VERIFICAR"
            fecha_dt = invoice.invoice_date if invoice and invoice.invoice_date else order.date_order.date()
            fecha = fecha_dt.strftime('%Y-%m-%d')
            mes = fecha_dt.month
            oc = order.client_order_ref or "VERIFICAR"
            dias_credito = self._get_dias_credito(order.payment_term_id)
            cred_cont = "VERIFICAR"
            if isinstance(dias_credito, int):
                cred_cont = "CRÉDITO" if dias_credito > 0 else "CONTADO"
            currency_map = {'MXN': 'Peso Mexicano', 'USD': 'Dólar Americano'}
            moneda = currency_map.get(order.currency_id.name, order.currency_id.name or "")

            # Determine exchange rate using Odoo's built-in conversion
            # Use order.date_order as reference date
            fecha_cot = order.date_order
            _logger.info("Using order date %s for exchange rate lookup", fecha_cot)
            # Odoo 17: _get_conversion_rate(from_currency, to_currency, company, date)
            try:
                # Swap parameters: from order currency to company currency to get USD->MXN
                tc = self.env['res.currency']._get_conversion_rate(
                    order.currency_id,
                    order.company_id.currency_id,
                    order.company_id,
                    fecha_cot and fecha_cot.date() or fields.Date.today()
                )
                _logger.info(
                    "Retrieved conversion rate %s %s->%s on date %s (company %s)",
                    tc, order.currency_id.name, order.company_id.currency_id.name, fecha_cot, order.company_id.name
                )
            except Exception as e:
                tc = 1.0
                _logger.error(
                    "Failed to get conversion rate for %s->%s: %s. Defaulting to %s",
                    order.currency_id.name, order.company_id.currency_id.name, str(e), tc
                )

            # End conversion lookup

            # Line data
            for line in order.order_line.filtered(lambda l: not l.display_type):
                concepto = re.sub(r'\[.*?\]\s*', '', line.name.replace('\n', ' ')).strip()
                categoria = 'FABRICACION' if any(t in concepto.lower() for t in ['tabla','cono','módulo']) else 'COMERCIAL'
                familia = (line.product_id.categ_id.name or '').upper()
                if order.currency_id != order.company_id.currency_id and isinstance(tc, (int, float)) and tc:
                    total_mxn = line.price_total * tc
                else:
                    total_mxn = line.price_total

                rows_to_add.append([
                    factura, str(mes), fecha, order.name or 'VERIFICAR', oc,
                    'DOMICILIO', order.partner_id.name or 'VERIFICAR',
                    line.product_id.default_code or '', concepto,
                    str(line.product_uom_qty), line.product_uom.name or '',
                    f"{line.price_unit:.2f}", f"{line.price_subtotal:.2f}",
                    f"{line.price_tax:.2f}", f"{line.price_total:.2f}",
                    moneda, str(tc) if tc else '',
                    f"{total_mxn:.2f}",
                    str(dias_credito), cred_cont, categoria, familia, 'PENDIENTE'
                ])

        if not rows_to_add:
            _logger.info("No new or updated rows to add to Google Sheet")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No New Data'),
                    'message': _('All selected orders are up to date.'),
                    'sticky': False,
                }
            }

        try:
            worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
            _logger.info("Appended %d rows to Google Sheet", len(rows_to_add))
        except Exception as e:
            _logger.error("Error writing to Google Sheet: %s", str(e))
            raise UserError(_("Failed to write to Google Sheets. Check logs for details."))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Extraction Successful'),
                'message': _('%s row(s) added to the Google Sheet.', len(rows_to_add)),
                'sticky': False,
            }
        }
