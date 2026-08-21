"""Generate the scanned and hybrid fixtures used by verify_b3.py.

    python api/scripts/make_scanned_pdf.py

A scanned PDF is a photograph of a page: the words are visually present and
computationally absent. To test the B3 gate honestly we need a file with
that property, so this renders the text to a bitmap and puts the bitmap on
the page. extract_text() then returns "" — exactly as it does for a real
scan out of a photocopier.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = ROOT / "docs"

PAGE_TEXT = [
    "INT. RECORD LABEL OFFICE - DAY",
    "",
    "A cluttered A&R office. Gold records",
    "line the walls. On a battered turntable,",
    "'Take On Me' by a-ha plays loudly.",
    "",
    "                    DIANA",
    "          Of course he did. Turn that off.",
]


def page_bitmap(number: int) -> Image.Image:
    img = Image.new("RGB", (1275, 1650), "white")
    draw = ImageDraw.Draw(img)
    y = 200
    for line in PAGE_TEXT:
        draw.text((190, y), line, fill="black")
        y += 40
    draw.text((1100, 100), f"{number}.", fill="black")
    return img


def build_scanned(dest: Path, pages: int = 3) -> None:
    pdf = canvas.Canvas(str(dest), pagesize=letter)
    for n in range(1, pages + 1):
        buf = io.BytesIO()
        page_bitmap(n).save(buf, "PNG")
        buf.seek(0)
        pdf.drawImage(ImageReader(buf), 0, 0, width=612, height=792)
        pdf.showPage()
    pdf.save()


def build_hybrid(dest: Path, scanned: Path, real: Path) -> None:
    writer = PdfWriter()
    writer.add_page(PdfReader(str(real)).pages[0])
    writer.add_page(PdfReader(str(scanned)).pages[1])
    writer.add_page(PdfReader(str(real)).pages[2])
    with dest.open("wb") as fh:
        writer.write(fh)


def main() -> int:
    real = DOCS / "test_screenplay.pdf"
    if not real.exists():
        print(f"Missing {real} — run make_test_pdf.py first")
        return 2
    scanned = DOCS / "scanned_screenplay.pdf"
    hybrid = DOCS / "hybrid_screenplay.pdf"
    build_scanned(scanned)
    build_hybrid(hybrid, scanned, real)
    for p in (scanned, hybrid):
        print(f"wrote {p.relative_to(ROOT)}  ({p.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())