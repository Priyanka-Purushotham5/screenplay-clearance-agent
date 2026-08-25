"""C3 smoke-test — canonicalisation and dedup.

    docker compose exec api python api/scripts/verify_c3.py

Runs against the frozen extraction in
`api/app/agents/fixtures/elements_fixture.json`, so it costs nothing and
gives the same answer every time. That is the point of freezing it.

Three kinds of check.

MEASURED: the reduction ratio the checklist asks for, and the Coca-Cola
cluster specifically, because that is the case that motivated the module.

INVARIANT: properties that must hold whatever the implementation does —
every mention lands in exactly one group, no group loses an element type,
every group routes to a category C6 can actually rate. These would still
mean something if the grouping were rewritten from scratch.

ADVERSARIAL: small synthetic inputs built to make the merge rules
misbehave. `nobu` must not swallow `nobuko`; an unrelated person who
shares a surname with a painter must not be folded into the painting.
A merge rule that is never attacked is a merge rule you do not know the
limits of.

Finally it prints the reconciliation against B7's answer key — which
mentions have a ground-truth rating and which do not. That is a report,
not a gate: the gaps need human judgement, and this only says where.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.agents.canonical import (  # noqa: E402
    RUBRIC_CATEGORIES,
    group_mentions,
    normalise_part,
    parse_name,
)

FIXTURE = ROOT / "api" / "app" / "agents" / "fixtures" / "elements_fixture.json"
CHUNK = ROOT / "api" / "app" / "agents" / "fixtures" / "scene_fixture.json"
GROUND_TRUTH = ROOT / "docs" / "ground-truth.json"

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def mention(element_id: str, category: str, canonical: str,
            surface: str, element_type: str = "action") -> dict:
    """A minimal ResolvedElement-shaped dict, for the adversarial cases."""
    return {
        "script_element_id": element_id, "scene_id": "sc_1", "category": category,
        "surface_form": surface, "canonical_name": canonical,
        "element_type": element_type, "page": 1, "char_start": None,
        "char_end": None, "confidence": 1.0, "offset_status": "unresolved",
    }


def main() -> int:
    if not FIXTURE.exists():
        print(f"No fixture at {FIXTURE.relative_to(ROOT)}")
        print("Record one: python api/scripts/make_elements_fixture.py --freeze")
        return 2

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    mentions = data["elements"]
    result = group_mentions(mentions)
    groups = result.groups

    print(f"{len(mentions)} mentions -> {len(groups)} entities "
          f"({result.reduction:.2f}:1)\n")

    # ── normalisation ──────────────────────────────────────────────────
    check("Punctuation variants normalise together",
          normalise_part("a-ha") == normalise_part("A_Ha") == "a_ha",
          normalise_part("a-ha"))
    p = parse_name("music:take_on_me:a-ha")
    check("A three-part name splits into category, slug, qualifier",
          (p.category, p.slug, p.qualifier) == ("music", "take_on_me", "a_ha"),
          str((p.category, p.slug, p.qualifier)))
    p2 = parse_name("nonsense")
    check("A name with no category keeps its whole text as the slug",
          (p2.category, p2.slug) == ("other", "nonsense"), str(p2))

    # ── measured ───────────────────────────────────────────────────────
    check("Reduction reaches the checklist's ~2:1",
          result.reduction >= 2.0, f"{result.reduction:.2f}:1")

    coke = [g for g in groups if "coca_cola" in g.canonical]
    check("Coca-Cola is exactly one entity", len(coke) == 1,
          f"{[g.canonical for g in coke]}")
    if coke:
        check("Every Coca-Cola name folded into it",
              len(coke[0].aliases) >= 2 and coke[0].rubric_category == "trademark",
              f"{sorted(coke[0].aliases)} -> {coke[0].rubric_category}")

    # ── invariants ─────────────────────────────────────────────────────
    check("Every mention lands in exactly one group",
          result.mention_count == len(mentions),
          f"{result.mention_count} vs {len(mentions)}")

    ids = [id(m) for g in groups for m in g.mentions]
    check("No mention is duplicated across groups",
          len(ids) == len(set(ids)), f"{len(ids)} placements")

    unroutable = [g.canonical for g in groups
                  if g.rubric_category not in RUBRIC_CATEGORIES]
    check("Every group routes to a category C6 can rate",
          not unroutable, str(unroutable))

    # The whole product in one check. Grouping exists to save research calls;
    # if it ever costs an element_type distinction it has destroyed the thing
    # it was built to serve.
    before = {}
    for m in mentions:
        before.setdefault(m["canonical_name"], set()).add(m["element_type"])
    after = {}
    for g in groups:
        for alias in g.aliases:
            after.setdefault(alias, set()).update(g.element_types)
    kept = all(before[a] <= after.get(a, set()) for a in before)
    check("Grouping never loses an element type", kept)

    split = [g for g in groups if len(g.element_types) > 1]
    check("The action/dialogue split survives grouping",
          any("take_on_me" in g.canonical for g in split),
          "; ".join(f"{g.canonical}={','.join(g.element_types)}" for g in split))

    # Derived names must not depend on the order mentions arrive in — the
    # canonical name is a cache key, and a key that depends on list order is
    # not a key.
    shuffled = group_mentions(list(reversed(mentions)))
    check("Canonical names are independent of mention order",
          {g.canonical for g in shuffled.groups} == {g.canonical for g in groups},
          str(sorted({g.canonical for g in shuffled.groups}
                     ^ {g.canonical for g in groups})))

    check("Every group offers a surface-form fallback key",
          all(g.surface_key and ":" in g.surface_key for g in groups))

    # ── adversarial ────────────────────────────────────────────────────
    near = group_mentions([
        mention("el_1", "location", "location:nobu", "Nobu"),
        mention("el_2", "location", "location:nobuko", "Nobuko"),
    ])
    check("A shared string prefix is not a shared entity — nobu vs nobuko",
          len(near.groups) == 2, str([g.canonical for g in near.groups]))

    apart = group_mentions([
        mention("el_1", "artwork", "artwork:nighthawks:hopper", "Nighthawks"),
        mention("el_9", "person", "person:dennis_hopper", "Dennis Hopper"),
    ])
    check("A surname match without co-occurrence does not merge",
          len(apart.groups) == 2, str([g.canonical for g in apart.groups]))

    together = group_mentions([
        mention("el_1", "artwork", "artwork:nighthawks:hopper", "Nighthawks"),
        mention("el_1", "person", "person:edward_hopper", "Edward Hopper"),
    ])
    check("The same surname on the same element does merge",
          len(together.groups) == 1, str([g.canonical for g in together.groups]))

    drift = group_mentions([
        mention("el_1", "logo", "logo:coca_cola", "Coca-Cola"),
        mention("el_2", "product", "product:coca_cola", "Coke"),
        mention("el_3", "trademark", "trademark:coca_cola", "Coca-Cola"),
    ])
    check("Category drift on an identical slug still merges",
          len(drift.groups) == 1
          and drift.groups[0].canonical == "trademark:coca_cola",
          str([g.canonical for g in drift.groups]))

    # ── reconciliation against B7's answer key (report, not a gate) ────
    print()
    print("-" * 74)
    print("RECONCILIATION — mentions vs docs/ground-truth.json")
    print("-" * 74)
    if not GROUND_TRUTH.exists():
        print("  ground-truth.json not found — skipped")
    else:
        key = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
        chunk = json.loads(CHUNK.read_text(encoding="utf-8"))
        text_of = {e["id"]: e["text"]
                   for s in chunk["scenes"] for e in s["elements"]}
        quotes = [(e["id"], e["quote"], e["rating"]) for e in key["entries"]]

        rated, unrated = [], []
        for g in groups:
            for m in g.mentions:
                source = text_of.get(m["script_element_id"], "")
                hit = next((gt for gt in quotes
                            if gt[1] in source
                            and m["surface_form"] in gt[1] + source), None)
                (rated if hit else unrated).append((m, g, hit))

        print(f"  {len(rated)} of {len(mentions)} mentions sit in an element "
              f"a ground-truth entry quotes")
        print(f"  {len(unrated)} have no rating:\n")
        for m, g, _ in unrated:
            print(f"    {m['script_element_id']:<6} {m['element_type']:<14} "
                  f"{g.canonical:<32} {m['surface_form'][:30]!r}")
        print("\n  These need a rating before C6 can be scored honestly.")
        print("  An unrated mention is invisible: a pipeline inventing ten")
        print("  extra findings would score the same as one that does not.")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
