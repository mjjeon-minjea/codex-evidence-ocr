---
name: evidence-ocr
description: Convert a user-specified PDF or scan into evidence-backed page images, OCR JSON and text, a review queue, and a SHA-256 manifest. Use when Codex needs reproducible OCR intake for PDF, PNG, JPG, or TIFF files without automatically treating OCR output as factual confirmation.
---

# Evidence OCR

Use this skill when a document must be converted into inspectable OCR evidence rather than an untraceable text dump.

## Workflow

1. Confirm that the user has identified the input file and authorized local processing.
2. Keep source files outside the repository and use a new output directory for each run.
3. Run `scripts/process_document.py` with an explicit input file and output directory.
4. Read `references/output-contract.md` before interpreting JSON fields or OCR confidence.
5. Treat every `OCR_READY_FOR_REVIEW` page as ready for human domain review, not as an automatically approved result.

## Run

```powershell
python scripts/process_document.py <input.pdf-or-image> --output <new-output-folder> --lang kor+eng
```

Install the dependencies in the repository `requirements.txt` and ensure Tesseract plus the requested language data are available.

## Safety Rules

- Do not upload, commit, or embed the user's source file in a public repository.
- Do not infer missing values, accept/reject status, technical compliance, or root cause from OCR confidence alone.
- Preserve the input SHA-256 and page image path in `manifest.json`.
- Send `OCR_NO_TEXT` and `OCR_REVIEW_REQUIRED` pages to human review.

## Resources

- `scripts/process_document.py`: PDF/image rendering and OCR runner.
- `references/output-contract.md`: output fields and interpretation boundary.
