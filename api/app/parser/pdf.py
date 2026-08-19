"""PDF reading primitives.

B1 needs only the page count. B2 adds line extraction with x0 geometry on
top of the same pdfplumber import, so it stays in one module.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber


class UnparseablePDF(Exception):
    """Starts with %PDF but pdfplumber could not open it — truncated or corrupt."""


def page_count(path: str | Path) -> int:
    try:
        with pdfplumber.open(str(path)) as pdf:
            return len(pdf.pages)
    except Exception as exc:  # pdfplumber raises a wide range of types
        raise UnparseablePDF(str(exc)) from exc