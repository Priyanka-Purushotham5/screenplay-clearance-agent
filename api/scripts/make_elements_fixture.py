"""make_elements_fixture.py — freeze one good extraction for C3/C5/C6 to develop against.

    python api/scripts/make_elements_fixture.py            # validate the committed fixture
    python api/scripts/make_elements_fixture.py --freeze   # run extraction and record it

Why this exists.

Three runs of C1 over an identical chunk returned 27, 25 and 30 mentions,
and the same Coca-Cola lines came back categorised `trademark` on one run
and `product` on the next. Pinning temperature to 0.0 did not settle it —
`gemini-2.5-flash` spends thousands of thinking tokens per call and the
thinking pass is generated too.

That variance is a legitimate property of the extraction stage, and C1's
gates are the right place to measure it. It is not something the stages
downstream should have to absorb. C6 grades its ratings against a fixed
answer key, so if its input moves 20% between runs, an improving score
cannot be distinguished from a luckier sample — and rubric tuning is the
highest-leverage work left in the project.

So this quarantines the variance rather than pretending to remove it.
`--freeze` records one extraction; C3, C5 and C6 read the recording. Their
iteration loop becomes instant and free instead of 25 seconds and 9k tokens,
and a score that moves means the code moved.

Production still runs live extraction. This is a development fixture, in the
same spirit as `scene_fixture.json`, which freezes the parser so that C1
grades the model rather than the parser.

--freeze REFUSES to record a run that misses a planted element. The b4
snapshot's docstring puts it well: re-freezing a broken parse simply blesses
the breakage. A frozen extraction that has lost the disparaged-Coca-Cola line
would silently remove the hardest case in the document from every stage that
follows.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "api" / "app" / "agents" / "fixtures"
CHUNK_FILE = FIXTURES / "scene_fixture.json"
EXPECTED_FILE = FIXTURES / "expected_elements.json"
OUTPUT_FILE = FIXTURES / "elements_fixture.json"


def _load_chunk():
    from api.app.agents.schemas import ExtractionChunk

    return ExtractionChunk.model_validate_json(CHUNK_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# check — no API calls, no key needed
# ---------------------------------------------------------------------------


def check() -> int:
    from api.app.agents.schemas import ResolvedElement

    if not OUTPUT_FILE.exists():
        print(f"No fixture at {OUTPUT_FILE.relative_to(ROOT)}")
        print("Record one with: python api/scripts/make_elements_fixture.py --freeze")
        return 2

    data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    chunk = _load_chunk()
    index = chunk.element_index()

    ok = True

    if data.get("chunk_id") != chunk.chunk_id:
        print(f"FAIL chunk_id {data.get('chunk_id')!r} != {chunk.chunk_id!r}")
        ok = False

    elements = [ResolvedElement.model_validate(e) for e in data["elements"]]
    print(f"{len(elements)} mentions, recorded from {data.get('model')} "
          f"/ {data.get('prompt_version')}")

    # Every mention must point at an element that still exists. If the parser
    # or the screenplay changes, this is what says so.
    orphans = [e.script_element_id for e in elements if e.script_element_id not in index]
    if orphans:
        print(f"FAIL {len(orphans)} mention(s) point at missing elements: {orphans[:5]}")
        ok = False
    else:
        print(f"ok   every mention resolves to an element in {CHUNK_FILE.name}")

    # Offsets must still index the surface form. Same gate C1 applies live —
    # a frozen fixture is not exempt from it.
    bad = []
    for e in elements:
        if e.char_start is None or e.char_end is None:
            continue
        source = index[e.script_element_id][0].text
        if source[e.char_start:e.char_end] != e.surface_form:
            bad.append(f"{e.script_element_id} {e.surface_form!r}")
    if bad:
        print(f"FAIL {len(bad)} offset(s) no longer re-slice: {bad[:3]}")
        ok = False
    else:
        print("ok   every offset re-slices to its surface form")

    groups: dict[str, list[str]] = {}
    for e in elements:
        groups.setdefault(e.canonical_name, []).append(e.script_element_id)
    ratio = len(elements) / len(groups) if groups else 0
    print(f"ok   {len(elements)} mentions across {len(groups)} canonical names "
          f"({ratio:.2f}:1 before C3 normalisation)")

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# freeze — runs the agent, so it needs credentials
# ---------------------------------------------------------------------------


def _planted_misses(elements) -> list[str]:
    """Which planted elements this run failed to find.

    Same rule as verify_c1's gate 2: an expectation is satisfied by a mention
    on the same script element whose canonical name contains the expected
    substring, and one mention cannot satisfy two expectations.
    """
    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    alts_by_id = expected.get("canonical_alt", {})
    claimed: set[int] = set()
    missed: list[str] = []

    for exp in expected["expected_present"]:
        terms = [exp["canonical_match"], *alts_by_id.get(exp["script_element_id"], [])]
        hit = next(
            (
                i
                for i, el in enumerate(elements)
                if i not in claimed
                and el.script_element_id == exp["script_element_id"]
                and any(t.casefold() in el.canonical_name.casefold() for t in terms)
            ),
            None,
        )
        if hit is None:
            missed.append(f"{exp['script_element_id']} {exp['canonical_match']}")
        else:
            claimed.add(hit)
    return missed


def freeze() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from api.app.agents.extract import extract_chunk
    from api.app.agents.prompts import EXTRACTION_PROMPT_VERSION
    from api.app.config import settings

    chunk = _load_chunk()
    outcome = asyncio.run(extract_chunk(chunk))
    elements = outcome.elements

    total = len(json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))["expected_present"])
    missed = _planted_misses(elements)
    print(f"extracted {len(elements)} mentions, "
          f"recall {total - len(missed)}/{total}")

    if missed:
        print("\nNOT FROZEN — this run missed planted elements:")
        for m in missed:
            print(f"  MISS  {m}")
        print("\nExtraction varies between runs. Try again; if a miss repeats,")
        print("it is an extraction problem and freezing it would hide it.")
        return 1

    payload = {
        "_comment": [
            "One frozen C1 extraction, for C3/C5/C6 to develop against.",
            "Recorded by api/scripts/make_elements_fixture.py --freeze, which",
            "refuses to record a run that misses a planted element.",
            "",
            "This is NOT what production runs. Live extraction happens per run;",
            "this exists so that a change in a downstream score means the",
            "downstream code changed, not that the extractor sampled differently.",
        ],
        "chunk_id": outcome.chunk_id,
        "model": settings.extraction_model,
        "prompt_version": EXTRACTION_PROMPT_VERSION,
        "recall": f"{total - len(missed)}/{total}",
        "elements": [e.model_dump(mode="json") for e in elements],
    }

    OUTPUT_FILE.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {OUTPUT_FILE.relative_to(ROOT)}")
    print("Validate it with: python api/scripts/make_elements_fixture.py")
    return 0


def main() -> int:
    return freeze() if "--freeze" in sys.argv else check()


if __name__ == "__main__":
    sys.exit(main())
