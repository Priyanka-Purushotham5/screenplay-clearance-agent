"""One call from a PDF path to scenes, for the upload endpoint.

B2-B5 are separate modules so each can be reasoned about and tested alone.
This composes them, so the endpoint has a single blocking call to hand to a
worker thread rather than four.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from api.app.parser.classify import classify_document
from api.app.parser.pdf import extract_lines
from api.app.parser.scenes import SceneDraft, group_document


@dataclass
class ParsedScript:
    scenes: list[SceneDraft] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    line_count: int = 0
    element_count: int = 0

    @property
    def scene_count(self) -> int:
        return len(self.scenes)


def parse_screenplay(path: str | Path) -> ParsedScript:
    """Lines -> typed elements -> scenes. Deterministic, and no AI anywhere.

    Slow: roughly five seconds for a feature-length script, nearly all of
    it inside pdfplumber. The caller must keep it off the event loop.
    """
    lines = extract_lines(path)
    classified = classify_document(lines)
    grouped = group_document(classified.elements)
    return ParsedScript(
        scenes=grouped.scenes,
        warnings=classified.warnings + grouped.warnings,
        line_count=len(lines),
        element_count=len(classified.elements),
    )