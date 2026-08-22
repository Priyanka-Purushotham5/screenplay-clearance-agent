"""Generate docs/messy_screenplay.pdf — a deliberately awkward script.

    python api/scripts/make_messy_pdf.py

Needs reportlab, this is a one-off
generator and the PDF it produces is committed.

docs/test_screenplay.pdf is too well behaved to prove anything about margin
derivation. It uses textbook margins with no jitter, so a hard-coded table
would parse it perfectly. This file breaks every convenient assumption:

  - non-standard margins (action 1.7", dialogue 2.7", character 4.0")
  - sub-point jitter, as any real PDF export has
  - mirrored production scene numbers in the left margin, which put a slug
    line's x0 *outside* the action margin
  - CONTINUED: headers, (CONTINUED) footers
  - a speech split across a page break with (MORE) / NAME (CONT'D)
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

# (kind, text). LEADING is the gap in line-units before each row: 2 starts a
# new block (a blank line), 1 continues the current one. Screenplays are
# leaded uniformly, and the classifier splits blocks on that blank line.
LEADING = {
    "slug": 2, "action": 2, "character": 2, "transition": 2,
    "paren": 1, "dialogue": 1, "more": 1,
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
        ("dialogue", "Then he can ask again tomorrow, and the"),
        ("dialogue", "answer will be the same one I gave"),
        ("more", "(MORE)"),
    ],
    [
        ("pageno", "2."),
        ("action", "CONTINUED:"),
        ("character", "SARAH (CONT'D)"),
        ("dialogue", "him the first time."),
        ("transition", "CUT TO:"),
        ("slug", "15", "EXT. PARKING LOT - CONTINUOUS"),
        ("action", "Marcus follows her out. A Coca-Cola machine hums."),
        ("character", "MARCUS"),
        ("dialogue", "Sarah. The Holloway estate is real."),
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

    pitch = 14.0
    pdf = canvas.Canvas(str(DEST), pagesize=letter)
    for page in PAGES:
        # setFont at the *start* of each page. Calling it after the final
        # showPage() writes to a fresh content stream, and save() then emits
        # that as a trailing blank page - invisible to extract_lines, which
        # skips empty pages, but page_count sees it.
        pdf.setFont("Courier", 12)
        y = 792 - 90
        first = True
        for row in page:
            kind = row[0]
            if kind == "pageno":
                pdf.drawString(jitter(MARGINS["pageno"]), 792 - 40, row[1])
                continue
            if not first:
                y -= pitch * LEADING[kind]
            first = False
            if kind == "slug":  # mirrored production scene numbers
                _, number, text = row
                pdf.drawString(jitter(MARGINS["scene_no"]), y, number)
                pdf.drawString(jitter(MARGINS["action"]), y, text)
                pdf.drawString(jitter(MARGINS["scene_no_right"]), y, number)
                continue
            column = "character" if kind == "more" else kind
            pdf.drawString(jitter(MARGINS[column]), y, row[1])
        pdf.showPage()
    pdf.save()
    print(f"wrote {DEST.relative_to(ROOT)}  ({DEST.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())