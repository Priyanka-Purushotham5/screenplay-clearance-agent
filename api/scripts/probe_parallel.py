"""
probe_parallel.py — A2 probe: Parallel Search API

Calls client.search() with three query shapes and writes all output to
docs/probe_parallel_output.txt (as well as printing to the terminal).

Run:
    python api/scripts/probe_parallel.py

Requires PARALLEL_API_KEY in .env (copy .env.example → .env and fill in the key).
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from parallel import Parallel

load_dotenv()

OUTPUT_FILE = Path(__file__).resolve().parents[2] / "docs" / "probe_parallel_output.txt"

# ---------------------------------------------------------------------------
# Three query shapes from the A2 checklist:
#   1. Easy / well-indexed
#   2. Obscure (minor 1970s artist)
#   3. Deliberately ambiguous
# ---------------------------------------------------------------------------
QUERIES = [
    {
        "label": "EASY — well-indexed rights query",
        "objective": "Who owns the publishing rights to Take On Me by a-ha?",
        "search_queries": ["Take On Me a-ha publishing rights", "a-ha music copyright holder"],
    },
    {
        "label": "OBSCURE — minor 1970s painter",
        "objective": "Who holds the estate rights to paintings by Gordon Matta-Clark?",
        "search_queries": ["Gordon Matta-Clark estate rights", "Gordon Matta-Clark artwork copyright"],
    },
    {
        "label": "AMBIGUOUS — multiple plausible meanings",
        "objective": "Who owns the rights to the name and brand 'Alien'?",
        "search_queries": ["Alien franchise trademark owner", "Alien film rights holder", "Alien brand copyright"],
    },
]


def result_to_dict(r) -> dict:
    """Convert a V1WebSearchResult to a plain dict for JSON serialisation."""
    return {
        "url": r.url,
        "title": r.title,          # may be None
        "publish_date": r.publish_date,  # YYYY-MM-DD or None
        "excerpts": r.excerpts,    # list[str] — markdown-formatted
    }


def response_to_dict(resp) -> dict:
    """Convert a V1SearchResponse to a plain dict for JSON serialisation."""
    return {
        "search_id": resp.search_id,
        "session_id": getattr(resp, "session_id", None),
        "results": [result_to_dict(r) for r in resp.results],
        "warnings": [str(w) for w in resp.warnings] if resp.warnings else None,
        "usage": [str(u) for u in resp.usage] if resp.usage else None,
    }


def main() -> None:
    api_key = os.environ.get("PARALLEL_API_KEY")
    if not api_key:
        raise SystemExit("PARALLEL_API_KEY is not set. Copy .env.example → .env and fill in your key.")

    client = Parallel(api_key=api_key)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        # Tee: write to both the file and stdout
        def emit(text: str = "") -> None:
            print(text)
            f.write(text + "\n")

        for q in QUERIES:
            emit("\n" + "=" * 72)
            emit(f"QUERY SHAPE: {q['label']}")
            emit(f"  objective      : {q['objective']}")
            emit(f"  search_queries : {q['search_queries']}")
            emit("=" * 72)

            response = client.search(
                objective=q["objective"],
                search_queries=q["search_queries"],
                mode="basic",       # $5/1k, ~1 s — recommended starting point
            )

            emit("\n--- repr(response) ---")
            emit(repr(response))

            emit("\n--- json.dumps (indent=2) ---")
            emit(json.dumps(response_to_dict(response), indent=2, default=str))

            emit(f"\n  result count : {len(response.results)}")
            if response.warnings:
                emit(f"  warnings     : {response.warnings}")

    print(f"\nFull output saved to: {OUTPUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
