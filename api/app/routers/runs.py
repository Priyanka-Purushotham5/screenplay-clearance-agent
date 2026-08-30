"""C8 — run orchestration.

    POST /api/runs                -> 202, starts a background run
    GET  /api/runs/{id}           -> status, progress, stats
    GET  /api/runs/{id}/findings  -> the enriched findings the review UI reads

The pipeline itself is C7's `run_pipeline`. This module owns the database:
turning a persisted script back into an `ExtractionChunk`, writing rows at
stage boundaries, moving `runs.status` along, and joining `findings` back out
into something a reviewer can read.

What persistence actually has to protect
----------------------------------------
The checklist asks for a write after every stage so that "a stage-3 failure
costs stage 3 only". Tracing where the money goes:

    extract    1 model call        cheap to redo
    dedup      free, pure Python   nothing to persist
    research   ~30 calls + searches  ALREADY PERSISTED by PostgresResearchCache
    assess     3 model calls       cheap to redo

The expensive stage persists itself, entity by entity, as long as this module
hands `run_pipeline` the Postgres cache rather than the in-memory one. That is
the single most important line in this file. What remains is writing
`elements` before research starts and `findings` after assessment, which is
what the rest of it does.

A run must always end somewhere
-------------------------------
The checklist's gate is that a killed run "reports failed rather than hanging".
The first version of this module could hang, and did: it stopped at
`composing` with `error` NULL, `finished_at` NULL and nothing in the log. Three
separate things had to be true for that to be possible, and all three are now
closed:

    the run was a Starlette BackgroundTask, so uvicorn could cancel it with
    the connection that started it — and CancelledError is a BaseException,
    which `except Exception` does not catch

    the terminal status was written on the happy path rather than in a
    `finally`, so any exit that was not anticipated left the row mid-flight

    nothing configured logging, so every logger.info in the application was
    discarded and the hang produced no evidence at all

Runs are now owned by this module, every exit writes a terminal state through
`_finalise`, and a watchdog dumps live stacks at WARNING if a stage stops
moving. `verify_c8` guards all three.

Element ids
-----------
`ExtractionChunk` element ids are opaque strings. The frozen test fixture uses
`el_1`, `el_2`; here they are the real `script_elements.id` UUIDs, so the
mention the model returns maps straight back to a row with no lookup table in
between. `mention_id` then reads `{uuid}#1`, `{uuid}#2` — unlovely in a log,
but the alternative is a mapping that can drift.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from api.app.agents.cache import SessionPerCallResearchCache
from api.app.agents.schemas import (
    ChunkElement,
    ChunkScene,
    ExtractionChunk,
)
from api.app.agents.workflow import run_pipeline
from api.app.config import settings
from api.app.db import get_session
from api.app.errors import ApiError
from api.app.models import (
    Element,
    Finding,
    ResearchCache,
    Run,
    Scene,
    Script,
    ScriptElement,
)
from api.app.schemas import (
    ERROR_RESPONSES,
    FindingOut,
    FindingsOut,
    RightsHolderOut,
    RunCreateIn,
    RunOut,
    RunProgressOut,
    SourceOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])

IN_FLIGHT = {"pending", "extracting", "researching", "assessing", "composing"}

# The frontend's Finding.category union. `logo` and `product` are real
# extraction categories with no place in it, and C3 already maps them onto
# trademark for rubric routing; the same mapping applies here so the UI never
# receives a value its types do not admit.
CATEGORY_FOR_UI = {"logo": "trademark", "product": "trademark",
                   "character_name": "person"}
UI_CATEGORIES = {"music", "trademark", "artwork", "person", "location",
                 "clip", "literary", "other"}


# ---------------------------------------------------------------------------
# script -> chunk
# ---------------------------------------------------------------------------


async def chunk_from_script(session: AsyncSession, script_id: uuid.UUID) -> ExtractionChunk:
    """Rebuild the extraction input from what B6 persisted.

    This is the replacement `load_fixture` was written as a placeholder for:
    "when B6 lands, the replacement reads scenes + script_elements from
    Postgres and builds the same ExtractionChunk."
    """
    scenes = (
        await session.execute(
            select(Scene)
            .where(Scene.script_id == script_id)
            .order_by(Scene.number)
            .options(selectinload(Scene.elements))
        )
    ).scalars().all()

    return ExtractionChunk(
        chunk_id=f"script-{script_id}",
        scenes=[
            ChunkScene(
                scene_id=str(scene.id),
                number=scene.number,
                heading=scene.heading,
                elements=[
                    ChunkElement(
                        id=str(element.id),
                        type=element.type,
                        page=element.page,
                        character=element.character,
                        text=element.text,
                    )
                    for element in sorted(scene.elements, key=lambda e: e.seq)
                ],
            )
            for scene in scenes
        ],
    )


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


class PostgresPersist:
    """C7's PersistHook, backed by Postgres.

    Each method opens its own session and commits. That is deliberate: a run
    lives for minutes, and holding one transaction across all of it would mean
    a failure in assessment rolls back the elements written before research
    started — losing exactly the record the checklist asks to keep.
    """

    def __init__(self, session_factory, run_id: uuid.UUID) -> None:
        self._sessions = session_factory
        self.run_id = run_id
        self._element_ids: dict[str, uuid.UUID] = {}
        # Read by the watchdog. A stage that has not changed in minutes is the
        # only in-process signal that a run is stuck rather than slow.
        self.current_stage = "pending"
        self.stage_entered = time.monotonic()

    async def stage(self, status: str) -> None:
        async with self._sessions() as session:
            run = await session.get(Run, self.run_id)
            if run is not None:
                run.status = status
                await session.commit()
        self.current_stage = status
        self.stage_entered = time.monotonic()
        logger.info("run %s -> %s", self.run_id, status)

    async def elements(self, mentions) -> None:
        async with self._sessions() as session:
            for mention in mentions:
                row = Element(
                    run_id=self.run_id,
                    script_element_id=uuid.UUID(mention.script_element_id),
                    category=_raw_category(mention.canonical_name),
                    surface_form=mention.surface_form,
                    canonical_name=mention.canonical_name,
                    element_type=mention.element_type,
                )
                session.add(row)
                await session.flush()
                self._element_ids[mention.mention_id] = row.id
            await session.commit()
        logger.info("run %s: %d elements", self.run_id, len(self._element_ids))

    async def findings(self, rows: list[dict]) -> None:
        async with self._sessions() as session:
            for row in rows:
                element_id = self._element_ids.get(row["mention_id"])
                if element_id is None:
                    # A rating for a mention that was never written. Skipping
                    # is right — a finding with a dangling element_id would
                    # break every join the UI makes — but it must be visible,
                    # so it is logged rather than passed over.
                    logger.warning("run %s: no element row for mention %s",
                                   self.run_id, row["mention_id"])
                    continue
                session.add(Finding(
                    element_id=element_id,
                    risk=row["risk"],
                    rights_required=row["rights_required"],
                    rights_holders=[_holder(h) for h in row["rights_holders"]],
                    rationale=row["rationale"],
                    sources=row["sources"],
                    alternatives=row["alternatives"],
                ))
            await session.commit()
        logger.info("run %s: %d findings", self.run_id, len(rows))


def _raw_category(canonical_name: str) -> str:
    return canonical_name.split(":")[0] if ":" in canonical_name else "other"


def _holder(value) -> dict:
    """C5 records rights holders as free text; the UI wants role/name/confidence.

    Rather than change the dossier schema — which would invalidate a cache
    that took a night to warm — the role is lifted out of the parenthetical
    the model tends to write: "ATV Music Ltd. (for the musical composition)".
    No parenthetical means no role, which is honest; inventing one would be
    worse than leaving it blank.
    """
    if isinstance(value, dict):
        return value
    text = str(value)
    role = ""
    if "(" in text and text.rstrip().endswith(")"):
        name, _, tail = text.partition("(")
        role = tail.rstrip(")").strip()
        for prefix in ("for the ", "for "):
            if role.lower().startswith(prefix):
                role = role[len(prefix):]
        text = name.strip()
    return {"role": role, "name": text, "confidence": "medium"}


# ---------------------------------------------------------------------------
# the background run
# ---------------------------------------------------------------------------


# Runs are owned here rather than by Starlette's BackgroundTasks. A background
# task runs inside the ASGI call that spawned it, so uvicorn cancels it when
# that connection goes away — and `CancelledError` is a BaseException, so an
# `except Exception` around the run does not catch it. The observable result is
# a run that stops mid-stage with `error` NULL, `finished_at` NULL and nothing
# in the log: it does not fail, it evaporates. This pipeline runs for minutes;
# it has no business inside a request's lifetime.
#
# The set is not decoration. asyncio holds only a weak reference to a task, so
# a task nobody keeps can be garbage-collected mid-await.
_RUNS: set[asyncio.Task] = set()

# How long a single stage may sit unchanged before the run is assumed stuck and
# its stacks are dumped. Generous on purpose: a cold research fan-out at
# GEMINI_RPM=2 legitimately spends a long time in `researching`.
STALL_SECONDS = 300.0
WATCH_INTERVAL = 30.0


def _spawn_run(run_id: uuid.UUID, script_id: uuid.UUID) -> None:
    task = asyncio.create_task(_execute(run_id, script_id), name=f"run-{run_id}")
    _RUNS.add(task)
    task.add_done_callback(_RUNS.discard)


def _dump_stacks(run_id: uuid.UUID) -> None:
    """Every live coroutine's stack, at WARNING.

    WARNING deliberately: this has to be visible even when logging is
    misconfigured, which is the exact situation in which it is most needed.
    """
    for task in asyncio.all_tasks():
        if task.done():
            continue
        frames = "".join(traceback.format_stack(f) for f in task.get_stack(limit=6))
        logger.warning("run %s stalled — task %r:\n%s",
                       run_id, task.get_name(), frames or "  <no python frames>")


async def _watchdog(persist: "PostgresPersist", run_id: uuid.UUID) -> None:
    """Say where a slow run is, and shout when it stops being slow and starts
    being stuck. Cancelled by `_execute` as soon as the run ends."""
    while True:
        await asyncio.sleep(WATCH_INTERVAL)
        waited = time.monotonic() - persist.stage_entered
        logger.info("run %s still in %s (%ds)", run_id, persist.current_stage,
                    int(waited))
        if waited >= STALL_SECONDS:
            logger.warning("run %s has not left %s for %ds", run_id,
                           persist.current_stage, int(waited))
            _dump_stacks(run_id)
            persist.stage_entered = time.monotonic()  # dump once per interval


async def _finalise(sessions, run_id: uuid.UUID, status: str,
                    error: Optional[str], stats: dict) -> None:
    """Write the terminal state. The one thing that must happen on every path.

    Idempotent via `finished_at`: whoever gets here first wins, so a late
    finaliser cannot overwrite a real result with a cancellation notice.
    """
    async with sessions() as session:
        run = await session.get(Run, run_id)
        if run is None or run.finished_at is not None:
            return
        run.status = status
        run.error = error
        if stats:
            run.stats = stats
        run.finished_at = datetime.now(timezone.utc)
        await session.commit()
    logger.info("run %s finished: %s (%s)", run_id, status, error or "no error")


async def _execute(run_id: uuid.UUID, script_id: uuid.UUID) -> None:
    """The whole run. Always reaches a terminal state."""
    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    persist = PostgresPersist(sessions, run_id)
    watchdog = asyncio.create_task(_watchdog(persist, run_id),
                                   name=f"watchdog-{run_id}")

    # Pessimistic defaults. Every success path overwrites them; every failure
    # path — including the ones nobody thought of — leaves a run that says it
    # failed and why, rather than one that sits at `composing` forever.
    status, error, stats = "failed", "run did not complete", {}

    logger.info("run %s starting for script %s", run_id, script_id)
    try:
        async with sessions() as session:
            chunk = await chunk_from_script(session, script_id)

        # The Postgres cache, not the in-memory one. This single argument is
        # what makes research survive the run that paid for it — and it is the
        # session-per-call variant, because research fans out six ways and one
        # AsyncSession shared across six coroutines is a bug.
        cache = SessionPerCallResearchCache(sessions)
        outcome = await run_pipeline(chunk, cache=cache, persist=persist)

        status = "complete" if outcome.ok else "failed"
        stats = outcome.stats.as_dict() | {
            "warnings": outcome.warnings[:20],
            "stage_reached": outcome.stage_reached,
        }
        error = None if outcome.ok else (
            "; ".join(outcome.warnings[:3]) or "run did not complete")
    except asyncio.CancelledError:
        # Not an error in the run — the run was killed. Say so, then re-raise
        # so the cancellation is not swallowed; `finally` still runs first.
        error = ("the run was cancelled: the server shut down or the task was "
                 "killed mid-run")
        logger.warning("run %s cancelled in %s", run_id, persist.current_stage)
        raise
    except Exception as exc:  # noqa: BLE001 — a run must not die silently
        logger.exception("run %s failed outside the pipeline", run_id)
        error = f"{type(exc).__name__}: {exc}"
    finally:
        watchdog.cancel()
        finaliser = asyncio.ensure_future(
            _finalise(sessions, run_id, status, error, stats))
        try:
            # Shielded: if we are here because of cancellation, the write still
            # has to land. Without this the cancelled run stays non-terminal,
            # which is the failure this whole rewrite exists to remove.
            await asyncio.shield(finaliser)
        except asyncio.CancelledError:
            await asyncio.wait({finaliser}, timeout=15)
        except Exception:  # noqa: BLE001
            logger.exception("could not record the outcome of run %s", run_id)
        await engine.dispose()


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=202, response_model=RunOut, responses=ERROR_RESPONSES)
async def create_run(
    body: RunCreateIn,
    session: AsyncSession = Depends(get_session),
) -> RunOut:
    """Start a run. Returns immediately; poll GET /api/runs/{id} or stream it."""
    script = await session.get(Script, body.script_id)
    if script is None:
        raise ApiError(404, "SCRIPT_NOT_FOUND", "No script with that id.")

    existing = (
        await session.execute(
            select(Run)
            .where(Run.script_id == body.script_id, Run.status.in_(IN_FLIGHT))
            .order_by(Run.started_at.desc())
        )
    ).scalars().first()
    if existing is not None:
        # 409 rather than starting a second run: two runs over one script
        # would double the spend and write two sets of findings the UI would
        # then interleave.
        raise ApiError(409, "RUN_IN_FLIGHT",
                       "A run is already in progress for this script.",
                       run_id=str(existing.id), status=existing.status)

    run = Run(script_id=body.script_id, status="pending")
    session.add(run)
    await session.commit()

    _spawn_run(run.id, body.script_id)
    return await _run_out(session, run)


@router.get("/{run_id}", response_model=RunOut, responses=ERROR_RESPONSES)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RunOut:
    run = await session.get(Run, run_id)
    if run is None:
        raise ApiError(404, "RUN_NOT_FOUND", "No run with that id.")
    return await _run_out(session, run)


async def _run_out(session: AsyncSession, run: Run) -> RunOut:
    elements = (await session.execute(
        select(func.count()).select_from(Element).where(Element.run_id == run.id)
    )).scalar_one()
    findings = (await session.execute(
        select(func.count()).select_from(Finding)
        .join(Element, Finding.element_id == Element.id)
        .where(Element.run_id == run.id)
    )).scalar_one()
    entities = (await session.execute(
        select(func.count(func.distinct(Element.canonical_name)))
        .where(Element.run_id == run.id)
    )).scalar_one()

    stats = run.stats or {}
    dossiers = stats.get("dossiers", {})
    return RunOut(
        run_id=run.id,
        script_id=run.script_id,
        status=run.status,  # type: ignore[arg-type]
        progress=RunProgressOut(
            elements_found=elements,
            entities=entities,
            findings=findings,
            dossiers_complete=dossiers.get("complete", 0),
            dossiers_failed=dossiers.get("failed", 0),
        ),
        stats=stats,
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        error=run.error,
    )


@router.get("/{run_id}/findings", response_model=FindingsOut,
            responses=ERROR_RESPONSES)
async def get_findings(
    run_id: uuid.UUID,
    risk: Optional[str] = Query(None, description="red, amber or green"),
    review_status: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> FindingsOut:
    """Every finding, enriched enough to render without a second request.

    `counts` is over the whole run rather than the returned page. A summary
    header that changed as you paged or filtered would be reporting the view
    rather than the script.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise ApiError(404, "RUN_NOT_FOUND", "No run with that id.")

    base = (
        select(Finding, Element, ScriptElement, Scene)
        .join(Element, Finding.element_id == Element.id)
        .join(ScriptElement, Element.script_element_id == ScriptElement.id)
        .join(Scene, ScriptElement.scene_id == Scene.id)
        .where(Element.run_id == run_id)
    )
    if risk:
        base = base.where(Finding.risk == risk)
    if review_status:
        base = base.where(Finding.review_status == review_status)

    total = (await session.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()

    rows = (await session.execute(
        base.order_by(Scene.number, ScriptElement.seq, Finding.created_at)
        .limit(limit).offset(offset)
    )).all()

    # Research status per entity, one query rather than one per finding.
    names = {element.canonical_name for _, element, _, _ in rows}
    statuses: dict[str, str] = {}
    if names:
        for row in (await session.execute(
            select(ResearchCache.canonical_name, ResearchCache.status)
            .where(ResearchCache.canonical_name.in_(names))
        )).all():
            statuses[row[0]] = row[1]

    counts_rows = (await session.execute(
        select(Finding.risk, func.count())
        .join(Element, Finding.element_id == Element.id)
        .where(Element.run_id == run_id)
        .group_by(Finding.risk)
    )).all()
    counts = {"red": 0, "amber": 0, "green": 0}
    for value, n in counts_rows:
        counts[value] = n

    return FindingsOut(
        findings=[
            _finding_out(finding, element, script_element, scene,
                         statuses.get(element.canonical_name, "complete"))
            for finding, element, script_element, scene in rows
        ],
        total=total,
        counts=counts,
    )


def _finding_out(finding, element, script_element, scene, research_status) -> FindingOut:
    category = CATEGORY_FOR_UI.get(element.category, element.category)
    return FindingOut(
        id=finding.id,
        element_id=element.id,
        risk=finding.risk,
        rights_required=finding.rights_required or [],
        rights_holders=[RightsHolderOut(**_holder(h))
                        for h in (finding.rights_holders or [])],
        rationale=finding.rationale,
        sources=[
            SourceOut(
                id=str(s.get("id", "")),
                claim=s.get("claim", ""),
                url=s.get("url", ""),
                # C5's evidence has no title. The domain is more useful to a
                # reviewer than an empty string: it is the difference between
                # a registry and a forum at a glance.
                title=s.get("title") or urlparse(s.get("url", "")).netloc,
                excerpt=s.get("excerpt", ""),
            )
            for s in (finding.sources or [])
        ],
        alternatives=finding.alternatives or [],
        review_status=finding.review_status,
        override_risk=finding.override_risk,
        review_note=finding.review_note,
        reviewed_at=finding.reviewed_at.isoformat() if finding.reviewed_at else None,
        created_at=finding.created_at.isoformat(),
        canonical_name=element.canonical_name,
        surface_form=element.surface_form,
        category=category if category in UI_CATEGORIES else "other",
        research_status=research_status,
        script_element_id=script_element.id,
        char_start=element.char_start,
        char_end=element.char_end,
        scene_number=scene.number,
        page=script_element.page,
    )
