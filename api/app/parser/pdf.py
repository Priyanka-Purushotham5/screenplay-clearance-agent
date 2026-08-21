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

# text-layer thresholds (B3)
# A scanned page is a photograph: the words are visually present and
# computationally absent, and extract_text() returns "" rather than raising.
# A real screenplay page yields 800-1500 characters, so the gap is wide.
TEXT_LAYER_SAMPLE = 10
MIN_MEAN_CHARS = 100  # averaged over the sampled pages — the accept/reject gate
MIN_PAGE_CHARS = 50   # below this, one page contributed nothing usable


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


@dataclass(frozen=True)
class PdfInspection:
    """What B1 needs to know before it accepts a file."""

    page_count: int
    pages_checked: int  # how many pages the text sample covered
    mean_chars: float  # mean stripped characters across those pages
    low_text_pages: list[int]  # 1-based, sampled pages under MIN_PAGE_CHARS

    @property
    def has_text_layer(self) -> bool:
        return self.mean_chars > MIN_MEAN_CHARS

    def warnings(self) -> list[str]:
        """Messages for scripts.parse_warnings — advisory, never fatal."""
        if not self.low_text_pages:
            return []
        listed = ", ".join(str(p) for p in self.low_text_pages[:10])
        extra = (
            f" (+{len(self.low_text_pages) - 10} more)"
            if len(self.low_text_pages) > 10
            else ""
        )
        return [
            f"No extractable text on page {listed}{extra} "
            f"of the first {self.pages_checked} checked; "
            f"those pages will parse as empty."
        ]


def inspect_pdf(path: str | Path, *, sample: int = TEXT_LAYER_SAMPLE) -> PdfInspection:
    """Page count plus a text-layer verdict, opening the file once.

    Only the first `sample` pages are read for text: a 120-page script takes
    ~5s to extract fully, and the upload request is synchronous. Ten pages
    is enough to tell a screenplay from a photocopy.
    """
    try:
        with pdfplumber.open(str(path)) as pdf:
            total = len(pdf.pages)
            sampled = pdf.pages[:sample]
            counts = [len((page.extract_text() or "").strip()) for page in sampled]
    except Exception as exc:  # pdfplumber raises a wide range of types
        raise UnparseablePDF(str(exc)) from exc

    checked = len(counts)
    mean = (sum(counts) / checked) if checked else 0.0
    low = [i for i, n in enumerate(counts, start=1) if n < MIN_PAGE_CHARS]
    return PdfInspection(
        page_count=total,
        pages_checked=checked,
        mean_chars=round(mean, 1),
        low_text_pages=low,
    )


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