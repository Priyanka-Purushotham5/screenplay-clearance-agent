"""C5 — the research agent.

One dossier per entity. C3 groups thirty mentions into twelve entities, and
this runs once per entity; C6 then rates every mention against the dossier its
entity produced.

Why the loop is written out rather than left to the agent
--------------------------------------------------------
An ADK agent given the search tool would loop on its own, and two of this
stage's three hard requirements would be unenforceable.

*The budget.* Six search calls is a cap, not a suggestion. Asking a model to
count its own calls works until the run where it does not, and that run costs
real money across every entity at once.

*Discarding the payload.* This is the one that matters. Tool results
accumulate in an agent's session, so by turn six the context carries turns one
through five — five searches' worth of raw pages, which C4 measured at ~6.4k
tokens each. Here, only the LATEST search results are put in front of the
model. Everything earlier survives as the compressed evidence the model itself
wrote. That is the difference between a sixth turn that costs 2k tokens and
one that costs 40k.

The model call sits behind `call_model` so the control flow can be tested
without spending anything: the budget, the accumulation, the discard and every
failure path are exercised in verify_c5 against a scripted model.

Failure is never an exception
-----------------------------
Twelve entities are researched per script. A Parallel outage or a model error
on entity seven marks entity seven `partial` or `failed` and lets eight
through twelve finish. `status` is the honest record of what happened, and C6
reads it: a `failed` dossier should produce a finding that says the research
did not complete, not a confident rating drawn from nothing.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Sequence

from api.app.agents.cache import ResearchCacheProtocol, cache_keys
from api.app.agents.prompts import RESEARCH_INSTRUCTION, RESEARCH_PROMPT_VERSION
from api.app.agents.schemas import EvidenceItem, ResearchDossier, ResearchTurn
from api.app.agents.tools import web_search
from api.app.config import settings

logger = logging.getLogger(__name__)

MAX_SEARCH_CALLS = 6

# How much of a screenplay line to show as context. Enough to disambiguate two
# real things that share a name, short enough that twelve of them do not
# become a prompt of their own.
CONTEXT_CHARS = 240

APP_NAME = "clearance-research"
USER_ID = "system"


@dataclass(frozen=True)
class ResearchRequest:
    """What one entity looks like to this stage.

    Deliberately not C3's `EntityGroup`: research needs the entity's identity
    and the words around it, not the mention records, and keeping the boundary
    narrow means C3 can change its internals without touching this.
    """

    canonical_name: str
    category: str
    surface_key: str = ""
    surface_forms: tuple[str, ...] = ()
    contexts: tuple[str, ...] = ()

    @classmethod
    def from_group(cls, group, text_of: dict[str, str]) -> "ResearchRequest":
        """Build from a C3 EntityGroup plus element id -> element text."""
        forms = tuple(dict.fromkeys(m["surface_form"] for m in group.mentions))
        contexts = tuple(
            dict.fromkeys(
                text_of[m["script_element_id"]][:CONTEXT_CHARS]
                for m in group.mentions
                if m["script_element_id"] in text_of
            )
        )
        return cls(
            canonical_name=group.canonical,
            category=group.rubric_category,
            surface_key=getattr(group, "surface_key", ""),
            surface_forms=forms,
            contexts=contexts,
        )


def _objective(request: ResearchRequest) -> str:
    """The steering sentence handed to Parallel with every query."""
    subject = request.surface_forms[0] if request.surface_forms else request.canonical_name
    return (
        f"Who owns or controls the rights to {subject} "
        f"({request.category}), and is it in the public domain?"
    )


def _turn_message(
    request: ResearchRequest,
    evidence: Sequence[EvidenceItem],
    latest_results: Optional[dict],
    searches_left: int,
) -> str:
    """The whole of what the model sees on one pass.

    Note what is NOT here: any earlier search's results. Evidence carries them
    forward in the model's own words, which is the entire economy of this loop.
    """
    payload = {
        "canonical_name": request.canonical_name,
        "category": request.category,
        "referred_to_in_screenplay_as": list(request.surface_forms),
        "screenplay_context": list(request.contexts),
        "evidence_so_far": [e.model_dump() for e in evidence],
        "searches_remaining": searches_left,
    }
    if latest_results is not None:
        payload["latest_search"] = latest_results
    return json.dumps(payload, ensure_ascii=False)


async def _call_model_adk(message: str) -> ResearchTurn:
    """One pass through Flash, structured output, no tools.

    No tools on purpose: searching is orchestrated here, so the model's only
    job is to read results and decide. A fresh session per call, like C1 —
    nothing carries between passes except what this module chooses to pass.
    """
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from api.app.agents.extract import _assert_credentials

    _assert_credentials()

    agent = LlmAgent(
        name="research",
        model=settings.extraction_model,
        description="Establishes the factual rights position of one entity.",
        instruction=RESEARCH_INSTRUCTION,
        output_schema=ResearchTurn,
        output_key="research_turn",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session_id = f"research-{uuid.uuid4().hex[:12]}"
    await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )

    text = ""
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    text = part.text
    return ResearchTurn.model_validate_json(text)


async def research_entity(
    request: ResearchRequest,
    *,
    cache: ResearchCacheProtocol,
    call_model: Optional[Callable[[str], Awaitable[ResearchTurn]]] = None,
    search: Callable[..., dict] = web_search,
    max_search_calls: int = MAX_SEARCH_CALLS,
) -> ResearchDossier:
    """Research one entity. Never raises."""
    started = time.monotonic()
    keys = cache_keys(request.canonical_name, request.surface_key)

    cached = await cache.get(keys)
    if cached is not None and cached.status != "failed":
        logger.info("research cache hit: %s (%s)",
                    request.canonical_name, cached.status)
        return cached
    if cached is not None:
        # A failed dossier is the ABSENCE of an answer wearing the shape of
        # one. Serving it from cache makes the hole permanent: every future
        # run of every script would get the same empty result, and C6 would
        # rate that entity from nothing forever. Retry instead.
        logger.info("ignoring cached failure for %s, researching again",
                    request.canonical_name)

    call_model = call_model or _call_model_adk

    evidence: list[EvidenceItem] = []
    queries_run: list[str] = []
    latest_results: Optional[dict] = None
    search_calls = 0
    turn: Optional[ResearchTurn] = None
    status = "partial"
    failure: str = ""

    # One pass more than the search budget: the final pass is the model reading
    # the last results and finalising, and it needs to happen after the last
    # search rather than instead of it.
    for _ in range(max_search_calls + 1):
        try:
            turn = await call_model(
                _turn_message(request, evidence, latest_results,
                              max_search_calls - search_calls)
            )
        except Exception as exc:  # noqa: BLE001 — a run of twelve must survive one
            failure = f"{type(exc).__name__}: {exc}"
            logger.warning("research model call failed for %s: %s",
                           request.canonical_name, failure)
            status = "failed" if not evidence else "partial"
            break

        evidence.extend(turn.new_evidence)
        # The discard. Results just folded into evidence are dropped, so the
        # next pass sees the model's summary rather than the pages.
        latest_results = None

        if turn.done:
            status = "complete"
            break
        if search_calls >= max_search_calls:
            logger.info("research budget spent for %s", request.canonical_name)
            break
        if not turn.next_queries:
            # Not done, but nothing to search for. Believing "not done" here
            # would loop until the budget ran out producing nothing.
            break

        result = search(_objective(request), list(turn.next_queries))
        search_calls += 1
        queries_run.extend(turn.next_queries)

        if result.get("status") != "ok":
            failure = f"{result.get('code')}: {result.get('detail')}"
            logger.warning("research search failed for %s: %s",
                           request.canonical_name, failure)
            # One more pass so the model can finalise on what it already has.
            latest_results = {"error": result.get("code"), "results": []}
            continue

        latest_results = {"results": result["results"]}

    dossier = _assemble(request, turn, evidence, queries_run, search_calls,
                        status, failure)
    # `partial` is worth keeping -- it has evidence, just not all of it.
    # `failed` is not: writing it would poison the cache for every later run,
    # and the usual cause is a transient quota or outage that will have
    # cleared by the next attempt.
    if dossier.status != "failed":
        await cache.put(dossier, keys)
    else:
        logger.info("not caching failed dossier for %s", request.canonical_name)
    logger.info("researched %s in %d searches (%s, %dms)", request.canonical_name,
                search_calls, dossier.status, int((time.monotonic() - started) * 1000))
    return dossier


def _assemble(
    request: ResearchRequest,
    turn: Optional[ResearchTurn],
    evidence: list[EvidenceItem],
    queries_run: list[str],
    search_calls: int,
    status: str,
    failure: str,
) -> ResearchDossier:
    identified = turn.identified_as if turn else ""
    if failure and not identified:
        identified = f"Research did not complete: {failure}"

    # An entity with no evidence is not complete, whatever the model claimed.
    # The model is the wrong judge of this: it has every incentive to declare
    # itself done, and C6 needs to know when it is reasoning from nothing.
    if status == "complete" and not evidence:
        status = "partial"

    return ResearchDossier(
        canonical_name=request.canonical_name,
        category=request.category,  # type: ignore[arg-type]
        identified_as=identified,
        rights_holders=list(turn.rights_holders) if turn else [],
        public_domain=turn.public_domain if turn else "unknown",
        notable_disputes=list(turn.notable_disputes) if turn else [],
        evidence=_renumber(evidence),
        queries_run=queries_run,
        search_calls=search_calls,
        status=status,  # type: ignore[arg-type]
        prompt_version=RESEARCH_PROMPT_VERSION,
    )


def _renumber(evidence: list[EvidenceItem]) -> list[EvidenceItem]:
    """Make evidence ids unique and contiguous across the whole dossier.

    Each pass numbers from ev_1 unless told otherwise, so two passes can both
    emit an ev_1. C6 validates that every id it cites exists, and duplicate
    ids would let a citation resolve to the wrong fact — which is worse than
    failing to resolve, because it looks like it worked.
    """
    return [
        EvidenceItem(id=f"ev_{i}", claim=e.claim, url=e.url, excerpt=e.excerpt)
        for i, e in enumerate(evidence, start=1)
    ]
