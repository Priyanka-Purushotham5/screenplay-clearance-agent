"""B4 smoke-test — every line of both fixtures is correctly typed.

    python api/scripts/verify_b4.py            # check against the snapshot
    python api/scripts/verify_b4.py --freeze   # record the current output

Two kinds of check.

SNAPSHOT: the full typed sequence for each fixture, recorded once in
docs/b4_expected_elements.json after being read by a human. It catches
regressions but proves nothing on its own - it only says "the same as when
someone last looked". That is why --freeze is a separate, deliberate act:
re-freezing a broken parse simply blesses the breakage.

INVARIANT: properties that must hold whatever the implementation does.
These would still be meaningful if the classifier were rewritten from
scratch, and the first is the product thesis itself - 'Take On Me' appears
in an action line and in dialogue, and the two must land in different
element types, because that difference is what makes one RED and the other
GREEN.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.app.parser.classify import classify_document, is_slug, split_cue  # noqa: E402
from api.app.parser.pdf import extract_lines  # noqa: E402

FIXTURES = ("test_screenplay.pdf", "messy_screenplay.pdf")
SNAPSHOT = ROOT / "docs" / "b4_expected_elements.json"

# The margins each fixture was authored with, in inches. Unlike the
# snapshot these are known independently: they are written down in
# make_messy_pdf.py and visible in the source screenplay.
EXPECTED_MARGINS = {
    "test_screenplay.pdf": {"action": 1.50, "dialogue": 2.50, "character": 3.70},
    "messy_screenplay.pdf": {"action": 1.70, "dialogue": 2.70, "character": 4.00},
}

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def shape(elements) -> list[list]:
    """The part of an element that the snapshot pins down."""
    return [[e.page, e.type, e.character, e.text] for e in elements]


def run_all() -> dict:
    runs = {}
    for name in FIXTURES:
        path = ROOT / "docs" / name
        if not path.exists():
            raise SystemExit(f"Fixture missing: {path}")
        runs[name] = classify_document(extract_lines(path))
    return runs


def freeze(runs: dict) -> int:
    SNAPSHOT.write_text(
        json.dumps({n: shape(r.elements) for n, r in runs.items()}, indent=1),
        encoding="utf-8",
    )
    total = sum(len(r.elements) for r in runs.values())
    print(f"Recorded {total} elements to {SNAPSHOT.relative_to(ROOT)}")
    print("Read the classification output before trusting this file.")
    return 0


def main() -> int:
    runs = run_all()
    if "--freeze" in sys.argv:
        return freeze(runs)

    if not SNAPSHOT.exists():
        print(f"No snapshot at {SNAPSHOT.relative_to(ROOT)}.")
        print("Check the classifier output by eye, then: "
              "python api/scripts/verify_b4.py --freeze")
        return 2

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    print()

    # ── snapshot ───────────────────────────────────────────────────────
    for name in FIXTURES:
        actual = shape(runs[name].elements)
        want = [list(row) for row in expected.get(name, [])]
        if actual == want:
            check(f"{name}: typed sequence matches snapshot", True,
                  f"{len(actual)} elements")
            continue
        check(f"{name}: typed sequence matches snapshot", False,
              f"{len(actual)} elements vs {len(want)} recorded")
        for i, (a, b) in enumerate(zip(actual, want)):
            if a != b:
                print(f"        first difference at index {i}")
                print(f"          got      {a}")
                print(f"          expected {b}")
                break

    # ── margins were derived, not remembered ───────────────────────────
    for name, want_margins in EXPECTED_MARGINS.items():
        profile = runs[name].profile
        ok = profile is not None and all(
            getattr(profile, role) is not None
            and abs(getattr(profile, role) / 72 - inches) < 0.02
            for role, inches in want_margins.items()
        )
        got = ({r: round(getattr(profile, r) / 72, 2) for r in want_margins}
               if profile else None)
        check(f"{name}: margins derived correctly", ok, str(got))

    # ── invariants that survive a rewrite ──────────────────────────────
    test = runs["test_screenplay.pdf"].elements
    messy = runs["messy_screenplay.pdf"].elements
    both = test + messy

    song = [e for e in test if "Take On Me" in e.text]
    types = {e.type for e in song}
    check("The same song appears in both an action line and dialogue",
          types == {"action", "dialogue"} and len(song) >= 2,
          f"{len(song)} mentions, types={sorted(types)}")

    check("Mini-slugs are action, not scene headings",
          all(e.type == "action" for e in both
              if e.text.startswith(("ANGLE ON", "MOMENTS LATER", "BACK TO"))),
          "ANGLE ON / MOMENTS LATER")

    check("Every scene heading opens with INT/EXT/I/E",
          all(e.text.lstrip("0123456789 ").upper().startswith(("INT", "EXT", "I/E"))
              for e in both if e.type == "scene_heading"),
          f"{sum(1 for e in both if e.type == 'scene_heading')} headings")

    check("Every dialogue block has a speaker",
          all(e.character for e in both if e.type == "dialogue"))

    check("Every parenthetical has a speaker",
          all(e.character for e in both if e.type == "parenthetical"))

    check("No element text is empty", all(e.text.strip() for e in both))

    check("Page numbers never go backwards",
          all(a.page <= b.page for a, b in zip(test, test[1:]))
          and all(a.page <= b.page for a, b in zip(messy, messy[1:])))

    check("Page-split dialogue was rejoined",
          any("retired" in e.text and "Marcus Harman" in e.text for e in test),
          "DIANA across pages 1-2")

    check("(MORE)/(CONT'D) split was stitched",
          any("first time" in e.text and "ask again tomorrow" in e.text for e in messy),
          "SARAH across pages 1-2")

    # Neither fixture contains a lower-case line that opens with INT/EXT,
    # so the ALL-CAPS half of the slug rule is not exercised by the
    # snapshot: deleting it leaves every check green. Pin it directly.
    check("A slug must be ALL CAPS as well as INT/EXT",
          is_slug("INT. DINER - NIGHT")
          and is_slug("14 EXT. STREET - DAY")
          and not is_slug("Ext. of the building was crumbling.")
          and not is_slug("Interior lights flicker.")
          and not is_slug("MOMENTS LATER"),
          "lower-case 'Ext.' in an action line is not a scene")

    check("Cue suffixes are stripped from the stored name",
          split_cue("SARAH (V.O.) (CONT'D)") == ("SARAH", ["(V.O.)", "(CONT'D)"]),
          str(split_cue("SARAH (V.O.) (CONT'D)")))

    check("Page furniture never becomes an element",
          not any(e.text.strip() in {"1.", "2.", "3.", "CONTINUED:", "(CONTINUED)", "(MORE)"}
                  for e in both))

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())