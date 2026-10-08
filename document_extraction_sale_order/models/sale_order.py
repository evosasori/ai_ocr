# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CUSTOMER_PO_SCHEMA = {
    "type": "object",
    "properties": {
        "customer": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "tax_id": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "address": {"type": "string"}
            }
        },
        "customer_name": {"type": "string"},
        "customer_vat": {"type": "string"},
        "customer_email": {"type": "string"},
        "customer_phone": {"type": "string"},
        "po_number": {"type": "string"},
        "po_date": {"type": "string"},
        "expected_delivery_date": {"type": "string"},
        "currency_code": {"type": "string"},
        "totals": {
            "type": "object",
            "properties": {
                "subtotal": {"type": "number"},
                "tax_amount": {"type": "number"},
                "total_amount": {"type": "number"}
            }
        },
        "total_amount": {"type": "number"},
        "subtotal_amount": {"type": "number"},
        "tax_amount": {"type": "number"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_code": {"type": "string"},
                    "description": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit_price": {"type": "number"},
                    "discount_percentage": {"type": "number"},
                    "line_total": {"type": "number"}
                },
                "required": ["description", "quantity", "unit_price"]
            }
        }
    },
    "required": ["po_number", "line_items"]
}


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'ai.document.extract.mixin']

    ai_detected_customer_name = fields.Char(
        string='Customer (AI Detected)',
        readonly=True,
        copy=False
    )
    ai_detected_po_number = fields.Char(
        string='Customer PO Number (AI)',
        readonly=True,
        copy=False
    )
    ai_detected_po_date = fields.Date(
        string='PO Date (AI)',
        readonly=True,
        copy=False
    )
    ai_detected_delivery_date = fields.Date(
        string='Delivery Date (AI)',
        readonly=True,
        copy=False
    )
    ai_detected_subtotal = fields.Monetary(
        string='Subtotal (AI)',
        currency_field='currency_id',
        readonly=True,
        copy=False
    )
    ai_detected_tax = fields.Monetary(
        string='Tax (AI)',
        currency_field='currency_id',
        readonly=True,
        copy=False
    )
    ai_detected_total = fields.Monetary(
        string='Total (AI)',
        currency_field='currency_id',
        readonly=True,
        copy=False
    )
    ai_po_discrepancy = fields.Float(
        string='PO Total Discrepancy',
        compute='_compute_ai_po_discrepancy',
        store=True,
        help='Selisih antara total dokumen PO fisik dengan total yang dihitung Odoo.'
    )
    ai_po_discrepancy_dismissed = fields.Boolean(
        string='Discrepancy Dismissed',
        default=False,
        copy=False
    )

    @api.depends('amount_total', 'ai_detected_total', 'ai_po_discrepancy_dismissed')
    def _compute_ai_po_discrepancy(self):
        for order in self:
            if order.ai_detected_total and not order.ai_po_discrepancy_dismissed:
                order.ai_po_discrepancy = round(abs(order.amount_total - order.ai_detected_total), 2)
            else:
                order.ai_po_discrepancy = 0.0

    def action_dismiss_ai_po_discrepancy(self):
        """Dismiss discrepancy alert on sale order."""
        self.ensure_one()
        self.write({'ai_po_discrepancy_dismissed': True})
        return True

    def action_extract_customer_po_ai(self):
        """
        Entry point for Customer PO AI extraction.
        If multiple documents are attached, presents the selection/merge wizard.
        If single document, runs extraction directly.
        """
        self.ensure_one()

        if self.state not in ('draft', 'sent'):
            raise UserError("Ekstraksi AI hanya dapat dijalankan pada Sales Order berstatus Quotation (Draft).")

        attachments = self._get_document_attachments()
        if not attachments:
            raise UserError(
                "Tidak ditemukan lampiran dokumen PO!\n\n"
                "Silakan unggah dokumen PDF atau gambar Surat Pesanan / Purchase Order dari Customer pada Chatter (ikon klip kertas) sebelum mengekstrak."
            )

        if len(attachments) > 1 and not self.env.context.get('skip_attachment_selector'):
            return self._open_attachment_select_wizard(attachments)

        return self.action_execute_ai_extraction(attachments)

    def action_execute_ai_extraction(self, attachments):
        """
        Executes AI Vision extraction on given attachment(s) and opens the preview wizard.
        """
        self.ensure_one()
        if not attachments:
            raise UserError("Tidak ada lampiran dokumen yang dipilih untuk diekstrak.")

        self.write({
            'extraction_status': 'processing',
            'extraction_error': False,
            'ai_po_discrepancy_dismissed': False,
        })

        system_prompt = (
            "You are an enterprise sales order parser specialized in Odoo ERP.\n"
            "Accurately extract all details from this Customer Purchase Order (PO) document into the JSON schema.\n"
            "Format dates as YYYY-MM-DD. Never invent or hallucinate data that is not visible on the document."
        )
        user_prompt = "Extract all Customer Purchase Order (PO) details, customer info, line items, and financial amounts."

        try:
            extracted_data = self._call_ai_vision_api(
                attachments=attachments,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=CUSTOMER_PO_SCHEMA
            )
            return self._open_sale_order_preview_wizard(extracted_data)
        except Exception as e:
            _logger.exception("AI Customer PO Extraction failed for Sale Order ID %s", self.id)
            self.write({
                'extraction_status': 'failed',
                'extraction_error': str(e),
            })
            self.message_post(
                body=f"<p>❌ <b>AI Customer PO Extraction Gagal</b>: {str(e)}</p>",
                subject="AI Extraction Error"
            )
            raise UserError(f"AI Extraction Gagal: {str(e)}")

    def _open_sale_order_preview_wizard(self, data):
        """
        Creates transient preview wizard pre-populated with matched extracted customer PO data.
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        auto_create_partner = company.auto_create_partner
        auto_create_product = company.auto_create_product

        partner_model = self.env['res.partner']
        product_model = self.env['product.product']

        # Metadata
        cust_data = data.get('customer') if isinstance(data.get('customer'), dict) else {}
        customer_name = (data.get('customer_name') or cust_data.get('name') or '').strip()
        customer_vat = (data.get('customer_vat') or cust_data.get('tax_id') or cust_data.get('vat') or '').strip()
        customer_email = (data.get('customer_email') or cust_data.get('email') or '').strip()
        customer_phone = (data.get('customer_phone') or cust_data.get('phone') or '').strip()
        po_number = (data.get('po_number') or data.get('client_order_ref') or '').strip()
        currency_code = (data.get('currency_code') or 'IDR').strip()

        # Customer matching (VAT -> Email -> Phone -> Name)
        matched_partner = False
        if customer_vat:
            matched_partner = partner_model.search([('vat', '=', customer_vat)], limit=1)
        if not matched_partner and customer_email:
            matched_partner = partner_model.search([('email', '=ilike', customer_email)], limit=1)
        if not matched_partner and customer_phone:
            matched_partner = partner_model.search(['|', ('phone', '=', customer_phone), ('mobile', '=', customer_phone)], limit=1)
        if not matched_partner and customer_name:
            matched_partner = partner_model.search([('name', '=ilike', customer_name)], limit=1)

        if not matched_partner and customer_name and auto_create_partner:
            matched_partner = partner_model.create({
                'name': customer_name,
                'customer_rank': 1,
                'vat': customer_vat or False,
                'email': customer_email or False,
                'phone': customer_phone or False,
            })

        # Currency matching
        matched_currency = False
        if currency_code:
            matched_currency = self.env['res.currency'].search([('name', '=ilike', currency_code)], limit=1)

        # Dates
        raw_po_date = data.get('po_date') or data.get('date')
        po_date = self._parse_extracted_date(raw_po_date)
        raw_deliv_date = data.get('expected_delivery_date') or data.get('delivery_date')
        deliv_date = self._parse_extracted_date(raw_deliv_date)

        # Totals
        totals_data = data.get('totals') if isinstance(data.get('totals'), dict) else {}
        total_amount = float(data.get('total_amount') or totals_data.get('total_amount') or data.get('total') or 0.0)
        subtotal_amount = float(data.get('subtotal_amount') or totals_data.get('subtotal') or data.get('subtotal') or 0.0)
        tax_amount = float(data.get('tax_amount') or totals_data.get('tax_amount') or 0.0)

        # Lines
        line_items = data.get('line_items') or []
        wizard_line_commands = []

        for item in line_items:
            desc = item.get('description') or 'Item'
            code = (item.get('product_code') or '').strip()
            qty = float(item.get('quantity') or 1.0)
            price = float(item.get('unit_price') or item.get('line_total') or 0.0)
            disc = float(item.get('discount_percentage') or 0.0)

            # Match product: SKU/Barcode -> Name
            matched_product = False
            if code:
                matched_product = product_model.search(['|', ('default_code', '=', code), ('barcode', '=', code)], limit=1)
            if not matched_product and desc:
                matched_product = product_model.search([('name', '=ilike', desc[:64])], limit=1)

            if not matched_product and code and auto_create_product:
                matched_product = product_model.create({
                    'name': desc,
                    'default_code': code,
                    'type': 'consu',
                    'sale_ok': True,
                    'purchase_ok': False,
                })

            wizard_line_commands.append((0, 0, {
                'description': desc,
                'product_id': matched_product.id if matched_product else False,
                'product_uom_qty': qty,
                'price_unit': price,
                'discount': disc,
                'price_subtotal': qty * price * (1.0 - (disc / 100.0)),
            }))

        wizard_vals = {
            'order_id': self.id,
            'partner_name_raw': customer_name,
            'client_order_ref': po_number or self.client_order_ref,
            'date_order': po_date or fields.Date.context_today(self),
            'commitment_date': deliv_date or False,
            'currency_id': matched_currency.id if matched_currency else (self.currency_id.id or self.company_id.currency_id.id),
            'detected_total': total_amount,
            'detected_subtotal': subtotal_amount,
            'detected_tax': tax_amount,
            'raw_json_text': json.dumps(data, indent=2, ensure_ascii=False),
            'line_ids': wizard_line_commands,
        }
        if matched_partner:
            wizard_vals['partner_id'] = matched_partner.id

        wizard = self.env['sale.order.ai.preview.wizard'].create(wizard_vals)

        return {
            'name': f'Preview AI PO Customer: {customer_name or po_number or "Sales Order"}',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.ai.preview.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model
    def _parse_extracted_date(self, date_val):
        """Helper to parse date string into date object."""
        if not date_val:
            return False
        date_str = str(date_val).strip()
        if not date_str:
            return False
        if 'T' in date_str:
            date_str = date_str.split('T')[0]
        elif ' ' in date_str:
            date_str = date_str.split(' ')[0]

        formats = ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%d.%m.%Y', '%b %d, %Y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue
        return False
