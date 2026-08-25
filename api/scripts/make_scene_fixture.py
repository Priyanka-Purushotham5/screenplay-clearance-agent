"""make_scene_fixture.py — rebuild api/app/agents/fixtures/scene_fixture.json

    python api/scripts/make_scene_fixture.py            # write the fixture
    python api/scripts/make_scene_fixture.py --check    # fail if it is stale

The extraction agent reads a frozen `ExtractionChunk` rather than parsing a
PDF, so C1 stays hermetic: no Postgres, no Docker, no parser, and the same
bytes on every run. That is the right trade for an agent test, whose job is
to grade the model rather than the parser.

The cost of freezing is drift. The fixture was frozen from a five-scene
parse; B7 appended two scenes, and nothing noticed, because a frozen file
cannot go stale loudly on its own. This script is what makes it loud —
`--check` compares the committed fixture against a fresh parse and fails if
they differ, so the staleness surfaces in a test run instead of in a
confusing extraction result three stages downstream.

Rohit's note on `load_fixture()` reads:

    Stands in for the parser until B6 lands.  When it does, the replacement
    reads `scenes` + `script_elements` from Postgres and builds the same
    `ExtractionChunk`.

This is the halfway house. It builds that same object from the parser rather
than from Postgres, which keeps C1 free of a database dependency. C2 adds the
Postgres path, where chunking has to slice a real script by page ranges
anyway.

Ids are positional and 1-based: `sc_{n}` per scene, `el_{n}` counted across
the whole document. `expected_elements.json` pins those strings, so they are
a contract, not an implementation detail — which is why B7 appended scenes
rather than inserting them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.app.parser.pipeline import parse_screenplay  # noqa: E402

FIXTURE = ROOT / "api" / "app" / "agents" / "fixtures" / "scene_fixture.json"
SOURCE = ROOT / "docs" / "test_screenplay.pdf"
CHUNK_ID = "ch_1"


def build(pdf: Path) -> dict:
    """Parse the screenplay into the ExtractionChunk wire shape."""
    parsed = parse_screenplay(pdf)

    scenes = []
    element_no = 0
    for scene in parsed.scenes:
        elements = []
        for element in scene.elements:
            element_no += 1
            elements.append(
                {
                    "id": f"el_{element_no}",
                    "type": element.type,
                    "page": element.page,
                    "character": element.character,
                    "text": element.text,
                }
            )
        scenes.append(
            {
                "scene_id": f"sc_{scene.number}",
                "number": scene.number,
                "heading": scene.heading,
                "elements": elements,
            }
        )

    return {"chunk_id": CHUNK_ID, "scenes": scenes}


def main() -> int:
    if not SOURCE.exists():
        print(f"Fixture PDF missing: {SOURCE}")
        return 2

    fresh = build(SOURCE)
    text = json.dumps(fresh, indent=1, ensure_ascii=False) + "\n"

    n_scenes = len(fresh["scenes"])
    n_elements = sum(len(s["elements"]) for s in fresh["scenes"])

    if "--check" in sys.argv:
        if not FIXTURE.exists():
            print(f"No fixture at {FIXTURE.relative_to(ROOT)}")
            return 1
        current = json.loads(FIXTURE.read_text(encoding="utf-8"))
        if current == fresh:
            print(f"Fixture is current — {n_scenes} scenes, {n_elements} elements")
            return 0
        was_scenes = len(current.get("scenes", []))
        was_elements = sum(len(s.get("elements", [])) for s in current.get("scenes", []))
        print("Fixture is STALE.")
        print(f"  committed: {was_scenes} scenes, {was_elements} elements")
        print(f"  parser    : {n_scenes} scenes, {n_elements} elements")
        for scene in fresh["scenes"]:
            for element in scene["elements"]:
                old = _find(current, element["id"])
                if old is None:
                    print(f"  + {element['id']} {element['type']}: {element['text'][:52]}")
                elif old != element:
                    # Report the fields that actually differ. Printing only
                    # `text` once hid a page-number drift across seventeen
                    # elements behind seventeen identical-looking lines.
                    for field in element:
                        if old.get(field) != element[field]:
                            print(f"  ~ {element['id']}.{field}: "
                                  f"{_short(old.get(field))} -> {_short(element[field])}")
        print("\nRebuild with: python api/scripts/make_scene_fixture.py")
        return 1

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(text, encoding="utf-8")
    print(f"Wrote {FIXTURE.relative_to(ROOT)}")
    print(f"  {n_scenes} scenes, {n_elements} elements, chunk_id={CHUNK_ID}")
    print("\nElement ids are pinned by api/app/agents/fixtures/expected_elements.json.")
    print("Re-run C1 before trusting this: docker compose exec api "
          "python api/scripts/verify_c1.py --scene 1")
    return 0


def _short(value: object, width: int = 44) -> str:
    text = repr(value)
    return text if len(text) <= width else text[: width - 1] + "…'"


def _find(chunk: dict, element_id: str) -> dict | None:
    for scene in chunk.get("scenes", []):
        for element in scene.get("elements", []):
            if element.get("id") == element_id:
                return element
    return None


if __name__ == "__main__":
    sys.exit(main())
