# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

VENDOR_BILL_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "vendor_name": {
            "type": "STRING",
            "description": "Legal company name or trade name of the supplier/vendor"
        },
        "vendor_vat": {
            "type": "STRING",
            "description": "Tax ID, VAT registration number, or NPWP of the vendor"
        },
        "vendor_email": {
            "type": "STRING",
            "description": "Email address of the vendor"
        },
        "vendor_phone": {
            "type": "STRING",
            "description": "Phone number or mobile number of the vendor"
        },
        "vendor_address": {
            "type": "STRING",
            "description": "Full street address or city/country of the vendor"
        },
        "bill_number": {
            "type": "STRING",
            "description": "Supplier invoice number, bill reference, or receipt number"
        },
        "bill_date": {
            "type": "STRING",
            "description": "Invoice date in YYYY-MM-DD format"
        },
        "due_date": {
            "type": "STRING",
            "description": "Payment due date in YYYY-MM-DD format"
        },
        "currency_code": {
            "type": "STRING",
            "description": "3-letter ISO currency code, e.g. USD, EUR, IDR, GBP"
        },
        "subtotal_amount": {
            "type": "NUMBER",
            "description": "Net untaxed subtotal amount"
        },
        "tax_amount": {
            "type": "NUMBER",
            "description": "Total tax / VAT / GST amount"
        },
        "total_amount": {
            "type": "NUMBER",
            "description": "Grand total amount payable on the invoice"
        },
        "line_items": {
            "type": "ARRAY",
            "description": "List of products, goods, or services billed",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "description": {
                        "type": "STRING",
                        "description": "Description of item or service"
                    },
                    "product_code": {
                        "type": "STRING",
                        "description": "Item SKU, part number, or barcode if visible"
                    },
                    "quantity": {
                        "type": "NUMBER",
                        "description": "Quantity purchased (default 1)"
                    },
                    "unit_price": {
                        "type": "NUMBER",
                        "description": "Unit price excluding tax"
                    },
                    "discount_percentage": {
                        "type": "NUMBER",
                        "description": "Discount percentage if applicable"
                    }
                },
                "required": ["description", "quantity", "unit_price"]
            }
        }
    },
    "required": ["bill_number", "total_amount", "line_items"]
}


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'ai.document.extract.mixin']

    ai_detected_vendor_name = fields.Char(string='Detected Vendor', readonly=True, copy=False)
    ai_detected_bill_ref = fields.Char(string='Detected Bill Ref', readonly=True, copy=False)
    ai_detected_bill_date = fields.Date(string='Detected Date', readonly=True, copy=False)
    ai_detected_due_date = fields.Date(string='Detected Due Date', readonly=True, copy=False)
    ai_detected_subtotal = fields.Monetary(string='Detected Subtotal', currency_field='currency_id', readonly=True, copy=False)
    ai_detected_tax = fields.Monetary(string='Detected Tax', currency_field='currency_id', readonly=True, copy=False)
    ai_detected_total = fields.Monetary(string='Detected Total', currency_field='currency_id', readonly=True, copy=False)

    ai_total_discrepancy = fields.Monetary(
        string='Discrepancy (Odoo vs Doc)',
        currency_field='currency_id',
        compute='_compute_ai_discrepancy',
        help='Difference between Odoo computed total and the total detected on the document.'
    )

    ai_has_discrepancy = fields.Boolean(
        string='Has Discrepancy',
        compute='_compute_ai_discrepancy',
        help='True if there is a discrepancy greater than 0.05 between Odoo and the document total.'
    )
    ai_discrepancy_dismissed = fields.Boolean(
        string='Discrepancy Dismissed',
        default=False,
        copy=False,
        help='Indicates whether the user has dismissed the discrepancy alert banner.'
    )

    @api.depends('amount_total', 'ai_detected_total', 'extraction_status')
    def _compute_ai_discrepancy(self):
        for move in self:
            if move.extraction_status == 'extracted' and move.ai_detected_total:
                diff = move.amount_total - move.ai_detected_total
                move.ai_total_discrepancy = diff
                move.ai_has_discrepancy = abs(diff) > 0.05
            else:
                move.ai_total_discrepancy = 0.0
                move.ai_has_discrepancy = False

    def action_dismiss_ai_discrepancy(self):
        """Dismiss the discrepancy alert banner for this bill."""
        self.ensure_one()
        self.write({'ai_discrepancy_dismissed': True})
        return True

    def action_extract_vendor_bill_ai(self):
        """
        Main extraction action triggered by 'Extract with AI' button on Vendor Bill.
        If multiple documents are attached, launches attachment selector/merge wizard.
        If single document, proceeds directly with extraction.
        """
        self.ensure_one()

        if self.move_type not in ('in_invoice', 'in_refund'):
            raise UserError("AI Bill Extraction is only applicable for Vendor Bills and Vendor Credit Notes.")

        if self.state != 'draft':
            raise UserError("You can only run AI extraction on Draft bills.")

        # Find attachments
        attachments = self._get_document_attachments()
        if not attachments:
            raise UserError(
                "No invoice document found!\n"
                "Please attach a PDF or image of the vendor bill (drag & drop into Chatter or the paperclip icon) before extracting."
            )

        if len(attachments) > 1 and not self.env.context.get('skip_attachment_selector'):
            return self._open_attachment_select_wizard(attachments)

        return self.action_execute_ai_extraction(attachments)

    def action_execute_ai_extraction(self, attachments):
        """
        Executes AI Vision extraction on given attachment(s) and opens preview wizard.
        """
        self.ensure_one()
        if not attachments:
            raise UserError("No document attachments selected for extraction.")

        self.write({
            'extraction_status': 'processing',
            'extraction_error': False,
            'ai_discrepancy_dismissed': False,
        })

        system_prompt = (
            "You are an enterprise accounting document parser specialized in Odoo ERP.\n"
            "Accurately extract all vendor invoice details into the specified JSON schema.\n"
            "Format dates as YYYY-MM-DD. Never invent or hallucinate data that is not visible on the bill."
        )

        user_prompt = "Extract all vendor bill details, line items, and financial amounts from this invoice document."

        try:
            extracted_data = self._call_ai_vision_api(
                attachments=attachments,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=VENDOR_BILL_SCHEMA
            )
            return self._open_ai_preview_wizard(extracted_data)
        except Exception as e:
            _logger.exception("AI Vendor Bill Extraction failed for move ID %s", self.id)
            self.write({
                'extraction_status': 'failed',
                'extraction_error': str(e),
            })
            self.message_post(
                body=f"<p>❌ <b>AI Document Extraction Failed</b>: {str(e)}</p>",
                subject="AI Extraction Error"
            )
            raise UserError(f"AI Extraction Failed: {str(e)}")

    def _open_ai_preview_wizard(self, data):
        """
        Creates transient preview wizard pre-populated with matched extracted data,
        allowing the user to inspect, modify, and confirm before applying to the bill.
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        auto_create_partner = company.auto_create_partner
        auto_create_product = company.auto_create_product

        partner_model = self.env['res.partner']
        product_model = self.env['product.product']

        # Extract vendor metadata
        vendor_data = data.get('vendor') if isinstance(data.get('vendor'), dict) else {}
        issuer_data = data.get('issuer') if isinstance(data.get('issuer'), dict) else {}
        platform_data = data.get('platform') if isinstance(data.get('platform'), dict) else {}

        vendor_name = (
            data.get('vendor_name') or
            vendor_data.get('name') or
            issuer_data.get('name') or
            platform_data.get('name') or
            ''
        ).strip()

        vendor_vat = (
            data.get('vendor_vat') or
            vendor_data.get('tax_id') or
            vendor_data.get('vat') or
            issuer_data.get('tax_id') or
            platform_data.get('tax_id') or
            ''
        ).strip()

        vendor_email = (
            data.get('vendor_email') or
            vendor_data.get('email') or
            issuer_data.get('email') or
            ''
        ).strip()

        vendor_phone = (
            data.get('vendor_phone') or
            vendor_data.get('phone') or
            issuer_data.get('phone') or
            ''
        ).strip()

        bill_number = (
            data.get('bill_number') or
            data.get('reference') or
            data.get('invoice_number') or
            data.get('order_id') or
            data.get('receipt_number') or
            ''
        ).strip()

        currency_code = (
            data.get('currency_code') or
            data.get('currency') or
            'IDR'
        ).strip()

        # Partner Matching
        matched_partner = False
        if vendor_vat:
            matched_partner = partner_model.search([('vat', '=', vendor_vat)], limit=1)
        if not matched_partner and vendor_email:
            matched_partner = partner_model.search([('email', '=ilike', vendor_email)], limit=1)
        if not matched_partner and vendor_phone:
            matched_partner = partner_model.search(['|', ('phone', '=', vendor_phone), ('mobile', '=', vendor_phone)], limit=1)
        if not matched_partner and vendor_name:
            matched_partner = partner_model.search([('name', '=ilike', vendor_name)], limit=1)

        if not matched_partner and vendor_name and auto_create_partner:
            matched_partner = partner_model.create({
                'name': vendor_name,
                'supplier_rank': 1,
                'vat': vendor_vat or False,
                'email': vendor_email or False,
                'phone': vendor_phone or False,
            })

        # Currency Matching
        matched_currency = False
        if currency_code:
            matched_currency = self.env['res.currency'].search([('name', '=ilike', currency_code)], limit=1)

        # Dates
        raw_bill_date = data.get('bill_date') or data.get('invoice_date') or data.get('date')
        inv_date = self._parse_extracted_date(raw_bill_date)
        raw_due_date = data.get('due_date') or data.get('payment_due_date') or data.get('due')
        due_date = self._parse_extracted_date(raw_due_date)

        # Financial totals
        totals_data = data.get('totals') if isinstance(data.get('totals'), dict) else {}
        total_amount = float(data.get('total_amount') or totals_data.get('total_bill_amount') or data.get('total') or 0.0)
        subtotal_amount = float(data.get('subtotal_amount') or totals_data.get('product_subtotal') or data.get('subtotal') or 0.0)
        tax_amount = float(data.get('tax_amount') or totals_data.get('tax_amount') or 0.0)

        # Line items
        line_items = data.get('line_items') or []
        charges = data.get('charges_and_discounts') or []

        wizard_line_commands = []
        for item in line_items:
            desc = item.get('description') or 'Item'
            code = (item.get('product_code') or '').strip()
            qty = float(item.get('quantity') or 1.0)
            price = float(item.get('unit_price') or item.get('line_total') or 0.0)
            disc = float(item.get('discount_percentage') or 0.0)

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
                    'purchase_ok': True,
                    'sale_ok': False,
                })

            wizard_line_commands.append((0, 0, {
                'description': desc,
                'product_id': matched_product.id if matched_product else False,
                'quantity': qty,
                'price_unit': price,
                'discount': disc,
                'price_subtotal': qty * price * (1.0 - (disc / 100.0)),
            }))

        for chg in charges:
            amt = float(chg.get('amount') or 0.0)
            if amt != 0:
                chg_desc = chg.get('description') or chg.get('type') or 'Charge / Discount'
                wizard_line_commands.append((0, 0, {
                    'description': chg_desc,
                    'quantity': 1.0,
                    'price_unit': amt,
                    'price_subtotal': amt,
                }))

        wizard_vals = {
            'move_id': self.id,
            'partner_name_raw': vendor_name,
            'ref': bill_number or self.ref,
            'invoice_date': inv_date or fields.Date.context_today(self),
            'invoice_date_due': due_date or False,
            'currency_id': matched_currency.id if matched_currency else self.currency_id.id,
            'detected_total': total_amount,
            'detected_subtotal': subtotal_amount,
            'detected_tax': tax_amount,
            'raw_json_text': json.dumps(data, indent=2, ensure_ascii=False),
            'line_ids': wizard_line_commands,
        }
        if matched_partner:
            wizard_vals['partner_id'] = matched_partner.id

        wizard = self.env['account.move.ai.preview.wizard'].create(wizard_vals)

        return {
            'name': f'AI Vision Preview: {vendor_name or bill_number or "Vendor Bill"}',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.ai.preview.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model
    def _parse_extracted_date(self, date_val):
        """
        Parses various date formats from extracted documents into datetime.date.
        Supports YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, etc.
        """
        if not date_val:
            return False
        date_str = str(date_val).strip()
        if not date_str:
            return False
        # If timestamp is included, take the date part
        if 'T' in date_str:
            date_str = date_str.split('T')[0]
        elif ' ' in date_str:
            date_str = date_str.split(' ')[0]

        formats = [
            '%Y-%m-%d',
            '%d-%m-%Y',
            '%d/%m/%Y',
            '%Y/%m/%d',
            '%d.%m.%Y',
            '%Y.%m.%d',
            '%b %d, %Y',
            '%d %b %Y',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue
        return False

    def _apply_extracted_vendor_bill(self, data):
        """
        Safely reconciles extracted data into Odoo account.move records without corrupting accounting totals.
        Handles standard flat invoice schemas as well as marketplace/nested formats (e.g. Tokopedia, Shopee).
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        auto_create_partner = company.auto_create_partner
        auto_create_product = company.auto_create_product

        partner_model = self.env['res.partner']
        product_model = self.env['product.product']

        # Extract vendor metadata with robust fallbacks for nested objects
        vendor_data = data.get('vendor') if isinstance(data.get('vendor'), dict) else {}
        issuer_data = data.get('issuer') if isinstance(data.get('issuer'), dict) else {}
        platform_data = data.get('platform') if isinstance(data.get('platform'), dict) else {}

        vendor_name = (
            data.get('vendor_name') or
            vendor_data.get('name') or
            issuer_data.get('name') or
            platform_data.get('name') or
            ''
        ).strip()

        vendor_vat = (
            data.get('vendor_vat') or
            vendor_data.get('tax_id') or
            vendor_data.get('vat') or
            issuer_data.get('tax_id') or
            platform_data.get('tax_id') or
            ''
        ).strip()

        vendor_email = (
            data.get('vendor_email') or
            vendor_data.get('email') or
            issuer_data.get('email') or
            ''
        ).strip()

        vendor_phone = (
            data.get('vendor_phone') or
            vendor_data.get('phone') or
            issuer_data.get('phone') or
            ''
        ).strip()

        vendor_address = (
            data.get('vendor_address') or
            vendor_data.get('address') or
            issuer_data.get('address') or
            platform_data.get('address') or
            ''
        ).strip()

        bill_number = (
            data.get('bill_number') or
            data.get('reference') or
            data.get('invoice_number') or
            data.get('order_id') or
            data.get('receipt_number') or
            ''
        ).strip()

        currency_code = (
            data.get('currency_code') or
            data.get('currency') or
            'IDR'
        ).strip()

        # 1. Partner Matching (Tax ID -> Email -> Phone -> Name)
        matched_partner = False
        if vendor_vat:
            matched_partner = partner_model.search([('vat', '=', vendor_vat)], limit=1)
        if not matched_partner and vendor_email:
            matched_partner = partner_model.search([('email', '=ilike', vendor_email)], limit=1)
        if not matched_partner and vendor_phone:
            matched_partner = partner_model.search(['|', ('phone', '=', vendor_phone), ('mobile', '=', vendor_phone)], limit=1)
        if not matched_partner and vendor_name:
            matched_partner = partner_model.search([('name', '=ilike', vendor_name)], limit=1)

        # Fallback creation if allowed
        if not matched_partner and vendor_name and auto_create_partner:
            partner_vals = {
                'name': vendor_name,
                'supplier_rank': 1,
            }
            if vendor_vat:
                partner_vals['vat'] = vendor_vat
            if vendor_email:
                partner_vals['email'] = vendor_email
            if vendor_phone:
                partner_vals['phone'] = vendor_phone
            if vendor_address:
                partner_vals['street'] = vendor_address

            matched_partner = partner_model.create(partner_vals)
            _logger.info("Auto-created new vendor partner: %s (ID: %s)", vendor_name, matched_partner.id)

        # 2. Currency Matching
        matched_currency = False
        if currency_code:
            matched_currency = self.env['res.currency'].search([('name', '=ilike', currency_code)], limit=1)

        # 3. Date Parsing
        raw_bill_date = (
            data.get('bill_date') or
            data.get('invoice_date') or
            data.get('purchase_date') or
            data.get('order_date') or
            data.get('date')
        )
        inv_date = self._parse_extracted_date(raw_bill_date)

        raw_due_date = (
            data.get('due_date') or
            data.get('payment_due_date') or
            data.get('due')
        )
        due_date = self._parse_extracted_date(raw_due_date)

        # Financial totals
        totals_data = data.get('totals') if isinstance(data.get('totals'), dict) else {}
        total_amount = float(
            data.get('total_amount') or
            totals_data.get('total_bill_amount') or
            totals_data.get('total_shopping_amount') or
            totals_data.get('total_amount') or
            data.get('total') or
            0.0
        )
        subtotal_amount = float(
            data.get('subtotal_amount') or
            totals_data.get('product_subtotal') or
            totals_data.get('untaxed_amount') or
            data.get('subtotal') or
            0.0
        )
        tax_amount = float(
            data.get('tax_amount') or
            totals_data.get('tax_amount') or
            0.0
        )

        # Prepare move vals
        move_vals = {
            'ref': bill_number or self.ref,
            'ai_detected_vendor_name': vendor_name,
            'ai_detected_bill_ref': bill_number,
            'ai_detected_subtotal': subtotal_amount,
            'ai_detected_tax': tax_amount,
            'ai_detected_total': total_amount,
            'extracted_raw_json': json.dumps(data, indent=2),
            'extraction_status': 'extracted',
            'extraction_error': False,
        }

        if matched_partner:
            move_vals['partner_id'] = matched_partner.id
        if matched_currency:
            move_vals['currency_id'] = matched_currency.id
        if inv_date:
            move_vals['invoice_date'] = inv_date
            move_vals['ai_detected_bill_date'] = inv_date
        if due_date:
            move_vals['invoice_date_due'] = due_date
            move_vals['ai_detected_due_date'] = due_date

        # 4. Line Items Mapping
        line_items = data.get('line_items') or []
        charges_and_discounts = data.get('charges_and_discounts') or []

        invoice_lines_commands = [(5, 0, 0)]  # Clear existing draft lines

        # Default expense account fallback if no product is found (Odoo 18 uses company_ids)
        fallback_account_id = False
        if self.journal_id and self.journal_id.default_account_id:
            fallback_account_id = self.journal_id.default_account_id.id
        if not fallback_account_id:
            exp_acc = self.env['account.account'].search([
                ('company_ids', 'in', self.company_id.id),
                ('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation')),
            ], limit=1)
            if exp_acc:
                fallback_account_id = exp_acc.id

        for item in line_items:
            desc = item.get('description') or 'Item'
            code = (item.get('product_code') or '').strip()
            qty = float(item.get('quantity') or 1.0)
            price = float(item.get('unit_price') or item.get('line_total') or 0.0)
            discount = float(item.get('discount_percentage') or 0.0)

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
                    'purchase_ok': True,
                    'sale_ok': False,
                })
                _logger.info("Auto-created new product: %s (%s)", desc, code)

            line_val = {
                'display_type': 'product',
                'name': desc,
                'quantity': qty,
                'price_unit': price,
                'discount': discount,
            }

            if matched_product:
                line_val['product_id'] = matched_product.id
            elif fallback_account_id:
                line_val['account_id'] = fallback_account_id

            invoice_lines_commands.append((0, 0, line_val))

        # Add marketplace fees, discounts, and shipping charges if present
        for charge in charges_and_discounts:
            amt = float(charge.get('amount') or 0.0)
            if amt != 0:
                charge_desc = charge.get('description') or charge.get('type') or 'Fee / Discount'
                charge_val = {
                    'display_type': 'product',
                    'name': charge_desc,
                    'quantity': 1.0,
                    'price_unit': amt,
                }
                if fallback_account_id:
                    charge_val['account_id'] = fallback_account_id
                invoice_lines_commands.append((0, 0, charge_val))

        move_vals['invoice_line_ids'] = invoice_lines_commands
        self.write(move_vals)

        # 5. Post Chatter Summary
        partner_str = matched_partner.name if matched_partner else (f"⚠️ Not matched ('{vendor_name}')")
        items_count = len(line_items) + len([c for c in charges_and_discounts if float(c.get('amount') or 0.0) != 0])
        msg_body = f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
            <h4 style="margin: 0 0 8px 0; color: #1e3a8a;">✨ AI Document Extraction Summary</h4>
            <table style="width: 100%; font-size: 13px;">
                <tr><td><b>Vendor:</b></td><td>{partner_str}</td></tr>
                <tr><td><b>Bill Ref:</b></td><td>{bill_number or '-'}</td></tr>
                <tr><td><b>Bill Date:</b></td><td>{inv_date or '-'}</td></tr>
                <tr><td><b>Due Date:</b></td><td>{due_date or '-'}</td></tr>
                <tr><td><b>Detected Total:</b></td><td>{total_amount:,.2f} {currency_code}</td></tr>
                <tr><td><b>Line Items:</b></td><td>{items_count} item(s) mapped</td></tr>
            </table>
        </div>
        """
        self.message_post(body=msg_body, subtype_xmlid='mail.mt_note')
