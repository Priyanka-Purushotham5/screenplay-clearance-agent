"""C6 — the assessment agent.

Rates every mention against the dossier its entity produced. Pro rather than
Flash, because this is the judgement stage and it runs perhaps three times per
script rather than thirty. No tools: everything knowable about the outside
world arrived in the dossiers, and an assessor that can search starts
substituting its own recollection for evidence somebody checked.

What each mention is shown
--------------------------
Not just its own words. Each mention carries **every other mention of the same
entity**, with scene and element type. That is what makes the rubric's
exception decidable: a character saying "turn that off" is only part of an
on-screen use if the entity is depicted in that same scene, and the model
cannot know that from the dialogue line alone. Without the sibling mentions
the rubric would be asking for a judgement on evidence the model does not
have, and it would guess — consistently, and wrongly, in the direction of
"dialogue is green".

Citations are validated, not trusted
------------------------------------
Every `cited_evidence_ids` entry must exist in the dossier that mention was
rated against. An invented id is worse than no citation at all: it reads as
though the rating was checked. A batch containing one is re-requested once
with the bad ids named. If it comes back wrong again the ratings are kept but
the invalid ids are stripped and counted, because dropping a whole batch of
ratings over a citation error loses more than it protects — and
`invalid_citations` on the outcome means the failure is reported rather than
absorbed.

Nothing raises. A model error on batch two leaves batches one and three rated
and records what happened, the same discipline as C4 and C5.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Sequence

from api.app.agents.rubric import ASSESSMENT_INSTRUCTION, RUBRIC_VERSION
from api.app.agents.schemas import (
    AssessmentBatch,
    AssessmentOutcome,
    MentionRating,
    ResearchDossier,
)
from api.app.config import settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
CONTEXT_CHARS = 300

APP_NAME = "clearance-assessment"
USER_ID = "system"


@dataclass(frozen=True)
class MentionToRate:
    """One mention, with everything the rubric needs to decide it."""

    mention_id: str
    script_element_id: str
    surface_form: str
    element_type: str
    scene: int
    context: str
    canonical_name: str

    @property
    def key(self) -> str:
        """The unique handle on a mention.

        Not (element_id, surface_form), which was the first attempt and is not
        unique: el_14 contains "that song" twice -- "You know that song? Take
        On Me? I actually love that song." -- two real mentions at different
        offsets. Under the tuple key they collide, a dropped rating goes
        undetected, and C7 would write one finding where there should be two.
        """
        return self.mention_id


def mentions_from_groups(groups, text_of: dict[str, str], scene_of: dict[str, int]):
    """Flatten C3's entity groups back into mentions to rate."""
    out: list[MentionToRate] = []
    seen: dict[str, int] = {}
    for group in groups:
        for mention in group.mentions:
            element_id = mention["script_element_id"]
            # Numbered per element, so the id is stable for a given parse and
            # readable in a log: el_14#1, el_14#2.
            seen[element_id] = seen.get(element_id, 0) + 1
            out.append(
                MentionToRate(
                    mention_id=f"{element_id}#{seen[element_id]}",
                    script_element_id=element_id,
                    surface_form=mention["surface_form"],
                    element_type=mention["element_type"],
                    scene=scene_of.get(element_id, 0),
                    context=text_of.get(element_id, "")[:CONTEXT_CHARS],
                    canonical_name=group.canonical,
                )
            )
    return out


def _siblings(mention: MentionToRate, all_mentions: Sequence[MentionToRate]) -> list[dict]:
    """Every other mention of the same entity — the rubric's exception needs it."""
    return [
        {
            "scene": other.scene,
            "element_type": other.element_type,
            "surface_form": other.surface_form,
        }
        for other in all_mentions
        if other.canonical_name == mention.canonical_name and other.key != mention.key
    ]


def _dossier_for_prompt(dossier: Optional[ResearchDossier]) -> dict:
    if dossier is None:
        return {"status": "missing",
                "note": "No research was performed for this entity."}
    return {
        "identified_as": dossier.identified_as,
        "rights_holders": dossier.rights_holders,
        "public_domain": dossier.public_domain,
        "notable_disputes": dossier.notable_disputes,
        "status": dossier.status,
        "evidence": [
            {"id": e.id, "claim": e.claim, "url": e.url,
             # Present so the model can weigh a registry against a forum, and
             # tolerated as absent so dossiers written before the field
             # existed still assess.
             "source_type": getattr(e, "source_type", "unknown")}
            for e in dossier.evidence
        ],
    }


