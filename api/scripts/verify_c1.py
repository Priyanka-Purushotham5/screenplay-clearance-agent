"""C1 acceptance — run the extraction agent and grade the result.

The gate C1 has to pass:

    one scene yields correct elements with offsets that actually index the
    right substring

So this script does two things. It re-slices every returned offset against the
source text and fails loudly if any slice is not exactly the surface form, and
it scores what came back against the planted elements in
`api/app/agents/fixtures/expected_elements.json`.

Needs GEMINI_API_KEY in .env (or GOOGLE_GENAI_USE_VERTEXAI=true with ADC).
No Postgres, no Docker, no parser.

    python api/scripts/verify_c1.py --scene 1     # the literal C1 gate
    python api/scripts/verify_c1.py               # all five scenes

Full output is also written to docs/c1_extraction_output.txt.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Make sure repo root is on the path when run as a script
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from api.app.agents.extract import (  # noqa: E402
    FIXTURES_DIR,
    extract_chunk,
    load_fixture,
    subset_chunk,
)
from api.app.agents.offsets import verify_offset  # noqa: E402
from api.app.agents.prompts import EXTRACTION_PROMPT_VERSION  # noqa: E402
from api.app.agents.schemas import ExtractionChunk, ResolvedElement  # noqa: E402
from api.app.config import settings  # noqa: E402

OUTPUT_FILE = ROOT / "docs" / "c1_extraction_output.txt"
EXPECTED_FILE = FIXTURES_DIR / "expected_elements.json"


def _matches(element: ResolvedElement, expected: dict, alts: list[str]) -> bool:
    """An expected element is found when the same real-world thing turns up in
    the same script element.  Canonical strings are matched loosely — exact
    normalisation is C3's job, not C1's."""
    if element.script_element_id != expected["script_element_id"]:
        return False
    canonical = element.canonical_name.casefold()
    terms = [expected["canonical_match"], *alts]
    return any(term.casefold() in canonical for term in terms)


async def main() -> int:
    parser = argparse.ArgumentParser(description="C1 extraction acceptance check")
    parser.add_argument(
        "--scene", type=int, default=None, help="run one scene by number (default: all)"
    )
    parser.add_argument(
        "--fixture", default="scene_fixture.json", help="fixture file in agents/fixtures"
    )
    args = parser.parse_args()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    # The Windows console defaults to cp1252, which cannot encode the dashes
    # and arrows below.  Without this the script dies mid-report.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    def emit(text: str = "") -> None:
        print(text)
        lines.append(text)

    chunk: ExtractionChunk = load_fixture(args.fixture)
    if args.scene is not None:
        chunk = subset_chunk(chunk, args.scene)

    index = chunk.element_index()
    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))

    emit("=" * 78)
    emit("C1 - EXTRACTION AGENT — ACCEPTANCE")
    emit("=" * 78)
    emit(f"  model         : {settings.extraction_model}")
    emit(f"  prompt version: {EXTRACTION_PROMPT_VERSION}")
    emit(f"  chunk         : {chunk.chunk_id}")
    emit(f"  scenes        : {len(chunk.scenes)}   elements: {len(index)}")

    outcome = await extract_chunk(chunk)

    # ── what came back ────────────────────────────────────────────────────
    emit()
    emit("-" * 78)
    emit(f"EXTRACTED ELEMENTS ({len(outcome.elements)})")
    emit("-" * 78)
    for el in sorted(outcome.elements, key=lambda e: (e.scene_id, e.script_element_id)):
        span = (
            f"[{el.char_start}:{el.char_end}]"
            if el.char_start is not None
            else "[unresolved]"
        )
        emit(
            f"  {el.script_element_id:<6} {el.element_type:<13} {el.category:<14} "
            f"{el.surface_form!r:<32} {el.canonical_name:<34} {span:<14} "
            f"{el.offset_status:<10} conf={el.confidence}"
        )

    if outcome.warnings:
        emit()
        emit("WARNINGS")
        for w in outcome.warnings:
            emit(f"  - {w}")

    # ── gate 1: offsets index the right substring ─────────────────────────
    emit()
    emit("-" * 78)
    emit("GATE 1 - OFFSETS RE-SLICE TO THE SURFACE FORM")
    emit("-" * 78)
    offset_failures: list[str] = []
    checked = 0
    for el in outcome.elements:
        if el.char_start is None:
            continue  # unresolved is reported separately, not a slice failure
        checked += 1
        source = index[el.script_element_id][0].text
        if not verify_offset(source, el.surface_form, el.char_start, el.char_end):
            actual = source[el.char_start : el.char_end]
            offset_failures.append(
                f"{el.script_element_id} {el.canonical_name}: "
                f"expected {el.surface_form!r}, text slice is {actual!r}"
            )
    for failure in offset_failures:
        emit(f"  FAIL  {failure}")
    emit(
        f"  {checked - len(offset_failures)}/{checked} offsets re-slice exactly"
        f"   ({outcome.stats.offsets_unresolved} unresolved, offsets nulled)"
    )

    # ── gate 2: the planted elements ──────────────────────────────────────
    emit()
    emit("-" * 78)
    emit("GATE 2 - PLANTED ELEMENTS")
    emit("-" * 78)
    present = [e for e in expected["expected_present"] if e["script_element_id"] in index]
    skipped = len(expected["expected_present"]) - len(present)
    matched_ids: set[int] = set()
    missed: list[dict] = []

    for exp in present:
        alts = expected.get("canonical_alt", {}).get(exp["script_element_id"], [])
        hit = next(
            (
                el
                for i, el in enumerate(outcome.elements)
                if _matches(el, exp, alts) and i not in matched_ids
            ),
            None,
        )
        if hit is None:
            missed.append(exp)
            emit(
                f"  MISS  {exp['script_element_id']:<6} {exp['category']:<12} "
                f"{exp['canonical_match']}"
            )
        else:
            matched_ids.add(outcome.elements.index(hit))
            flag = "  ok  " if hit.category == exp["category"] else " cat? "
            emit(
                f"  {flag}{exp['script_element_id']:<6} {exp['category']:<12} "
                f"{exp['canonical_match']:<16} -> {hit.canonical_name} "
                f"({hit.category}, {hit.element_type})"
            )
    emit(f"  recall: {len(present) - len(missed)}/{len(present)} planted elements found")
    if skipped:
        emit(f"  ({skipped} planted elements are outside this chunk — not counted)")

    # ── gate 3: the precision trap ────────────────────────────────────────
    emit()
    emit("-" * 78)
    emit("GATE 3 - FALSE POSITIVES")
    emit("-" * 78)
    trap_hits: list[str] = []
    for rule in expected["expected_absent"]:
        for el in outcome.elements:
            haystack = f"{el.surface_form} {el.canonical_name}".casefold()
            for form in rule["surface_forms"]:
                if form.casefold() in haystack:
                    trap_hits.append(
                        f"{el.script_element_id} extracted {el.surface_form!r} "
                        f"as {el.canonical_name} — {rule['why']}"
                    )
                    break
    for hit in trap_hits:
        emit(f"  FALSE POSITIVE  {hit}")
    if not trap_hits:
        emit("  none — the fictional-character trap was not taken")

    extras = [
        el for i, el in enumerate(outcome.elements) if i not in matched_ids
    ]
    if extras:
        acceptable = {a["canonical_match"].casefold() for a in expected["acceptable_extra"]}
        emit()
        emit(f"  EXTRAS ({len(extras)}) — reported, not penalised:")
        for el in extras:
            known = any(term in el.canonical_name.casefold() for term in acceptable)
            emit(
                f"    {'(known)' if known else '(new)  '} {el.script_element_id:<6} "
                f"{el.canonical_name} — {el.surface_form!r} in {el.element_type}"
            )

    # ── the split ─────────────────────────────────────────────────────────
    emit()
    emit("-" * 78)
    emit("THE SPLIT - same entity, different element_type")
    emit("-" * 78)
    by_canonical: dict[str, set[str]] = {}
    for el in outcome.elements:
        by_canonical.setdefault(el.canonical_name, set()).add(el.element_type)
    split = {k: v for k, v in by_canonical.items() if len(v) > 1}
    if split:
        for name, types_ in split.items():
            emit(f"  {name}: {', '.join(sorted(types_))}")
    else:
        emit("  no entity appeared in two element types in this chunk")
    emit(
        "  (C6 rates action-line mentions and dialogue mentions differently — "
        "collapsing them loses the product's core distinction)"
    )

    # ── stats ─────────────────────────────────────────────────────────────
    s = outcome.stats
    emit()
    emit("-" * 78)
    emit("STATS")
    emit("-" * 78)
    emit(f"  returned {s.elements_returned}, kept {s.elements_kept}, orphans {s.orphan_elements}")
    emit(
        f"  offsets: {s.offsets_exact} exact, {s.offsets_repaired} repaired, "
        f"{s.offsets_unresolved} unresolved"
    )
    emit(
        f"  tokens : {s.input_tokens} in, {s.output_tokens} out, "
        f"{s.thinking_tokens} thinking (billed)"
    )
    emit(f"  attempts {s.attempts}, wall {s.wall_ms} ms")

    # ── verdict ───────────────────────────────────────────────────────────
    failed = bool(offset_failures) or not outcome.elements
    emit()
    emit("=" * 78)
    if failed:
        reason = "offsets do not index the right substring" if offset_failures else "no elements extracted"
        emit(f"FAILED: {reason}")
    else:
        emit("PASSED: every offset indexes the right substring")
        if missed:
            emit(f"         {len(missed)} planted element(s) missed — see GATE 2")
        if trap_hits:
            emit(f"         {len(trap_hits)} false positive(s) — see GATE 3")
    emit("=" * 78)

    OUTPUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nFull output saved to: {OUTPUT_FILE}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
