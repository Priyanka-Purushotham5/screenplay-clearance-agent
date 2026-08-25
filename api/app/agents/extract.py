"""Stage 1 — extraction.  ADK LlmAgent on Flash, no tools.

Turns a chunk of parsed screenplay into one record per mention of real-world
material.  Structured output is enforced against `ExtractionResult`; the A2
probe confirmed Gemini honours `response_schema` rather than merely trying to.

**No tools, deliberately.**  An extraction agent with search will find
elements that are not in the script.  Tool isolation here is a correctness
property, not organisation — see technical-spec.md §3.

Everything the model is not asked for, code derives: `element_type`, `page`
and `scene_id` are joined back from the input chunk, and offsets are verified
and repaired against the source text.  C1 does not touch the database; C2
persists the results per chunk.
"""

import json
import logging
import os
import time
import uuid
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from api.app.agents.offsets import resolve_offset
from api.app.agents.prompts import EXTRACTION_INSTRUCTION
from api.app.agents.schemas import (
    ExtractedElement,
    ExtractionChunk,
    ExtractionOutcome,
    ExtractionResult,
    ExtractionStats,
    ResolvedElement,
)
from api.app.config import settings

logger = logging.getLogger(__name__)

APP_NAME = "clearance-extraction"
USER_ID = "pipeline"
MAX_ATTEMPTS = 2  # one retry; a bad chunk must not kill the run

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _assert_credentials() -> None:
    """Fail early and legibly rather than deep inside the SDK.

    ADK builds its `genai.Client` from the process environment, while our
    config comes from `.env` through pydantic-settings.  Nothing bridges the
    two automatically, so do it here — otherwise a key that is plainly present
    in `.env` produces "No API key was provided" from three frames deep.
    """
    os.environ.setdefault(
        "GOOGLE_GENAI_USE_VERTEXAI", "true" if settings.google_genai_use_vertexai else "0"
    )
    if settings.google_genai_use_vertexai:
        return  # Application Default Credentials; nothing to check here
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return  # already exported, e.g. by load_dotenv in a verify script
    if not settings.gemini_api_key:
        raise RuntimeError(
            "No Gemini credentials. Set GEMINI_API_KEY in .env, or set "
            "GOOGLE_GENAI_USE_VERTEXAI=true to authenticate with ADC."
        )
    os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key


def build_extraction_agent() -> LlmAgent:
    """The Stage 1 agent.  Flash, structured output, no tools, no transfer."""
    return LlmAgent(
        name="extraction",
        model=settings.extraction_model,
        description="Identifies third-party material in parsed screenplay text.",
        instruction=EXTRACTION_INSTRUCTION,
        output_schema=ExtractionResult,
        output_key="extraction",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        # Extraction is a structural task with one right answer, so sampling
        # variance is pure loss. Unset, Flash defaults to temperature 1.0:
        # three runs over an identical fixture returned 27, 25 and 30 mentions,
        # and the same Coca-Cola lines came back as `trademark` once and
        # `product` the next time. C6 grades against a fixed answer key, and a
        # score cannot separate a better rubric from a luckier sample if the
        # input moves 20% between runs.
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )


def load_fixture(name: str = "scene_fixture.json") -> ExtractionChunk:
    """Load a chunk from the fixtures directory.

    Stands in for the parser until B6 lands.  When it does, the replacement
    reads `scenes` + `script_elements` from Postgres and builds the same
    `ExtractionChunk` — the agent below does not change.
    """
    path = FIXTURES_DIR / name
    return ExtractionChunk.model_validate_json(path.read_text(encoding="utf-8"))


async def _run_agent(chunk: ExtractionChunk) -> tuple[str, types.GenerateContentResponseUsageMetadata | None]:
    """One pass through the agent.  Returns raw text and usage metadata.

    A fresh session per call, with no state carried between calls: chunks must
    stay independent so C2 can run them concurrently.
    """
    runner = InMemoryRunner(agent=build_extraction_agent(), app_name=APP_NAME)
    session_id = f"extract-{uuid.uuid4().hex[:12]}"
    await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=chunk.model_dump_json(exclude_none=False))],
    )

    final_text = ""
    usage = None
    try:
        async for event in runner.run_async(
            user_id=USER_ID, session_id=session_id, new_message=message
        ):
            if event.usage_metadata is not None:
                usage = event.usage_metadata
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(
                    part.text for part in event.content.parts if part.text
                )
    finally:
        await runner.close()

    return final_text, usage


