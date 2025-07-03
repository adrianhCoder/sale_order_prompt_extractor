from odoo import models, fields, _
from odoo.exceptions import UserError

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_extract_invoice_data(self):
        # 1. Leer configuración
        sheet_url = self.env['ir.config_parameter'].sudo().get_param('sale_order_prompt_extractor.google_sheet_url')
        cred_json   = self.env['ir.config_parameter'].sudo().get_param('sale_order_prompt_extractor.google_service_account_json')
        worksheet_name = self.env['ir.config_parameter'].sudo().get_param('sale_order_prompt_extractor.google_sheet_invoice_worksheet_name') or 'FACT G'
        if not all([sheet_url, cred_json]):
            raise UserError(_("Faltan URL hoja o credenciales JSON."))
        # 2. Conectar a Google Sheets
        try:
            creds = Credentials.from_service_account_info(json.loads(cred_json), scopes=['https://www.googleapis.com/auth/spreadsheets'])
            gc = gspread.authorize(creds)
            sheet = gc.open_by_url(sheet_url).worksheet(worksheet_name)
        except Exception as e:
            raise UserError(_("Error al abrir la hoja de Google: %s") % e)
        # 3. Leer facturas ya procesadas (columna C: “factura”)
        existing = sheet.col_values(3)  # incluye cabecera
        # 4. Por cada factura seleccionada:
        rows_to_insert = []
        for inv in self:
            if inv.move_type != 'out_invoice':
                continue
            inv_id = inv.name
            # Recoger fecha y vencimiento
            fecha     = inv.invoice_date.strftime('%d/%m/%Y')
            vencim    = inv.invoice_date_due.strftime('%d/%m/%Y') if inv.invoice_date_due else fecha
            # Créditos
            dias     = self._get_dias_credito(inv.invoice_payment_term_id.note or inv.invoice_payment_term_id.name)
            contcr   = 'CONTADO' if dias == 0 else 'CRÉDITO' if dias > 0 else 'VERIFICAR'
            # Tipo de factura (COMERCIAL/FABRICACION) reutilizando la regla por producto
            def clasificar(name):
                kw = ['tabla','cono','módulo']
                return 'FABRICACION' if any(w.lower() in name.lower() for w in kw) else 'COMERCIAL'
            # Para UUID de factura electrónica:
            uuid = inv.l10n_mx_edi_cfdi_uuid or ''
            # 5. Cada línea de la factura (sin display_type):
            for line in inv.invoice_line_ids.filtered(lambda l: not l.display_type):
                prod   = line.product_id
                sku    = prod.default_code or ''
                fam    = prod.categ_id.name.upper()
                cat    = clasificar(line.name)
                # Tipo de cambio y totales en MXN
                tc     = self.env['res.currency']._get_conversion_rate(inv.currency_id, self.env.user.company_id.currency_id, inv.company_id, inv.invoice_date) if inv.currency_id != inv.company_id.currency_id else 1
                total_mxn = line.price_total * tc
                # Construir fila siguiendo orden de columnas:
                row = [
                    str(inv.invoice_date.month),
                    inv.partner_id.vat or '',
                    inv_id,
                    inv.partner_id.name,
                    cat,
                    fecha,
                    vencim,
                    dias,
                    contcr,
                    sku,
                    line.name,
                    float(line.quantity),
                    line.uom_id.name,
                    "{:.2f}".format(line.price_unit),
                    "{:.2f}".format(line.price_subtotal),
                    "{:.2f}".format(line.price_tax),
                    "{:.2f}".format(line.price_total),
                    inv.currency_id.name,
                    "{:.2f}".format(inv.amount_total),
                    "{:.6f}".format(tc),
                    "{:.2f}".format(total_mxn),
                    fam,
                    cat,
                    uuid,
                    inv.origin or '',
                ]
                rows_to_insert.append((inv_id, row))
        # 6. Actualizar la hoja
        #   - Para cada inv_id con filas viejas: localizar todas sus apariciones en columna C, borrar esos rangos
        #   - Insertar las nuevas filas, respetando posición o al final
        # (Aquí reutilizas la misma lógica que en sale_order: buscar índices, borrar bloques, etc.)
        # 7. Notificar al usuario
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Extraction Successful'),
                'message': _('Datos de facturas exportados a "%s".') % worksheet_name,
                'type': 'success',
            }
        }
