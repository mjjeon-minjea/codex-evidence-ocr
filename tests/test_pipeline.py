from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "evidence-ocr" / "scripts" / "process_document.py"
SAMPLE_GENERATOR = ROOT / "samples" / "synthetic" / "generate_sample.py"
SPEC = importlib.util.spec_from_file_location("process_document_pipeline", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
EMPTY_PDF = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
    b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
    b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n110\n%%EOF\n"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output_snapshot(output_dir: Path) -> dict[str, str]:
    return {
        str(path.relative_to(output_dir)).replace("\\", "/"): sha256(path)
        for path in output_dir.rglob("*")
        if path.is_file()
    }


def make_png(path: Path, color: str) -> None:
    from PIL import Image

    Image.new("RGB", (32, 32), color).save(path)


def tesseract_ready() -> bool:
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"], check=True, capture_output=True, text=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return {"kor", "eng"} <= set(result.stdout.splitlines())


class PipelineGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        import pytesseract

        version = mock.patch.object(pytesseract, "get_tesseract_version", return_value="5.0")
        languages = mock.patch.object(pytesseract, "get_languages", return_value=["kor", "eng"])
        version.start()
        languages.start()
        self.addCleanup(languages.stop)
        self.addCleanup(version.stop)

    def test_rejects_source_replaced_during_ocr_without_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work_dir = Path(directory)
            source, replacement, output = work_dir / "source.png", work_dir / "replacement.png", work_dir / "output"
            make_png(source, "white")
            make_png(replacement, "black")

            def replace_source(page_path: Path, page_number: int, language: str) -> dict[str, object]:
                source.write_bytes(replacement.read_bytes())
                return {"page": page_number, "image": page_path.name, "text": "stub", "word_count": 1,
                        "mean_confidence": 100.0, "classification": "OCR_READY_FOR_REVIEW", "words": []}

            with mock.patch.object(MODULE, "ocr_page", side_effect=replace_source):
                with self.assertRaisesRegex(RuntimeError, "changed during processing"):
                    MODULE.run(source, output, 250, "kor+eng")
            self.assertFalse((output / "manifest.json").exists())

    def test_rejects_zero_page_pdf_without_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work_dir = Path(directory)
            source, output = work_dir / "empty.pdf", work_dir / "output"
            source.write_bytes(EMPTY_PDF)
            with self.assertRaisesRegex(ValueError, "contains no pages"):
                MODULE.run(source, output, 250, "kor+eng")
            self.assertFalse((output / "manifest.json").exists())

    def test_preflight_failures_do_not_create_output(self) -> None:
        import pytesseract

        with tempfile.TemporaryDirectory() as directory:
            work_dir = Path(directory)
            source = work_dir / "source.png"
            make_png(source, "white")
            cases = (
                ("missing-pillow", mock.patch.dict(sys.modules, {"PIL": None}), "Pillow"),
                ("missing-pytesseract", mock.patch.dict(sys.modules, {"pytesseract": None}), "pytesseract"),
                ("missing-tesseract", mock.patch.object(pytesseract, "get_tesseract_version", side_effect=pytesseract.TesseractNotFoundError()), "Tesseract executable"),
            )
            for name, patch, error in cases:
                with self.subTest(name=name):
                    output = work_dir / name
                    with patch, self.assertRaisesRegex(RuntimeError, error):
                        MODULE.run(source, output, 250, "kor+eng")
                    self.assertFalse(output.exists())

            output = work_dir / "missing-kor"
            with mock.patch.object(pytesseract, "get_tesseract_version", return_value="5.0"), mock.patch.object(pytesseract, "get_languages", return_value=["eng"]):
                with self.assertRaisesRegex(RuntimeError, "kor"):
                    MODULE.run(source, output, 250, "kor+eng")
            self.assertFalse(output.exists())


@unittest.skipUnless(tesseract_ready(), "requires Tesseract on PATH with kor and eng language data")
class PipelineIntegrationTests(unittest.TestCase):
    def run_cli(self, source: Path, output: Path) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(source), "--output", str(output), "--dpi", "144", "--lang", "kor+eng"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def assert_evidence(self, source: Path, output: Path, page_count: int) -> None:
        source_sha256 = sha256(source)
        summary = self.run_cli(source, output)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["pages"], page_count)
        self.assertEqual(manifest["input"]["sha256"], source_sha256)
        self.assertEqual(sha256(source), source_sha256)
        self.assertEqual(len(manifest["pages"]), page_count)

        review_pages: list[tuple[str, str]] = []
        for number, page in enumerate(manifest["pages"], start=1):
            image, ocr_json, ocr_text = (output / page[key] for key in ("image", "ocr_json", "ocr_text"))
            self.assertTrue(image.is_file())
            self.assertTrue(ocr_json.is_file())
            self.assertTrue(ocr_text.is_file())
            result = json.loads(ocr_json.read_text(encoding="utf-8"))
            self.assertEqual((result["page"], result["image"]), (number, image.name))
            self.assertEqual(result["classification"], page["classification"])
            self.assertEqual(ocr_text.read_text(encoding="utf-8"), result["text"] + "\n")
            self.assertIn("SYNTHETIC", result["text"].upper())
            if page["classification"] != "OCR_READY_FOR_REVIEW":
                review_pages.append((str(number), page["classification"]))

        with (output / "review_queue.csv").open(encoding="utf-8", newline="") as stream:
            review_queue = list(csv.DictReader(stream))
        self.assertEqual(manifest["review_queue_count"], len(review_pages))
        self.assertEqual([(row["page"], row["classification"]) for row in review_queue], review_pages)

        evidence_before_rerun = output_snapshot(output)
        rerun = subprocess.run(
            [sys.executable, str(SCRIPT), str(source), "--output", str(output), "--lang", "kor+eng"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(rerun.returncode, 0)
        self.assertIn("Output directory must be new or empty", rerun.stderr)
        self.assertEqual(output_snapshot(output), evidence_before_rerun)
        self.assertEqual(sha256(source), source_sha256)

    def test_cli_generates_and_preserves_synthetic_evidence(self) -> None:
        import pymupdf

        with tempfile.TemporaryDirectory() as directory:
            work_dir = Path(directory)
            sample_png, sample_pdf = work_dir / "synthetic.png", work_dir / "synthetic.pdf"
            subprocess.run(
                [sys.executable, str(SAMPLE_GENERATOR), "--output", str(sample_png)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            document = pymupdf.open()
            for _ in range(2):
                page = document.new_page(width=1600, height=900)
                page.insert_image(page.rect, filename=sample_png)
            document.save(sample_pdf)
            document.close()

            for source, page_count in ((sample_png, 1), (sample_pdf, 2)):
                with self.subTest(source=source.suffix):
                    self.assert_evidence(source, work_dir / f"{source.suffix[1:]}-output", page_count)


if __name__ == "__main__":
    unittest.main()
