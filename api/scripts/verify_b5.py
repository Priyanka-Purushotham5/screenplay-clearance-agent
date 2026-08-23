"""B5 smoke-test — scene grouping and slug-line parsing.

    python api/scripts/verify_b5.py

The done-when is "scene count matches a manual count and no mini-slug has
created a spurious scene". Both fixtures are short enough to count by hand,
so the expected numbers below are a manual count, not a recorded output.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.app.parser.classify import classify_document  # noqa: E402
from api.app.parser.pdf import extract_lines  # noqa: E402
from api.app.parser.scenes import (  # noqa: E402
    group_document,
    parse_heading,
    strip_scene_number,
)

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


# Every variant §1.2 of the spec requires, plus the three that trap a
# naive parser: a location containing a time word, a location ending in a
# number, and a single-segment heading.
HEADINGS = [
    ("INT. DINER - NIGHT",                     "INT",     "DINER",                      "NIGHT"),
    ("EXT. PARKING LOT - DAY",                 "EXT",     "PARKING LOT",                "DAY"),
    ("INT./EXT. CAR - MOVING - NIGHT",         "INT/EXT", "CAR - MOVING",               "NIGHT"),
    ("I/E. WAREHOUSE - CONTINUOUS",            "INT/EXT", "WAREHOUSE",                  "CONTINUOUS"),
    ("INT. DINER - KITCHEN - NIGHT",           "INT",     "DINER - KITCHEN",            "NIGHT"),
    ("INT. DINER - LATER",                     "INT",     "DINER",                      "LATER"),
    ("EXT. BEACH - MAGIC HOUR",                "EXT",     "BEACH",                      "MAGIC HOUR"),
    ("I/E. PARKING GARAGE - NIGHT",            "INT/EXT", "PARKING GARAGE",             "NIGHT"),
    ("INT. LAW FIRM - CONFERENCE ROOM - NIGHT","INT",     "LAW FIRM - CONFERENCE ROOM", "NIGHT"),
    ("14 INT. DINER - KITCHEN - NIGHT 14",     "INT",     "DINER - KITCHEN",            "NIGHT"),
    # traps
    ("INT. NIGHT CLUB",                        "INT",     "NIGHT CLUB",                 None),
    ("INT. DAY CARE CENTRE - NIGHT",           "INT",     "DAY CARE CENTRE",            "NIGHT"),
    ("EXT. HIGHWAY 101 - DAY",                 "EXT",     "HIGHWAY 101",                "DAY"),
]

MINI_SLUGS = ("ANGLE ON", "MOMENTS LATER", "BACK TO SCENE", "LATER", "CONTINUOUS")


def main() -> int:
    print()
    # ── slug parsing, no PDF involved ──────────────────────────────────
    bad = [
        (h, parse_heading(h), (ie, loc, tod))
        for h, ie, loc, tod in HEADINGS
        if parse_heading(h) != (ie, loc, tod)
    ]
    check("Every §1.2 heading variant parses correctly", not bad,
          f"{len(HEADINGS)} headings" if not bad else f"first bad: {bad[0]}")

    check("Mirrored scene numbers are stripped",
          strip_scene_number("14 INT. DINER - NIGHT 14") == ("14", "INT. DINER - NIGHT"),
          str(strip_scene_number("14 INT. DINER - NIGHT 14")))

    check("A number that is part of the location survives",
          strip_scene_number("INT. ROOM 237") == (None, "INT. ROOM 237"),
          str(strip_scene_number("INT. ROOM 237")))

    check("A right-margin-only scene number is recognised",
          strip_scene_number("INT. DINER - NIGHT 14") == ("14", "INT. DINER - NIGHT"),
          str(strip_scene_number("INT. DINER - NIGHT 14")))

    # ── grouping, against both fixtures ────────────────────────────────
    runs = {}
    for name, expected_scenes in (("test_screenplay.pdf", 7), ("messy_screenplay.pdf", 2)):
        path = ROOT / "docs" / name
        if not path.exists():
            print(f"Fixture missing: {path}")
            return 2
        elements = classify_document(extract_lines(path)).elements
        group = group_document(elements)
        runs[name] = (elements, group)
        check(f"{name}: scene count matches a manual count",
              len(group.scenes) == expected_scenes,
              f"{len(group.scenes)} scenes, expected {expected_scenes}")

    for name, (elements, group) in runs.items():
        scenes = group.scenes

        check(f"{name}: every element lands in exactly one scene",
              sum(len(s.elements) for s in scenes) == len(elements),
              f"{sum(len(s.elements) for s in scenes)} vs {len(elements)} elements")

        check(f"{name}: no mini-slug started a scene",
              not any(s.heading.upper().startswith(MINI_SLUGS) for s in scenes),
              "; ".join(s.heading[:24] for s in scenes))

        check(f"{name}: every scene has an INT/EXT and a location",
              all(s.int_ext in ("INT", "EXT", "INT/EXT") and s.location for s in scenes))

        check(f"{name}: headings carry no scene numbers",
              not any(s.heading[:1].isdigit() or s.heading[-1:].isdigit() for s in scenes),
              "; ".join(s.heading[:20] for s in scenes))

        check(f"{name}: page ranges are sane and ordered",
              all(s.page_start <= s.page_end for s in scenes)
              and all(a.page_start <= b.page_start for a, b in zip(scenes, scenes[1:])))

        check(f"{name}: scene numbers are unique and increasing",
              all(a.number < b.number for a, b in zip(scenes, scenes[1:])),
              str([s.number for s in scenes]))

        check(f"{name}: the first element of each scene is its heading",
              all(s.elements[0].type == "scene_heading" for s in scenes if s.heading))

    # ── numbering policy ───────────────────────────────────────────────
    _, clean = runs["test_screenplay.pdf"]
    _, messy = runs["messy_screenplay.pdf"]
    check("A script without printed numbers is numbered by position",
          [s.number for s in clean.scenes] == list(range(1, len(clean.scenes) + 1)),
          str([s.number for s in clean.scenes]))
    check("A script with printed numbers keeps them",
          [s.number for s in messy.scenes] == [14, 15],
          str([s.number for s in messy.scenes]))

    check("No warnings on either fixture",
          not clean.warnings and not messy.warnings,
          str(clean.warnings + messy.warnings))

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())