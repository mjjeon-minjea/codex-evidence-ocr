"""Create a harmless synthetic inspection-like image for local OCR smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a synthetic OCR sample image.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 900), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=32)
    small = ImageFont.load_default(size=24)

    draw.text((80, 55), "SYNTHETIC INSPECTION RECORD - NOT A REAL DOCUMENT", fill="black", font=font)
    columns = [80, 350, 760, 1120, 1450]
    rows = [150, 240, 330, 420, 510, 600]
    for x in columns:
        draw.line((x, rows[0], x, rows[-1]), fill="black", width=3)
    for y in rows:
        draw.line((columns[0], y, columns[-1], y), fill="black", width=3)
    headers = ["Item", "Spec", "Measured", "Decision"]
    for index, value in enumerate(headers):
        draw.text((columns[index] + 20, 180), value, fill="black", font=small)
    records = [("Outer diameter", "50.0 +/- 0.2", "50.1", "Y"), ("Thread pitch", "2.0 +/- 0.1", "2.0", "Y"), ("Surface", "No scratch", "Visual", "")]
    for row_index, record in enumerate(records, start=1):
        for col_index, value in enumerate(record):
            draw.text((columns[col_index] + 20, rows[row_index] + 28), value, fill="black", font=small)
    image.save(args.output)
    print(f"Synthetic sample written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
