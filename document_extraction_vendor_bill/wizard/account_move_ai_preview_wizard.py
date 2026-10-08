# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMoveAiPreviewWizard(models.TransientModel):
    _name = 'account.move.ai.preview.wizard'
    _description = 'Preview & Konfirmasi Ekstraksi AI Vendor Bill'

    move_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    company_id = fields.Many2one(
        'res.company',
        related='move_id.company_id',
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Mata Uang',
        default=lambda self: self.env.company.currency_id
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor Odoo Terkait',
        help='Kontak vendor yang dicocokkan di database Odoo.'
    )
    partner_name_raw = fields.Char(
        string='Nama Vendor (Hasil OCR)',
        readonly=True
    )

    ref = fields.Char(
        string='No. Referensi / Tagihan',
        help='Nomor faktur vendor atau invoice number.'
    )
    invoice_date = fields.Date(
        string='Tanggal Faktur'
    )
    invoice_date_due = fields.Date(
        string='Tanggal Jatuh Tempo'
    )

    detected_total = fields.Monetary(
        string='Total Tagihan (OCR)',
        currency_field='currency_id'
    )
    detected_subtotal = fields.Monetary(
        string='Subtotal (OCR)',
        currency_field='currency_id'
    )
    detected_tax = fields.Monetary(
        string='Pajak (OCR)',
        currency_field='currency_id'
    )

    line_ids = fields.One2many(
        'account.move.ai.preview.wizard.line',
        'wizard_id',
        string='Rincian Item'
    )

    raw_json_text = fields.Text(
        string='Hasil Mentah OCR & JSON',
        readonly=True
    )

    def action_apply_to_bill(self):
        """
        Applies verified preview data from the wizard into the draft account.move record.
        """
        self.ensure_one()
        move = self.move_id

        if move.state != 'draft':
            raise UserError("Faktur ini tidak lagi dalam status draft.")

        # Update move header
        move_vals = {
            'ref': self.ref or move.ref,
            'ai_detected_vendor_name': self.partner_name_raw,
            'ai_detected_bill_ref': self.ref,
            'ai_detected_subtotal': self.detected_subtotal,
            'ai_detected_tax': self.detected_tax,
            'ai_detected_total': self.detected_total,
            'extracted_raw_json': self.raw_json_text,
            'extraction_status': 'extracted',
            'extraction_error': False,
        }

        if self.partner_id:
            move_vals['partner_id'] = self.partner_id.id
        if self.currency_id:
            move_vals['currency_id'] = self.currency_id.id
        if self.invoice_date:
            move_vals['invoice_date'] = self.invoice_date
            move_vals['ai_detected_bill_date'] = self.invoice_date
        if self.invoice_date_due:
            move_vals['invoice_date_due'] = self.invoice_date_due
            move_vals['ai_detected_due_date'] = self.invoice_date_due

        # Determine fallback expense account if lines don't have product
        fallback_account_id = False
        if move.journal_id and move.journal_id.default_account_id:
            fallback_account_id = move.journal_id.default_account_id.id
        if not fallback_account_id:
            exp_acc = self.env['account.account'].search([
                ('company_ids', 'in', move.company_id.id),
                ('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation')),
            ], limit=1)
            if exp_acc:
                fallback_account_id = exp_acc.id

        # Replace existing draft lines with verified lines from wizard
        line_commands = [(5, 0, 0)]
        for line in self.line_ids:
            line_val = {
                'display_type': 'product',
                'name': line.description or 'Item',
                'quantity': line.quantity or 1.0,
                'price_unit': line.price_unit or 0.0,
                'discount': line.discount or 0.0,
            }
            if line.product_id:
                line_val['product_id'] = line.product_id.id
            elif fallback_account_id:
                line_val['account_id'] = fallback_account_id

            line_commands.append((0, 0, line_val))

        if len(line_commands) > 1:
            move_vals['invoice_line_ids'] = line_commands

        move.write(move_vals)

        # Log confirmation in chatter
        move.message_post(
            body=f"<p>✅ <b>AI Vision Extraction Disetujui & Diterapkan</b>: {len(self.line_ids)} baris item dimasukkan.</p>",
            subject="AI Extraction Applied"
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Berhasil Diterapkan! 📄✨',
                'message': f"Data ekstraksi AI berhasil dimasukkan ke faktur '{move.name or move.ref or ''}'.",
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                },
            }
        }


class AccountMoveAiPreviewWizardLine(models.TransientModel):
    _name = 'account.move.ai.preview.wizard.line'
    _description = 'Line Item Preview Ekstraksi AI'

    wizard_id = fields.Many2one(
        'account.move.ai.preview.wizard',
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
    quantity = fields.Float(
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

    @api.depends('quantity', 'price_unit', 'discount')
    def _compute_price_subtotal(self):
        for line in self:
            qty = line.quantity or 0.0
            price = line.price_unit or 0.0
            disc = line.discount or 0.0
            line.price_subtotal = qty * price * (1.0 - (disc / 100.0))
