# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

EXPENSE_RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "merchant_name": {
            "type": "string",
            "description": "Store name, merchant, vendor, restaurant, gas station, hotel, or service provider"
        },
        "expense_date": {
            "type": "string",
            "description": "Date of transaction or receipt in YYYY-MM-DD format"
        },
        "description": {
            "type": "string",
            "description": "Brief description of the expense, items purchased, or purpose"
        },
        "currency_code": {
            "type": "string",
            "description": "3-letter ISO currency code, e.g. IDR, USD, EUR, SGD"
        },
        "total_amount": {
            "type": "number",
            "description": "Grand total paid on receipt including taxes and service fees"
        },
        "tax_amount": {
            "type": "number",
            "description": "Tax amount (PPN, PB1, VAT, service tax) if listed, otherwise 0"
        },
        "category_suggestion": {
            "type": "string",
            "description": "Category suggestion: meals, transport, fuel, travel, hotel, communication, supplies, other"
        }
    },
    "required": ["total_amount"]
}


class HrExpense(models.Model):
    _name = 'hr.expense'
    _inherit = ['hr.expense', 'ai.document.extract.mixin']

    ai_detected_merchant_name = fields.Char(
        string='Merchant (AI)',
        readonly=True,
        copy=False
    )
    ai_detected_date = fields.Date(
        string='Receipt Date (AI)',
        readonly=True,
        copy=False
    )
    ai_detected_total = fields.Monetary(
        string='Total (AI)',
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
    ai_detected_category = fields.Char(
        string='Category Suggestion (AI)',
        readonly=True,
        copy=False
    )

    def action_extract_expense_receipt_ai(self):
        """
        Entry point for Expense Receipt AI extraction.
        If multiple documents/photos are attached, opens attachment selector wizard.
        If single document, runs extraction directly.
        """
        self.ensure_one()

        if self.state not in ('draft', 'reported'):
            raise UserError("Ekstraksi AI hanya dapat dijalankan pada Expense berstatus Draft / Reported.")

        attachments = self._get_document_attachments()
        if not attachments:
            raise UserError(
                "Tidak ditemukan lampiran struk / bukti pengeluaran!\n\n"
                "Silakan unggah foto struk kasir, nota, atau invoice PDF pada Chatter (ikon klip kertas) sebelum mengekstrak."
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
            raise UserError("Tidak ada lampiran bukti struk yang dipilih untuk diekstrak.")

        self.write({
            'extraction_status': 'processing',
            'extraction_error': False,
        })

        system_prompt = (
            "You are an enterprise expense receipt parser specialized in Odoo ERP.\n"
            "Accurately extract all details from this receipt or expense document into the JSON schema.\n"
            "Format dates as YYYY-MM-DD. Never invent or hallucinate data that is not visible on the document."
        )
        user_prompt = "Extract all receipt details: merchant name, transaction date, total amount paid, taxes, description, and expense category."

        try:
            extracted_data = self._call_ai_vision_api(
                attachments=attachments,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=EXPENSE_RECEIPT_SCHEMA
            )
            return self._open_expense_preview_wizard(extracted_data)
        except Exception as e:
            _logger.exception("AI Receipt Extraction failed for Expense ID %s", self.id)
            self.write({
                'extraction_status': 'failed',
                'extraction_error': str(e),
            })
            self.message_post(
                body=f"<p>❌ <b>AI Receipt Extraction Gagal</b>: {str(e)}</p>",
                subject="AI Extraction Error"
            )
            raise UserError(f"AI Extraction Gagal: {str(e)}")

    def _open_expense_preview_wizard(self, data):
        """
        Prepares and opens the transient preview wizard for reviewing extracted receipt data.
        """
        self.ensure_one()
        company = self.company_id or self.env.company

        merchant_name = (data.get('merchant_name') or '').strip()
        description = (data.get('description') or '').strip()
        if not description:
            description = f"{merchant_name} - Pengeluaran" if merchant_name else self.name or "Pengeluaran"

        # Date parsing
        raw_date = data.get('expense_date') or data.get('date')
        receipt_date = self._parse_extracted_date(raw_date) or fields.Date.context_today(self)

        # Financial totals
        total_amount = float(data.get('total_amount') or 0.0)
        tax_amount = float(data.get('tax_amount') or 0.0)
        currency_code = (data.get('currency_code') or 'IDR').strip()

        matched_currency = False
        if currency_code:
            matched_currency = self.env['res.currency'].search([('name', '=ilike', currency_code)], limit=1)

        # Partner matching
        matched_partner = False
        if merchant_name:
            matched_partner = self.env['res.partner'].search([('name', '=ilike', merchant_name)], limit=1)

        # Smart Category matching
        category_suggestion = (data.get('category_suggestion') or '').strip()
        matched_product = self._match_expense_category_to_product(category_suggestion)

        # If no smart match, fall back to company default expense product
        if not matched_product and company.default_expense_product_id:
            matched_product = company.default_expense_product_id

        wizard_vals = {
            'expense_id': self.id,
            'merchant_name': merchant_name,
            'description': description,
            'date': receipt_date,
            'currency_id': matched_currency.id if matched_currency else (self.currency_id.id or company.currency_id.id),
            'total_amount': total_amount,
            'tax_amount': tax_amount,
            'category_suggestion': category_suggestion or 'other',
            'product_id': matched_product.id if matched_product else False,
            'partner_id': matched_partner.id if matched_partner else (self.vendor_id.id if hasattr(self, 'vendor_id') and self.vendor_id else False),
            'raw_json_text': json.dumps(data, indent=2, ensure_ascii=False),
        }

        wizard = self.env['hr.expense.ai.preview.wizard'].create(wizard_vals)

        return {
            'name': f'Preview Ekstraksi Struk AI: {merchant_name or description or "Expense"}',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.expense.ai.preview.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model
    def _match_expense_category_to_product(self, category_str):
        """
        Attempts to map AI category suggestion to existing expensed product.
        """
        if not category_str:
            return False

        cat = category_str.lower()
        Product = self.env['product.product']

        keywords_map = {
            'meals': ['meal', 'konsumsi', 'makan', 'food', 'restoran', 'restaurant'],
            'fuel': ['mileage', 'bbm', 'bensin', 'pertamina', 'shell', 'fuel'],
            'transport': ['travel', 'transport', 'tiket', 'grab', 'gojek', 'taksi', 'taxi'],
            'lodging': ['hotel', 'penginapan', 'lodging', 'accommodation'],
            'communication': ['comm', 'pulsa', 'telp', 'phone', 'internet'],
        }

        search_terms = []
        for key, terms in keywords_map.items():
            if key in cat or any(t in cat for t in terms):
                search_terms.extend(terms)

        if not search_terms:
            search_terms = [cat]

        for term in search_terms:
            prod = Product.search([
                ('can_be_expensed', '=', True),
                ('name', 'ilike', term)
            ], limit=1)
            if prod:
                return prod

        return False

    @api.model
    def _parse_extracted_date(self, date_val):
        """Parses various date formats from extracted documents into datetime.date."""
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
