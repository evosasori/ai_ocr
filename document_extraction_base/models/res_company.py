# -*- coding: utf-8 -*-
import logging
import time
import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    ai_connection_mode = fields.Selection(
        [
            ('cloud', 'Odoo AI Cloud Gateway (Gratis 50 Dokumen - Siap Pakai)'),
            ('custom', 'Custom AI Endpoint / BYOK (OpenAI Compatible)'),
        ],
        string='AI Connection Mode',
        default='cloud',
        required=True,
        help='Pilih apakah perusahaan ini menggunakan Odoo AI Cloud Gateway (otomatis terhubung dengan lisensi & kuota trial) atau Custom Endpoint (BYOK OpenAI-compatible).'
    )

    # Cloud Gateway Settings
    gateway_url = fields.Char(
        string='Cloud Gateway URL',
        default='https://ai-gateway.triadiputra.my.id',
        help='Base URL server Odoo AI Cloud Gateway.'
    )

    # Custom / BYOK Settings
    custom_ai_endpoint = fields.Char(
        string='Custom Base URL',
        default='https://api.openai.com/v1',
        help='Base URL API OpenAI-compatible (contoh: https://api.openai.com/v1, https://api.groq.com/openai/v1, atau Ollama)'
    )

    custom_ai_api_key = fields.Char(
        string='Custom API Key',
        help='API Key / Bearer token untuk Custom AI Endpoint.'
    )

    custom_ai_model = fields.Char(
        string='Model Vision AI',
        default='gpt-4o-mini',
        help='Kode model vision yang digunakan (contoh: gpt-4o-mini, llama-3.2-11b-vision-preview, dll).'
    )

    # Matching Rules
    auto_create_partner = fields.Boolean(
        string='Auto-Create Contact / Vendor',
        default=False,
        help='Jika diaktifkan, otomatis membuat kontak/vendor baru jika tidak ditemukan kecocokan.'
    )

    auto_create_product = fields.Boolean(
        string='Auto-Create Products',
        default=False,
        help='Jika diaktifkan, otomatis membuat produk baru jika tidak ditemukan barcode/SKU.'
    )

    def init(self):
        super().init()
        self.env.cr.execute("""
            UPDATE res_company
            SET ai_connection_mode = 'cloud'
            WHERE ai_connection_mode IS NULL OR ai_connection_mode NOT IN ('cloud', 'custom');

            UPDATE res_company
            SET gateway_url = 'https://ai-gateway.triadiputra.my.id'
            WHERE gateway_url IS NULL OR gateway_url = '' OR gateway_url LIKE '%9router%';
        """)

    def _get_database_uuid(self):
        """Retrieve unique database UUID for Cloud Gateway identification."""
        return self.env['ir.config_parameter'].sudo().get_param('database.uuid') or 'unknown-db-uuid'

    def action_check_quota_status(self):
        """Checks live instance quota and subscription plan from Odoo AI Cloud Gateway."""
        self.ensure_one()
        gateway_url = (self.gateway_url or 'https://ai-gateway.triadiputra.my.id').rstrip('/')
        db_uuid = self._get_database_uuid()

        status_url = f"{gateway_url}/api/v1/status"
        headers = {
            'X-Odoo-DB-UUID': db_uuid,
            'X-Odoo-Company-Name': self.name,
            'X-Odoo-Base-URL': self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '',
        }

        try:
            start_time = time.time()
            response = requests.get(status_url, headers=headers, timeout=15)
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                data = response.json()
                plan = (data.get('plan') or 'trial').upper()
                remaining = data.get('remaining', 0)
                quota_limit = data.get('quota_limit', 50)
                quota_used = data.get('quota_used', 0)

                active_model = data.get('ai_model', '')
                model_str = f" | Model: {active_model}" if active_model else ""

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': f"⚡ Sisa Kuota AI ({self.name}): {remaining} Dokumen",
                        'message': f"Paket: {plan}{model_str} | Terpakai: {quota_used}/{quota_limit} docs | Sisa Kuota: {remaining} docs (Latensi: {latency_ms} ms)",
                        'type': 'success' if remaining > 10 else 'warning',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': f"Gagal Cek Kuota (HTTP {response.status_code})",
                        'message': response.text[:200],
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except requests.exceptions.RequestException as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Gagal Menghubungi Cloud Gateway',
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_open_topup_portal(self):
        """Opens user top-up portal on Cloud Gateway with current database UUID."""
        self.ensure_one()
        gateway_url = (self.gateway_url or 'https://ai-gateway.triadiputra.my.id').rstrip('/')
        db_uuid = self._get_database_uuid()
        upgrade_url = f"{gateway_url}/upgrade?uuid={db_uuid}"

        return {
            'type': 'ir.actions.act_url',
            'url': upgrade_url,
            'target': 'new',
        }

    def action_test_ai_connection(self):
        """Tests the active AI connection (Cloud Gateway or Custom BYOK) and reports latency."""
        self.ensure_one()
        mode = self.ai_connection_mode or 'cloud'

        if mode == 'cloud':
            return self.action_check_quota_status()

        elif mode == 'custom':
            endpoint = (self.custom_ai_endpoint or '').rstrip('/')
            api_key = self.custom_ai_api_key
            model = self.custom_ai_model or 'gpt-4o-mini'

            if not endpoint:
                raise UserError("Custom Base URL wajib diisi untuk mode BYOK.")
            if not api_key:
                raise UserError("Custom API Key wajib diisi untuk mode BYOK.")

            chat_url = f"{endpoint}/chat/completions" if not endpoint.endswith('/chat/completions') else endpoint
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            }
            payload = {
                'model': model,
                'messages': [
                    {'role': 'user', 'content': 'Ping test. Reply with JSON: {"status": "ok", "message": "PONG"}'}
                ],
                'temperature': 0.1,
                'stream': False
            }

            start_time = time.time()
            try:
                response = requests.post(chat_url, json=payload, headers=headers, timeout=20)
                latency_ms = int((time.time() - start_time) * 1000)

                if response.status_code == 200:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': f'Custom AI Connected! ({self.name}) 🚀',
                            'message': f'Endpoint: {endpoint} | Model: {model} | Latensi: {latency_ms} ms',
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': f'Custom AI Error (HTTP {response.status_code})',
                            'message': response.text[:250],
                            'type': 'danger',
                            'sticky': True,
                        }
                    }
            except requests.exceptions.RequestException as e:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Koneksi ke Custom AI Gagal',
                        'message': str(e),
                        'type': 'danger',
                        'sticky': True,
                    }
                }

