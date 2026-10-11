# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrExpenseAiPreviewWizard(models.TransientModel):
    _name = 'hr.expense.ai.preview.wizard'
    _description = 'AI Expense Receipt Extraction Preview'

    expense_id = fields.Many2one(
        'hr.expense',
        string='Related Expense',
        required=True,
        ondelete='cascade'
    )
    merchant_name = fields.Char(
        string='Merchant / Store Name',
        help='Merchant or store name detected on the receipt.'
    )
    description = fields.Char(
        string='Expense Description',
        required=True,
        help='Description of the expense to be recorded on the Expense record.'
    )
    date = fields.Date(
        string='Transaction Date',
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        currency_field='currency_id',
        required=True,
        help='Final total amount paid on the receipt.'
    )
    tax_amount = fields.Monetary(
        string='Tax Amount',
        currency_field='currency_id',
        help='Tax amount listed on the receipt if any.'
    )
    category_suggestion = fields.Char(
        string='AI Suggested Category',
        readonly=True,
        help='Expense category predicted by AI from the receipt content.'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Expense Category / Product (Optional)',
        domain="[('can_be_expensed', '=', True)]",
        help='Select an expense product for this transaction. If left empty, the system automatically uses the Default Expense Product from Settings.'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor / Merchant Contact',
        help='Vendor contact matched in Odoo.'
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
            raise UserError("Target Expense record not found.")

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
                "No active expense product found!\n\n"
                "Please select an expense product in this modal or configure a Default Expense Product under Settings > AI Document Extraction."
            )

        # Write to expense
        vals = {
            'name': self.description or self.merchant_name or effective_product.name or 'Expense',
            'product_id': effective_product.id,
            'date': self.date or fields.Date.context_today(self),
            'currency_id': self.currency_id.id,
            'ai_detected_merchant_name': self.merchant_name,
            'ai_detected_date': self.date,
            'ai_detected_total': self.total_amount,
            'ai_detected_tax': self.tax_amount,
            'ai_detected_category': self.category_suggestion,
            'extraction_status': 'extracted',
            'extraction_error': False,
            'extracted_raw_json': self.raw_json_text,
        }
        if 'total_amount_currency' in expense._fields:
            vals['total_amount_currency'] = self.total_amount
        else:
            vals['unit_amount'] = self.total_amount or 0.0
            vals['quantity'] = 1.0

        if self.partner_id:
            vals['vendor_id'] = self.partner_id.id

        expense.write(vals)

        # Post summary note in Chatter
        curr_name = self.currency_id.name or 'IDR'
        msg_body = f"""
        <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px;">
            <h4 style="margin: 0 0 8px 0; color: #1e3a8a;">🧾 AI Receipt Extraction Applied</h4>
            <table style="width: 100%; font-size: 13px;">
                <tr><td><b>Merchant:</b></td><td>{self.merchant_name or '-'}</td></tr>
                <tr><td><b>Date:</b></td><td>{self.date or '-'}</td></tr>
                <tr><td><b>Total:</b></td><td><b>{self.total_amount:,.2f} {curr_name}</b></td></tr>
                <tr><td><b>Tax:</b></td><td>{self.tax_amount:,.2f} {curr_name}</td></tr>
                <tr><td><b>Category / Product:</b></td><td>{effective_product.display_name}</td></tr>
                <tr><td><b>Description:</b></td><td>{self.description or '-'}</td></tr>
            </table>
        </div>
        """
        expense.message_post(body=msg_body, subtype_xmlid='mail.mt_note')

        return {'type': 'ir.actions.act_window_close'}
