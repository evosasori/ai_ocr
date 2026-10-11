# -*- coding: utf-8 -*-
{
    'name': 'AI Document Extraction - Vendor Bills',
    'version': '15.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Automatic Vendor Bill & Supplier Invoice Extraction into Odoo using Gemini AI Vision',
    'description': """
AI Document Extraction for Vendor Bills (Odoo 15)
=================================================
- Automatically extracts Vendor Bills from attached PDFs or scanned invoice images.
- Uses Gemini Multimodal AI Vision to parse Vendor Details, Bill Number, Invoice & Due Dates, and Line Items.
- Smart Reconciliation Engine:
    * Matches Vendor via Tax ID / VAT, Email, Phone, or Name.
    * Matches Line Products via SKU, Part Number, Barcode, or Description.
- Preserves Accounting Integrity:
    * Taxes and totals are natively computed by Odoo ORM (never hallucinated).
    * Highlights discrepancy alerts if physical bill total differs from Odoo computed total.
- Requires base module: document_extraction_base.
    """,
    'author': "Tyr",
    'website': "https://github.com/evosasori/ai_ocr",
    'support': "triadisputra123@gmail.com",
    'license': 'LGPL-3',
    'depends': [
        'document_extraction_base',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/account_move_ai_preview_wizard_views.xml',
        'views/account_move_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
