# AI OCR & Document Extraction Suite for Odoo 18 / 19

Koleksi modul Odoo untuk ekstraksi otomatis data dokumen (Purchase Orders, Vendor Bills, Employee Receipts) menggunakan multimodal AI Vision (Google Gemini & OpenAI-compatible endpoint).

---

## 📦 Modul dalam Repositori

| Modul | Deskripsi | Dependensi Utama |
|---|---|---|
| **`document_extraction_base`** | Fondasi engine AI Vision, mixin ekstraksi (`ai.document.extract.mixin`), konfigurasi gateway/BYOK, dan wizard pemilih dokumen | `base`, `mail` |
| **`document_extraction_sale_order`** | Ekstraksi otomatis Customer Purchase Order (PO) PDF/gambar menjadi Sales Order di Odoo | `document_extraction_base`, `sale` |
| **`document_extraction_vendor_bill`** | Ekstraksi otomatis Faktur Supplier / Vendor Bill PDF/gambar menjadi Vendor Bill di Odoo | `document_extraction_base`, `account` |
| **`document_extraction_hr_expense`** | Ekstraksi otomatis kuitansi/struk pengeluaran karyawan menjadi Expense claim di Odoo | `document_extraction_base`, `hr_expense` |

---

## 🚀 Fitur Utama

- **Dual Mode AI:**
  1. *Cloud Gateway*: Siap pakai langsung tanpa setup rumit.
  2. *Bring Your Own Key (BYOK)*: Mendukung Google Gemini, OpenAI, Groq, Ollama, dan LiteLLM.
- **Smart Reconciliation:**
  - Pencocokan Partner/Vendor via NPWP/VAT, Email, Nomor Telepon, atau Nama.
  - Pencocokan Baris Produk via SKU/Internal Reference, Barcode, atau Deskripsi.
- **Integritas Bisnis & Pajak Terjamin:**
  - Pajak, subtotal, dan total akhir dihitung ulang secara native oleh Odoo ORM (mencegah halusinasi angka AI).
  - Peringatan deviasi jika total fisik dokumen berbeda dengan kalkulasi Odoo.
- **Preview Wizard:**
  - Review interaktif sebelum data masuk ke draft resmi Odoo.

---

## 🛠️ Persyaratan & Instalasi

1. Pastikan modul diletakkan di dalam folder `addons_path` Odoo Anda.
2. Update App List di Odoo Developer Mode.
3. Install modul `document_extraction_base` terlebih dahulu, lalu install modul ekstensi yang dibutuhkan (`document_extraction_sale_order`, `document_extraction_vendor_bill`, `document_extraction_hr_expense`).
4. Atur konfigurasi API Key / Gateway pada menu **Settings > General Settings > AI Document Extraction**.

---

## 📄 Lisensi
LGPL-3