def _resolve(
    extracted: list[ExtractedElement], chunk: ExtractionChunk, stats: ExtractionStats
) -> tuple[list[ResolvedElement], list[str]]:
    """Join model output back onto the chunk and fix up offsets."""
    index = chunk.element_index()
    resolved: list[ResolvedElement] = []
    warnings: list[str] = []

    for item in extracted:
        entry = index.get(item.script_element_id)
        if entry is None:
            # The model referred to an element that is not in the chunk.  Drop
            # it — a mention we cannot anchor is worse than no mention.
            stats.orphan_elements += 1
            warnings.append(
                f"dropped element with unknown script_element_id "
                f"{item.script_element_id!r} ({item.surface_form!r})"
            )
            continue

        element, scene = entry
        offsets = resolve_offset(
            element.text, item.surface_form, item.char_start, item.char_end
        )

        if offsets.status == "exact":
            stats.offsets_exact += 1
        elif offsets.status == "repaired":
            stats.offsets_repaired += 1
        else:
            stats.offsets_unresolved += 1
            warnings.append(
                f"could not locate {item.surface_form!r} in {element.id} — "
                "offsets nulled"
            )

        resolved.append(
            ResolvedElement(
                script_element_id=item.script_element_id,
                scene_id=scene.scene_id,
                category=item.category,
                surface_form=offsets.surface_form,
                canonical_name=item.canonical_name,
                element_type=element.type,
                page=element.page,
                char_start=offsets.char_start,
                char_end=offsets.char_end,
                confidence=item.confidence,
                offset_status=offsets.status,
            )
        )

    return resolved, warnings


async def extract_chunk(chunk: ExtractionChunk) -> ExtractionOutcome:
    """Extract every mention of real-world material in one chunk.

    Never raises on model failure.  A chunk that cannot be extracted comes
    back empty with a warning, so C2 loses one chunk rather than the run.
    """
    _assert_credentials()

    stats = ExtractionStats()
    warnings: list[str] = []
    started = time.perf_counter()
    result: ExtractionResult | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        stats.attempts = attempt
        try:
            raw, usage = await _run_agent(chunk)
        except Exception as exc:  # noqa: BLE001 — the run must survive this
            warnings.append(f"attempt {attempt}: agent call failed — {exc}")
            logger.warning("extraction attempt %s failed for %s: %s", attempt, chunk.chunk_id, exc)
            continue

        if usage is not None:
            stats.input_tokens = usage.prompt_token_count or 0
            stats.output_tokens = usage.candidates_token_count or 0
            stats.thinking_tokens = usage.thoughts_token_count or 0

        if not raw.strip():
            warnings.append(f"attempt {attempt}: empty response")
            continue

        try:
            result = ExtractionResult.model_validate_json(raw)
            break
        except Exception as exc:  # noqa: BLE001 — same reason
            warnings.append(f"attempt {attempt}: response failed validation — {exc}")
            logger.warning("extraction validation failed for %s: %s", chunk.chunk_id, exc)

    if result is None:
        stats.wall_ms = int((time.perf_counter() - started) * 1000)
        warnings.append(f"chunk {chunk.chunk_id} produced no usable extraction")
        return ExtractionOutcome(
            chunk_id=chunk.chunk_id, elements=[], stats=stats, warnings=warnings
        )

    stats.elements_returned = len(result.elements)
    resolved, resolve_warnings = _resolve(result.elements, chunk, stats)
    stats.elements_kept = len(resolved)
    stats.wall_ms = int((time.perf_counter() - started) * 1000)

    return ExtractionOutcome(
        chunk_id=chunk.chunk_id,
        elements=resolved,
        stats=stats,
        warnings=warnings + resolve_warnings,
    )


def subset_chunk(chunk: ExtractionChunk, scene_number: int) -> ExtractionChunk:
    """A single-scene chunk — the literal C1 gate is one scene."""
    scenes = [s for s in chunk.scenes if s.number == scene_number]
    if not scenes:
        raise ValueError(f"no scene numbered {scene_number} in {chunk.chunk_id}")
    return ExtractionChunk(chunk_id=f"{chunk.chunk_id}-sc{scene_number}", scenes=scenes)


__all__ = [
    "build_extraction_agent",
    "extract_chunk",
    "load_fixture",
    "subset_chunk",
]


if __name__ == "__main__":  # pragma: no cover — quick manual smoke test
    import asyncio

    async def _main() -> None:
        outcome = await extract_chunk(subset_chunk(load_fixture(), 1))
        print(json.dumps(outcome.model_dump(), indent=2))

    asyncio.run(_main())
