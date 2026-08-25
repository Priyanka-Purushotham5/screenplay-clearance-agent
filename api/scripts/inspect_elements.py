"""inspect_elements.py — look at the frozen extraction before normalising it.

    docker compose exec api python api/scripts/inspect_elements.py

Read-only. Decides nothing, changes nothing. The same role `inspect_margins.py`
played before B4: get the shape of the real data on screen before writing code
that assumes a shape.

Four views:

  1. Mentions grouped by canonical name — what C3 will collapse.
  2. The category histogram — what C6's rubric has to route.
  3. The element_type split per entity — what C3 must NOT collapse, because
     an action-line mention and a dialogue mention of the same work get
     different ratings, and that difference is the product.
  4. A preview of what a naive normalisation would merge, and what it would
     leave alone. A preview, not a proposal — the point is to see which
     merges look right and which look like accidents before any of it is
     written down as a rule.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "api" / "app" / "agents" / "fixtures" / "elements_fixture.json"


def preview_normalise(name: str) -> str:
    """One plausible normalisation, shown so it can be argued with.

    Lowercase, collapse every run of non-alphanumerics to a single
    underscore, trim. Nothing category-aware, nothing clever — the question
    this answers is only 'how much of the drift is punctuation?'
    """
    parts = [
        re.sub(r"[^a-z0-9]+", "_", part.strip().casefold()).strip("_")
        for part in name.split(":")
    ]
    return ":".join(p for p in parts if p)


def main() -> int:
    if not FIXTURE.exists():
        print(f"No fixture at {FIXTURE.relative_to(ROOT)}")
        print("Record one: python api/scripts/make_elements_fixture.py --freeze")
        return 2

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    elements = data["elements"]

    print(f"{len(elements)} mentions from {data.get('model')} / "
          f"{data.get('prompt_version')}, recall {data.get('recall')}")

    # ── 1. what C3 will collapse ───────────────────────────────────────
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in elements:
        groups[e["canonical_name"]].append(e)

    print(f"\n{'=' * 78}\n1. MENTIONS BY CANONICAL NAME — "
          f"{len(elements)} mentions, {len(groups)} names, "
          f"{len(elements) / len(groups):.2f}:1\n{'=' * 78}")
    for name, mentions in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"\n{len(mentions)}x  {name}")
        for m in mentions:
            print(f"      {m['script_element_id']:<6} {m['category']:<14} "
                  f"{m['element_type']:<14} {m['surface_form'][:44]!r}")

    # ── 2. what C6's rubric has to route ───────────────────────────────
    print(f"\n{'=' * 78}\n2. CATEGORY HISTOGRAM\n{'=' * 78}")
    # C6's per-category criteria, from the checklist. Anything outside this
    # set has no rule and would be rated by nothing.
    RUBRIC = {"music", "trademark", "artwork", "person", "location", "clip", "literary"}
    for category, n in Counter(e["category"] for e in elements).most_common():
        flag = "" if category in RUBRIC else "   <-- no rubric rule"
        print(f"  {n:>3}  {category:<16}{flag}")

    # ── 3. what C3 must not collapse ───────────────────────────────────
    print(f"\n{'=' * 78}\n3. THE SPLIT — one entity, several element types\n{'=' * 78}")
    split = 0
    for name, mentions in sorted(groups.items()):
        types = sorted({m["element_type"] for m in mentions})
        if len(types) > 1:
            split += 1
            print(f"  {name:<38} {', '.join(types)}")
    print(f"\n  {split} entities appear in more than one element type.")
    print("  Each mention keeps its own rating. Grouping is for research only.")

    # ── 4. what a naive normalisation would do ─────────────────────────
    print(f"\n{'=' * 78}\n4. PREVIEW — naive normalisation "
          f"(lowercase, punctuation to _)\n{'=' * 78}")
    merged: dict[str, set[str]] = defaultdict(set)
    for name in groups:
        merged[preview_normalise(name)].add(name)

    changed = {k: v for k, v in merged.items() if len(v) > 1 or v != {k}}
    if not changed:
        print("  Nothing changes — every canonical name is already normal form.")
    for norm, originals in sorted(changed.items()):
        if len(originals) > 1:
            print(f"  MERGE  {norm}")
            for o in sorted(originals):
                print(f"           <- {o}")
        else:
            print(f"  rename {sorted(originals)[0]}  ->  {norm}")

    print(f"\n  {len(groups)} names -> {len(merged)} after punctuation alone "
          f"({len(elements) / len(merged):.2f}:1)")
    print("\n  Read the MERGE lines. A merge that pairs two spellings of one")
    print("  thing is the fix; a merge that pairs two different things is a")
    print("  bug that would send one research dossier to both.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
