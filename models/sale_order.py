# -*- coding: utf-8 -*-

import logging
import re
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_dias_credito(self, payment_term):
        if not payment_term:
            return "VERIFICAR"
        
        name = payment_term.name.lower()
        if "inmediato" in name or "immediate" in name:
            return 0
        
        numbers = re.findall(r'\d+', name)
        return int(numbers[0]) if numbers else "VERIFICAR"

    def action_extract_prompt_data(self):
        for order in self:
            output_lines = []
            
            header = [
                "FACTURA", "MES", "fecha emision", "Pedido Interno", "O.C.", "ENTREGA", 
                "Cliente", "código prod/serv", "Concepto", "cantidad", "unidad", 
                "p.u.", "importe", "iva", "total", "moneda", "tc", "total mxn", 
                "dias de credito", "cred-cont", "categoria", "familia", "ESTATUS"
            ]
            output_lines.append("\t".join(header))

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

            tc_field_name = 'x_studio_tasa_de_cambio'
            tc = order[tc_field_name] if tc_field_name in order and order.currency_id.name != 'MXN' else ""
            
            # Line Info
            for line in order.order_line.filtered(lambda l: not l.display_type):
                concepto = line.name.replace('\n', ' ').replace('\r', ' ')
                
                categoria = "VERIFICAR"
                if any(term in concepto for term in ["Tabla", "Cono", "Módulo"]):
                    categoria = "FABRICACION"
                else:
                    categoria = "COMERCIAL"
                
                familia = concepto.split(' ')[0] if concepto else ''
                
                total_mxn = line.price_total
                if order.currency_id.name != 'MXN' and isinstance(tc, (int, float)) and tc > 0:
                    total_mxn = line.price_total * tc
                elif order.currency_id.name != 'MXN':
                    total_mxn = "VERIFICAR"

                line_data = [
                    factura,
                    str(mes),
                    fecha_emision,
                    order.name or "VERIFICAR",
                    oc,
                    "DOMICILIO",
                    order.partner_id.name or "VERIFICAR",
                    line.product_id.default_code or "",
                    concepto,
                    str(line.product_uom_qty),
                    line.product_uom.name or "",
                    f"{line.price_unit:.2f}",
                    f"{line.price_subtotal:.2f}",
                    f"{line.price_tax:.2f}",
                    f"{line.price_total:.2f}",
                    order.currency_id.name or "",
                    str(tc) if tc else "",
                    f"{total_mxn:.2f}" if isinstance(total_mxn, (int, float)) else total_mxn,
                    str(dias_credito),
                    cred_cont,
                    categoria,
                    familia,
                    "PENDIENTE"
                ]
                output_lines.append("\t".join(line_data))

            final_output = "contenido: |\n  " + "\n  ".join(output_lines)
            _logger.info("Datos Extraídos para Prompt:\n%s", final_output)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Extracción Exitosa',
                'message': 'Los datos han sido extraídos y registrados en el log.',
                'sticky': False,
            }
        } 