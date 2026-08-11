"""
probe_gemini_pdf.py — A2 probe: Gemini PDF byte ingestion (google-genai 2.x)

Sends PDF bytes directly to Gemini (gemini-2.0-flash) and confirms it can read them.
This is the fallback path for B2 (page extraction) if pdfplumber disappoints.

The probe:
  1. Reads the PDF from the path given on the command line.
  2. Sends the bytes inline as a Part (for files ≤ ~20 MB).
  3. Asks Gemini to extract all scene headings as a JSON list.
  4. Prints the raw response text.
  5. Reports the file size so the inline-vs-upload threshold is observable.

Run:
    python api/scripts/probe_gemini_pdf.py <path-to-pdf>

Requires GEMINI_API_KEY in .env (copy .env.example → .env and fill in the key).

Notes on inline size limit:
  - google-genai 2.x accepts inline bytes up to ~20 MB via Part.from_bytes().
  - For larger files use client.files.upload() which stages to a temporary GCS URL.
  - This probe uses inline bytes; if your PDF is > 20 MB the API will return an error —
    note the exact error message in docs/api-notes.md.
"""

import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = "gemini-2.5-flash"

PROMPT = (
    "This is a screenplay PDF. "
    "Extract every scene heading (lines starting with INT. or EXT. or I/E.) "
    "and return them as a JSON array of strings — nothing else, no commentary. "
    "Example format: [\"INT. OFFICE - DAY\", \"EXT. STREET - NIGHT\"]"
)


OUTPUT_FILE = Path(__file__).resolve().parents[2] / "docs" / "probe_gemini_pdf_output.txt"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python api/scripts/probe_gemini_pdf.py <path-to-pdf>")

    pdf_path = sys.argv[1]
    if not os.path.isfile(pdf_path):
        raise SystemExit(f"File not found: {pdf_path}")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set. Copy .env.example → .env and fill in your key.")

    pdf_bytes = open(pdf_path, "rb").read()
    size_kb = len(pdf_bytes) / 1024

    client = genai.Client(api_key=api_key)
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:

        def emit(text: str = "") -> None:
            print(text)
            f.write(text + "\n")

        emit(f"PDF: {pdf_path}  ({size_kb:.1f} KB)")
        emit("Sending inline as Part.from_bytes() — limit ~20 MB")
        emit(f"\nPrompt: {PROMPT}\n")
        emit("=" * 72)

        response = client.models.generate_content(
            model=MODEL,
            contents=[pdf_part, PROMPT],
        )

        emit("--- raw response.text ---")
        emit(response.text)

        # Strip markdown fences — model wraps JSON in ```json``` even without response_schema
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", response.text.strip())

        emit("\n--- parsed JSON (fence-stripped) ---")
        try:
            headings = json.loads(raw)
            emit(f"  type    : {type(headings).__name__}")
            emit(f"  count   : {len(headings)}")
            for i, h in enumerate(headings, 1):
                emit(f"  [{i:02d}] {h}")

            # Post-filter: only real INT./EXT./I/E. headings
            HEADING_RE = re.compile(r"^(INT\.|EXT\.|I/E\.|INT\./EXT\.)", re.IGNORECASE)
            real = [h for h in headings if HEADING_RE.match(h)]
            emit(f"\n--- post-filtered (INT/EXT/I/E only) ---")
            emit(f"  count    : {len(real)}")
            for i, h in enumerate(real, 1):
                emit(f"  [{i:02d}] {h}")
            if len(headings) != len(real):
                dropped = [h for h in headings if not HEADING_RE.match(h)]
                emit(f"\n  ⚠ dropped (mini-slugs/false positives): {dropped}")
        except json.JSONDecodeError as e:
            emit(f"  Response is not valid JSON even after fence-strip: {e}")
            emit(f"  Raw text was: {raw[:200]}")

        emit(f"\n  model used : {MODEL}")
        emit(f"  file size  : {size_kb:.1f} KB")
        emit(f"  usage      : {response.usage_metadata}")

    print(f"\nFull output saved to: {OUTPUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
