"""Render one PDF or image, run OCR, and preserve page-level evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def classify_page(text: str, mean_confidence: float | None) -> str:
    if not text.strip():
        return "OCR_NO_TEXT"
    if mean_confidence is None or mean_confidence < 85.0:
        return "OCR_REVIEW_REQUIRED"
    return "OCR_READY_FOR_REVIEW"


def create_output_tree(output_dir: Path) -> tuple[Path, Path]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory must be new or empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    ocr_dir = output_dir / "ocr"
    pages_dir.mkdir(exist_ok=True)
    ocr_dir.mkdir(exist_ok=True)
    return pages_dir, ocr_dir


def render_input(input_path: Path, pages_dir: Path, dpi: int) -> list[Path]:
    if input_path.suffix.lower() == ".pdf":
        try:
            import fitz
        except ImportError as error:
            raise RuntimeError("PyMuPDF is required. Run: python -m pip install -r requirements.txt") from error
        document = fitz.open(input_path)
        page_paths: list[Path] = []
        scale = dpi / 72.0
        for page_index, page in enumerate(document, start=1):
            rendered = pages_dir / f"page-{page_index:04d}.png"
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            pixmap.save(rendered)
            page_paths.append(rendered)
        document.close()
        return page_paths

    if input_path.suffix.lower() not in IMAGE_SUFFIXES:
        supported = ", ".join(sorted(IMAGE_SUFFIXES | {".pdf"}))
        raise ValueError(f"Unsupported input type: {input_path.suffix}. Supported: {supported}")

    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Pillow is required. Run: python -m pip install -r requirements.txt") from error
    rendered = pages_dir / "page-0001.png"
    with Image.open(input_path) as image:
        image.convert("RGB").save(rendered)
    return [rendered]


def ocr_page(page_path: Path, page_number: int, language: str) -> dict[str, Any]:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as error:
        raise RuntimeError("Pillow and pytesseract are required. Run: python -m pip install -r requirements.txt") from error

    try:
        with Image.open(page_path) as image:
            data = pytesseract.image_to_data(image, lang=language, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError as error:
        raise RuntimeError("Tesseract executable was not found. Install Tesseract and retry.") from error

    words: list[dict[str, Any]] = []
    confidences: list[float] = []
    for index, raw_text in enumerate(data["text"]):
        value = raw_text.strip()
        if not value:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence >= 0:
            confidences.append(confidence)
        words.append(
            {
                "text": value,
                "confidence": round(confidence, 2),
                "left": int(data["left"][index]),
                "top": int(data["top"][index]),
                "width": int(data["width"][index]),
                "height": int(data["height"][index]),
            }
        )

    text = " ".join(word["text"] for word in words)
    mean_confidence = round(sum(confidences) / len(confidences), 2) if confidences else None
    return {
        "page": page_number,
        "image": page_path.name,
        "text": text,
        "word_count": len(words),
        "mean_confidence": mean_confidence,
        "classification": classify_page(text, mean_confidence),
        "words": words,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(input_path: Path, output_dir: Path, dpi: int, language: str) -> dict[str, Any]:
    resolved_input = input_path.resolve()
    resolved_output = output_dir.resolve()
    if not resolved_input.is_file():
        raise FileNotFoundError(f"Input file was not found: {resolved_input}")
    if not 72 <= dpi <= 600:
        raise ValueError("DPI must be between 72 and 600.")

    pages_dir, ocr_dir = create_output_tree(resolved_output)
    page_images = render_input(resolved_input, pages_dir, dpi)
    page_summaries: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    for page_number, page_image in enumerate(page_images, start=1):
        result = ocr_page(page_image, page_number, language)
        ocr_json = ocr_dir / f"page-{page_number:04d}.json"
        ocr_text = ocr_dir / f"page-{page_number:04d}.txt"
        write_json(ocr_json, result)
        ocr_text.write_text(result["text"] + "\n", encoding="utf-8")
        page_summaries.append(
            {
                "page": page_number,
                "image": str(page_image.relative_to(resolved_output)).replace("\\", "/"),
                "ocr_json": str(ocr_json.relative_to(resolved_output)).replace("\\", "/"),
                "ocr_text": str(ocr_text.relative_to(resolved_output)).replace("\\", "/"),
                "word_count": result["word_count"],
                "mean_confidence": result["mean_confidence"],
                "classification": result["classification"],
            }
        )
        if result["classification"] != "OCR_READY_FOR_REVIEW":
            review_rows.append(
                {
                    "page": page_number,
                    "classification": result["classification"],
                    "mean_confidence": result["mean_confidence"],
                    "reason": "OCR did not reach the review-ready threshold; inspect the source page.",
                }
            )

    with (resolved_output / "review_queue.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["page", "classification", "mean_confidence", "reason"])
        writer.writeheader()
        writer.writerows(review_rows)

    manifest = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {"filename": resolved_input.name, "sha256": sha256_file(resolved_input)},
        "ocr": {"language": language, "dpi": dpi},
        "pages": page_summaries,
        "review_queue_count": len(review_rows),
    }
    write_json(resolved_output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Create page-level OCR evidence from one PDF or scan.")
    parser.add_argument("input", type=Path, help="PDF, PNG, JPG, or TIFF input file")
    parser.add_argument("--output", required=True, type=Path, help="New or empty output directory")
    parser.add_argument("--dpi", type=int, default=250, help="PDF rendering DPI (72-600)")
    parser.add_argument("--lang", default="kor+eng", help="Tesseract language string")
    args = parser.parse_args()
    manifest = run(args.input, args.output, args.dpi, args.lang)
    print(json.dumps({"pages": len(manifest["pages"]), "review_queue_count": manifest["review_queue_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
