# AI OCR & Document Extraction Suite for Odoo 18 / 19

A comprehensive suite of Odoo modules for automated document extraction (Customer Purchase Orders, Vendor Bills, Employee Receipts) using multimodal AI Vision (Google Gemini & OpenAI-compatible endpoints).

---

## 📦 Modules in this Repository

| Module | Description | Key Dependencies |
|---|---|---|
| **`document_extraction_base`** | Core multimodal AI Vision engine, extraction mixin (`ai.document.extract.mixin`), Cloud Gateway / BYOK settings, and document selector wizard | `base`, `mail` |
| **`document_extraction_sale_order`** | Automatic extraction of Customer Purchase Orders (PO) into Sales Orders | `document_extraction_base`, `sale` |
| **`document_extraction_vendor_bill`** | Automatic extraction of Supplier Invoices & Bills into Odoo Vendor Bills | `document_extraction_base`, `account` |
| **`document_extraction_hr_expense`** | Automatic extraction of receipts and employee expenses into Odoo Expense records | `document_extraction_base`, `hr_expense` |

---

## 🚀 Key Features

- **Dual Mode AI Connectivity:**
  1. *Odoo AI Cloud Gateway*: Instant, zero-config setup with free trial quota.
  2. *Bring Your Own Key (BYOK)*: Full support for OpenAI, Google Gemini, Groq, Ollama, and LiteLLM.
- **Smart Partner & Product Reconciliation:**
  - Matches Customer / Vendor by Tax ID / VAT, Email, Phone, or Name.
  - Matches line items by SKU / Internal Reference, Barcode, or Product Name.
- **Financial & Tax Integrity:**
  - Taxes, subtotals, and grand totals are natively computed by Odoo ORM (eliminating AI numerical hallucinations).
  - Real-time discrepancy alerts if physical document totals differ from Odoo calculations.
- **Interactive Preview Wizard:**
  - User verification modal before applying data into formal Odoo draft records.

---

## 🛠️ Requirements & Installation

1. Place the modules inside your Odoo `addons_path`.
2. Update the App List in Odoo Developer Mode.
3. Install `document_extraction_base` first, then install the desired extension modules (`document_extraction_sale_order`, `document_extraction_vendor_bill`, `document_extraction_hr_expense`).
4. Configure your connection settings under **Settings > General Settings > AI Document Extraction**.

---

## 📄 License
LGPL-3
