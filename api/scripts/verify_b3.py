"""B3 smoke-test — text-layer detection at the upload boundary.

Start the stack first (docker compose up -d), then from the repo root:

    python api/scripts/verify_b3.py

Fixtures live in docs/ and are committed; api/scripts/make_scanned_pdf.py
regenerates them if they are ever lost.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
API = os.environ.get("API_URL", "http://localhost:8080").rstrip("/")
DOCS = ROOT / "docs"

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def salted(path: Path) -> bytes:
    """Unique bytes per run, so dedup never masks the case under test."""
    return path.read_bytes() + b"\n%% verify_b3 " + os.urandom(8).hex().encode() + b"\n"


def upload(client: httpx.Client, path: Path) -> httpx.Response:
    return client.post(
        "/api/scripts",
        files={"file": (path.name, salted(path), "application/pdf")},
    )


def main() -> int:
    real = DOCS / "test_screenplay.pdf"
    scanned = DOCS / "scanned_screenplay.pdf"
    hybrid = DOCS / "hybrid_screenplay.pdf"
    for f in (real, scanned, hybrid):
        if not f.exists():
            print(f"Fixture missing: {f}\nRun: python api/scripts/make_scanned_pdf.py")
            return 2

    from api.app.parser.pdf import inspect_pdf  # noqa: PLC0415

    r_real, r_scan, r_hyb = (inspect_pdf(f) for f in (real, scanned, hybrid))
    print(f"\ninspect_pdf: real mean={r_real.mean_chars}  "
          f"scanned mean={r_scan.mean_chars}  hybrid mean={r_hyb.mean_chars}\n")

    check("Text screenplay has a text layer", r_real.has_text_layer,
          f"mean={r_real.mean_chars} chars/page")
    check("Scanned PDF has no text layer", not r_scan.has_text_layer,
          f"mean={r_scan.mean_chars} chars/page")
    check("Scanned PDF flags every page", r_scan.low_text_pages == [1, 2, 3],
          f"low_text_pages={r_scan.low_text_pages}")
    check("Hybrid still passes the gate", r_hyb.has_text_layer,
          f"mean={r_hyb.mean_chars} chars/page")
    check("Hybrid names the image page", r_hyb.low_text_pages == [2],
          f"low_text_pages={r_hyb.low_text_pages}")
    check("Clean script produces no warnings", r_real.warnings() == [])
    check("Hybrid produces one warning", len(r_hyb.warnings()) == 1,
          r_hyb.warnings()[0][:60] if r_hyb.warnings() else "none")

    with httpx.Client(base_url=API, timeout=120.0) as c:
        r = upload(c, scanned)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        check("Scanned upload rejected with 422", r.status_code == 422, str(r.status_code))
        check("422 body has code NO_TEXT_LAYER at the top level",
              body.get("code") == "NO_TEXT_LAYER", str(body)[:90])
        check("422 body carries pages_checked", isinstance(body.get("pages_checked"), int),
              f"pages_checked={body.get('pages_checked')}")
        check("422 detail is a human sentence", isinstance(body.get("detail"), str)
              and len(body.get("detail", "")) > 20)

        same_bytes = salted(scanned)
        a = c.post("/api/scripts", files={"file": ("scan.pdf", same_bytes, "application/pdf")})
        b = c.post("/api/scripts", files={"file": ("scan.pdf", same_bytes, "application/pdf")})
        check("Rejected scan was never stored (identical re-upload still 422)",
              a.status_code == 422 and b.status_code == 422,
              f"first={a.status_code} second={b.status_code}")

        r3 = upload(c, hybrid)
        b3 = r3.json()
        check("Hybrid upload accepted with 201", r3.status_code == 201, str(r3.status_code))
        check("Hybrid response carries the parse warning",
              len(b3.get("parse_warnings", [])) == 1,
              str(b3.get("parse_warnings"))[:70])

        r4 = upload(c, real)
        check("Clean script still accepted with no warnings",
              r4.status_code == 201 and r4.json().get("parse_warnings") == [],
              f"{r4.status_code} {r4.json().get('parse_warnings')}")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())