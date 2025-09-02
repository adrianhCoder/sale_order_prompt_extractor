# -*- coding: utf-8 -*-

import logging
import re
import json
from datetime import datetime

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

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

    def _get_worksheet(self, company_name):
        _logger.info("Connecting to Google Sheet at configured URL and worksheet for company: %s", company_name)
        param = self.env['ir.config_parameter'].sudo()
        sheet_url = param.get_param('sale_order_prompt_extractor.google_sheet_url')
        
        # Obtener mapeo de empresas a hojas para facturas
        company_mapping_str = param.get_param('sale_order_prompt_extractor.company_invoice_mapping')
        default_worksheet = param.get_param('sale_order_prompt_extractor.google_sheet_worksheet_name', 'FACT G')
        
        _logger.info("DEBUG: company_invoice_mapping_str = '%s'", company_mapping_str)
        _logger.info("DEBUG: default_worksheet = '%s'", default_worksheet)
        
        # Determinar qué hoja usar
        worksheet_name = default_worksheet
        if company_name and company_mapping_str:
            try:
                company_mapping = json.loads(company_mapping_str)
                worksheet_name = company_mapping.get(company_name, default_worksheet)
                _logger.info("Company '%s' mapped to worksheet '%s'", company_name, worksheet_name)
            except json.JSONDecodeError:
                _logger.warning("Invalid JSON in company mapping, using default worksheet")
                worksheet_name = default_worksheet

        if not sheet_url:
            raise UserError(_("Google Sheet URL is not set in settings."))
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
            _logger.info("Successfully accessed worksheet '%s' for company '%s'", worksheet_name, company_name)
            return worksheet
        except gspread.exceptions.SpreadsheetNotFound:
            raise UserError(_("Spreadsheet not found at the provided URL."))
        except gspread.exceptions.WorksheetNotFound:
            raise UserError(_("Worksheet '%s' not found in the spreadsheet." % worksheet_name))
        except Exception as e:
            _logger.error("Error accessing Google Sheets for company '%s': %s", company_name, str(e))
            raise UserError(_("An error occurred while accessing Google Sheets for company '%s': %s" % (company_name, str(e))))

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

    def _get_tipo_cambio(self, currency, date):
        """Obtiene el tipo de cambio según la moneda"""
        if currency.name == 'USD':
            return 18.0  # Tipo de cambio fijo para USD
        elif currency.name == 'MXN':
            return 1.0   # Tipo de cambio fijo para MXN
        else:
            return 1.0   # Por defecto

    def _get_uuid(self):
        """Obtiene el UUID de la factura electrónica mexicana"""
        if hasattr(self, 'l10n_mx_edi_cfdi_uuid') and self.l10n_mx_edi_cfdi_uuid:
            return self.l10n_mx_edi_cfdi_uuid
        return ""

    # ---------------------------------------------------------------------
    # Acción principal: exportar / actualizar Sheet
    # ---------------------------------------------------------------------

    def action_extract_invoice_data(self):
        """Exporta facturas a Google Sheets.

        - Si la factura ya existe, se eliminan sus filas actuales y se
          insertan las nuevas en la MISMA posición.
        - Si hay menos filas nuevas que antiguas, las sobrantes quedan eliminadas.
        - Si la factura no existe, simplemente se añaden al final.
        - Agrupa facturas por empresa para usar la hoja correspondiente.
        """
        # Filtrar solo facturas de cliente (out_invoice)
        invoices = self.filtered(lambda inv: inv.move_type == 'out_invoice')
        
        if not invoices:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Invoices Selected'),
                    'message': _('Please select only customer invoices.'),
                    'sticky': False,
                }
            }

        # Agrupar facturas por empresa
        invoices_by_company = {}
        for invoice in invoices:
            company_name = invoice.company_id.name
            if company_name not in invoices_by_company:
                invoices_by_company[company_name] = []
            invoices_by_company[company_name].append(invoice)
        
        _logger.info("Processing invoices for companies: %s", list(invoices_by_company.keys()))
        
        any_change = False
        
        # Procesar cada empresa por separado
        for company_name, company_invoices in invoices_by_company.items():
            try:
                worksheet = self._get_worksheet(company_name)
                all_invoices = worksheet.col_values(3)  # columna C = Factura
                _logger.info("Processing %d invoices for company '%s' in worksheet (existing invoices: %d)", 
                           len(company_invoices), company_name, len(all_invoices))
            except UserError:
                raise
            except Exception as e:
                _logger.error("Failed to connect to Google Sheets for company '%s': %s", company_name, str(e))
                raise UserError(_("Failed to connect to Google Sheets for company '%s'. Check logs for details." % company_name))

            # Procesar facturas de esta empresa
            for invoice in company_invoices:
                # ------------------------- Construir filas -------------------------
                invoice_rows = []

                # Datos básicos de la factura
                mes = invoice.invoice_date.month if invoice.invoice_date else 1
                rfc = invoice.partner_id.vat or "VERIFICAR"
                factura = invoice.name or "VERIFICAR"
                cliente = invoice.partner_id.name or "VERIFICAR"
                
                # Determinar tipo (FABRICACION/COMERCIAL)
                tipo = "FABRICACION"  # Por defecto, se puede ajustar según lógica de negocio
                
                fecha_emision = invoice.invoice_date.strftime('%d/%m/%Y') if invoice.invoice_date else "VERIFICAR"
                vencimiento = invoice.invoice_date_due.strftime('%d/%m/%Y') if invoice.invoice_date_due else fecha_emision
                
                dias_credito = self._get_dias_credito(invoice.invoice_payment_term_id)
                cred_cont = (
                    "CRÉDITO" if isinstance(dias_credito, int) and dias_credito > 0 else
                    "CONTADO" if isinstance(dias_credito, int) else
                    "VERIFICAR"
                )

                # Recorrer líneas de la factura
                for line in invoice.invoice_line_ids:
                    codigo_prod = line.product_id.default_code or ""
                    full_name = line.product_id.display_name or line.name or ""
                    producto_concepto = re.sub(r'^\[.*?\]\s*', '', full_name)
                    
                    cantidad = line.quantity
                    unidad = line.product_uom_id.name if line.product_uom_id else "PZA"
                    precio_unitario = line.price_unit
                    importe = line.price_subtotal
                    iva = line.price_total - line.price_subtotal
                    total = line.price_total
                    
                    # Moneda y tipo de cambio
                    currency_map = {'MXN': 'Peso Mexicano', 'USD': 'Dólar Americano'}
                    moneda = currency_map.get(invoice.currency_id.name, invoice.currency_id.name or "MXN")
                    tc = self._get_tipo_cambio(invoice.currency_id, invoice.invoice_date)
                    total_factura = total
                    total_mxn = total * tc if tc != 1.0 else total
                    
                    # Familia y categoría
                    familia = (line.product_id.categ_id.name or "").upper()
                    categoria = "(Ninguno)"
                    
                    # UUID
                    uuid = self._get_uuid()

                    invoice_rows.append([
                        str(mes), rfc, factura, cliente, tipo, fecha_emision, vencimiento,
                        str(dias_credito), cred_cont, codigo_prod, producto_concepto,
                        str(cantidad), unidad, f"${precio_unitario:.2f}", f"${importe:.2f}",
                        f"${iva:.2f}", f"${total:.2f}", moneda, f"${total_factura:.2f}",
                        f"${tc:.2f}", f"${total_mxn:.2f}", familia, categoria, uuid
                    ])

                # --------------------------- Escribir Sheet ---------------------------
                if invoice.name in all_invoices:
                    indices = [i + 1 for i, v in enumerate(all_invoices) if v == invoice.name]
                    start_idx = indices[0]
                    _logger.info("Updating invoice %s at rows %s (start %s) in company '%s'", 
                               invoice.name, indices, start_idx, company_name)

                    # Borrar existentes en orden descendente
                    for idx in reversed(indices):
                        worksheet.delete_rows(idx)
                    # Insertar nuevas filas en la misma posición
                    worksheet.insert_rows(invoice_rows, start_idx, value_input_option='USER_ENTERED')
                    _logger.info("Inserted %d row(s) for invoice %s at position %s in company '%s'", 
                               len(invoice_rows), invoice.name, start_idx, company_name)
                else:
                    worksheet.append_rows(invoice_rows, value_input_option='USER_ENTERED')
                    _logger.info("Appended %d row(s) for new invoice %s in company '%s'", 
                               len(invoice_rows), invoice.name, company_name)

                any_change = True

        # ------------------------- Notificación final -------------------------
        title = _('Extraction Successful') if any_change else _('No New Data')
        message = _('Invoices exported / updated successfully.') if any_change else _('All selected invoices are up to date.')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'sticky': False,
            }
        }
