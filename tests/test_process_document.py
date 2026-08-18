from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "evidence-ocr" / "scripts" / "process_document.py"
SPEC = importlib.util.spec_from_file_location("process_document", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ClassifyPageTests(unittest.TestCase):
    def test_empty_text_requires_review(self) -> None:
        self.assertEqual(MODULE.classify_page("", None), "OCR_NO_TEXT")

    def test_low_confidence_requires_review(self) -> None:
        self.assertEqual(MODULE.classify_page("sample", 84.99), "OCR_REVIEW_REQUIRED")

    def test_ready_means_human_review_ready_only(self) -> None:
        self.assertEqual(MODULE.classify_page("sample", 85.0), "OCR_READY_FOR_REVIEW")


if __name__ == "__main__":
    unittest.main()
