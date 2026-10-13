# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrderAiPreviewWizard(models.TransientModel):
    _name = 'sale.order.ai.preview.wizard'
    _description = 'AI Sales Order Extraction Preview & Confirmation'

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
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Odoo Customer',
        help='Customer contact matched in Odoo database.'
    )
    partner_name_raw = fields.Char(
        string='Customer Name (OCR)',
        readonly=True
    )

    client_order_ref = fields.Char(
        string='Customer PO No. (Ref)',
        help='Customer Purchase Order reference.'
    )
    date_order = fields.Date(
        string='PO Order Date'
    )
    commitment_date = fields.Date(
        string='Expected Delivery Date'
    )

    detected_total = fields.Monetary(
        string='PO Total (OCR)',
        currency_field='currency_id'
    )
    detected_subtotal = fields.Monetary(
        string='PO Subtotal (OCR)',
        currency_field='currency_id'
    )
    detected_tax = fields.Monetary(
        string='PO Tax (OCR)',
        currency_field='currency_id'
    )

    line_ids = fields.One2many(
        'sale.order.ai.preview.wizard.line',
        'wizard_id',
        string='Order Line Items'
    )

    raw_json_text = fields.Text(
        string='Raw OCR & JSON Output',
        readonly=True
    )

    def action_apply_to_sale_order(self):
        """
        Applies verified preview data from the wizard into the draft sale.order record.
        """
        self.ensure_one()
        order = self.order_id

        if order.state not in ('draft', 'sent'):
            raise UserError("This Sales Order is no longer in draft or quotation state.")

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
        company = order.company_id or self.env.company
        Product = self.env['product.product']

        for line in self.line_ids:
            target_product = line.product_id

            if not target_product and line.description:
                target_product = Product.search([
                    ('name', '=ilike', line.description.strip()[:64])
                ], limit=1)

            if not target_product:
                if company.auto_create_product and line.description:
                    target_product = Product.create({
                        'name': line.description.strip(),
                        'sale_ok': True,
                        'type': 'consu',
                        'list_price': line.price_unit or 0.0,
                    })
                else:
                    # Look for any existing saleable product in database
                    target_product = Product.search([
                        ('sale_ok', '=', True)
                    ], limit=1)
                    if not target_product:
                        # Fallback: create a general sale product so line is valid in Odoo view
                        target_product = Product.create({
                            'name': line.description.strip() or 'Customer PO Item',
                            'default_code': 'PO_ITEM',
                            'type': 'consu',
                            'sale_ok': True,
                        })

            line_val = {
                'name': line.description or (target_product.display_name if target_product else 'Product Item'),
                'product_uom_qty': line.product_uom_qty or 1.0,
                'price_unit': line.price_unit or 0.0,
                'discount': line.discount or 0.0,
            }
            if target_product:
                line_val['product_id'] = target_product.id

            line_commands.append((0, 0, line_val))

        if len(line_commands) > 1:
            order_vals['order_line'] = line_commands

        order.write(order_vals)

        order.message_post(
            body=f"<p>✅ <b>AI PO Extraction Approved & Applied</b>: {len(self.line_ids)} line items inserted.</p>",
            subject="AI Customer PO Applied"
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Applied to Sales Order Successfully! 📄✨',
                'message': f"Customer PO data applied successfully to '{order.name}'.",
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
    _description = 'AI Sales Order Preview Line Item'

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
        string='Odoo Product',
        help='Automatically matched Odoo product.'
    )
    description = fields.Char(
        string='Item Description',
        required=True
    )
    product_uom_qty = fields.Float(
        string='Quantity',
        default=1.0
    )
    price_unit = fields.Monetary(
        string='Unit Price',
        currency_field='currency_id'
    )
    discount = fields.Float(
        string='Discount (%)',
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
