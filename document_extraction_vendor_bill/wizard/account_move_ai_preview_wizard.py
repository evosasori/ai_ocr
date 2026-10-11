# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMoveAiPreviewWizard(models.TransientModel):
    _name = 'account.move.ai.preview.wizard'
    _description = 'AI Vendor Bill Extraction Preview & Confirmation'

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
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Matched Odoo Vendor',
        help='Vendor contact matched in Odoo database.'
    )
    partner_name_raw = fields.Char(
        string='Vendor Name (OCR)',
        readonly=True
    )

    ref = fields.Char(
        string='Bill / Reference No.',
        help='Vendor bill or invoice reference number.'
    )
    invoice_date = fields.Date(
        string='Bill Date'
    )
    invoice_date_due = fields.Date(
        string='Due Date'
    )

    detected_total = fields.Monetary(
        string='Bill Total (OCR)',
        currency_field='currency_id'
    )
    detected_subtotal = fields.Monetary(
        string='Subtotal (OCR)',
        currency_field='currency_id'
    )
    detected_tax = fields.Monetary(
        string='Tax (OCR)',
        currency_field='currency_id'
    )

    line_ids = fields.One2many(
        'account.move.ai.preview.wizard.line',
        'wizard_id',
        string='Line Items'
    )

    raw_json_text = fields.Text(
        string='Raw OCR & JSON Output',
        readonly=True
    )

    def action_apply_to_bill(self):
        """
        Applies verified preview data from the wizard into the draft account.move record.
        """
        self.ensure_one()
        move = self.move_id

        if move.state != 'draft':
            raise UserError("This bill is no longer in draft state.")

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

        # Ensure Vendor is resolved
        partner = self.partner_id
        if not partner and self.partner_name_raw:
            partner = self.env['res.partner'].search([('name', '=ilike', self.partner_name_raw.strip())], limit=1)
            if not partner:
                partner = self.env['res.partner'].create({
                    'name': self.partner_name_raw.strip(),
                    'supplier_rank': 1,
                })
            self.partner_id = partner

        if partner:
            move_vals['partner_id'] = partner.id
        elif not move.partner_id:
            raise UserError("A Vendor is required for Vendor Bills. Please select or enter a Vendor before applying to the bill.")

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
            AccountAccount = self.env['account.account']
            acc_domain = []
            if 'account_type' in AccountAccount._fields:
                acc_domain.append(('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation')))
            elif 'user_type_id' in AccountAccount._fields:
                acc_domain.append(('user_type_id.internal_group', '=', 'expense'))

            if 'company_ids' in AccountAccount._fields:
                acc_domain.append(('company_ids', 'in', move.company_id.id))
            elif 'company_id' in AccountAccount._fields:
                acc_domain.append(('company_id', '=', move.company_id.id))

            exp_acc = AccountAccount.search(acc_domain, limit=1)
            if not exp_acc and 'account_type' in AccountAccount._fields:
                exp_acc = AccountAccount.search([('account_type', 'in', ('expense', 'expense_direct_cost'))], limit=1)
            if not exp_acc:
                exp_acc = AccountAccount.search([('code', '=like', '6%')], limit=1) or AccountAccount.search([('code', '=like', '5%')], limit=1)
            if exp_acc:
                fallback_account_id = exp_acc.id

        # Replace existing draft lines with verified lines from wizard
        line_commands = [(5, 0, 0)]
        for line in self.line_ids:
            line_val = {
                'name': line.description or 'Item',
                'quantity': line.quantity or 1.0,
                'price_unit': line.price_unit or 0.0,
                'discount': line.discount or 0.0,
            }
            if line.product_id:
                line_val['product_id'] = line.product_id.id
                prod_acc = line.product_id.property_account_expense_id or line.product_id.categ_id.property_account_expense_categ_id
                if prod_acc:
                    line_val['account_id'] = prod_acc.id
                elif fallback_account_id:
                    line_val['account_id'] = fallback_account_id
            elif fallback_account_id:
                line_val['account_id'] = fallback_account_id

            line_commands.append((0, 0, line_val))

        if len(line_commands) > 1:
            move_vals['invoice_line_ids'] = line_commands

        move.write(move_vals)

        # Log confirmation in chatter
        move.message_post(
            body=f"<p>✅ <b>AI Vision Extraction Approved & Applied</b>: {len(self.line_ids)} line items inserted.</p>",
            subject="AI Extraction Applied"
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Applied Successfully! 📄✨',
                'message': f"AI extraction data applied successfully to bill '{move.name or move.ref or ''}'.",
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
    _description = 'AI Extraction Preview Line Item'

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
        string='Odoo Product',
        help='Automatically matched Odoo product.'
    )
    description = fields.Char(
        string='Item Description',
        required=True
    )
    quantity = fields.Float(
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

    @api.depends('quantity', 'price_unit', 'discount')
    def _compute_price_subtotal(self):
        for line in self:
            qty = line.quantity or 0.0
            price = line.price_unit or 0.0
            disc = line.discount or 0.0
            line.price_subtotal = qty * price * (1.0 - (disc / 100.0))
