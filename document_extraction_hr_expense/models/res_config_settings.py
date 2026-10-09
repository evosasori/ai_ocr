# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_expense_product_id = fields.Many2one(
        related='company_id.default_expense_product_id',
        readonly=False,
        string='Default Expense Product',
        domain="[('can_be_expensed', '=', True)]",
        help='Default expense product used if the user does not select a product in the AI receipt extraction modal.'
    )
