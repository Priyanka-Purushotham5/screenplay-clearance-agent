"""Group typed elements into scenes, and parse each slug line.

A scene runs from one slug line to the next. Everything in between - action,
cues, dialogue, transitions - belongs to the scene above it.

The hard part is not the grouping, it is deciding what counts as a slug.
Mini-slugs like ANGLE ON and MOMENTS LATER are ALL CAPS and sit at the
action margin, and treating them as scenes is, per the spec, "the most
common parser bug". B4 already types them as action, so by the time the
elements reach here that trap is closed: this module only ever starts a
scene on something B4 called a scene_heading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from api.app.parser.classify import ScriptElementDraft

# A production scene number: 14, 14A, A14. Printed in the left margin and
# mirrored in the right.
SCENE_NUMBER = r"[A-Z]?\d{1,4}[A-Z]?"
LEADING_NUMBER = re.compile(rf"^({SCENE_NUMBER})\s+")
TRAILING_NUMBER = re.compile(rf"\s+({SCENE_NUMBER})$")

INT_EXT = re.compile(
    r"^(INT\.?/EXT\.?|EXT\.?/INT\.?|I/E\.?|INT\.?|EXT\.?)(?=[\s.]|$)", re.IGNORECASE
)
NORMALISED = {
    "INT": "INT", "EXT": "EXT", "I/E": "INT/EXT",
    "INT/EXT": "INT/EXT", "EXT/INT": "INT/EXT",
}

# Words that mark the final segment as a time rather than more location.
# Matched as whole words, so "DAY CARE CENTRE" is a place, not a time.
TIME_WORDS = {
    "DAY", "NIGHT", "MORNING", "AFTERNOON", "EVENING", "DUSK", "DAWN", "NOON",
    "MIDNIGHT", "LATER", "CONTINUOUS", "SUNSET", "SUNRISE", "TWILIGHT", "HOUR",
    "MOMENTS", "SAME", "PRESENT", "PAST", "FLASHBACK",
}

# Slug segments are separated by a dash with spaces around it. Em and en
# dashes appear in files exported from word processors with smart dashes on.
SEPARATOR = re.compile(r"\s+[-–—]+\s+")


@dataclass
class SceneDraft:
    """One scene, before it is persisted."""

    number: int  # what goes in scenes.number
    printed_number: str | None  # the production number, when the script has one
    int_ext: str | None
    location: str | None
    time_of_day: str | None
    heading: str  # slug line with scene numbers stripped
    page_start: int
    page_end: int
    elements: list[ScriptElementDraft] = field(default_factory=list)


@dataclass
class GroupResult:
    scenes: list[SceneDraft] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def strip_scene_number(heading: str) -> tuple[str | None, str]:
    """Remove mirrored production scene numbers: "14 INT. DINER 14"."""
    text = heading.strip()
    lead = LEADING_NUMBER.match(text)
    if lead:
        number = lead.group(1)
        text = text[lead.end():].strip()
        trail = TRAILING_NUMBER.search(text)
        # Only strip the trailing copy when it mirrors the leading one, so
        # "INT. ROOM 237" keeps its room number.
        if trail and trail.group(1) == number:
            text = text[: trail.start()].strip()
        return number, text

    trail = TRAILING_NUMBER.search(text)
    if trail:
        before = text[: trail.start()].strip()
        # A number after a time of day is a scene number in the right
        # margin. A number anywhere else is part of the location.
        if set(SEPARATOR.split(before)[-1].upper().split()) & TIME_WORDS:
            return trail.group(1), before
    return None, text


def parse_heading(heading: str) -> tuple[str | None, str | None, str | None]:
    """"INT. DINER - KITCHEN - NIGHT" -> ("INT", "DINER - KITCHEN", "NIGHT")."""
    _, text = strip_scene_number(heading)
    m = INT_EXT.match(text)
    if not m:
        return None, (text or None), None

    raw = m.group(1).upper().rstrip(".").replace("./", "/").rstrip(".")
    int_ext = NORMALISED.get(raw, raw)
    rest = text[m.end():].lstrip(" .").strip()
    if not rest:
        return int_ext, None, None

    parts = [p.strip() for p in SEPARATOR.split(rest) if p.strip()]
    # The last segment is a time only when something precedes it. A single
    # segment is the location, so "INT. NIGHT CLUB" is a place.
    if len(parts) >= 2 and set(parts[-1].upper().split()) & TIME_WORDS:
        return int_ext, " - ".join(parts[:-1]) or None, parts[-1]
    return int_ext, " - ".join(parts) or None, None

def _new_scene(element: ScriptElementDraft) -> SceneDraft:
    printed, cleaned = strip_scene_number(element.text)
    int_ext, location, time_of_day = parse_heading(element.text)
    heading = ScriptElementDraft("scene_heading", None, element.page, cleaned)
    return SceneDraft(
        number=0,  # assigned once the whole document is grouped
        printed_number=printed,
        int_ext=int_ext,
        location=location,
        time_of_day=time_of_day,
        heading=cleaned,
        page_start=element.page,
        page_end=element.page,
        elements=[heading],
    )


def group_document(elements: list[ScriptElementDraft]) -> GroupResult:
    """Scenes plus anything doubtful. Never raises on a strange heading."""
    result = GroupResult()
    if not elements:
        result.warnings.append("No elements to group into scenes.")
        return result

    scenes: list[SceneDraft] = []
    orphans: list[ScriptElementDraft] = []

    for element in elements:
        if element.type == "scene_heading":
            scenes.append(_new_scene(element))
            continue
        if not scenes:
            orphans.append(element)  # title page, FADE IN: and the like
            continue
        scene = scenes[-1]
        scene.elements.append(element)
        scene.page_end = max(scene.page_end, element.page)

    if orphans:
        if scenes:
            first = scenes[0]
            first.elements = orphans + first.elements
            first.page_start = min(first.page_start, orphans[0].page)
            result.warnings.append(
                f"{len(orphans)} element(s) appear before the first scene "
                f"heading; attached to scene 1."
            )
        else:
            page_start = min(e.page for e in orphans)
            scenes.append(
                SceneDraft(
                    number=1, printed_number=None, int_ext=None, location=None,
                    time_of_day=None, heading="", page_start=page_start,
                    page_end=max(e.page for e in orphans), elements=orphans,
                )
            )
            result.warnings.append(
                "No scene headings were found; the whole script is one scene."
            )

    # --- numbering -------------------------------------------------------
    # Prefer the production's own numbers when every scene has one and they
    # are plain integers: a clearance report that says "scene 47" should
    # mean the same thing to the production office. Fall back to ordinals
    # the moment they are partial or contain letters, because a mixture is
    # worse than either.
    printed = [s.printed_number for s in scenes]
    usable = all(p is not None and p.isdigit() for p in printed)
    if usable and len(set(printed)) == len(printed):
        for scene in scenes:
            scene.number = int(scene.printed_number)  # type: ignore[arg-type]
    else:
        for i, scene in enumerate(scenes, start=1):
            scene.number = i
        if any(p is not None for p in printed):
            result.warnings.append(
                "Production scene numbers were incomplete or not numeric; "
                "scenes are numbered by position instead."
            )

    for scene in scenes:
        if scene.int_ext is None and scene.heading:
            result.warnings.append(
                f"Scene {scene.number} heading has no INT/EXT marker: "
                f"{scene.heading[:60]!r}"
            )
        elif scene.location is None and scene.heading:
            result.warnings.append(
                f"Scene {scene.number} heading has no location: "
                f"{scene.heading[:60]!r}"
            )

    result.scenes = scenes
    return result


def group_scenes(elements: list[ScriptElementDraft]) -> list[SceneDraft]:
    """The signature IMPLEMENTATION_SPEC.md specifies."""
    return group_document(elements).scenes