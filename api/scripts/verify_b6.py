"""B6 smoke-test — upload parses, persists, and reads back.

    python api/scripts/verify_b6.py

The done-when: "upload returns 201 with real page and scene counts and the
scenes endpoint returns the parsed structure."

The last check is the one that matters most. It follows the RED/GREEN pair
all the way through HTTP and Postgres: 'Take On Me' appears once in an
action element and once in dialogue, and the two must still be different
element types when the frontend reads them back. Everything B2-B5 does is
in service of that distinction surviving the round trip.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
API = os.environ.get("API_URL", "http://localhost:8080").rstrip("/")

SCENE_FIELDS = {"id", "script_id", "number", "int_ext", "location",
                "time_of_day", "heading", "page_start", "page_end", "elements"}
ELEMENT_FIELDS = {"id", "scene_id", "seq", "type", "character", "page", "text"}

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def salted(path: Path) -> bytes:
    return path.read_bytes() + b"\n%% verify_b6 " + os.urandom(8).hex().encode() + b"\n"


def main() -> int:
    clean = ROOT / "docs" / "test_screenplay.pdf"
    messy = ROOT / "docs" / "messy_screenplay.pdf"
    for f in (clean, messy):
        if not f.exists():
            print(f"Fixture missing: {f}")
            return 2

    with httpx.Client(base_url=API, timeout=180.0) as c:
        print()
        # ── upload and read back ───────────────────────────────────────
        r = c.post("/api/scripts", files={"file": (clean.name, salted(clean), "application/pdf")})
        body = r.json()
        check("Upload returns 201", r.status_code == 201, str(r.status_code))
        check("page_count is real", body.get("page_count") == 4, f"{body.get('page_count')}")
        check("scene_count is real", body.get("scene_count") == 7, f"{body.get('scene_count')}")
        sid = body["script_id"]

        s = c.get(f"/api/scripts/{sid}/scenes")
        scenes = s.json().get("scenes", [])
        check("GET /scenes returns 200", s.status_code == 200, str(s.status_code))
        check("scenes endpoint agrees with scene_count",
              len(scenes) == body["scene_count"], f"{len(scenes)} vs {body['scene_count']}")

        # ── the shape the frontend generates its types from ────────────
        check("Every scene has exactly the frontend's Scene fields",
              all(set(sc) == SCENE_FIELDS for sc in scenes),
              str(sorted(set(scenes[0]) ^ SCENE_FIELDS)) if scenes else "no scenes")
        elements = [e for sc in scenes for e in sc["elements"]]
        check("Every element has exactly the frontend's ScriptElement fields",
              all(set(e) == ELEMENT_FIELDS for e in elements),
              str(sorted(set(elements[0]) ^ ELEMENT_FIELDS)) if elements else "none")

        check("All 58 elements were persisted", len(elements) == 58, str(len(elements)))
        check("seq is 1-based and contiguous within each scene",
              all([e["seq"] for e in sc["elements"]] == list(range(1, len(sc["elements"]) + 1))
                  for sc in scenes))
        check("Every element points at its own scene",
              all(e["scene_id"] == sc["id"] for sc in scenes for e in sc["elements"]))
        check("Every scene points at the script",
              all(sc["script_id"] == sid for sc in scenes))
        check("Scenes come back in number order",
              [sc["number"] for sc in scenes] == sorted(sc["number"] for sc in scenes),
              str([sc["number"] for sc in scenes]))
        check("Each scene opens with its heading element",
              all(sc["elements"][0]["type"] == "scene_heading" for sc in scenes))
        check("Slug lines were parsed into their parts",
              all(sc["int_ext"] in ("INT", "EXT", "INT/EXT") and sc["location"] for sc in scenes))

        # ── the RED/GREEN pair, end to end ─────────────────────────────
        song = [e for e in elements if "Take On Me" in e["text"]]
        types = {e["type"] for e in song}
        check("The song survives the round trip in two different element types",
              types == {"action", "dialogue"} and len(song) >= 2,
              f"{len(song)} mentions, types={sorted(types)}")

        # ── range query ────────────────────────────────────────────────
        rng = c.get(f"/api/scripts/{sid}/scenes", params={"from": 2, "to": 4}).json()
        check("?from=&to= filters by scene number",
              [sc["number"] for sc in rng["scenes"]] == [2, 3, 4],
              str([sc["number"] for sc in rng["scenes"]]))

        # ── the messy fixture: production numbering survives ───────────
        r2 = c.post("/api/scripts", files={"file": (messy.name, salted(messy), "application/pdf")})
        b2 = r2.json()
        check("Messy fixture uploads with 2 scenes and 3 pages",
              r2.status_code == 201 and b2.get("scene_count") == 2 and b2.get("page_count") == 3,
              f"{r2.status_code} scenes={b2.get('scene_count')} pages={b2.get('page_count')}")
        m = c.get(f"/api/scripts/{b2['script_id']}/scenes").json()["scenes"]
        check("Production scene numbers reach the database",
              [sc["number"] for sc in m] == [14, 15], str([sc["number"] for sc in m]))
        check("Scene headings are stored without their mirrored numbers",
              all(not sc["heading"][:1].isdigit() for sc in m),
              "; ".join(sc["heading"][:22] for sc in m))
        check("Parse warnings reach the response",
              any("Rejoined" in w for w in b2.get("parse_warnings", [])),
              str(b2.get("parse_warnings")))

        # ── nothing partial is ever left behind ────────────────────────
        corrupt = b"%PDF-1.7\n" + b"junk" * 200
        r3 = c.post("/api/scripts", files={"file": ("broken.pdf", corrupt, "application/pdf")})
        check("A file that cannot be parsed is rejected, not half-written",
              r3.status_code == 422, str(r3.status_code))

        r4 = c.get("/api/scripts/00000000-0000-0000-0000-000000000000/scenes")
        check("Unknown script id returns 404 from /scenes", r4.status_code == 404, str(r4.status_code))

        spec = c.get("/openapi.json").json()
        check("OpenAPI declares the scenes endpoint",
              "/api/scripts/{id}/scenes" in spec.get("paths", {}),
              str(sorted(spec.get("paths", {}))))

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())