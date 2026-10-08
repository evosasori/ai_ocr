# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    default_expense_product_id = fields.Many2one(
        related='company_id.default_expense_product_id',
        readonly=False,
        string='Default Expense Product',
        domain="[('can_be_expensed', '=', True)]",
        help='Produk biaya default yang digunakan jika pengguna tidak memilih produk pada modal ekstraksi receipt AI.'
    )
