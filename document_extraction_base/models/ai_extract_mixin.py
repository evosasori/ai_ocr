# -*- coding: utf-8 -*-
import base64
import json
import logging
import time
import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiDocumentExtractMixin(models.AbstractModel):
    _name = 'ai.document.extract.mixin'
    _description = 'AI Document Extraction Mixin'

    extraction_status = fields.Selection(
        [
            ('draft', 'Not Extracted'),
            ('processing', 'Processing AI...'),
            ('extracted', 'Extracted'),
            ('failed', 'Extraction Failed'),
        ],
        string='AI Status',
        default='draft',
        copy=False,
        help='Current status of AI extraction for this document.'
    )

    extraction_error = fields.Text(
        string='Extraction Error',
        copy=False,
        readonly=True
    )

    extracted_raw_json = fields.Text(
        string='Raw AI Response JSON',
        copy=False,
        readonly=True
    )

    ai_model_used = fields.Char(
        string='Model Used',
        copy=False,
        readonly=True
    )

    ai_confidence_score = fields.Float(
        string='Confidence (%)',
        default=100.0,
        copy=False,
        readonly=True
    )

    def _get_document_attachments(self):
        """
        Locates all valid document attachments (PDF or Images) linked to this record.
        """
        self.ensure_one()
        Attachment = self.env['ir.attachment'].sudo()
        attachments = Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
        ], order='id desc')

        allowed_mimes = [
            'application/pdf',
            'image/jpeg',
            'image/png',
            'image/webp',
            'image/tiff',
        ]

        valid_attachments = Attachment.browse()
        for att in attachments:
            if att.mimetype in allowed_mimes or (att.name and att.name.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.webp'))):
                if (hasattr(att, 'raw') and att.raw) or (hasattr(att, 'datas') and att.datas):
                    valid_attachments |= att

        return valid_attachments

    def _get_document_attachment(self, preferred_attachment_id=None):
        """
        Locates the most relevant attachment (PDF or Image) linked to this record.
        Maintained for backward compatibility.
        """
        self.ensure_one()
        Attachment = self.env['ir.attachment'].sudo()

        if preferred_attachment_id:
            att = Attachment.browse(preferred_attachment_id)
            if att.exists() and ((hasattr(att, 'raw') and att.raw) or (hasattr(att, 'datas') and att.datas)):
                return att

        atts = self._get_document_attachments()
        return atts[0] if atts else False

    def _open_attachment_select_wizard(self, attachments):
        """
        Launches the document selection and merger wizard when more than 1 attachment exists.
        """
        self.ensure_one()
        wizard = self.env['ai.document.select.wizard'].create({
            'res_model': self._name,
            'res_id': self.id,
            'available_attachment_ids': [(6, 0, attachments.ids)],
            'selected_attachment_id': attachments[0].id if attachments else False,
            'selected_attachment_ids': [(6, 0, attachments.ids)],
            'mode': 'single',
        })
        return {
            'name': 'Select Documents for AI Extraction',
            'type': 'ir.actions.act_window',
            'res_model': 'ai.document.select.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _convert_single_attachment_to_vision_images(self, attachment, max_pages=3):
        """
        Converts a single attachment (PDF pages or image) into vision-compatible base64 data URLs.
        """
        import base64
        if hasattr(attachment, 'raw') and attachment.raw:
            raw_bytes = attachment.raw
            base64_str = base64.b64encode(raw_bytes).decode('utf-8')
        elif hasattr(attachment, 'datas') and attachment.datas:
            datas = attachment.datas
            if isinstance(datas, bytes):
                base64_str = datas.decode('utf-8')
            else:
                base64_str = str(datas or '')
            raw_bytes = base64.b64decode(base64_str)
        else:
            base64_str = ''
            raw_bytes = b''

        mimetype = attachment.mimetype or 'application/pdf'
        if attachment.name:
            lower_name = attachment.name.lower()
            if lower_name.endswith('.pdf'):
                mimetype = 'application/pdf'
            elif lower_name.endswith('.png'):
                mimetype = 'image/png'
            elif lower_name.endswith('.webp'):
                mimetype = 'image/webp'
            elif lower_name.endswith(('.jpg', '.jpeg')):
                mimetype = 'image/jpeg'

        # If it's a PDF, convert each page to PNG using PyMuPDF (fitz)
        if mimetype == 'application/pdf':
            try:
                import fitz
                doc = fitz.open(stream=raw_bytes, filetype='pdf')
                image_urls = []
                total_pages = min(len(doc), max_pages)
                for page_num in range(total_pages):
                    page = doc[page_num]
                    # 2.0 zoom gives ~144 DPI, ideal OCR clarity without excessive payload size
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                    png_bytes = pix.tobytes('png')
                    b64_page = base64.b64encode(png_bytes).decode('utf-8')
                    image_urls.append(f"data:image/png;base64,{b64_page}")

                _logger.info("Auto-converted PDF '%s' (%s pages, processed %s) to PNG images for Vision AI.", attachment.name, len(doc), total_pages)
                if image_urls:
                    return image_urls
            except Exception as e:
                _logger.warning("Could not convert PDF to PNG using PyMuPDF: %s. Using raw base64 data.", str(e))

        return [f"data:{mimetype};base64,{base64_str}"]

    def _convert_attachment_to_vision_images(self, attachments, max_pages=3):
        """
        Converts one or multiple attachments to vision image URLs.
        """
        if hasattr(attachments, '_name') and attachments._name == 'ir.attachment':
            att_list = attachments
        elif isinstance(attachments, (list, tuple)):
            att_list = attachments
        else:
            att_list = [attachments]

        all_urls = []
        for att in att_list:
            all_urls.extend(self._convert_single_attachment_to_vision_images(att, max_pages=max_pages))
        return all_urls

    def _call_gemini_vision_api(self, attachment=None, system_prompt=None, user_prompt=None, response_schema=None, attachments=None):
        """Backward-compatible alias pointing to _call_ai_vision_api."""
        target = attachments if attachments is not None else attachment
        return self._call_ai_vision_api(target, system_prompt, user_prompt, response_schema)

    def _call_ai_vision_api(self, attachments=None, system_prompt="", user_prompt="", response_schema=None, attachment=None):
        """
        Executes Multimodal Vision AI extraction via:
        1. 'cloud': Odoo AI Cloud Gateway (Zero-Config, License & Quota tracking per database.uuid)
        2. 'custom': Generic OpenAI-Compatible BYOK endpoint (OpenAI, Groq, LiteLLM, Ollama)
        Supports single or merged multiple document attachments.
        """
        self.ensure_one()
        company = getattr(self, 'company_id', False) or self.env.company
        mode = company.ai_connection_mode or 'cloud'

        # Resolve target attachments recordset
        target_atts = attachments if attachments is not None else attachment
        if not target_atts:
            target_atts = self._get_document_attachments()
        if not target_atts:
            raise UserError("No document attachments found to extract.")

        if hasattr(target_atts, '_name') and target_atts._name == 'ir.attachment':
            att_records = target_atts
        elif isinstance(target_atts, (list, tuple)):
            att_records = self.env['ir.attachment'].browse([a.id if hasattr(a, 'id') else a for a in target_atts])
        else:
            att_records = self.env['ir.attachment'].browse(target_atts.id if hasattr(target_atts, 'id') else target_atts)

        doc_count = len(att_records)
        doc_names = ", ".join(att_records.mapped('name')) or "document.pdf"

        # Build vision image payloads across all selected attachments
        vision_image_urls = self._convert_attachment_to_vision_images(att_records, max_pages=3)
        effective_user_prompt = user_prompt
        if doc_count > 1:
            effective_user_prompt += (
                f"\n\n[MULTI-DOCUMENT NOTICE]: You are analyzing {doc_count} combined documents/attachments ({doc_names}). "
                "Carefully consolidate all line items, dates, and financial amounts across all attached document pages "
                "into the single document schema response."
            )

        user_content = [{"type": "text", "text": effective_user_prompt}]
        for img_url in vision_image_urls:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": img_url}
            })

        sys_text = system_prompt or ""
        if response_schema:
            sys_text += (
                f"\nYou must return ONLY a valid JSON object adhering strictly to this schema:\n"
                f"{json.dumps(response_schema, indent=2)}\n"
                "Ensure required fields are populated without markdown block fences."
            )

        messages = []
        if sys_text:
            messages.append({"role": "system", "content": sys_text})
        messages.append({"role": "user", "content": user_content})

        # --- MODE 1: ODOO AI CLOUD GATEWAY ---
        if mode == 'cloud':
            gateway_url = (company.gateway_url or 'https://ai-gateway.triadiputra.my.id').rstrip('/')
            extract_url = f"{gateway_url}/api/v1/extract"
            db_uuid = company._get_database_uuid() if hasattr(company, '_get_database_uuid') else (company._get_config_param('database.uuid') if hasattr(company, '_get_config_param') else 'unknown-db')

            headers = {
                'X-Odoo-DB-UUID': db_uuid,
                'X-Odoo-Company-Name': company.name or 'Odoo Client',
                'X-Odoo-Base-URL': company._get_config_param('web.base.url') if hasattr(company, '_get_config_param') else '',
                'X-Odoo-Document-Count': str(doc_count),
                'Content-Type': 'application/json',
            }

            payload = {
                "messages": messages,
                "temperature": 0.1,
                "stream": False,
                "document_count": doc_count,
                "document_name": doc_names,
            }

            _logger.info("Calling Odoo AI Cloud Gateway (%s) for documents %s (count: %s, db_uuid: %s)", extract_url, doc_names, doc_count, db_uuid)

            max_retries = 3
            response = None
            for attempt in range(max_retries):
                try:
                    response = requests.post(extract_url, json=payload, headers=headers, timeout=90)
                except requests.exceptions.RequestException as e:
                    if attempt == max_retries - 1:
                        _logger.error("Network error communicating with Cloud Gateway: %s", str(e))
                        raise UserError(f"Failed to communicate with Odoo AI Cloud Gateway: {str(e)}")
                    time.sleep(2)
                    continue

                if response.status_code in (503, 429) and attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                break

            # Handle Quota Exceeded (HTTP 402)
            if response.status_code == 402:
                err_data = response.json() if response.content else {}
                upgrade_url = err_data.get('upgrade_url', f"{gateway_url}/upgrade?uuid={db_uuid}")
                raise UserError(
                    f"⚠️ Your AI document extraction quota has been exceeded!\n\n"
                    f"Please top up or upgrade your plan to continue automated extraction:\n"
                    f"👉 {upgrade_url}"
                )

            if response.status_code != 200:
                err_text = response.text
                try:
                    err_json = response.json()
                    err_text = err_json.get('message', response.text)
                except Exception:
                    pass
                raise UserError(f"Cloud Gateway Error (HTTP {response.status_code}): {err_text}")

            res_json = response.json()
            choices = res_json.get('choices', [])
            if not choices:
                raise UserError("Cloud Gateway returned an empty response without extraction content.")

            raw_text = choices[0].get('message', {}).get('content', '')
            model_used = res_json.get('model', 'cloud-vision-gateway')
            self.sudo().write({'ai_model_used': model_used})

            return self._parse_json_completion(raw_text)

        # --- MODE 2: CUSTOM OPENAI-COMPATIBLE BYOK ---
        elif mode == 'custom':
            endpoint = (company.custom_ai_endpoint or '').rstrip('/')
            api_key = company.custom_ai_api_key
            model = company.custom_ai_model or 'gpt-4o-mini'

            if not endpoint:
                raise UserError(f"Custom Base URL is required for company '{company.name}'!")
            if not api_key:
                raise UserError(f"Custom API Key is required for company '{company.name}'!")

            chat_url = f"{endpoint}/chat/completions" if not endpoint.endswith('/chat/completions') else endpoint
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "stream": False,
                "response_format": {"type": "json_object"}
            }

            _logger.info("Calling Custom AI Endpoint (%s, model: %s) for documents %s (count: %s)", chat_url, model, doc_names, doc_count)

            max_retries = 3
            response = None
            for attempt in range(max_retries):
                try:
                    response = requests.post(chat_url, json=payload, headers=headers, timeout=90)
                except requests.exceptions.RequestException as e:
                    if attempt == max_retries - 1:
                        _logger.error("Network error communicating with Custom AI: %s", str(e))
                        raise UserError(f"Failed to communicate with Custom AI Endpoint: {str(e)}")
                    time.sleep(2)
                    continue

                if response.status_code in (503, 429) and attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                break

            if response.status_code != 200:
                err_text = response.text
                try:
                    err_json = response.json()
                    err_text = err_json.get('error', {}).get('message', response.text)
                except Exception:
                    pass
                raise UserError(f"Custom AI Error (HTTP {response.status_code}): {err_text}")

            res_json = response.json()
            choices = res_json.get('choices', [])
            if not choices:
                raise UserError("Custom AI returned an empty response without extraction content.")

            raw_text = choices[0].get('message', {}).get('content', '')
            self.sudo().write({'ai_model_used': model})

            return self._parse_json_completion(raw_text)

        raise UserError(f"Unsupported AI Connection Mode: {mode}")

    def _parse_json_completion(self, raw_text):
        """Cleans markdown wrappers and safely parses JSON content."""
        cleaned = (raw_text or '').strip()
        if cleaned.startswith('```'):
            lines = cleaned.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].startswith('```'):
                lines = lines[:-1]
            cleaned = '\n'.join(lines).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            _logger.error("Failed to parse AI output into JSON: %s\nRaw output: %s", str(e), raw_text)
            raise UserError(f"AI response is not valid JSON format: {str(e)}")


