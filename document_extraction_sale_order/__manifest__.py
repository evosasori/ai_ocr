# -*- coding: utf-8 -*-
{
    'name': 'AI Document Extraction - Sales Orders',
    'version': '15.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Automatic Sales Order Creation from Customer Purchase Orders (PO) using AI Vision',
    'description': """
AI Document Extraction for Customer Purchase Orders (Odoo 15)
=============================================================
- Automatically extracts Customer Purchase Orders (PO) from attached PDFs or scanned order documents.
- Preview & Confirmation Wizard before creating real order lines.
- Smart Customer & Product Reconciliation:
    * Matches Customer via VAT/NPWP, Email, Phone, or Name.
    * Matches Order Products via SKU, Barcode, or Product Name.
- Native Pricing & Tax Calculation:
    * Maintains full Odoo pricing & tax calculation integrity.
    * Flags discrepancy alert if physical PO total differs from Odoo calculated total.
- Requires base module: document_extraction_base.
    """,
    'author': "Tyr",
    'website': "https://github.com/evosasori/ai_ocr",
    'support': "triadisputra123@gmail.com",
    'license': 'LGPL-3',
    'depends': [
        'document_extraction_base',
        'sale_management',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/sale_order_ai_preview_wizard_views.xml',
        'views/sale_order_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
