# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiDocumentSelectWizard(models.TransientModel):
    _name = 'ai.document.select.wizard'
    _description = 'AI Document Selection & Merge Wizard'

    res_model = fields.Char(string='Related Model', required=True)
    res_id = fields.Integer(string='Record ID', required=True)

    available_attachment_ids = fields.Many2many(
        'ir.attachment',
        'ai_select_wizard_avail_rel',
        string='Available Attachments',
        readonly=True
    )

    mode = fields.Selection([
        ('single', 'Select Single Document'),
        ('merge', 'Merge Multiple Documents (Multi-page / Separate Files)')
    ], string='Extraction Mode', default='single', required=True)

    selected_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Primary Document',
        domain="[('id', 'in', available_attachment_ids)]",
        help='Select the primary document to extract.'
    )

    selected_attachment_ids = fields.Many2many(
        'ir.attachment',
        'ai_select_wizard_chosen_rel',
        string='Merged Documents',
        domain="[('id', 'in', available_attachment_ids)]",
        help='Select documents to combine into a single AI extraction process.'
    )

    quota_cost = fields.Integer(
        string='Quota Cost',
        compute='_compute_quota_cost',
        help='Estimated quota usage deducted from your instance balance.'
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
                raise UserError("Please select a document to extract.")
            chosen_attachments = self.selected_attachment_id
        else:
            if not self.selected_attachment_ids:
                raise UserError("Please select at least 1 document to merge.")
            chosen_attachments = self.selected_attachment_ids

        target_record = self.env[self.res_model].browse(self.res_id)
        if not target_record.exists():
            raise UserError(f"Source record '{self.res_model} (ID: {self.res_id})' not found.")

        if hasattr(target_record, 'action_execute_ai_extraction'):
            return target_record.action_execute_ai_extraction(chosen_attachments)
        else:
            raise UserError(
                f"Model '{self.res_model}' does not support action_execute_ai_extraction()."
            )
