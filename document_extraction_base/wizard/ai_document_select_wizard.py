# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiDocumentSelectWizard(models.TransientModel):
    _name = 'ai.document.select.wizard'
    _description = 'AI Document Selection & Merge Wizard'

    res_model = fields.Char(string='Model Terkait', required=True)
    res_id = fields.Integer(string='ID Record', required=True)

    available_attachment_ids = fields.Many2many(
        'ir.attachment',
        'ai_select_wizard_avail_rel',
        string='Lampiran Tersedia',
        readonly=True
    )

    mode = fields.Selection([
        ('single', 'Pilih Satu Dokumen Spesifik'),
        ('merge', 'Gabungkan Beberapa Dokumen (Multi-Dokumen / Lampiran Terpisah)')
    ], string='Mode Ekstraksi', default='single', required=True)

    selected_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Dokumen Utama',
        domain="[('id', 'in', available_attachment_ids)]",
        help='Pilih satu file yang menjadi dokumen utama yang ingin diekstrak.'
    )

    selected_attachment_ids = fields.Many2many(
        'ir.attachment',
        'ai_select_wizard_chosen_rel',
        string='Dokumen yang Digabung',
        domain="[('id', 'in', available_attachment_ids)]",
        help='Centang dokumen-dokumen yang ingin digabungkan ke dalam 1 proses ekstraksi AI.'
    )

    quota_cost = fields.Integer(
        string='Biaya Kuota',
        compute='_compute_quota_cost',
        help='Estimasi jumlah limit kuota yang akan dipotong dari saldo instance Anda.'
    )

    @api.depends('mode', 'selected_attachment_id', 'selected_attachment_ids')
    def _compute_quota_cost(self):
        for wiz in self:
            if wiz.mode == 'single':
                wiz.quota_cost = 1 if wiz.selected_attachment_id else 0
            else:
                wiz.quota_cost = len(wiz.selected_attachment_ids)

    def action_confirm_extract(self):
        """
        Validates the user document selection and triggers AI extraction on target record.
        """
        self.ensure_one()

        if self.mode == 'single':
            if not self.selected_attachment_id:
                raise UserError("Silakan tentukan salah satu dokumen yang ingin diekstrak.")
            chosen_attachments = self.selected_attachment_id
        else:
            if not self.selected_attachment_ids:
                raise UserError("Silakan centang minimal 1 dokumen untuk digabungkan.")
            chosen_attachments = self.selected_attachment_ids

        target_record = self.env[self.res_model].browse(self.res_id)
        if not target_record.exists():
            raise UserError(f"Record sumber '{self.res_model} (ID: {self.res_id})' tidak ditemukan.")

        if hasattr(target_record, 'action_execute_ai_extraction'):
            return target_record.action_execute_ai_extraction(chosen_attachments)
        else:
            raise UserError(
                f"Model '{self.res_model}' belum mendukung metode action_execute_ai_extraction()."
            )
