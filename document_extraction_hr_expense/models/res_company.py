# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    default_expense_product_id = fields.Many2one(
        'product.product',
        string='Default Expense Product',
        domain="[('can_be_expensed', '=', True)]",
        help='Produk biaya default yang digunakan jika tidak memilih produk pada ekstraksi receipt AI.'
    )

    def init(self):
        super().init()
        # Auto-initialize default_expense_product_id to standard Expenses product if available
        for company in self.search([('default_expense_product_id', '=', False)]):
            expense_prod = self.env['product.product'].search([
                ('can_be_expensed', '=', True),
                ('name', 'ilike', 'expense'),
            ], limit=1)
            if not expense_prod:
                expense_prod = self.env['product.product'].search([
                    ('can_be_expensed', '=', True)
                ], limit=1)
            if expense_prod:
                company.default_expense_product_id = expense_prod.id
