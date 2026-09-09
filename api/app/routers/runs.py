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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional, get_args
from urllib.parse import urlparse

import anyio.to_thread
from fastapi import APIRouter, Body, Depends, Query, Response
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
from api.app.report import (
    ReportFinding,
    ReportRun,
    ReportSource,
    build_report,
)
from api.app.schemas import (
    ERROR_RESPONSES,
    FindingOut,
    FindingReviewIn,
    FindingsOut,
    RightsHolderOut,
    RunCreateIn,
    RunOut,
    RunProgressOut,
    SourceOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Findings are reviewed one at a time and are addressed by their own id, not
# through the run that produced them — a reviewer works from the findings list,
# not from a run. Separate prefix, same module, because the response shape and
# every join behind it already live here.
findings_router = APIRouter(prefix="/api/findings", tags=["findings"])

IN_FLIGHT = {"pending", "extracting", "researching", "assessing", "composing"}

# The frontend's Finding.category union. `logo` and `product` are real
# extraction categories with no place in it, and C3 already maps them onto
# trademark for rubric routing; the same mapping applies here so the UI never
# receives a value its types do not admit.
CATEGORY_FOR_UI = {"logo": "trademark", "product": "trademark",
                   "character_name": "person"}

# Derived from the schema rather than restated. These two lists have to agree
# — the schema promises the frontend a union and this set is what enforces it
# — and two hand-maintained copies of the same list is how they stop agreeing.
UI_CATEGORIES = set(get_args(FindingOut.model_fields["category"].annotation))


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

    # `runs.stats` is written once, by `_finalise`, when the run is over. So
    # every number read from it is zero for the entire time somebody is
    # watching the run happen — which is exactly when they want to see it move.
    # `research_cache` is written entity by entity as research completes, so
    # counting it gives a figure that climbs during the run and is still
    # correct after it. Stats win once they exist, because they record what
    # THIS run did; the live count is the fallback while it is still running.
    researched = (await session.execute(
        select(func.count(func.distinct(ResearchCache.canonical_name)))
        .where(
            ResearchCache.canonical_name.in_(
                select(Element.canonical_name).where(Element.run_id == run.id)
            ),
            ResearchCache.status == "complete",
        )
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
            dossiers_complete=dossiers.get("complete", researched),
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

    # The research trail per entity, one query rather than one per finding.
    # Both columns come from the same row, so pulling `queries_run` alongside
    # `status` costs nothing over fetching the status alone.
    names = {element.canonical_name for _, element, _, _ in rows}
    trails: dict[str, _Trail] = {}
    if names:
        for row in (await session.execute(
            select(ResearchCache.canonical_name, ResearchCache.status,
                   ResearchCache.queries_run)
            .where(ResearchCache.canonical_name.in_(names))
        )).all():
            trails[row[0]] = _Trail(status=row[1], queries=list(row[2] or []))

    # Grouped by the EFFECTIVE risk — an override is the reviewer's answer, and
    # a header still counting the model's original rating would disagree with
    # the list underneath it the moment anyone overrode anything.
    effective_risk = func.coalesce(Finding.override_risk, Finding.risk)
    counts_rows = (await session.execute(
        select(effective_risk, func.count())
        .join(Element, Finding.element_id == Element.id)
        .where(Element.run_id == run_id)
        .group_by(effective_risk)
    )).all()
    counts = {"red": 0, "amber": 0, "green": 0}
    for value, n in counts_rows:
        counts[value] = n

    return FindingsOut(
        findings=[
            _finding_out(finding, element, script_element, scene,
                         trails.get(element.canonical_name, _NO_TRAIL))
            for finding, element, script_element, scene in rows
        ],
        total=total,
        counts=counts,
    )


@dataclass(frozen=True)
class _Trail:
    """One entity's research outcome: how it went, and what was searched for.

    A pair rather than two parallel dicts keyed by canonical name. Two dicts
    can disagree — a name present in one and missing from the other — and the
    only thing that would show it is a finding rendering a status from a
    dossier whose queries came from nowhere.
    """

    status: str
    queries: list[str]


# The fallback for an entity with no cache row at all. `complete` matches the
# behaviour this replaced: a finding exists, so research ran; a missing row
# means the dossier was served from a run whose cache has since been cleared,
# which is not the same as research having failed. The empty query list is
# honest — we genuinely do not know what was searched.
_NO_TRAIL = _Trail(status="complete", queries=[])


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@router.get(
    "/{run_id}/report",
    responses={**ERROR_RESPONSES,
               200: {"content": {"application/pdf": {}},
                     "description": "The clearance report"}},
    response_class=Response,
    summary="Download the clearance report",
)
async def get_report(
    run_id: uuid.UUID,
    format: Literal["pdf"] = Query("pdf", description="Only pdf, for now."),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """The run as the document a production actually files.

    Deliberately unpaginated: this is the whole run, and a clearance report
    that stopped at finding 500 would be worse than no report, because it
    looks complete. `get_findings` caps at 2000 for a UI that renders rows
    into the DOM; nothing here renders anything until every row is in hand.

    A run still in flight is refused rather than half-rendered. A partial
    report is indistinguishable from a finished one once it is a PDF on
    someone's desk, and this is the artefact most likely to be forwarded to
    somebody who was not watching the run.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise ApiError(404, "RUN_NOT_FOUND", "No run with that id.")
    if run.status not in ("complete", "failed"):
        raise ApiError(
            409, "RUN_IN_FLIGHT",
            f"This run is still {run.status}. A report can only be produced "
            "once the run has finished.",
        )

    script = await session.get(Script, run.script_id)
    if script is None:
        raise ApiError(404, "SCRIPT_NOT_FOUND", "The script has been deleted.")

    rows = (await session.execute(
        select(Finding, Element, ScriptElement, Scene)
        .join(Element, Finding.element_id == Element.id)
        .join(ScriptElement, Element.script_element_id == ScriptElement.id)
        .join(Scene, ScriptElement.scene_id == Scene.id)
        .where(Element.run_id == run_id)
        .order_by(Scene.number, ScriptElement.seq, Finding.created_at)
    )).all()

    names = {element.canonical_name for _, element, _, _ in rows}
    trails: dict[str, _Trail] = {}
    if names:
        for row in (await session.execute(
            select(ResearchCache.canonical_name, ResearchCache.status,
                   ResearchCache.queries_run)
            .where(ResearchCache.canonical_name.in_(names))
        )).all():
            trails[row[0]] = _Trail(status=row[1], queries=list(row[2] or []))

    findings = []
    for finding, element, script_element, scene in rows:
        trail = trails.get(element.canonical_name, _NO_TRAIL)
        category = CATEGORY_FOR_UI.get(element.category, element.category)
        findings.append(ReportFinding(
            canonical_name=element.canonical_name,
            surface_form=element.surface_form or "",
            category=category if category in UI_CATEGORIES else "other",
            risk=finding.risk,
            override_risk=finding.override_risk,
            review_status=finding.review_status,
            review_note=finding.review_note,
            scene_number=scene.number,
            page=script_element.page,
            rationale=finding.rationale or "",
            rights_required=list(finding.rights_required or []),
            # Flattened to strings here rather than in the renderer: the PDF
            # prints "Name (role)" as one line, and giving report.py the
            # dict shape would make it re-derive that from raw model output.
            rights_holders=[_holder_line(h) for h in (finding.rights_holders or [])],
            sources=[
                ReportSource(
                    title=str(s.get("title") or urlparse(str(s.get("url", ""))).netloc),
                    url=str(s.get("url", "")),
                    excerpt=str(s.get("excerpt", "")),
                )
                for s in (finding.sources or [])
            ],
            alternatives=list(finding.alternatives or []),
            research_status=trail.status,
            queries_run=trail.queries,
        ))

    report = ReportRun(
        script_title=script.title,
        page_count=script.page_count,
        scene_count=script.scene_count,
        run_id=str(run.id),
        started_at=run.started_at,
        finished_at=run.finished_at,
        rubric_version=str((run.stats or {}).get("rubric_version", "")),
        findings=findings,
    )

    # reportlab is synchronous and CPU-bound; an 80-finding report is a second
    # or so of pure Python. On the event loop that second is every other
    # request's latency, including the status polls driving the run overlay.
    # Same treatment scripts.py gives pdfplumber.
    pdf = await anyio.to_thread.run_sync(build_report, report)

    logger.info("report for run %s: %d findings, %d bytes",
                run_id, len(findings), len(pdf))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            # `inline` rather than `attachment`: a judge clicking this during
            # a demo should get the report in a browser tab, not a file in a
            # downloads folder they then have to go and find.
            "Content-Disposition":
                f'inline; filename="{_report_filename(script.title)}"',
        },
    )


def _report_filename(title: str) -> str:
    """A filename that survives every OS and every quoting rule.

    Screenplay titles contain colons, slashes and quotes; a Content-Disposition
    header containing an unescaped quote is a malformed header, and a filename
    containing a slash is a path. Anything outside a conservative set becomes
    a hyphen.
    """
    safe = "".join(c if c.isalnum() or c in " -_" else "-" for c in title).strip()
    safe = "-".join(part for part in safe.replace(" ", "-").split("-") if part)
    return f"clearance-{(safe or 'report').lower()[:60]}.pdf"


def _holder_line(holder) -> str:
    """`{name, role}` as one line, tolerating the shapes the model has produced."""
    parsed = _holder(holder)
    name = (parsed.get("name") or "").strip()
    role = (parsed.get("role") or "").strip()
    if name and role:
        return f"{name} ({role})"
    return name or role or "unknown"


def _finding_out(finding, element, script_element, scene, trail: _Trail) -> FindingOut:
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
        research_status=trail.status,
        queries_run=trail.queries,
        script_element_id=script_element.id,
        char_start=element.char_start,
        char_end=element.char_end,
        scene_number=scene.number,
        page=script_element.page,
    )


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------


@findings_router.patch("/{finding_id}", response_model=FindingOut,
                       responses=ERROR_RESPONSES, summary="Record a review verdict")
async def review_finding(
    finding_id: uuid.UUID,
    body: FindingReviewIn = Body(...),
    session: AsyncSession = Depends(get_session),
) -> FindingOut:
    """Accept, override or un-review one finding.

    The combinations are checked here rather than trusted from the client.
    `overridden` without an `override_risk` would be a row claiming the
    reviewer disagreed while not saying what with, and `accepted` carrying an
    override would be a row that agrees and disagrees at once. Both are
    representable in the database and neither means anything, so both are
    refused.

    Returns the whole enriched finding rather than an acknowledgement, so the
    list can replace one row from the response without refetching every
    finding in the run.
    """
    row = (
        await session.execute(
            select(Finding, Element, ScriptElement, Scene)
            .join(Element, Finding.element_id == Element.id)
            .join(ScriptElement, Element.script_element_id == ScriptElement.id)
            .join(Scene, ScriptElement.scene_id == Scene.id)
            .where(Finding.id == finding_id)
        )
    ).first()
    if row is None:
        raise ApiError(404, "FINDING_NOT_FOUND", "No finding with that id.")
    finding, element, script_element, scene = row

    if body.review_status == "overridden" and body.override_risk is None:
        raise ApiError(422, "OVERRIDE_RISK_REQUIRED",
                       "An overridden finding must say what it is overridden to.")
    if body.review_status == "accepted" and body.override_risk is not None:
        raise ApiError(422, "OVERRIDE_NOT_ALLOWED",
                       "An accepted finding keeps its rating; it cannot also "
                       "carry an override.")

    finding.review_status = body.review_status
    if body.review_status == "unreviewed":
        # Undo, and undo completely: a mistaken click should leave no trace.
        finding.override_risk = None
        finding.review_note = None
        finding.reviewed_at = None
    else:
        finding.override_risk = body.override_risk
        finding.review_note = body.review_note
        finding.reviewed_at = datetime.now(timezone.utc)
    await session.commit()

    # The same trail the list endpoint returns. The review response replaces a
    # row in the client's cache wholesale, so a response missing the queries
    # would blank the research trail on whichever finding was just reviewed —
    # the panel would empty out as a side effect of clicking Accept.
    trail_row = (await session.execute(
        select(ResearchCache.status, ResearchCache.queries_run)
        .where(ResearchCache.canonical_name == element.canonical_name)
    )).first()
    trail = (_Trail(status=trail_row[0], queries=list(trail_row[1] or []))
             if trail_row else _NO_TRAIL)

    logger.info("finding %s reviewed: %s%s", finding_id, body.review_status,
                f" -> {body.override_risk}" if body.override_risk else "")
    return _finding_out(finding, element, script_element, scene, trail)
