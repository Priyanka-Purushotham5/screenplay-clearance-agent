"""B7 smoke-test — the answer key describes the screenplay that actually exists.

    python api/scripts/verify_b7.py

No Docker, no Postgres, no API. Like B4 and B5 this runs straight off the
parser, so it stays usable when the stack is down.

A hand-written answer key is a document that rots. Someone edits a line of
the screenplay, the key still says what it said last month, and every score
computed against it is quietly wrong. Nothing about that failure is visible:
the key still parses, the ratings still look reasonable, and the number that
comes out the other end is still a number.

So the key anchors on QUOTED TEXT rather than element numbers, and this
script resolves every quote against the freshly parsed document. A quote
that no longer appears, or that appears twice, or that has moved to a
different scene or element type, is a loud failure. Element indices would be
worse on all three counts: they resolve silently to the wrong thing.

It also checks the two halves of the key against each other. docs/
ground-truth.md is written for humans and docs/ground-truth.json for
machines, and duplicated data drifts, so the markdown table is parsed and
compared against the JSON row by row.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.app.parser.pipeline import parse_screenplay  # noqa: E402

DOCS = ROOT / "docs"
KEY_JSON = DOCS / "ground-truth.json"
KEY_MD = DOCS / "ground-truth.md"

RATINGS = {"RED", "AMBER", "GREEN"}

# The content rows of B7 in implementation-checklist.md. Every one of them
# has to be represented by at least one entry, or the fixture has stopped
# covering the thing it was built to cover.
REQUIRED_CHECKLIST = {
    "song-in-action",
    "song-in-dialogue",
    "brand-held-to-camera",
    "brand-disparaged",
    "20th-century-painting",
    "living-public-figure",
    "real-restaurant-location",
    "shakespeare-line",
    "fictional-doctor",
}

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def md_rows(text: str) -> dict[str, dict]:
    """Parse the answer-key table out of the markdown.

    Only rows whose first cell is a gt_ id are taken, so the ratings table,
    the discrimination-set table and the false-positive tables are ignored.
    """
    rows: dict[str, dict] = {}
    for line in text.splitlines():
        if not line.startswith("| gt_"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        rows[cells[0]] = {
            "scene": cells[1],
            "element_type": cells[2],
            "rating": cells[4],
            "set": cells[5],
        }
    return rows


def main() -> int:
    for path in (KEY_JSON, KEY_MD):
        if not path.exists():
            print(f"Missing: {path.relative_to(ROOT)}")
            return 2

    key = json.loads(KEY_JSON.read_text(encoding="utf-8"))
    md = KEY_MD.read_text(encoding="utf-8")

    fixture = ROOT / key["fixture"]
    if not fixture.exists():
        print(f"Fixture missing: {fixture}")
        return 2

    parsed = parse_screenplay(fixture)
    elements = [(s.number, e.type, e.text) for s in parsed.scenes for e in s.elements]

    entries = key["entries"]
    sets = key["discrimination_sets"]

    # ── the document is the one the key was written against ────────────
    check("Fixture parses without warnings", parsed.warnings == [],
          str(parsed.warnings))
    check("Scene count matches the key", len(parsed.scenes) == key["fixture_scenes"],
          f"{len(parsed.scenes)} vs {key['fixture_scenes']}")
    check("Element count matches the key", parsed.element_count == key["fixture_elements"],
          f"{parsed.element_count} vs {key['fixture_elements']}")

    # ── every anchor still resolves, uniquely, where it claims to ──────
    anchored = entries + key["must_not_flag"] + key["acceptable_either_way"]
    misses = []
    for e in anchored:
        hits = [(sn, t) for sn, t, text in elements if e["quote"] in text]
        ok = (
            len(hits) == 1
            and hits[0][0] == e["scene"]
            and ("element_type" not in e or hits[0][1] == e["element_type"])
        )
        if not ok:
            misses.append(f"{e.get('id', e['quote'][:24])}: {len(hits)} hit(s) {hits}")
    check(f"All {len(anchored)} quotes resolve to exactly one element in the right place",
          not misses, "; ".join(misses[:3]))

    # ── the key is internally well formed ──────────────────────────────
    ids = [e["id"] for e in entries]
    check("Entry ids are unique", len(set(ids)) == len(ids),
          f"{len(ids)} entries")
    bad_ratings = [e["id"] for e in entries if e["rating"] not in RATINGS]
    check("Every rating is RED, AMBER or GREEN", not bad_ratings, str(bad_ratings))
    unreasoned = [e["id"] for e in entries if len(e.get("rationale", "")) < 40]
    check("Every entry carries a rationale", not unreasoned, str(unreasoned))

    # ── checklist coverage ─────────────────────────────────────────────
    covered = {e.get("checklist") for e in entries}
    missing = sorted(REQUIRED_CHECKLIST - covered)
    check("Every content row of the B7 checklist is covered", not missing,
          f"missing {missing}" if missing else f"{len(REQUIRED_CHECKLIST)} rows")

    # ── discrimination sets ────────────────────────────────────────────
    by_id = {e["id"]: e for e in entries}
    dangling = [m for s in sets.values() for m in s["members"] if m not in by_id]
    check("Every set member is a real entry", not dangling, str(dangling))

    declared = {e["id"]: e.get("set") for e in entries if e.get("set")}
    listed = {m: name for name, s in sets.items() for m in s["members"]}
    check("Set membership agrees in both directions", declared == listed,
          f"{sorted(declared.items())} vs {sorted(listed.items())}")

    # A set discriminates when its members carry exactly the spread of
    # ratings it declares. "All members differ" was the first version of this
    # check and it stopped working the moment a set grew past three members:
    # set B has five mentions of Coca-Cola across three ratings, so two pairs
    # legitimately match. Declaring the expected spread keeps the check exact
    # instead of weakening it to "at least two are different".
    for name, s in sorted(sets.items()):
        ratings = [by_id[m]["rating"] for m in s["members"] if m in by_id]
        want = set(s.get("ratings", []))
        check(f"Set {name} ({s['entity']}) spans {sorted(want)}",
              set(ratings) == want and len(ratings) == len(s["members"]),
              f"{s['members']} -> {ratings}")

    # A derived entry must not silently disagree with the entry it points at.
    # These exist so repeat mentions can be scored without duplicating the
    # reasoning; if one drifts to a different rating it is no longer derived
    # and needs its own argument.
    inconsistent = [
        f"{e['id']}={e['rating']} but {e['same_as']}={by_id[e['same_as']]['rating']}"
        for e in entries
        if e.get("same_as") and e["same_as"] in by_id
        and e["rating"] != by_id[e["same_as"]]["rating"]
    ]
    dangling_refs = [e["id"] for e in entries
                     if e.get("same_as") and e["same_as"] not in by_id]
    check("Derived entries agree with the entry they cite",
          not inconsistent and not dangling_refs,
          str(inconsistent + dangling_refs))

    # ── the two halves of the key agree ────────────────────────────────
    rows = md_rows(md)
    check("Markdown table lists every entry", set(rows) == set(ids),
          f"md-only {sorted(set(rows) - set(ids))}, json-only {sorted(set(ids) - set(rows))}")

    disagree = [
        f"{i}: md={rows[i]['rating']}/{rows[i]['scene']} json={by_id[i]['rating']}/{by_id[i]['scene']}"
        for i in sorted(set(rows) & set(ids))
        if rows[i]["rating"] != by_id[i]["rating"]
        or rows[i]["scene"] != str(by_id[i]["scene"])
        or rows[i]["element_type"] != by_id[i]["element_type"]
    ]
    check("Markdown and JSON agree on rating, scene and element type",
          not disagree, "; ".join(disagree[:3]))

    md_sets = {i: r["set"] for i, r in rows.items() if r["set"] not in ("", "—", "-")}
    check("Markdown and JSON agree on set membership", md_sets == listed,
          f"{sorted(md_sets.items())} vs {sorted(listed.items())}")

    # The prose tally is hand-written, so it is the line most likely to be
    # wrong. It was, the first time this script ran.
    counts = {r: sum(1 for e in entries if e["rating"] == r) for r in RATINGS}
    tally = re.search(r"(\d+) RED, (\d+) AMBER, (\d+) GREEN", md)
    check("The prose tally matches the entries",
          tally is not None
          and [int(g) for g in tally.groups()]
          == [counts["RED"], counts["AMBER"], counts["GREEN"]],
          (tally.group(0) if tally else "no tally line")
          + f" vs {counts['RED']}/{counts['AMBER']}/{counts['GREEN']}")

    # ── evidence-required entries ──────────────────────────────────────
    # Stated as a property rather than a list of ids. The first version of
    # this check named gt_15 and gt_16 explicitly and broke as soon as
    # reconciliation added two more mentions of the same invented person —
    # a snapshot wearing an invariant's clothes, exactly like verify_b5's
    # scene-numbering check before B7.
    needs_evidence = {e["id"] for e in entries if e.get("requires_evidence")}
    fictional = {e["id"] for e in entries
                 if e.get("checklist") in {"fictional-name", "fictional-doctor"}}
    check("Exactly the fictional-name entries require evidence",
          needs_evidence == fictional,
          f"flagged {sorted(needs_evidence)} vs fictional {sorted(fictional)}")
    check("Evidence-required entries are rated GREEN",
          all(by_id[i]["rating"] == "GREEN" for i in needs_evidence),
          str({i: by_id[i]["rating"] for i in needs_evidence}))
    check("docs/ground-truth.md explains the evidence requirement",
          "requires_evidence" in md and "cite the search" in md)

    # ── the parser edge cases the checklist also asks for ──────────────
    headings = [s.heading for s in parsed.scenes]
    check("An INT./EXT. heading is present",
          any(h.startswith("INT./EXT.") for h in headings), str(headings[:3]))
    check("An I/E. heading is present",
          any(h.startswith("I/E.") for h in headings))
    minis = [e.text for s in parsed.scenes for e in s.elements
             if e.type == "action" and re.fullmatch(r"[A-Z0-9 .'\-]+", e.text)
             and len(e.text) < 40]
    check("Mini-slugs survive as action, not headings", len(minis) >= 2, str(minis))
    check("At least one scene spans a page break",
          any(s.page_end > s.page_start for s in parsed.scenes),
          str([(s.number, s.page_start, s.page_end) for s in parsed.scenes]))

    reds = sum(1 for e in entries if e["rating"] == "RED")
    ambers = sum(1 for e in entries if e["rating"] == "AMBER")
    greens = sum(1 for e in entries if e["rating"] == "GREEN")
    print(f"\nKey: {len(entries)} entries — {reds} RED, {ambers} AMBER, {greens} GREEN, "
          f"{len(sets)} discrimination sets")
    print(f"{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
