# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_connection_mode = fields.Selection(
        related='company_id.ai_connection_mode',
        readonly=False,
        required=True,
        string='AI Connection Mode',
        help='Pilih apakah perusahaan ini menggunakan Odoo AI Cloud Gateway atau Custom Endpoint (BYOK).'
    )

    gateway_url = fields.Char(
        related='company_id.gateway_url',
        readonly=False,
        string='Cloud Gateway URL',
        help='Base URL server Odoo AI Cloud Gateway.'
    )

    custom_ai_endpoint = fields.Char(
        related='company_id.custom_ai_endpoint',
        readonly=False,
        string='Custom Base URL',
        help='Base URL API OpenAI-compatible (contoh: https://api.openai.com/v1 atau https://api.groq.com/openai/v1)'
    )

    custom_ai_api_key = fields.Char(
        related='company_id.custom_ai_api_key',
        readonly=False,
        string='Custom API Key',
        help='API Key / Bearer token untuk Custom AI Endpoint.'
    )

    custom_ai_model = fields.Char(
        related='company_id.custom_ai_model',
        readonly=False,
        string='Model Vision AI',
        help='Kode model vision yang digunakan (contoh: gpt-4o-mini, llama-3.2-11b-vision-preview, dll).'
    )

    auto_create_partner = fields.Boolean(
        related='company_id.auto_create_partner',
        readonly=False,
        string='Auto-Create Contact / Vendor',
        help='Jika diaktifkan, otomatis membuat kontak/vendor baru jika tidak ditemukan kecocokan.'
    )

    auto_create_product = fields.Boolean(
        related='company_id.auto_create_product',
        readonly=False,
        string='Auto-Create Products',
        help='Jika diaktifkan, otomatis membuat produk baru jika tidak ditemukan barcode/SKU.'
    )

    def action_check_quota_status(self):
        """Delegate quota check to active company."""
        record = self or self.create({})
        record.ensure_one()
        company = record.company_id or self.env.company
        return company.action_check_quota_status()

    def action_open_topup_portal(self):
        """Delegate opening topup portal to active company."""
        record = self or self.create({})
        record.ensure_one()
        company = record.company_id or self.env.company
        return company.action_open_topup_portal()

    def action_test_ai_connection(self):
        """Delegate connection testing to active company."""
        record = self or self.create({})
        record.ensure_one()
        company = record.company_id or self.env.company
        return company.action_test_ai_connection()