def _batch_message(
    batch: Sequence[MentionToRate],
    all_mentions: Sequence[MentionToRate],
    dossiers: dict[str, ResearchDossier],
    note: str = "",
) -> str:
    payload = {
        "rubric_version": RUBRIC_VERSION,
        "mentions": [
            {
                "mention_id": m.mention_id,
                "script_element_id": m.script_element_id,
                "surface_form": m.surface_form,
                "element_type": m.element_type,
                "scene": m.scene,
                "screenplay_text": m.context,
                "entity": m.canonical_name,
                "other_mentions_of_this_entity": _siblings(m, all_mentions),
                "dossier": _dossier_for_prompt(dossiers.get(m.canonical_name)),
            }
            for m in batch
        ],
    }
    if note:
        payload["correction"] = note
    return json.dumps(payload, ensure_ascii=False)


async def _call_model_adk(message: str) -> AssessmentBatch:
    """Pro, structured output, no tools."""
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from api.app.agents.extract import _assert_credentials

    _assert_credentials()

    agent = LlmAgent(
        name="assessment",
        model=settings.assessment_model,
        description="Rates screenplay mentions for rights clearance.",
        instruction=ASSESSMENT_INSTRUCTION,
        output_schema=AssessmentBatch,
        output_key="assessment",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session_id = f"assess-{uuid.uuid4().hex[:12]}"
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
    return AssessmentBatch.model_validate_json(text)


def _bad_citations(
    ratings: Sequence[MentionRating],
    by_key: dict[tuple[str, str], MentionToRate],
    dossiers: dict[str, ResearchDossier],
) -> dict[str, list[str]]:
    """Cited ids that do not exist in the dossier that rating was made against."""
    bad: dict[str, list[str]] = {}
    for rating in ratings:
        mention = by_key.get(rating.mention_id)
        if mention is None:
            continue
        dossier = dossiers.get(mention.canonical_name)
        known = {e.id for e in dossier.evidence} if dossier else set()
        missing = [i for i in rating.cited_evidence_ids if i not in known]
        if missing:
            bad.setdefault(rating.mention_id, []).extend(missing)
    return bad


async def assess_mentions(
    mentions: Sequence[MentionToRate],
    dossiers: dict[str, ResearchDossier],
    *,
    call_model: Optional[Callable[[str], Awaitable[AssessmentBatch]]] = None,
    batch_size: int = BATCH_SIZE,
) -> AssessmentOutcome:
    """Rate every mention. Never raises."""
    call_model = call_model or _call_model_adk
    by_key = {m.key: m for m in mentions}

    ratings: list[MentionRating] = []
    warnings: list[str] = []
    invalid = 0
    batches = 0

    for start in range(0, len(mentions), batch_size):
        batch = list(mentions[start:start + batch_size])
        batches += 1
        note = ""

        for attempt in (1, 2):
            try:
                result = await call_model(
                    _batch_message(batch, mentions, dossiers, note)
                )
            except Exception as exc:  # noqa: BLE001 — one bad batch, not one bad run
                warnings.append(
                    f"batch {batches} failed: {type(exc).__name__}: {exc}")
                logger.warning("assessment batch %d failed: %s", batches, exc)
                result = None
                break

            bad = _bad_citations(result.ratings, by_key, dossiers)
            if not bad:
                break
            if attempt == 1:
                # Name the invented ids. A model told only "that was wrong"
                # tends to return the same thing with more confidence.
                note = (
                    "The previous response cited evidence ids that do not exist: "
                    + json.dumps(bad)
                    + ". Cite only ids present in each mention's dossier, or none."
                )
                logger.info("batch %d re-requested over %d bad citations",
                            batches, sum(len(v) for v in bad.values()))
                continue

            # Second failure: keep the ratings, strip the fiction, report it.
            count = sum(len(v) for v in bad.values())
            invalid += count
            warnings.append(
                f"batch {batches}: {count} invented evidence id(s) removed after retry")
            known_by_key = {
                m.key: {e.id for e in dossiers[m.canonical_name].evidence}
                if m.canonical_name in dossiers else set()
                for m in batch
            }
            result = AssessmentBatch(ratings=[
                r.model_copy(update={"cited_evidence_ids": [
                    i for i in r.cited_evidence_ids
                    if i in known_by_key.get(r.mention_id, set())
                ]})
                for r in result.ratings
            ])

        if result is not None:
            ratings.extend(result.ratings)

    # A mention the model quietly dropped is not a green mention. Surfacing it
    # matters more than it looks: an assessor that returns nine ratings for ten
    # mentions leaves one piece of third-party material with no finding at all,
    # and nothing downstream would notice.
    returned = {r.mention_id for r in ratings}
    unrated = [f"{m.mention_id} {m.surface_form!r}"
               for m in mentions if m.key not in returned]
    if unrated:
        warnings.append(f"{len(unrated)} mention(s) received no rating")

    return AssessmentOutcome(
        ratings=ratings,
        warnings=warnings,
        batches=batches,
        invalid_citations=invalid,
        unrated=unrated,
        rubric_version=RUBRIC_VERSION,
    )
