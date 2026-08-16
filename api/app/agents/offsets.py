"""Verify and repair the character offsets the extraction model reports.

Offsets are what let the UI jump from a finding to the exact span in the
script, so they have to be right.  Language models count characters badly —
they are asked for offsets as a *hint*, and this module decides what is
actually stored.

The ladder, in order:

    exact       text[start:end] == surface_form           → keep as given
    repaired    surface_form found by search              → use the found span
    unresolved  no match at all                           → null the offsets

A repair also rewrites `surface_form` to the substring actually found, so the
invariant `text[char_start:char_end] == surface_form` holds for every element
that has offsets at all.  That matters twice over: `surface_form` is defined
as "as written in the script", and the C1 gate is exactly this invariant.

Pure functions, no I/O.  C2 reuses this unchanged over every chunk.
"""

import re
from typing import NamedTuple

from api.app.agents.schemas import OffsetStatus

_WS = re.compile(r"\s+")

# Screenplays quote song titles inconsistently — 'Take On Me', "Take On Me",
# TAKE ON ME.  A model asked for the surface form often returns it unquoted
# even when the text quotes it.
_STRIPPABLE = "\"'“”‘’ \t.,!?;:-"


class OffsetResolution(NamedTuple):
    char_start: int | None
    char_end: int | None
    status: OffsetStatus
    surface_form: str  # the text actually spanned, or the model's on failure


def _spans(haystack: str, needle: str) -> list[tuple[int, int]]:
    """All non-overlapping occurrences of `needle`, as (start, end) spans."""
    if not needle:
        return []
    out: list[tuple[int, int]] = []
    start = haystack.find(needle)
    while start != -1:
        out.append((start, start + len(needle)))
        start = haystack.find(needle, start + len(needle))
    return out


def _nearest(spans: list[tuple[int, int]], hint: int) -> tuple[int, int]:
    """The span whose start is closest to `hint`.

    A surface form can legitimately appear more than once in one action line.
    The model's hint is usually wrong by a handful of characters rather than
    by a whole sentence, so proximity picks the mention it meant.
    """
    return min(spans, key=lambda s: abs(s[0] - hint))


def _whitespace_map(text: str) -> tuple[str, list[int]]:
    """Collapse runs of whitespace, keeping an index back into the original.

    Parsed screenplay text carries line-wrap artifacts, so a surface form the
    model read as `Nighthawks by Edward Hopper` may sit in the text with a
    newline in the middle of it.
    """
    collapsed: list[str] = []
    index: list[int] = []
    prev_ws = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_ws:
                continue
            collapsed.append(" ")
            index.append(i)
            prev_ws = True
        else:
            collapsed.append(ch)
            index.append(i)
            prev_ws = False
    return "".join(collapsed), index


def resolve_offset(
    text: str,
    surface_form: str,
    hint_start: int | None,
    hint_end: int | None,
) -> OffsetResolution:
    """Resolve one mention's span within its own element text.

    Offsets are always element-local, never document-wide.
    """
    if not surface_form:
        return OffsetResolution(None, None, "unresolved", surface_form)

    hint = hint_start if isinstance(hint_start, int) and hint_start >= 0 else 0

    # 1 — exact: the model got it right, which is the common case for short
    #     surface forms near the start of a line.
    if (
        isinstance(hint_start, int)
        and isinstance(hint_end, int)
        and 0 <= hint_start < hint_end <= len(text)
        and text[hint_start:hint_end] == surface_form
    ):
        return OffsetResolution(hint_start, hint_end, "exact", surface_form)

    candidates: list[tuple[int, int]] = []

    # 2 — literal search.
    candidates = _spans(text, surface_form)

    # 2b — case-insensitive.  Action lines shout brand names in caps
    #      (`A Coca-Cola can`) while the model may normalise the casing.
    if not candidates:
        candidates = _spans(text.casefold(), surface_form.casefold())

    # 2c — stripped of surrounding quotes and punctuation.
    if not candidates:
        trimmed = surface_form.strip(_STRIPPABLE)
        if trimmed and trimmed != surface_form:
            candidates = _spans(text.casefold(), trimmed.casefold())

    if candidates:
        start, end = _nearest(candidates, hint)
        return OffsetResolution(start, end, "repaired", text[start:end])

    # 2d — whitespace-insensitive, mapped back to real indices.
    flat_text, index = _whitespace_map(text)
    flat_form = _WS.sub(" ", surface_form).strip()
    if flat_form:
        spans = _spans(flat_text.casefold(), flat_form.casefold())
        if spans:
            start, end = _nearest(spans, hint)
            real_start = index[start]
            real_end = index[end - 1] + 1
            return OffsetResolution(
                real_start, real_end, "repaired", text[real_start:real_end]
            )

    # 3 — unresolved.  The element is still worth keeping: the mention may be
    #     real and only the span unrecoverable.  The caller records a warning
    #     and the UI simply cannot deep-link this one.
    return OffsetResolution(None, None, "unresolved", surface_form)


def verify_offset(
    text: str, surface_form: str, start: int | None, end: int | None
) -> bool:
    """True when `text[start:end]` is exactly `surface_form`.

    This is the C1 acceptance criterion, expressed once so the agent and the
    verify script check the same thing.
    """
    if start is None or end is None:
        return False
    if not 0 <= start < end <= len(text):
        return False
    return text[start:end] == surface_form
