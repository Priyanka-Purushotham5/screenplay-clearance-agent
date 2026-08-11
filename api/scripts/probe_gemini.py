"""
probe_gemini.py — A2 probe: Gemini structured output (google-genai 2.x)

Confirms that structured output is *enforced* against a Pydantic schema, not merely
requested. Uses gemini-2.0-flash.

The probe:
  1. Defines a non-trivial Pydantic model (FilmRight) with nested fields, enum, and
     an Optional field.
  2. Sends a prompt that would tempt the model to add free-text commentary.
  3. Prints the raw response and the validated model instance.
  4. Sends a second prompt designed to stress Optional and enum fields.

Output is written to docs/probe_gemini_output.txt and also printed to the terminal.

Run:
    python api/scripts/probe_gemini.py

Requires GEMINI_API_KEY in .env (copy .env.example → .env and fill in the key).
"""

import os
import sys
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()

OUTPUT_FILE = Path(__file__).resolve().parents[2] / "docs" / "probe_gemini_output.txt"

MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Pydantic schema — representative of the shapes used in C1 (extraction agent)
# and C6 (assessment agent).  Deliberately includes:
#   - an enum field (confidence) to test Literal enforcement
#   - an Optional field (notes) to test that absent data stays None, not ""
#   - a nested list (sources) to test nested object enforcement
# ---------------------------------------------------------------------------
class Source(BaseModel):
    url: str
    excerpt: str


class FilmRight(BaseModel):
    title: str                                         # work title
    rights_holder: str                                 # current rights owner
    public_domain: bool                                # True if PD
    confidence: Literal["high", "medium", "low"]       # enforcement target
    sources: list[Source]                              # at least one citation
    notes: Optional[str] = None                        # absent = None, not ""


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
PROMPTS = [
    {
        "label": "STANDARD — well-known rights query",
        # Tempts the model to add a disclaimer sentence before the JSON
        "text": (
            "Identify the current rights holder for the song 'Happy Birthday to You'. "
            "Include at least one source URL with a brief excerpt. "
            "Before answering, please note any caveats about your knowledge cutoff date."
            # ↑ the instruction to add caveats is the temptation to deviate
        ),
    },
    {
        "label": "STRESS — optional + enum edge case",
        # Tempts low-confidence answer with no notes
        "text": (
            "Identify the rights holder for a 1971 experimental short film called "
            "'Wavelength' directed by Michael Snow. "
            "If you are uncertain, say so in the confidence field. "
            "Do not include a notes field if there is nothing to add."
        ),
    },
]


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set. Copy .env.example → .env and fill in your key.")

    client = genai.Client(api_key=api_key)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:

        def emit(text: str = "") -> None:
            print(text)
            f.write(text + "\n")

        for p in PROMPTS:
            emit("\n" + "=" * 72)
            emit(f"PROMPT: {p['label']}")
            emit("=" * 72)
            emit(f"  text: {p['text']}")

            response = client.models.generate_content(
                model=MODEL,
                contents=p["text"],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FilmRight,
                ),
            )

            emit("\n--- raw response.text ---")
            emit(response.text)

            emit("\n--- validated Pydantic model ---")
            validated = FilmRight.model_validate_json(response.text)
            emit(validated.model_dump_json(indent=2))

            emit(f"\n  model used  : {MODEL}")
            emit(f"  usage       : {response.usage_metadata}")

    print(f"\nFull output saved to: {OUTPUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
