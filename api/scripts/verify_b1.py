"""B1 smoke-test — every done-when from the checklist, plus the frontend contract.

Uses docs/test_screenplay.pdf as the happy-path fixture, salted with a few
random bytes per run so the SHA-256 is unique. Without that, the second run
against the same database sees its own first upload as a duplicate and the
"duplicate_of is null on a first upload" check fails, a test isolation bug,
not a product bug. The salt is a PDF comment appended after %%EOF, which
readers ignore; page_count is unaffected.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
API = os.environ.get("API_URL", "http://localhost:8080").rstrip("/")
FIXTURE = ROOT / "docs" / "test_screenplay.pdf"

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def body(r: httpx.Response) -> dict:
    try:
        return r.json()
    except Exception:
        return {}


def main() -> int:
    if not FIXTURE.exists():
        print(f"Fixture missing: {FIXTURE}")
        return 2
    # Salt the fixture so every run uploads content this database has never
    # seen. Trailing bytes after %%EOF are ignored by PDF readers.
    pdf = FIXTURE.read_bytes() + b"\n%% verify_b1 " + os.urandom(8).hex().encode() + b"\n"

    with httpx.Client(base_url=API, timeout=120.0) as c:
        r = c.get("/health")
        check("GET /health returns ok", r.status_code == 200 and body(r).get("ok") is True,
              str(r.status_code))

        # checklist: curl uploads a PDF and gets a script_id
        r = c.post("/api/scripts", files={"file": ("test_screenplay.pdf", pdf, "application/pdf")})
        b = body(r)
        sid = b.get("script_id")
        check("PDF upload returns 201 with a script_id", r.status_code == 201 and bool(sid),
              f"{r.status_code} script_id={sid}")
        check("page_count is a real count", bool(b.get("page_count")),
              f"page_count={b.get('page_count')}")
        check("duplicate_of is null on a first upload", b.get("duplicate_of") is None)
        check("response has exactly the frontend's Script fields",
              set(b) == {"script_id", "title", "source_format", "page_count",
                         "scene_count", "parse_warnings", "duplicate_of"},
              f"got {sorted(b)}")

        # checklist: re-uploading the same file returns the same id =
        r2 = c.post("/api/scripts", files={"file": ("renamed_copy.pdf", pdf, "application/pdf")})
        b2 = body(r2)
        check("Re-upload returns 201 (the upload screen only accepts 201)",
              r2.status_code == 201, str(r2.status_code))
        check("Re-upload returns the same script_id", b2.get("script_id") == sid,
              f"{b2.get('script_id')}")
        check("Duplicate sets duplicate_of", b2.get("duplicate_of") == sid,
              f"duplicate_of={b2.get('duplicate_of')}")

        # checklist: a 30 MB file gets 413
        big = b"%PDF-1.4\n" + os.urandom(30 * 1024 * 1024)
        r3 = c.post("/api/scripts", files={"file": ("huge.pdf", io.BytesIO(big), "application/pdf")})
        check("30 MB upload rejected with 413", r3.status_code == 413, str(r3.status_code))
        check("413 body is flat {code, detail}",
              isinstance(body(r3).get("detail"), str) and body(r3).get("code") == "FILE_TOO_LARGE",
              str(body(r3))[:80])

        # checklist: a .docx gets 415 (magic bytes, not extension)
        fake_docx = b"PK\x03\x04" + b"\x00" * 2048
        r4 = c.post("/api/scripts", files={"file": ("resume.pdf", fake_docx, "application/pdf")})
        check("Non-PDF bytes rejected with 415 even when named .pdf",
              r4.status_code == 415, str(r4.status_code))
        check("415 body is flat {code, detail}",
              isinstance(body(r4).get("detail"), str) and body(r4).get("code") == "UNSUPPORTED_TYPE",
              str(body(r4))[:80])

        # corrupt PDF
        r5 = c.post("/api/scripts",
                    files={"file": ("corrupt.pdf", b"%PDF-1.7\n" + b"junk" * 100, "application/pdf")})
        check("Corrupt PDF rejected with 422", r5.status_code == 422, str(r5.status_code))

        # read back
        r6 = c.get(f"/api/scripts/{sid}")
        check("GET /api/scripts/{id} returns the row", r6.status_code == 200, str(r6.status_code))
        r7 = c.get("/api/scripts/00000000-0000-0000-0000-000000000000")
        check("Unknown script id returns 404", r7.status_code == 404, str(r7.status_code))

        # the OpenAPI schema the frontend generates from
        r8 = c.get("/openapi.json")
        spec = body(r8)
        paths = set(spec.get("paths", {}))
        check("OpenAPI declares /api/scripts and /api/scripts/{id}",
              {"/api/scripts", "/api/scripts/{id}"} <= paths,
              f"paths={sorted(paths)}")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())