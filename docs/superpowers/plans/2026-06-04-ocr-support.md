# PDF OCR Support Implementation Plan

**Goal:** Add OCR support for scanned PDFs using RapidOCR.

**Tech Stack:** rapidocr-onnxruntime, pypdfium2

---

## Task 1: Install dependencies

**Files:** backend/pyproject.toml

- Add rapidocr-onnxruntime>=1.3.0 and pypdfium2>=4.0.0 to dependencies
- Run: cd backend && uv sync
- Verify: uv run python -c 'from rapidocr_onnxruntime import RapidOCR; print("OK")'

## Task 2: Modify document_parser.py

**Files:** backend/services/document_parser.py

- Add OCR imports (RapidOCR, numpy, pypdfium2)
- Add lazy OCR engine initialization
- Add _pdf_to_images() function using pypdfium2
- Add _parse_pdf_with_ocr() function
- Modify _parse_pdf() to fallback to OCR when text extraction fails
- Add logging for OCR fallback

## Task 3: Test

- Test with existing scanned PDF
- Upload via API and verify
