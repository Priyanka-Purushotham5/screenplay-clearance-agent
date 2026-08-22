"""Type every line of a screenplay by its indentation and its wording.

The margins come from margins.derive_margins(); this module decides what
each line *is*, merges runs of the same type into blocks, and attaches the
speaking character to dialogue.

Why the type matters more than the text: a song playing in an action line
needs synchronisation and master-use rights, while the same song named in
dialogue needs nothing at all. One string, two ratings, decided entirely by
which element it appeared in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from api.app.parser.margins import (
    TRANSITION_WORDS,
    MarginProfile,
    derive_margins,
    is_furniture,
)
from api.app.parser.pdf import Line

ElementType = Literal[
    "scene_heading", "action", "character", "dialogue", "parenthetical", "transition"
]

# A slug line: ALL CAPS *and* opening with an interior/exterior marker.
# Both halves are required. "ANGLE ON THE JUKEBOX" and "MOMENTS LATER" are
# ALL CAPS mini-slugs that are emphatically not new scenes.
SLUG = re.compile(
    r"^(?:\d{1,4}[A-Z]?\s+)?(INT\.?/EXT\.?|I/E\.?|INT\.?|EXT\.?)[\s.]", re.IGNORECASE
)

# Trailing bracketed qualifiers on a cue: (V.O.), (O.S.), (CONT'D), and
# combinations of them. Stripped from the stored name so that "SARAH" and
# "SARAH (V.O.)" are one character rather than two.
CUE_SUFFIX = re.compile(r"\s*\([^()]*\)\s*$")

# Types that may absorb the line beneath them when it has the same type.
# A cue, a slug and a transition are each complete in one line.
MERGEABLE = {"action", "dialogue", "parenthetical"}

# A gap wider than this many line-pitches means a blank line, and a blank
# line separates blocks. Screenplays are leaded uniformly, so the pitch is
# stable within a document and the signal is a clean 2x.
BLOCK_GAP_RATIO = 1.6


@dataclass
class ScriptElementDraft:
    """One typed block, before it is assigned to a scene and persisted."""

    type: ElementType
    character: Optional[str]
    page: int
    text: str


@dataclass
class ClassifyResult:
    elements: list[ScriptElementDraft] = field(default_factory=list)
    profile: Optional[MarginProfile] = None
    warnings: list[str] = field(default_factory=list)

def split_cue(text: str) -> tuple[str, list[str]]:
    """"SARAH (V.O.) (CONT'D)" -> ("SARAH", ["(V.O.)", "(CONT'D)"])."""
    name = text.strip()
    suffixes: list[str] = []
    while (m := CUE_SUFFIX.search(name)) is not None:
        suffixes.insert(0, m.group(0).strip())
        name = name[: m.start()].strip()
    return name, suffixes


def is_slug(text: str) -> bool:
    stripped = text.strip()
    return bool(SLUG.match(stripped)) and stripped.isupper()


def _nearest_role(x0: float, profile: MarginProfile, tolerance: float) -> str | None:
    """Which derived margin is this line sitting at?"""
    best, best_gap = None, tolerance
    for role in ("action", "dialogue", "parenthetical", "character", "transition"):
        margin = getattr(profile, role)
        if margin is None:
            continue
        gap = abs(x0 - margin)
        if gap <= best_gap:
            best, best_gap = role, gap
    return best


def _type_of(line: Line, profile: MarginProfile, tolerance: float) -> ElementType:
    text = line.text.strip()

    # Wording wins over position for the two unambiguous cases.
    if is_slug(text):
        return "scene_heading"
    if TRANSITION_WORDS.search(text) and text.isupper():
        return "transition"
    if text.startswith("(") and text.endswith(")"):
        return "parenthetical"

    role = _nearest_role(line.x0, profile, tolerance)
    if role == "character":
        # Guard the cue margin: only a short ALL-CAPS line is a cue. A long
        # sentence that happens to sit there is dialogue that overran.
        if text.isupper() and len(text.split()) <= 6:
            return "character"
        return "dialogue"
    if role in ("action", "dialogue", "parenthetical", "transition"):
        return role  # type: ignore[return-value]

    # Sitting at no known margin: fall back on the leftmost thing it is
    # closest to, which is nearly always action.
    if profile.action is not None and profile.dialogue is not None:
        return "action" if abs(line.x0 - profile.action) <= abs(line.x0 - profile.dialogue) else "dialogue"
    return "action"

def _line_pitch(lines: list[Line]) -> float:
    """Distance between two consecutive lines *within* a block, in points.

    Measured rather than assumed: 12pt Courier is usually 14pt leading, but
    a script set at a different size or spacing will differ, and the
    block-splitting threshold has to be relative to this document.

    Deliberately the smallest *recurring* gap, not the median. Blocks are
    separated by a blank line, so gaps come in two families - one pitch and
    two - and in a short script the two-pitch family can outnumber the
    other. A median would then return the blank-line gap and no block would
    ever split. The single-pitch gap is by definition the smaller of the
    two, so take the smallest value that occurs often enough to be real.
    """
    gaps = [
        round(b.top - a.top)
        for a, b in zip(lines, lines[1:])
        if a.page == b.page and 0 < b.top - a.top < 100
    ]
    if not gaps:
        return 14.0
    counts: dict[int, int] = {}
    for g in gaps:
        counts[g] = counts.get(g, 0) + 1
    floor = max(2, len(gaps) // 10)
    recurring = [g for g, n in counts.items() if n >= floor]
    return float(min(recurring)) if recurring else float(min(gaps))


def _stitch_page_splits(elements: list[ScriptElementDraft]) -> tuple[list[ScriptElementDraft], int]:
    """Rejoin dialogue broken across a page.

    The pattern is: dialogue, "(MORE)", page break, "SARAH (CONT'D)", the
    rest of the dialogue. (MORE) is dropped as furniture before we get
    here, so what remains is a cue marked CONT'D sitting directly between
    two dialogue blocks by the same speaker. Nothing in between means it
    was one speech.
    """
    out: list[ScriptElementDraft] = []
    stitched = 0
    i = 0
    while i < len(elements):
        el = elements[i]
        if (
            el.type == "character"
            and getattr(el, "_cont_d", False)
            and out
            and out[-1].type == "dialogue"
            and out[-1].character == el.character
            and i + 1 < len(elements)
            and elements[i + 1].type == "dialogue"
        ):
            out[-1].text = f"{out[-1].text} {elements[i + 1].text}".strip()
            stitched += 1
            i += 2  # skip the cue and fold in the dialogue after it
            continue
        out.append(el)
        i += 1
    return out, stitched

def classify_document(
    lines: list[Line], *, tolerance: float = 12.0
) -> ClassifyResult:
    """Full result: elements, the margin profile, and anything doubtful."""
    result = ClassifyResult()
    if not lines:
        result.warnings.append("No lines to classify.")
        return result

    profile = derive_margins(lines)
    result.profile = profile
    result.warnings.extend(profile.notes)
    if not profile.usable:
        result.warnings.append(
            "Margins could not be derived; every line was treated as action."
        )

    speaker: str | None = None
    drafts: list[ScriptElementDraft] = []
    pitch = _line_pitch(lines)
    body = [ln for ln in lines if not is_furniture(ln)]
    prev_line: Line | None = None
    first_on_page = {ln.page: ln for ln in reversed(body)}  # first body line per page

    for line in body:
        text = line.text.strip()
        etype = _type_of(line, profile, tolerance) if profile.usable else "action"

        if etype == "scene_heading":
            speaker = None  # a new scene has no speaker until one is cued
            drafts.append(ScriptElementDraft("scene_heading", None, line.page, text))
            prev_line = line
            continue

        if etype == "character":
            name, suffixes = split_cue(text)
            speaker = name or None
            draft = ScriptElementDraft("character", speaker, line.page, text)
            draft._cont_d = any("CONT" in s.upper() for s in suffixes)  # type: ignore[attr-defined]
            drafts.append(draft)
            prev_line = line
            continue

        owner = speaker if etype in ("dialogue", "parenthetical") else None
        prev = drafts[-1] if drafts else None
        continues_block = False
        if (
            prev is not None
            and prev_line is not None
            and prev.type == etype
            and etype in MERGEABLE
            and prev.character == owner
        ):
            if prev_line.page == line.page:
                # Same page: a blank line ends the block, and a blank line
                # shows up as a vertical gap of roughly twice the pitch.
                continues_block = (line.top - prev_line.top) <= pitch * BLOCK_GAP_RATIO
            elif etype == "dialogue" and first_on_page.get(line.page) is line:
                # A speech running over the page break. The page number and
                # any (MORE) have already been dropped as furniture, so the
                # continuation is the first body line on the new page.
                continues_block = True

        if continues_block:
            prev.text = f"{prev.text} {text}".strip()
        else:
            drafts.append(ScriptElementDraft(etype, owner, line.page, text))
        prev_line = line

    elements, stitched = _stitch_page_splits(drafts)
    if stitched:
        result.warnings.append(
            f"Rejoined {stitched} dialogue block(s) split across a page break."
        )
    result.elements = elements
    return result


def classify(lines: list[Line]) -> list[ScriptElementDraft]:
    """The signature IMPLEMENTATION_SPEC.md specifies."""
    return classify_document(lines).elements