# -*- coding: utf-8 -*-
{
    'name': 'AI Document Extraction for Employee Expenses',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Automated AI Receipt Extraction for Employee Reimbursements and Expenses',
    'description': """
AI Document Extraction for Employee Expenses (Odoo 18 & 19)
==========================================================
- Automatically parses employee expense receipts, invoices, restaurant bills, fuel tickets, and hotel folios using Vision AI.
- Smart Receipt Metadata Extraction: Merchant, Transaction Date, Currency, Total Amount, Tax/PPN, and Category suggestion.
- Interactive Preview Wizard allowing review and adjustment of detected totals and optional expense product selection.
- Automated Fallback to Default Expense Product configured in Settings.
- Full Multi-Attachment Support: Multi-page hotel folios or dual receipts (cash receipt + EDC slip) with merge quota tracking.
- Zero-config Cloud Gateway integration or Bring Your Own Key (BYOK) OpenAI-compatible multimodal endpoint.
    """,
    'author': "Tyr",
    'website': "https://github.com/evosasori/ai_ocr",
    'support': "triadisputra123@gmail.com",
    'license': 'LGPL-3',
    'depends': [
        'hr_expense',
        'document_extraction_base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/hr_expense_ai_preview_wizard_views.xml',
        'views/hr_expense_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
