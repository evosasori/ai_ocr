# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrderAiPreviewWizard(models.TransientModel):
    _name = 'sale.order.ai.preview.wizard'
    _description = 'Preview & Konfirmasi Ekstraksi AI Sales Order'

    order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    company_id = fields.Many2one(
        'res.company',
        related='order_id.company_id',
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Mata Uang',
        default=lambda self: self.env.company.currency_id
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Pelanggan Odoo',
        help='Kontak customer yang dicocokkan di database Odoo.'
    )
    partner_name_raw = fields.Char(
        string='Nama Pelanggan (Hasil OCR)',
        readonly=True
    )

    client_order_ref = fields.Char(
        string='No. PO Pelanggan (Ref)',
        help='Nomor Purchase Order resmi dari customer.'
    )
    date_order = fields.Date(
        string='Tanggal Order PO'
    )
    commitment_date = fields.Date(
        string='Target Pengiriman (Delivery Date)'
    )

    detected_total = fields.Monetary(
        string='Total PO (OCR)',
        currency_field='currency_id'
    )
    detected_subtotal = fields.Monetary(
        string='Subtotal PO (OCR)',
        currency_field='currency_id'
    )
    detected_tax = fields.Monetary(
        string='Pajak PO (OCR)',
        currency_field='currency_id'
    )

    line_ids = fields.One2many(
        'sale.order.ai.preview.wizard.line',
        'wizard_id',
        string='Rincian Item Pesanan'
    )

    raw_json_text = fields.Text(
        string='Hasil Mentah OCR & JSON',
        readonly=True
    )

    def action_apply_to_sale_order(self):
        """
        Applies verified preview data from the wizard into the draft sale.order record.
        """
        self.ensure_one()
        order = self.order_id

        if order.state not in ('draft', 'sent'):
            raise UserError("Sales Order ini tidak lagi dalam status draft/quotation.")

        order_vals = {
            'client_order_ref': self.client_order_ref or order.client_order_ref,
            'ai_detected_customer_name': self.partner_name_raw,
            'ai_detected_po_number': self.client_order_ref,
            'ai_detected_subtotal': self.detected_subtotal,
            'ai_detected_tax': self.detected_tax,
            'ai_detected_total': self.detected_total,
            'extracted_raw_json': self.raw_json_text,
            'extraction_status': 'extracted',
            'extraction_error': False,
        }

        if self.partner_id:
            order_vals['partner_id'] = self.partner_id.id
        if self.date_order:
            order_vals['date_order'] = fields.Datetime.to_datetime(self.date_order)
            order_vals['ai_detected_po_date'] = self.date_order
        if self.commitment_date:
            order_vals['commitment_date'] = fields.Datetime.to_datetime(self.commitment_date)
            order_vals['ai_detected_delivery_date'] = self.commitment_date

        # Clear existing draft order lines and replace with verified lines from wizard
        line_commands = [(5, 0, 0)]
        for line in self.line_ids:
            line_val = {
                'name': line.description or 'Product Item',
                'product_uom_qty': line.product_uom_qty or 1.0,
                'price_unit': line.price_unit or 0.0,
                'discount': line.discount or 0.0,
            }
            if line.product_id:
                line_val['product_id'] = line.product_id.id
            else:
                # If product is not linked, Odoo sale.order requires product_id or section/note.
                # Find a generic service or first consumable product if exists
                gen_prod = self.env['product.product'].search([
                    ('sale_ok', '=', True),
                    ('type', '=', 'consu')
                ], limit=1)
                if gen_prod:
                    line_val['product_id'] = gen_prod.id

            if 'product_id' in line_val:
                line_commands.append((0, 0, line_val))

        if len(line_commands) > 1:
            order_vals['order_line'] = line_commands

        order.write(order_vals)

        order.message_post(
            body=f"<p>✅ <b>AI PO Extraction Disetujui & Diterapkan</b>: {len(self.line_ids)} baris item dimasukkan.</p>",
            subject="AI Customer PO Applied"
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Berhasil Diterapkan ke Sales Order! 📄✨',
                'message': f"Data PO Customer berhasil dimasukkan ke '{order.name}'.",
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                },
            }
        }


class SaleOrderAiPreviewWizardLine(models.TransientModel):
    _name = 'sale.order.ai.preview.wizard.line'
    _description = 'Line Item Preview Ekstraksi AI Sales Order'

    wizard_id = fields.Many2one(
        'sale.order.ai.preview.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='wizard_id.currency_id'
    )

    product_id = fields.Many2one(
        'product.product',
        string='Produk Odoo',
        help='Produk Odoo yang dicocokkan otomatis.'
    )
    description = fields.Char(
        string='Deskripsi Item',
        required=True
    )
    product_uom_qty = fields.Float(
        string='Kuantiti',
        default=1.0
    )
    price_unit = fields.Monetary(
        string='Harga Satuan',
        currency_field='currency_id'
    )
    discount = fields.Float(
        string='Diskon (%)',
        default=0.0
    )
    price_subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_price_subtotal',
        store=True,
        readonly=False,
        currency_field='currency_id'
    )

    @api.depends('product_uom_qty', 'price_unit', 'discount')
    def _compute_price_subtotal(self):
        for line in self:
            qty = line.product_uom_qty or 0.0
            price = line.price_unit or 0.0
            disc = line.discount or 0.0
            line.price_subtotal = qty * price * (1.0 - (disc / 100.0))
