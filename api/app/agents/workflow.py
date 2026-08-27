"""C7 — the whole graph, in one call.

    extract -> group -> research (fan-out) -> assess -> compose

Not an ADK `SequentialAgent`. The stages are not ADK agents: C3 is pure
Python, C5 and C6 are loops that call ADK inside. Wrapping them so a
framework could sequence them would trade working code for ceremony, and it
would give away the two things this module exists to enforce — a concurrency
cap and a shared rate limit — for the same reason C5's loop is written out by
hand.

The fan-out
-----------
Research is the only stage with anything to parallelise: twelve independent
entities, each spending most of its time waiting on a network. It runs under
a semaphore capped at `concurrency`, defaulting to six.

But the semaphore is not what keeps you inside quota — the limiter is. They
solve different problems and both are needed. Six concurrent workers each
making three sequential calls still make thirty-six calls; concurrency
governs how many are in flight, the limiter governs how fast they arrive and
how many there may be in total.

Failure
-------
Nothing raises. Every stage is caught, recorded in `warnings`, and the run
continues with whatever it has. An entity that fails research still gets
rated — against a dossier marked `failed`, which the rubric tells the model
to treat conservatively and say so. That path is not hypothetical: it is what
happened on the C6 live run when the daily quota ran out mid-fan-out, and the
ratings around it stayed sane.

`stats` is the honest record: what ran, what it cost, what was cached, and
what went wrong. C8 writes it to `runs.stats`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Sequence

from api.app.agents.assess import (
    MentionToRate,
    assess_mentions,
    mentions_from_groups,
)
from api.app.agents.cache import ResearchCacheProtocol
from api.app.agents.canonical import group_mentions
from api.app.agents.limiter import QuotaExhausted, RateLimiter
from api.app.agents.rubric import RUBRIC_VERSION
from api.app.agents.schemas import (
    ExtractionChunk,
    MentionRating,
    ResearchDossier,
)

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 6


@dataclass
class PipelineStats:
    mentions: int = 0
    entities: int = 0
    ratings: int = 0
    reduction: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    dossiers_complete: int = 0
    dossiers_partial: int = 0
    dossiers_failed: int = 0
    invalid_citations: int = 0
    search_calls: int = 0
    stage_ms: dict = field(default_factory=dict)
    limiter: dict = field(default_factory=dict)
    rubric_version: str = RUBRIC_VERSION
    wall_ms: int = 0

    def as_dict(self) -> dict:
        return {
            "mentions": self.mentions,
            "entities": self.entities,
            "ratings": self.ratings,
            "reduction": round(self.reduction, 2),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "dossiers": {
                "complete": self.dossiers_complete,
                "partial": self.dossiers_partial,
                "failed": self.dossiers_failed,
            },
            "invalid_citations": self.invalid_citations,
            "search_calls": self.search_calls,
            "stage_ms": self.stage_ms,
            "limiter": self.limiter,
            "rubric_version": self.rubric_version,
            "wall_ms": self.wall_ms,
        }


@dataclass
class PipelineOutcome:
    ratings: list[MentionRating] = field(default_factory=list)
    mentions: list[MentionToRate] = field(default_factory=list)
    dossiers: dict[str, ResearchDossier] = field(default_factory=dict)
    stats: PipelineStats = field(default_factory=PipelineStats)
    warnings: list[str] = field(default_factory=list)
    stage_reached: str = "start"

    @property
    def ok(self) -> bool:
        return bool(self.ratings) and self.stage_reached == "complete"


class _Timer:
    def __init__(self, stats: PipelineStats, name: str):
        self.stats, self.name = stats, name

    def __enter__(self):
        self._t = time.monotonic()
        return self

    def __exit__(self, *_):
        self.stats.stage_ms[self.name] = int((time.monotonic() - self._t) * 1000)


async def run_pipeline(
    chunk: ExtractionChunk,
    *,
    cache: ResearchCacheProtocol,
    limiter: Optional[RateLimiter] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    extract: Optional[Callable[[ExtractionChunk], Awaitable]] = None,
    research: Optional[Callable[..., Awaitable[ResearchDossier]]] = None,
    assess: Optional[Callable[..., Awaitable]] = None,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> PipelineOutcome:
    """Run the whole graph over one chunk. Never raises.

    Every stage is injectable so the graph can be tested without a model —
    the concurrency cap, the limiter and the failure paths are properties of
    this function, not of the stages it calls.

    `on_event` is the seam C9's event bus plugs into. It is called
    synchronously with (name, payload) and any exception it raises is
    swallowed: a broken progress listener must not take down a run.
    """
    started = time.monotonic()
    outcome = PipelineOutcome()
    stats = outcome.stats
    limiter = limiter or RateLimiter()

    def emit(name: str, payload: dict) -> None:
        if on_event is None:
            return
        try:
            on_event(name, payload)
        except Exception as exc:  # noqa: BLE001
            # One line, no traceback. A listener that raises on every event
            # would otherwise bury the run's own output in stack traces, and
            # the listener's failure is not the run's problem.
            logger.warning("event listener raised on %s: %s: %s",
                           name, type(exc).__name__, exc)

    # Wire the limiter into the real call sites. Injected stages are left
    # alone: a test supplying its own stage is not making network calls.
    if extract is None or research is None or assess is None:
        from api.app.agents.extract import extract_chunk
        from api.app.agents.research import _call_model_adk as research_model
        from api.app.agents.assess import _call_model_adk as assess_model
        from api.app.agents.tools import web_search

        limited_research_model = limiter.wrap_gemini(research_model)
        limited_assess_model = limiter.wrap_gemini(assess_model)
        limited_search = limiter.wrap_parallel(web_search)

    text_of = {e.id: e.text for s in chunk.scenes for e in s.elements}
    scene_of = {e.id: s.number for s in chunk.scenes for e in s.elements}

    # ── 1. extract ─────────────────────────────────────────────────────
    emit("stage.started", {"stage": "extract"})
    with _Timer(stats, "extract"):
        try:
            if extract is not None:
                extraction = await extract(chunk)
            else:
                extraction = await extract_chunk(chunk)
        except Exception as exc:  # noqa: BLE001
            outcome.warnings.append(f"extract failed: {type(exc).__name__}: {exc}")
            logger.warning("extraction failed", exc_info=True)
            stats.wall_ms = int((time.monotonic() - started) * 1000)
            stats.limiter = limiter.stats.as_dict()
            outcome.stage_reached = "extract"
            return outcome

    elements = [e.model_dump(mode="json") for e in extraction.elements]
    stats.mentions = len(elements)
    emit("stage.completed", {"stage": "extract", "mentions": len(elements)})

    # ── 2. group (C3) ──────────────────────────────────────────────────
    emit("stage.started", {"stage": "dedup"})
    with _Timer(stats, "dedup"):
        grouped = group_mentions(elements)
    stats.entities = len(grouped.groups)
    stats.reduction = grouped.reduction
    outcome.warnings.extend(grouped.warnings)
    outcome.mentions = mentions_from_groups(grouped.groups, text_of, scene_of)
    emit("stage.completed", {"stage": "dedup", "entities": stats.entities,
                             "reduction": round(stats.reduction, 2)})

    # ── 3. research, fanned out under a cap ────────────────────────────
    emit("stage.started", {"stage": "research", "entities": stats.entities})
    semaphore = asyncio.Semaphore(max(1, concurrency))
    dossiers: dict[str, ResearchDossier] = {}

    async def research_one(group) -> None:
        from api.app.agents.research import ResearchRequest, research_entity

        request = ResearchRequest.from_group(group, text_of)
        async with semaphore:
            try:
                if research is not None:
                    dossier = await research(request, cache=cache)
                else:
                    dossier = await research_entity(
                        request, cache=cache,
                        call_model=limited_research_model,
                        search=limited_search,
                    )
            except QuotaExhausted as exc:
                # The budget, not a transient failure. Record it and let the
                # remaining entities discover the same thing cheaply.
                outcome.warnings.append(f"{group.canonical}: {exc}")
                dossier = ResearchDossier(
                    canonical_name=group.canonical,
                    category=group.rubric_category,  # type: ignore[arg-type]
                    identified_as=f"Not researched: {exc}",
                    rights_holders=[], public_domain="unknown",
                    notable_disputes=[], evidence=[], queries_run=[],
                    search_calls=0, status="failed",
                )
            except Exception as exc:  # noqa: BLE001
                outcome.warnings.append(
                    f"{group.canonical}: research raised "
                    f"{type(exc).__name__}: {exc}")
                logger.warning("research raised for %s", group.canonical,
                               exc_info=True)
                dossier = ResearchDossier(
                    canonical_name=group.canonical,
                    category=group.rubric_category,  # type: ignore[arg-type]
                    identified_as=f"Research raised {type(exc).__name__}.",
                    rights_holders=[], public_domain="unknown",
                    notable_disputes=[], evidence=[], queries_run=[],
                    search_calls=0, status="failed",
                )
        dossiers[group.canonical] = dossier
        emit("research.result", {"entity": group.canonical,
                                 "status": dossier.status,
                                 "evidence": len(dossier.evidence)})

    with _Timer(stats, "research"):
        await asyncio.gather(*(research_one(g) for g in grouped.groups))

    outcome.dossiers = dossiers
    for dossier in dossiers.values():
        stats.search_calls += dossier.search_calls
        if dossier.status == "complete":
            stats.dossiers_complete += 1
        elif dossier.status == "partial":
            stats.dossiers_partial += 1
        else:
            stats.dossiers_failed += 1
    stats.cache_hits = getattr(cache, "hits", 0)
    stats.cache_misses = getattr(cache, "misses", 0)
    emit("stage.completed", {"stage": "research",
                             "complete": stats.dossiers_complete,
                             "failed": stats.dossiers_failed})

    # ── 4. assess ──────────────────────────────────────────────────────
    emit("stage.started", {"stage": "assess", "mentions": len(outcome.mentions)})
    with _Timer(stats, "assess"):
        try:
            if assess is not None:
                assessment = await assess(outcome.mentions, dossiers)
            else:
                assessment = await assess_mentions(
                    outcome.mentions, dossiers,
                    call_model=limited_assess_model)
        except Exception as exc:  # noqa: BLE001
            outcome.warnings.append(f"assess failed: {type(exc).__name__}: {exc}")
            logger.warning("assessment failed", exc_info=True)
            stats.wall_ms = int((time.monotonic() - started) * 1000)
            stats.limiter = limiter.stats.as_dict()
            outcome.stage_reached = "assess"
            return outcome

    outcome.ratings = list(assessment.ratings)
    outcome.warnings.extend(assessment.warnings)
    stats.ratings = len(outcome.ratings)
    stats.invalid_citations = assessment.invalid_citations
    emit("stage.completed", {"stage": "assess", "ratings": stats.ratings})

    # ── 5. compose ─────────────────────────────────────────────────────
    stats.wall_ms = int((time.monotonic() - started) * 1000)
    stats.limiter = limiter.stats.as_dict()
    outcome.stage_reached = "complete"
    emit("run.complete", stats.as_dict())
    logger.info("pipeline complete: %s | %s",
                stats.as_dict(), limiter.budget_report())
    return outcome


def findings_rows(outcome: PipelineOutcome) -> list[dict]:
    """Flatten to `findings`-shaped dicts, ready for C8 to persist.

    One row per mention, matching db/init.sql. The join back to `elements`
    happens in C8, which owns the run and its ids; this stays free of the
    database so the graph can be tested without one.
    """
    by_id = {m.mention_id: m for m in outcome.mentions}
    rows = []
    for rating in outcome.ratings:
        mention = by_id.get(rating.mention_id)
        rows.append({
            "mention_id": rating.mention_id,
            "script_element_id": rating.script_element_id,
            "canonical_name": mention.canonical_name if mention else "",
            "risk": rating.risk,
            "rights_required": rating.rights_required,
            "rights_holders": (
                outcome.dossiers[mention.canonical_name].rights_holders
                if mention and mention.canonical_name in outcome.dossiers else []
            ),
            "rationale": rating.rationale,
            "sources": [
                {"id": e.id, "url": e.url, "claim": e.claim}
                for e in (outcome.dossiers[mention.canonical_name].evidence
                          if mention and mention.canonical_name in outcome.dossiers
                          else [])
                if e.id in rating.cited_evidence_ids
            ],
            "alternatives": rating.alternatives,
        })
    return rows
