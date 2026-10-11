# -*- coding: utf-8 -*-
{
    'name': 'AI Document Extraction Base Engine',
    'version': '15.0.1.0.0',
    'category': 'Productivity/AI',
    'summary': 'Universal Multimodal AI Document Extraction Engine for Odoo (Cloud Gateway & BYOK OpenAI-Compatible)',
    'description': """
Universal AI Document Extraction Foundation Engine for Odoo 15
==============================================================
- Dual Operational Mode:
    1. Odoo AI Cloud Gateway (Default, Zero-Config, automatic trial quota per database UUID).
    2. Bring Your Own Key (BYOK) - Generic OpenAI-compatible multimodal endpoint (OpenAI, Groq, Ollama, LiteLLM).
- Multimodal Vision Support for PDFs (auto-converted to crisp images) and standard image files.
- Real-time Quota Monitoring & Integrated Top-up / Upgrade Portal.
- Abstract Mixin (ai.document.extract.mixin) for rapid extension to any Odoo model (Invoices, Receipts, Delivery Orders).
- One-click Connection & Latency Tester.
    """,
    'author': "Tyr",
    'website': "https://github.com/evosasori/ai_ocr",
    'support': "triadisputra123@gmail.com",
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/ai_document_select_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_company_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
