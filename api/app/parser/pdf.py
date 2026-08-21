"""PDF reading primitives.

Everything that opens a PDF lives here, so there is one place to change if
pdfplumber disappoints. B1 needs only the page count; B2 adds the line
extraction whose x0 geometry B4 derives its margins from.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber

POINTS_PER_INCH = 72.0


class UnparseablePDF(Exception):
    """Starts with %PDF but pdfplumber could not open it — truncated or corrupt."""


@dataclass(frozen=True)
class Line:
    """One visual line of text, with the geometry the classifier reads.

    A PDF has no concept of a line — it places words at coordinates. The
    lines a human sees have to be reconstructed by grouping words that
    share a vertical position.
    """

    page: int  # 1-based, matching what the reader sees
    top: float  # points from the top of the page
    x0: float  # left edge of the leftmost word — the margin signal
    x1: float  # right edge of the rightmost word
    text: str

    @property
    def indent_inches(self) -> float:
        """x0 in inches. Screenplay margins are specified in inches."""
        return self.x0 / POINTS_PER_INCH


def page_count(path: str | Path) -> int:
    """Number of pages. Doubles as B1's "is this a readable PDF" gate."""
    try:
        with pdfplumber.open(str(path)) as pdf:
            return len(pdf.pages)
    except Exception as exc:  # pdfplumber raises a wide range of types
        raise UnparseablePDF(str(exc)) from exc


def extract_lines(path: str | Path) -> list[Line]:
    """Every line of the document, in reading order, with its geometry.

    Order is page by page, and within a page top to bottom — the order a
    person reads in, which is what B5 relies on when it walks the lines
    assigning each to the scene currently open.
    """
    lines: list[Line] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for row in page.extract_text_lines():
                    text = row["text"].strip()
                    if not text:
                        continue
                    lines.append(
                        Line(
                            page=page_number,
                            top=round(row["top"], 2),
                            x0=round(row["x0"], 2),
                            x1=round(row["x1"], 2),
                            text=text,
                        )
                    )
    except Exception as exc:
        raise UnparseablePDF(str(exc)) from exc
    return lines