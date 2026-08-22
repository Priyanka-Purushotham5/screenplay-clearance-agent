"""Generate docs/messy_screenplay.pdf — a deliberately awkward script.

    python api/scripts/make_messy_pdf.py

docs/test_screenplay.pdf is too well behaved to prove anything about margin
derivation. It uses textbook margins with no jitter, so a hard-coded table
would parse it perfectly. This file breaks every convenient assumption:

  - non-standard margins (action 1.7", dialogue 2.7", character 4.0")
  - sub-point jitter, as any real PDF export has
  - mirrored production scene numbers in the left margin, which put a slug
    line's x0 *outside* the action margin
  - CONTINUED: headers, (CONTINUED) footers, (CONT'D) on a character cue
  - mini-slugs (ANGLE ON, MOMENTS LATER) that are ALL CAPS but not scenes

If derive_margins() returns the right answer for both files, it is deriving
rather than remembering.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent.parent
DEST = ROOT / "docs" / "messy_screenplay.pdf"

INCH = 72.0
MARGINS = {
    "scene_no": 1.0 * INCH,
    "action": 1.7 * INCH,
    "dialogue": 2.7 * INCH,
    "paren": 3.2 * INCH,
    "character": 4.0 * INCH,
    "transition": 6.2 * INCH,
    "pageno": 7.4 * INCH,
    "scene_no_right": 7.0 * INCH,
}

PAGES = [
    [
        ("pageno", "1."),
        ("slug", "14", "INT. DINER - KITCHEN - NIGHT"),
        ("action", "Steam. A radio plays 'Take On Me'. SARAH scrubs a pan."),
        ("character", "SARAH"),
        ("paren", "(not looking up)"),
        ("dialogue", "You brought him here? To my kitchen?"),
        ("character", "MARCUS"),
        ("dialogue", "He asked for you by name."),
        ("action", "She sets the pan down. Turns."),
        ("character", "SARAH"),
        ("dialogue", "Then he can ask again tomorrow."),
        ("transition", "CUT TO:"),
    ],
    [
        ("pageno", "2."),
        ("action", "CONTINUED:"),
        ("slug", "15", "EXT. PARKING LOT - CONTINUOUS"),
        ("action", "Marcus follows her out. A Coca-Cola machine hums."),
        ("character", "MARCUS"),
        ("dialogue", "Sarah. The Holloway estate is real."),
        ("character", "SARAH (CONT'D)"),
        ("dialogue", "So is my lawyer."),
        ("action", "ANGLE ON -- THE MACHINE"),
        ("action", "The logo, dead centre. She kicks it."),
        ("action", "(CONTINUED)"),
    ],
    [
        ("pageno", "3."),
        ("action", "CONTINUED:"),
        ("character", "MARCUS"),
        ("dialogue", "That's not an answer."),
        ("action", "MOMENTS LATER"),
        ("action", "The lot is empty. Rain starts."),
        ("transition", "FADE OUT."),
    ],
]


def main() -> int:
    random.seed(7)  # reproducible jitter — the fixture must not change per run

    def jitter(x: float) -> float:
        return x + random.uniform(-0.4, 0.4)

    pdf = canvas.Canvas(str(DEST), pagesize=letter)
    pdf.setFont("Courier", 12)
    for page in PAGES:
        y = 792 - 46
        for row in page:
            kind = row[0]
            if kind == "pageno":
                pdf.drawString(jitter(MARGINS["pageno"]), 792 - 40, row[1])
                y = 792 - 90
                continue
            if kind == "slug":  # mirrored production scene numbers
                _, number, text = row
                pdf.drawString(jitter(MARGINS["scene_no"]), y, number)
                pdf.drawString(jitter(MARGINS["action"]), y, text)
                pdf.drawString(jitter(MARGINS["scene_no_right"]), y, number)
                y -= 24
                continue
            pdf.drawString(jitter(MARGINS[kind]), y, row[1])
            y -= 24 if kind in ("action", "transition") else 14
        pdf.showPage()
        pdf.setFont("Courier", 12)
    pdf.save()
    print(f"wrote {DEST.relative_to(ROOT)}  ({DEST.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())