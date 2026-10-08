# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrExpenseAiPreviewWizard(models.TransientModel):
    _name = 'hr.expense.ai.preview.wizard'
    _description = 'Preview Ekstraksi Struk Pengeluaran AI'

    expense_id = fields.Many2one(
        'hr.expense',
        string='Expense Terkait',
        required=True,
        ondelete='cascade'
    )
    merchant_name = fields.Char(
        string='Nama Merchant / Toko',
        help='Nama merchant atau tempat pembelian yang terdeteksi pada struk.'
    )
    description = fields.Char(
        string='Keterangan Pengeluaran',
        required=True,
        help='Deskripsi pengeluaran yang akan dicatat pada record Expense.'
    )
    date = fields.Date(
        string='Tanggal Transaksi',
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Mata Uang',
        required=True
    )
    total_amount = fields.Monetary(
        string='Total Pengeluaran',
        currency_field='currency_id',
        required=True,
        help='Total nominal akhir yang dibayarkan pada struk.'
    )
    tax_amount = fields.Monetary(
        string='Pajak (PPN/PB1)',
        currency_field='currency_id',
        help='Nominal pajak yang tercantum pada struk jika ada.'
    )
    category_suggestion = fields.Char(
        string='Kategori Estimasi AI',
        readonly=True,
        help='Kategori biaya yang diprediksi oleh AI dari isi struk.'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Kategori / Produk Beban (Opsional)',
        domain="[('can_be_expensed', '=', True)]",
        help='Pilih produk beban untuk transaksi ini. Jika dikosongkan, sistem akan otomatis menggunakan Default Expense Product dari Settings.'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor / Merchant Kontak',
        help='Kontak vendor yang dicocokkan di Odoo.'
    )
    raw_json_text = fields.Text(
        string='Raw AI Response JSON',
        readonly=True
    )

    def action_apply_to_expense(self):
        """
        Applies verified preview data to the target hr.expense record.
        Falls back to company default expense product if product_id is left empty.
        """
        self.ensure_one()
        expense = self.expense_id
        if not expense.exists():
            raise UserError("Record Expense target tidak ditemukan.")

        company = expense.company_id or self.env.company

        # Determine effective product
        effective_product = self.product_id
        if not effective_product:
            effective_product = company.default_expense_product_id

        if not effective_product:
            # Fallback to any active expensed product
            effective_product = self.env['product.product'].search([
                ('can_be_expensed', '=', True)
            ], limit=1)

        if not effective_product:
            raise UserError(
                "Tidak ditemukan produk beban yang aktif!\n\n"
                "Silakan pilih produk beban di modal ini atau atur Default Expense Product pada menu Settings > AI Document Extraction."
            )

        # Write to expense
        vals = {
            'name': self.description or self.merchant_name or effective_product.name or 'Expense',
            'product_id': effective_product.id,
            'date': self.date or fields.Date.context_today(self),
            'currency_id': self.currency_id.id,
            'total_amount_currency': self.total_amount,
            'ai_detected_merchant_name': self.merchant_name,
            'ai_detected_date': self.date,
            'ai_detected_total': self.total_amount,
            'ai_detected_tax': self.tax_amount,
            'ai_detected_category': self.category_suggestion,
            'extraction_status': 'extracted',
            'extraction_error': False,
            'extracted_raw_json': self.raw_json_text,
        }
        if self.partner_id:
            vals['vendor_id'] = self.partner_id.id

        expense.write(vals)

        # Post summary note in Chatter
        curr_name = self.currency_id.name or 'IDR'
        msg_body = f"""
        <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px;">
            <h4 style="margin: 0 0 8px 0; color: #1e3a8a;">🧾 Hasil Ekstraksi Struk AI Diterapkan</h4>
            <table style="width: 100%; font-size: 13px;">
                <tr><td><b>Merchant:</b></td><td>{self.merchant_name or '-'}</td></tr>
                <tr><td><b>Tanggal:</b></td><td>{self.date or '-'}</td></tr>
                <tr><td><b>Total:</b></td><td><b>{self.total_amount:,.2f} {curr_name}</b></td></tr>
                <tr><td><b>Pajak:</b></td><td>{self.tax_amount:,.2f} {curr_name}</td></tr>
                <tr><td><b>Kategori / Produk:</b></td><td>{effective_product.display_name}</td></tr>
                <tr><td><b>Keterangan:</b></td><td>{self.description or '-'}</td></tr>
            </table>
        </div>
        """
        expense.message_post(body=msg_body, subtype_xmlid='mail.mt_note')

        return {'type': 'ir.actions.act_window_close'}
