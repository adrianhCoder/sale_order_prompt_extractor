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

    # ---------------------------------------------------------------------
    # Credenciales y acceso a Google Sheets
    # ---------------------------------------------------------------------

    def _get_google_sheet_credentials(self):
        _logger.info("Retrieving Google Sheets credentials from config parameters")
        param = self.env['ir.config_parameter'].sudo()
        key_content = param.get_param('sale_order_prompt_extractor.google_service_account_key')
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
        param = self.env['ir.config_parameter'].sudo()
        sheet_url = param.get_param('sale_order_prompt_extractor.google_sheet_url')
        worksheet_name = param.get_param('sale_order_prompt_extractor.google_sheet_worksheet_name')

        if not sheet_url or not worksheet_name:
            raise UserError(_("Google Sheet URL or Worksheet Name are not set in settings."))
        if gspread is None:
            raise UserError(_("The 'gspread' library is not installed. Please install it with: pip install gspread google-auth-oauthlib"))

        creds_dict = self._get_google_sheet_credentials()
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)

        try:
            sheet = client.open_by_url(sheet_url)
            worksheet = sheet.worksheet(worksheet_name)
            _logger.info("Successfully accessed worksheet '%s'", worksheet_name)
            return worksheet
        except gspread.exceptions.SpreadsheetNotFound:
            raise UserError(_("Spreadsheet not found at the provided URL."))
        except gspread.exceptions.WorksheetNotFound:
            raise UserError(_("Worksheet '%s' not found in the spreadsheet." % worksheet_name))
        except Exception as e:
            _logger.error("Error accessing Google Sheets: %s", str(e))
            raise UserError(_("An error occurred while accessing Google Sheets: %s" % str(e)))

    # ---------------------------------------------------------------------
    # Utilidades varias
    # ---------------------------------------------------------------------

    @staticmethod
    def _get_dias_credito(payment_term):
        if not payment_term:
            return "VERIFICAR"
        name = payment_term.name.lower()
        if "inmediato" in name or "immediate" in name or "contado" in name:
            return 0
        numbers = re.findall(r'\d+', name)
        return int(numbers[0]) if numbers else "VERIFICAR"

    # ---------------------------------------------------------------------
    # Acción principal: exportar / actualizar Sheet
    # ---------------------------------------------------------------------

    def action_extract_prompt_data(self):
        """Exporta pedidos a Google Sheets.

        - Si el folio (pedido interno) ya existe, se eliminan sus filas actuales y se
          insertan las nuevas en la MISMA posición.
        - Si hay menos filas nuevas que antiguas, las sobrantes quedan eliminadas.
        - Si el folio no existe, simplemente se añaden al final.
        """
        try:
            worksheet = self._get_worksheet()
            all_pids = worksheet.col_values(4)  # columna D = Pedido Interno
            _logger.info("Existing folios fetched (%d)", len(all_pids))
        except UserError:
            raise
        except Exception as e:
            _logger.error("Failed to connect to Google Sheets: %s", str(e))
            raise UserError(_("Failed to connect to Google Sheets. Check logs for details."))

        any_change = False

        for order in self:
            # ------------------------- Construir filas -------------------------
            order_rows = []

            invoice = self.env['account.move'].search([
                ('invoice_origin', '=', order.name),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted')
            ], limit=1)
            factura = invoice.name if invoice else "VERIFICAR"
            fecha_dt = (invoice.invoice_date if invoice and invoice.invoice_date else order.date_order.date())
            fecha = fecha_dt.strftime('%Y-%m-%d')
            mes = fecha_dt.month

            oc = order.client_order_ref or "VERIFICAR"
            dias_credito = self._get_dias_credito(order.payment_term_id)
            cred_cont = (
                "CRÉDITO" if isinstance(dias_credito, int) and dias_credito > 0 else
                "CONTADO" if isinstance(dias_credito, int) else
                "VERIFICAR"
            )

            currency_map = {'MXN': 'Peso Mexicano', 'USD': 'Dólar Americano'}
            moneda = currency_map.get(order.currency_id.name, order.currency_id.name or "")

            # Tipo de cambio (order.currency -> MXN)
            fecha_cot = order.date_order
            try:
                tc = self.env['res.currency']._get_conversion_rate(
                    order.currency_id,
                    order.company_id.currency_id,
                    order.company_id,
                    fecha_cot.date()
                )
            except Exception as e:
                tc = 1.0 if order.currency_id == order.company_id.currency_id else 0.0
                _logger.warning("Rate error for %s on %s: %s", order.currency_id.name, fecha_cot, str(e))

            # Recorrer líneas no display_type
            for line in order.order_line.filtered(lambda l: not l.display_type):
                full = line.product_id.display_name or ''
                concepto = re.sub(r'^\[.*?\]\s*', '', full)

                
                _logger.info("Using product name for concepto: %s", concepto)
                categoria = 'FABRICACION' if any(t in concepto.lower() for t in ['tabla', 'cono', 'módulo']) else 'COMERCIAL'
                familia = (line.product_id.categ_id.name or '').upper()
                total_mxn = line.price_total * tc if order.currency_id != order.company_id.currency_id else line.price_total

                order_rows.append([
                    factura, str(mes), fecha, order.name or 'VERIFICAR', oc,
                    'DOMICILIO', order.partner_id.name or 'VERIFICAR',
                    line.product_id.default_code or '', concepto,
                    str(line.product_uom_qty), line.product_uom.name or '',
                    f"{line.price_unit:.2f}", f"{line.price_subtotal:.2f}",
                    f"{line.price_tax:.2f}", f"{line.price_total:.2f}",
                    moneda, f"{tc:.6f}", f"{total_mxn:.2f}",
                    str(dias_credito), cred_cont, categoria, familia, 'PENDIENTE'
                ])

            # --------------------------- Escribir Sheet ---------------------------
            if order.name in all_pids:
                indices = [i + 1 for i, v in enumerate(all_pids) if v == order.name]
                start_idx = indices[0]
                _logger.info("Updating folio %s at rows %s (start %s)", order.name, indices, start_idx)

                # Borrar existentes en orden descendente
                for idx in reversed(indices):
                    worksheet.delete_rows(idx)
                # Insertar nuevas filas en la misma posición
                worksheet.insert_rows(order_rows, start_idx, value_input_option='USER_ENTERED')
                _logger.info("Inserted %d row(s) for folio %s at position %s", len(order_rows), order.name, start_idx)
            else:
                worksheet.append_rows(order_rows, value_input_option='USER_ENTERED')
                _logger.info("Appended %d row(s) for new folio %s", len(order_rows), order.name)

            any_change = True

        # ------------------------- Notificación final -------------------------
        title = _('Extraction Successful') if any_change else _('No New Data')
        message = _('Sale orders exported / updated successfully.') if any_change else _('All selected orders are up to date.')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'sticky': False,
            }
        }
