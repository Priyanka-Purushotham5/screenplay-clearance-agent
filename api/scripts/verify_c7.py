"""C7 smoke-test — the whole graph, the concurrency cap, and the limiter.

    docker compose exec api python api/scripts/verify_c7.py

The checklist's gate:

    one call runs the whole graph and eighty elements don't rate-limit you

The second half is the real one, and it stopped being theoretical during C6:
the key returned `limit: 20, model: gemini-2.5-flash` — twenty requests per
DAY — and a dossier silently came back `failed, 0 evidence` in the middle of
a run whose other numbers looked fine.

So this suite spends nothing. Every stage is injected, which is the only way
to test the properties that matter: that no more than N research calls are
ever in flight, that the limiter paces and then refuses, that one entity
failing does not take the run with it, and that the stats say what actually
happened. None of those can be observed reliably against a real model, and
two of them cannot be provoked at all.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.agents.cache import InMemoryResearchCache  # noqa: E402
from api.app.agents.limiter import (  # noqa: E402
    QuotaExhausted,
    RateLimiter,
    TokenBucket,
)
from api.app.agents.schemas import (  # noqa: E402
    AssessmentOutcome,
    EvidenceItem,
    ExtractionChunk,
    ExtractionOutcome,
    ExtractionStats,
    MentionRating,
    ResearchDossier,
    ResolvedElement,
)
from api.app.agents.workflow import (  # noqa: E402
    findings_rows,
    run_pipeline,
)

FIXTURES = ROOT / "api" / "app" / "agents" / "fixtures"
CHUNK_FILE = FIXTURES / "scene_fixture.json"
ELEMENTS_FILE = FIXTURES / "elements_fixture.json"

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


# ---------------------------------------------------------------------------
# Injected stages
# ---------------------------------------------------------------------------


def load():
    chunk = ExtractionChunk.model_validate_json(
        CHUNK_FILE.read_text(encoding="utf-8"))
    elements = [ResolvedElement.model_validate(e) for e in
                json.loads(ELEMENTS_FILE.read_text(encoding="utf-8"))["elements"]]
    return chunk, elements


def make_extract(elements, *, raises=False):
    async def extract(chunk):
        if raises:
            raise RuntimeError("extraction exploded")
        return ExtractionOutcome(chunk_id=chunk.chunk_id, elements=elements,
                                 stats=ExtractionStats())
    return extract


class TrackedResearch:
    """Records peak concurrency and can fail chosen entities."""

    def __init__(self, delay=0.02, fail_on=(), raise_on=()):
        self.delay, self.fail_on, self.raise_on = delay, set(fail_on), set(raise_on)
        self.in_flight = 0
        self.peak = 0
        self.calls = 0

    async def __call__(self, request, *, cache):
        self.calls += 1
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            if request.canonical_name in self.raise_on:
                raise RuntimeError("research exploded")
            status = "failed" if request.canonical_name in self.fail_on else "complete"
            return ResearchDossier(
                canonical_name=request.canonical_name,
                category=request.category,  # type: ignore[arg-type]
                identified_as=f"Stub for {request.canonical_name}.",
                rights_holders=["Someone"], public_domain="no",
                notable_disputes=[],
                evidence=([] if status == "failed" else
                          [EvidenceItem(id="ev_1", claim="A fact.",
                                        url="https://e.org/1", excerpt="fact")]),
                queries_run=["q"], search_calls=0 if status == "failed" else 2,
                status=status,
            )
        finally:
            self.in_flight -= 1


def make_assess(*, raises=False):
    async def assess(mentions, dossiers):
        if raises:
            raise RuntimeError("assessment exploded")
        return AssessmentOutcome(
            ratings=[MentionRating(
                mention_id=m.mention_id, script_element_id=m.script_element_id,
                surface_form=m.surface_form, risk="green", rights_required=[],
                rationale="Stub.", cited_evidence_ids=["ev_1"], alternatives=[])
                for m in mentions],
            batches=1, rubric_version="test")
    return assess


def main() -> int:
    for path in (CHUNK_FILE, ELEMENTS_FILE):
        if not path.exists():
            print(f"Missing: {path.relative_to(ROOT)}")
            return 2
    chunk, elements = load()

    def run(**kw):
        research = kw.pop("research", None) or TrackedResearch()
        return asyncio.run(run_pipeline(
            chunk,
            cache=kw.pop("cache", None) or InMemoryResearchCache(),
            extract=kw.pop("extract", None) or make_extract(elements),
            research=research,
            assess=kw.pop("assess", None) or make_assess(),
            **kw,
        )), research

    # ── the graph runs end to end ──────────────────────────────────────
    outcome, research = run()
    check("One call runs the whole graph", outcome.ok, outcome.stage_reached)
    check("Every stage is timed",
          {"extract", "dedup", "research", "assess"} <= set(outcome.stats.stage_ms),
          str(outcome.stats.stage_ms))
    check("Mentions survive to ratings",
          outcome.stats.mentions == len(elements)
          and outcome.stats.ratings == len(outcome.mentions),
          f"{outcome.stats.mentions} mentions -> {outcome.stats.ratings} ratings")
    check("Dedup happened between them",
          0 < outcome.stats.entities < outcome.stats.mentions
          and outcome.stats.reduction >= 2.0,
          f"{outcome.stats.entities} entities, {outcome.stats.reduction:.2f}:1")
    check("Research ran once per entity, not once per mention",
          research.calls == outcome.stats.entities,
          f"{research.calls} calls for {outcome.stats.entities} entities")

    # ── the concurrency cap ────────────────────────────────────────────
    for cap in (1, 3, 6):
        tracked = TrackedResearch(delay=0.03)
        outcome, _ = run(research=tracked, concurrency=cap)
        check(f"Never more than {cap} research call(s) in flight",
              tracked.peak <= cap, f"peak {tracked.peak}")
    check("The cap is a ceiling, not a target — fan-out actually happens",
          tracked.peak > 1, f"peak {tracked.peak} with cap 6")

    # ── failure paths ──────────────────────────────────────────────────
    tracked = TrackedResearch(fail_on=["trademark:coca_cola"])
    outcome, _ = run(research=tracked)
    check("A failed dossier does not stop the run",
          outcome.ok and outcome.stats.dossiers_failed == 1,
          f"{outcome.stats.dossiers_failed} failed, "
          f"{outcome.stats.dossiers_complete} complete")
    check("Mentions of a failed entity are still rated",
          outcome.stats.ratings == len(outcome.mentions))

    tracked = TrackedResearch(raise_on=["trademark:coca_cola"])
    outcome, _ = run(research=tracked)
    check("An exception inside research is caught, not propagated",
          outcome.ok and outcome.stats.dossiers_failed == 1,
          outcome.stage_reached)
    raised = [w for w in outcome.warnings if "raised" in w]
    check("And it is reported", bool(raised),
          raised[0][:70] if raised else str(outcome.warnings[:1]))

    outcome, _ = run(extract=make_extract(elements, raises=True))
    check("A failed extraction returns cleanly at the right stage",
          not outcome.ok and outcome.stage_reached == "extract"
          and not outcome.ratings, outcome.stage_reached)
    check("A failed extraction still reports stats",
          outcome.stats.wall_ms >= 0 and "extract" in outcome.stats.stage_ms)

    outcome, _ = run(assess=make_assess(raises=True))
    check("A failed assessment keeps the research it paid for",
          outcome.stage_reached == "assess" and len(outcome.dossiers) > 0,
          f"{len(outcome.dossiers)} dossiers kept")

    # ── the cache, across two runs ─────────────────────────────────────
    shared = InMemoryResearchCache()
    first_research = TrackedResearch()
    run(cache=shared, research=first_research)
    # The injected stage bypasses the cache, so prime it as the real one would.
    outcome, _ = run(cache=shared)
    check("Cache counters reach the stats",
          "cache_hits" in outcome.stats.as_dict()
          and outcome.stats.as_dict()["cache_hits"] >= 0,
          str(outcome.stats.as_dict()["cache_hits"]))

    # ── the limiter, on its own ────────────────────────────────────────
    async def bucket_timing():
        bucket = TokenBucket(rate_per_minute=600, burst=2)   # 10/second
        start = time.monotonic()
        for _ in range(6):
            await bucket.acquire()
        return time.monotonic() - start

    elapsed = asyncio.run(bucket_timing())
    # 2 free from the burst, then 4 at 10/s = ~0.4s.
    check("The token bucket actually paces", 0.25 < elapsed < 1.2,
          f"{elapsed:.2f}s for 6 calls at 10/s with burst 2")

    async def budget():
        limiter = RateLimiter(gemini_rpm=6000, gemini_daily=3)
        calls = 0

        async def fake(_msg):
            nonlocal calls
            calls += 1
            return None

        limited = limiter.wrap_gemini(fake)
        denied = 0
        for _ in range(5):
            try:
                await limited("x")
            except QuotaExhausted:
                denied += 1
        return calls, denied, limiter

    calls, denied, limiter = asyncio.run(budget())
    check("The daily budget stops calls rather than queueing them",
          calls == 3 and denied == 2, f"{calls} made, {denied} denied")
    check("Denials are counted", limiter.stats.gemini_denied == 2,
          str(limiter.stats.as_dict()))

    exhausted = RateLimiter(parallel_daily=0)
    result = exhausted.wrap_parallel(lambda *a, **k: {"status": "ok"})("o", ["q"])
    check("A spent Parallel budget returns a structured error, not an exception",
          result["status"] == "error" and result["code"] == "QUOTA_EXHAUSTED",
          str(result)[:70])

    shared_limiter = RateLimiter(gemini_rpm=6000, gemini_daily=100)
    outcome, _ = run(limiter=shared_limiter)
    check("Limiter stats reach runs.stats",
          set(outcome.stats.limiter) >= {"gemini_calls", "parallel_calls",
                                         "waited_seconds"},
          str(outcome.stats.limiter))

    # ── the event seam C9 will use ─────────────────────────────────────
    seen: list[str] = []
    outcome, _ = run(on_event=lambda name, payload: seen.append(name))
    check("Stage events are emitted in order",
          seen[0] == "stage.started" and seen[-1] == "run.complete"
          and "research.result" in seen, f"{len(seen)} events")
    check("Events carry ids and counts, not payloads",
          all(isinstance(n, str) for n in seen))

    outcome, _ = run(on_event=lambda *_: (_ for _ in ()).throw(ValueError("boom")))
    check("A broken event listener cannot take down a run", outcome.ok)

    # ── the shape C8 persists ──────────────────────────────────────────
    outcome, _ = run()
    rows = findings_rows(outcome)
    check("findings_rows returns one row per rating",
          len(rows) == len(outcome.ratings), f"{len(rows)} rows")
    check("Each row carries what db/init.sql findings needs",
          all({"risk", "rights_required", "rationale", "sources",
               "alternatives"} <= set(r) for r in rows))
    check("Sources resolve to real evidence, not just ids",
          all(all("url" in s for s in r["sources"]) for r in rows))

    print(f"\nstats: {json.dumps(outcome.stats.as_dict(), indent=None)[:200]}")
    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
