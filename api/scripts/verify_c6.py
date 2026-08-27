"""C6 smoke-test — rubric, assessment, and the score against ground truth.

    docker compose exec api python api/scripts/verify_c6.py
    docker compose exec api python api/scripts/verify_c6.py --live

The checklist's gate:

    the test script scores clean against ground truth, and your planted
    same-song-two-contexts pair rates RED and GREEN respectively

Two different things are being tested and it is worth keeping them apart.

**The scorer.** Everything B7 built exists so a rating can be graded. If the
scorer is wrong, every number after it is decoration. So it is tested first,
and tested the only way a scorer can be: feed it a perfect answer sheet and
require a perfect score, then feed it a deliberately broken one and require
it to notice. A scorer that has only ever seen good input has not been tested.

**The assessment loop.** Batching, sibling mentions, citation validation and
the retry, a model error mid-run, and mentions the model silently drops. All
driven by a scripted model, because a real one cannot be made to invent an
evidence id on demand.

--live is the actual gate: research two entities for real, rate their
mentions with Pro, and score. Costs a handful of searches and a few model
calls.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.agents import rubric as rubric_mod  # noqa: E402
from api.app.agents.assess import (  # noqa: E402
    MentionToRate,
    _batch_message,
    assess_mentions,
    mentions_from_groups,
)
from api.app.agents.canonical import group_mentions  # noqa: E402
from api.app.agents.schemas import (  # noqa: E402
    AssessmentBatch,
    EvidenceItem,
    MentionRating,
    ResearchDossier,
)

FIXTURES = ROOT / "api" / "app" / "agents" / "fixtures"
ELEMENTS = FIXTURES / "elements_fixture.json"
CHUNK = FIXTURES / "scene_fixture.json"
GROUND_TRUTH = ROOT / "docs" / "ground-truth.json"

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


# ---------------------------------------------------------------------------
# The scorer
# ---------------------------------------------------------------------------

ORDER = {"green": 0, "amber": 1, "red": 2}


@dataclass
class ScoreReport:
    exact: int = 0
    adjacent: int = 0
    inverted: int = 0
    missed_reds: list[str] = None      # ground truth red, we said otherwise
    false_reds: list[str] = None       # ground truth green, we said red
    unmapped: list[str] = None         # no ground-truth entry found
    sets: dict = None

    def __post_init__(self):
        self.missed_reds = self.missed_reds or []
        self.false_reds = self.false_reds or []
        self.unmapped = self.unmapped or []
        self.sets = self.sets or {}

    @property
    def graded(self) -> int:
        return self.exact + self.adjacent + self.inverted

    def summary(self) -> str:
        return (f"{self.exact} exact, {self.adjacent} adjacent, "
                f"{self.inverted} inverted of {self.graded}; "
                f"{len(self.missed_reds)} missed red, "
                f"{len(self.false_reds)} false red, "
                f"{len(self.unmapped)} unmapped")


def _slug(canonical: str) -> str:
    parts = canonical.split(":")
    return parts[1] if len(parts) > 1 else canonical


def _entry_for(mention, key, text_of):
    """The ground-truth entry that covers this mention.

    Matched on the element first (the entry's quote appears in that element's
    text), then narrowed by CATEGORY. The element alone is not enough: el_23
    names both Coca-Cola and Pepsi and carries a separate entry for each, and
    grading one against the other would be quietly wrong in both directions.

    Category rather than canonical slug, because slugs are model output and
    drift structurally: gt_13 records the Hamlet quote as
    `literary:hamlet:shakespeare` while extraction produced
    `literary:to_be_or_not_to_be:hamlet`. Those share no leading token, so a
    slug-prefix rule dropped the mention entirely and reported it as unmapped
    — a mention that silently leaves the score is exactly the failure the
    score exists to prevent. Slug overlap is still used to break ties inside a
    category, which is what separates the two trademarks on el_23.

    Falls back to `must_not_flag`, treated as an expected green. Without that,
    a pipeline that rated Shakespeare RED as a living person would not be
    penalised — it would simply not be graded.
    """
    source = text_of.get(mention.script_element_id, "")
    category = mention.canonical_name.split(":")[0]
    want = _slug(mention.canonical_name).split("_")

    candidates = [e for e in key["entries"]
                  if e["quote"] in source and e["category"] == category]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        scored = []
        for entry in candidates:
            have = _slug(entry["canonical"]).split("_")
            overlap = len(set(want) & set(have))
            scored.append((overlap, len(entry["quote"]), entry))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return scored[0][2]

    for i, rule in enumerate(key.get("must_not_flag", []), start=1):
        if rule["quote"] in source and mention.surface_form in rule["quote"]:
            return {"id": f"mnf_{i}", "rating": "GREEN", "quote": rule["quote"],
                    "category": category, "canonical": mention.canonical_name}
    return None


def score(ratings, mentions, key, text_of) -> ScoreReport:
    report = ScoreReport()
    by_key = {m.key: m for m in mentions}
    entry_risk: dict[str, list[str]] = {}

    for rating in ratings:
        mention = by_key.get(rating.mention_id)
        if mention is None:
            report.unmapped.append(rating.mention_id)
            continue
        entry = _entry_for(mention, key, text_of)
        if entry is None:
            report.unmapped.append(f"{mention.mention_id} {mention.surface_form!r}")
            continue

        expected = entry["rating"].lower()
        got = rating.risk.lower()
        entry_risk.setdefault(entry["id"], []).append(got)

        distance = abs(ORDER[expected] - ORDER[got])
        if distance == 0:
            report.exact += 1
        elif distance == 1:
            report.adjacent += 1
        else:
            report.inverted += 1

        label = f"{entry['id']} {mention.mention_id} {mention.surface_form!r}"
        if expected == "red" and got != "red":
            report.missed_reds.append(f"{label}: expected red, got {got}")
        if expected == "green" and got == "red":
            report.false_reds.append(f"{label}: expected green, got red")

    # Set discrimination: rated independently of per-item accuracy, because a
    # system can score respectably while giving every mention of one entity the
    # same rating — which is the signature of matching on names rather than
    # reading context.
    for name, spec in key["discrimination_sets"].items():
        got = {r for member in spec["members"] for r in entry_risk.get(member, [])}
        want = {r.lower() for r in spec["ratings"]}
        report.sets[name] = {"want": sorted(want), "got": sorted(got),
                             "pass": got == want}
    return report


# ---------------------------------------------------------------------------
# Scripted model
# ---------------------------------------------------------------------------


class ScriptedAssessor:
    """Rates from a lookup table, or misbehaves on cue."""

    def __init__(self, answers=None, *, invent_ids=False, raises_on=None,
                 drop_last=False):
        self.answers = answers or {}
        self.invent_ids = invent_ids
        self.raises_on = raises_on
        self.drop_last = drop_last
        self.messages: list[str] = []

    async def __call__(self, message: str) -> AssessmentBatch:
        self.messages.append(message)
        if self.raises_on is not None and len(self.messages) == self.raises_on:
            raise RuntimeError("assessor exploded")
        payload = json.loads(message)
        items = payload["mentions"]
        if self.drop_last:
            items = items[:-1]
        ratings = []
        for item in items:
            risk = self.answers.get(item["mention_id"], "green")
            cited = ["ev_999"] if self.invent_ids else [
                e["id"] for e in item["dossier"].get("evidence", [])[:1]]
            ratings.append(MentionRating(
                mention_id=item["mention_id"],
                script_element_id=item["script_element_id"],
                surface_form=item["surface_form"],
                risk=risk,
                rights_required=[] if risk == "green" else ["a licence"],
                rationale="Scripted.",
                cited_evidence_ids=cited,
                alternatives=[],
            ))
        return AssessmentBatch(ratings=ratings)


def stub_dossier(canonical: str, category: str) -> ResearchDossier:
    return ResearchDossier(
        canonical_name=canonical, category=category,
        identified_as=f"Stub for {canonical}.",
        rights_holders=["Someone"], public_domain="no", notable_disputes=[],
        evidence=[EvidenceItem(id="ev_1", claim="A fact.",
                               url="https://example.org/1", excerpt="fact")],
        queries_run=[], search_calls=1, status="complete",
    )


def main() -> int:
    for path in (ELEMENTS, CHUNK, GROUND_TRUTH):
        if not path.exists():
            print(f"Missing: {path.relative_to(ROOT)}")
            return 2

    key = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    chunk = json.loads(CHUNK.read_text(encoding="utf-8"))
    text_of = {e["id"]: e["text"] for s in chunk["scenes"] for e in s["elements"]}
    scene_of = {e["id"]: s["number"] for s in chunk["scenes"] for e in s["elements"]}

    elements = json.loads(ELEMENTS.read_text(encoding="utf-8"))["elements"]
    grouped = group_mentions(elements)
    mentions = mentions_from_groups(grouped.groups, text_of, scene_of)
    dossiers = {g.canonical: stub_dossier(g.canonical, g.rubric_category)
                for g in grouped.groups}

    print(f"{len(mentions)} mentions across {len(grouped.groups)} entities, "
          f"{len(key['entries'])} ground-truth entries\n")

    # ── the rubric ─────────────────────────────────────────────────────
    text = rubric_mod.ASSESSMENT_INSTRUCTION
    check("Rubric has no curly braces (ADK template trap)",
          "{" not in text and "}" not in text)
    check("The rubric is versioned", bool(rubric_mod.RUBRIC_VERSION))
    check("The decisive rule names element_type",
          "action line" in text.lower() and "dialogue" in text.lower())
    check("The rule states its exception",
          "currently being depicted" in text.lower())
    for category in ("music", "trademark", "artwork", "person", "location",
                     "literary", "clip"):
        pass
    missing = [c for c in ("music", "trademark", "artwork", "person",
                           "location", "literary", "clip")
               if f"**{c}**" not in text]
    check("Every rubric category has criteria", not missing, str(missing))
    check("Ratings are lowercase, matching findings.risk",
          "`red`" in text and "RED" not in text.replace("REDUC", ""))

    # ── every mention can be graded ────────────────────────────────────
    unmapped = [f"{m.mention_id} {m.surface_form!r}"
                for m in mentions if _entry_for(m, key, text_of) is None]
    check("Every mention maps to a ground-truth entry", not unmapped,
          str(unmapped[:4]))

    # ── the scorer, on a perfect answer sheet ──────────────────────────
    perfect = {}
    for m in mentions:
        entry = _entry_for(m, key, text_of)
        if entry:
            perfect[m.mention_id] = entry["rating"].lower()

    outcome = asyncio.run(assess_mentions(
        mentions, dossiers, call_model=ScriptedAssessor(perfect)))
    report = score(outcome.ratings, mentions, key, text_of)
    check("A perfect answer sheet scores perfectly",
          report.exact == report.graded and report.graded == len(mentions),
          report.summary())
    check("No missed reds on a perfect sheet", not report.missed_reds)
    check("All discrimination sets pass on a perfect sheet",
          all(s["pass"] for s in report.sets.values()),
          str({k: v["pass"] for k, v in report.sets.items()}))

    # ── the scorer, on a broken one ────────────────────────────────────
    broken = asyncio.run(assess_mentions(
        mentions, dossiers, call_model=ScriptedAssessor({})))  # everything green
    bad = score(broken.ratings, mentions, key, text_of)
    check("Rating everything green is caught as missed reds",
          len(bad.missed_reds) >= 3, f"{len(bad.missed_reds)} missed")
    check("Rating everything green is caught as inversions",
          bad.inverted >= 3, f"{bad.inverted} inverted")
    check("Rating everything green fails every discrimination set",
          not any(s["pass"] for s in bad.sets.values()),
          str({k: v["pass"] for k, v in bad.sets.items()}))

    # ── the batch message ──────────────────────────────────────────────
    message = _batch_message(mentions[:3], mentions, dossiers)
    payload = json.loads(message)
    check("The batch message carries the rubric version",
          payload["rubric_version"] == rubric_mod.RUBRIC_VERSION)
    check("Each mention carries its siblings, so the exception is decidable",
          any(m["other_mentions_of_this_entity"] for m in payload["mentions"]),
          str([len(m["other_mentions_of_this_entity"]) for m in payload["mentions"]]))
    check("Each mention carries its dossier evidence",
          all("evidence" in m["dossier"] for m in payload["mentions"]))

    # ── batching ───────────────────────────────────────────────────────
    batched = ScriptedAssessor(perfect)
    outcome = asyncio.run(assess_mentions(mentions, dossiers,
                                          call_model=batched, batch_size=10))
    check("Mentions are batched, not sent one at a time",
          outcome.batches == -(-len(mentions) // 10) == len(batched.messages),
          f"{outcome.batches} batches for {len(mentions)} mentions")
    check("Every mention comes back rated",
          len(outcome.ratings) == len(mentions) and not outcome.unrated,
          f"{len(outcome.ratings)} ratings")

    # ── citation validation ────────────────────────────────────────────
    liar = ScriptedAssessor(perfect, invent_ids=True)
    outcome = asyncio.run(assess_mentions(mentions[:5], dossiers, call_model=liar))
    check("An invented evidence id triggers a retry",
          len(liar.messages) == 2, f"{len(liar.messages)} calls")
    check("The retry names the invented ids",
          "ev_999" in liar.messages[1] and "correction" in liar.messages[1])
    check("Invented ids are stripped, not silently kept",
          all(not r.cited_evidence_ids for r in outcome.ratings)
          and outcome.invalid_citations == 5,
          f"invalid_citations={outcome.invalid_citations}")
    check("The outcome warns about it",
          any("invented" in w for w in outcome.warnings), str(outcome.warnings))

    honest = ScriptedAssessor(perfect)
    outcome = asyncio.run(assess_mentions(mentions[:5], dossiers, call_model=honest))
    check("A clean batch is not retried", len(honest.messages) == 1)
    check("Real citations survive validation",
          all(r.cited_evidence_ids == ["ev_1"] for r in outcome.ratings))

    # ── failure paths ──────────────────────────────────────────────────
    outcome = asyncio.run(assess_mentions(
        mentions, dossiers, call_model=ScriptedAssessor(perfect, raises_on=1),
        batch_size=10))
    check("A failed batch does not lose the other batches",
          len(outcome.ratings) == len(mentions) - 10, f"{len(outcome.ratings)} ratings")
    check("A failed batch is reported",
          any("failed" in w for w in outcome.warnings), str(outcome.warnings[:1]))

    outcome = asyncio.run(assess_mentions(
        mentions[:5], dossiers, call_model=ScriptedAssessor(perfect, drop_last=True)))
    check("A silently dropped mention is reported, not treated as green",
          len(outcome.unrated) == 1 and any("no rating" in w for w in outcome.warnings),
          str(outcome.unrated))

    # ── optional live run ──────────────────────────────────────────────
    if "--live" in sys.argv:
        from api.app.agents.cache import InMemoryResearchCache
        from api.app.agents.research import ResearchRequest, research_entity

        set_entries = {m for s in ("A", "B")
                       for m in key["discrimination_sets"][s]["members"]}
        wanted = [m for m in mentions
                  if (e := _entry_for(m, key, text_of)) and e["id"] in set_entries]
        entities = sorted({m.canonical_name for m in wanted})
        print(f"\n--- live: researching {len(entities)} entities, "
              f"rating {len(wanted)} mentions ---")

        cache = InMemoryResearchCache()
        live_dossiers = {}
        for group in grouped.groups:
            if group.canonical not in entities:
                continue
            request = ResearchRequest.from_group(group, text_of)
            live_dossiers[group.canonical] = asyncio.run(
                research_entity(request, cache=cache))
            d = live_dossiers[group.canonical]
            print(f"  {group.canonical}: {d.status}, {len(d.evidence)} evidence, "
                  f"{d.search_calls} searches")

        outcome = asyncio.run(assess_mentions(wanted, live_dossiers))
        report = score(outcome.ratings, wanted, key, text_of)
        print(f"\n  {report.summary()}")
        for name, s in sorted(report.sets.items()):
            print(f"  set {name}: want {s['want']} got {s['got']} "
                  f"{'PASS' if s['pass'] else 'FAIL'}")
        print()
        for r in outcome.ratings:
            print(f"  {r.risk:<6} {r.mention_id:<9} {r.surface_form[:26]!r:<30}"
                  f" {r.rationale[:60]}")

        check("Live assessment rated every mention",
              len(outcome.ratings) == len(wanted) and not outcome.unrated,
              f"{len(outcome.ratings)}/{len(wanted)}")
        check("Live assessment invented no citations",
              outcome.invalid_citations == 0, str(outcome.invalid_citations))
        check("Zero missed reds", not report.missed_reds,
              "; ".join(report.missed_reds))
        check("Discrimination sets A and B both pass",
              all(report.sets[s]["pass"] for s in ("A", "B")),
              str({k: v["got"] for k, v in report.sets.items() if k in "AB"}))

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
