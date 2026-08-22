"""Derive a screenplay's margins from its own geometry.

Screenplay format encodes element type in indentation, but the exact inch
values vary by tool, template and decade. Hard-coding a table works on the
scripts you tested and fails on the next one, so the margins are derived
per document: cluster the x0 values, then decide which cluster is which
using what the lines actually say.

Content evidence beats position evidence. The naive rule "largest x0 is the
character cue" fails on the first script you meet, because page numbers and
transitions sit further right than any cue.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from api.app.parser.pdf import POINTS_PER_INCH, Line

# Two x0 values closer than this belong to the same margin. Real exports
# jitter by a few tenths of a point; the tightest genuine gap in standard
# format is dialogue to parenthetical, half an inch — 36pt of headroom.
CLUSTER_TOLERANCE = 4.0

# A margin has to carry this share of the body before it counts as a real
# margin rather than a stray line.
MIN_CLUSTER_SHARE = 0.02
MIN_CLUSTER_LINES = 2

# page furniture: printed by the software, not written by the author
PAGE_NUMBER = re.compile(r"^\d{1,4}\.?$")
CONTINUED = re.compile(r"^\(?\s*(CONTINUED|MORE)\s*[:.)]?\s*\)?$", re.IGNORECASE)
REVISION_MARK = re.compile(r"^[*•]+$")

# A slug line carrying mirrored production scene numbers: "14  INT. DINER  14".
# Its x0 is the scene-number margin, not a text margin, so it must not vote.
NUMBERED_SLUG = re.compile(r"^\d{1,4}[A-Z]?\s+(INT|EXT|I/E|INT\.?/EXT)", re.IGNORECASE)

TRANSITION_WORDS = re.compile(
    r"(^FADE (IN|OUT)\b|^CUT TO\b|^DISSOLVE\b|^SMASH CUT\b|^MATCH CUT\b|TO:$)"
)


def is_furniture(line: Line) -> bool:
    """Printed page decoration that carries no story content."""
    t = line.text.strip()
    return bool(PAGE_NUMBER.match(t) or CONTINUED.match(t) or REVISION_MARK.match(t))


def is_numbered_slug(line: Line) -> bool:
    return bool(NUMBERED_SLUG.match(line.text.strip()))


@dataclass(frozen=True)
class Cluster:
    """One derived margin, with the evidence used to label it."""

    x0: float  # median of the member x0 values
    count: int
    role: str | None = None
    sample: str = ""

    @property
    def inches(self) -> float:
        return self.x0 / POINTS_PER_INCH


@dataclass
class MarginProfile:
    """The margins of one document, plus what could not be determined."""

    action: float | None = None
    dialogue: float | None = None
    parenthetical: float | None = None
    character: float | None = None
    transition: float | None = None
    clusters: list[Cluster] = field(default_factory=list)
    body_lines: int = 0
    furniture_dropped: int = 0
    slugs_excluded: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """The three margins classification cannot work without."""
        return None not in (self.action, self.dialogue, self.character)


def _cluster(values: list[float], tolerance: float) -> list[list[float]]:
    """One-dimensional agglomeration: a gap wider than `tolerance` splits."""
    groups: list[list[float]] = []
    for v in sorted(values):
        if groups and v - groups[-1][-1] <= tolerance:
            groups[-1].append(v)
        else:
            groups.append([v])
    return groups


def _all_caps(text: str) -> bool:
    return text.isupper() and any(c.isalpha() for c in text)


def _leads_into_indent(lines: list[Line], index: int) -> bool:
    """Is the next line indented noticeably *less*?

    That is the structural signature of a character cue: the cue sits far
    right, and the dialogue beneath it steps back left. Transitions and page
    numbers do not behave that way, which is what separates them from cues
    without relying on position.
    """
    if index + 1 >= len(lines):
        return False
    nxt = lines[index + 1]
    return nxt.x0 < lines[index].x0 - 10.0


def derive_margins(lines: list[Line], *, tolerance: float = CLUSTER_TOLERANCE) -> MarginProfile:
    profile = MarginProfile()
    if not lines:
        profile.notes.append("No lines to analyse.")
        return profile

    body: list[Line] = []
    for line in lines:
        if is_furniture(line):
            profile.furniture_dropped += 1
        elif is_numbered_slug(line):
            profile.slugs_excluded += 1
        else:
            body.append(line)

    profile.body_lines = len(body)
    if not body:
        profile.notes.append("Every line was furniture — nothing to cluster.")
        return profile

    index_of = {id(line): i for i, line in enumerate(lines)}
    groups = _cluster([line.x0 for line in body], tolerance)
    threshold = max(MIN_CLUSTER_LINES, round(len(body) * MIN_CLUSTER_SHARE))

    candidates: list[tuple[float, list[Line]]] = []
    for group in groups:
        lo, hi = group[0], group[-1]
        members = [ln for ln in body if lo <= ln.x0 <= hi]
        candidates.append((statistics.median(group), members))

    # label by what the lines say, not where they sit
    features = []
    for x0, members in candidates:
        n = len(members)
        features.append(
            {
                "x0": round(x0, 1),
                "members": members,
                "count": n,
                "caps": sum(_all_caps(m.text) for m in members) / n,
                "paren": sum(m.text.startswith("(") for m in members) / n,
                "transition": sum(bool(TRANSITION_WORDS.search(m.text)) for m in members) / n,
                "short": sum(len(m.text.split()) <= 5 for m in members) / n,
                "leads_in": sum(
                    _leads_into_indent(lines, index_of[id(m)]) for m in members
                ) / n,
                "significant": n >= threshold,
            }
        )

    if not any(f["significant"] for f in features):
        profile.notes.append(
            f"No margin carried {threshold}+ lines; document may be too short."
        )
        for f in features:
            f["significant"] = True

    assigned: dict[str, dict] = {}

    def take(role: str, pick, *, require_significant: bool = True) -> None:
        used = {a["x0"] for a in assigned.values()}
        pool = [
            f for f in features
            if f["x0"] not in used and (f["significant"] or not require_significant)
        ]
        chosen = pick(pool)
        if chosen is not None:
            assigned[role] = chosen

    # Transitions and parentheticals are identified by wording, which is
    # strong enough that a single line is enough. A script may contain one
    # "FADE OUT." and nothing else at that margin.
    take("transition", lambda p: max(
        (f for f in p if f["transition"] >= 0.5), key=lambda f: f["x0"], default=None),
        require_significant=False)
    take("parenthetical", lambda p: max(
        (f for f in p if f["paren"] >= 0.5), key=lambda f: f["count"], default=None),
        require_significant=False)
    # The three structural margins need weight behind them: they are what
    # every unlabelled line gets measured against.
    # Character cues: short, ALL CAPS, and the line beneath steps back left.
    take("character", lambda p: max(
        (f for f in p if f["caps"] >= 0.6 and f["short"] >= 0.6 and f["leads_in"] >= 0.5),
        key=lambda f: f["count"], default=None))
    # Action is the leftmost of what remains.
    take("action", lambda p: min(p, key=lambda f: f["x0"], default=None))
    # Dialogue is the busiest of what remains.
    take("dialogue", lambda p: max(p, key=lambda f: f["count"], default=None))

    for role, f in assigned.items():
        setattr(profile, role, f["x0"])

    role_of = {f["x0"]: role for role, f in assigned.items()}
    profile.clusters = [
        Cluster(
            x0=f["x0"],
            count=f["count"],
            role=role_of.get(f["x0"]),
            sample=f["members"][0].text[:48],
        )
        for f in sorted(features, key=lambda f: f["x0"])
    ]

    # --- sanity notes: report, never raise -------------------------------
    if not profile.usable:
        missing = [r for r in ("action", "dialogue", "character") if getattr(profile, r) is None]
        profile.notes.append(f"Could not identify: {', '.join(missing)}.")
    else:
        if not profile.action < profile.dialogue < profile.character:
            profile.notes.append(
                "Margins are not in the expected order "
                f"(action {profile.action} < dialogue {profile.dialogue} "
                f"< character {profile.character})."
            )
        if profile.parenthetical is not None and not (
            profile.dialogue < profile.parenthetical < profile.character
        ):
            profile.notes.append(
                "Parenthetical margin is not between dialogue and character."
            )
    if profile.parenthetical is None:
        profile.notes.append("No parenthetical margin found (the script may have none).")
    if profile.transition is None:
        profile.notes.append("No transition margin found (the script may have none).")
    return profile