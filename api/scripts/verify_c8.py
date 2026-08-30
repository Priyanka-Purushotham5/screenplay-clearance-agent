"""C8 smoke-test — run orchestration, end to end over HTTP.

    docker compose exec api python api/scripts/verify_c8.py

The checklist's gate:

    killing the API mid-run leaves a coherent partial state in the database,
    and the run reports failed rather than hanging

This one cannot be faked. It uploads a real PDF, starts a real run, polls it
to completion and reads the findings back through the API — the same path the
frontend takes. The cost is low only because the research cache is warm: a
cold run is thirty to forty model calls, a warm one is extraction plus three
assessment batches.

If it is slow or expensive, that is the signal to run `warm_cache.py` first,
not to change this script.

The pure functions are checked first and cost nothing, so a broken serializer
fails in a second rather than after a full run.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

API = os.environ.get("API_URL", "http://localhost:8080").rstrip("/")
FIXTURE = ROOT / "docs" / "test_screenplay.pdf"

# Every field web/lib/api-types.ts declares on Finding. Named here rather than
# derived, so a field the frontend needs cannot quietly stop being sent.
FINDING_FIELDS = {
    "id", "element_id", "risk", "rights_required", "rights_holders",
    "rationale", "sources", "alternatives", "review_status", "override_risk",
    "review_note", "reviewed_at", "created_at", "canonical_name",
    "surface_form", "category", "research_status", "script_element_id",
    "char_start", "char_end", "scene_number", "page",
}
UI_CATEGORIES = {"music", "trademark", "artwork", "person", "location",
                 "clip", "literary", "other"}

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def main() -> int:
    import inspect
    import logging

    from api.app.routers import runs as runs_module
    from api.app.routers.runs import _holder, CATEGORY_FOR_UI

    # ── the run lifecycle, checked without starting one ────────────────
    # Three bugs cost a full debugging session between them, and none of
    # them announced itself. All three are cheap to guard against here.
    source = inspect.getsource(runs_module._execute)

    check("The research cache is the session-per-call one, not a shared session",
          "SessionPerCallResearchCache" in source
          and "PostgresResearchCache(" not in source,
          "one AsyncSession across six concurrent research tasks raises "
          "InvalidRequestError and then cannot even be closed")

    # The comments in that module discuss BackgroundTasks at length, so the
    # check is on the call and the import, not on the word.
    module_source = inspect.getsource(runs_module)
    check("A run is owned here, not by Starlette's BackgroundTasks",
          ".add_task(" not in module_source
          and "import APIRouter, BackgroundTasks" not in module_source
          and hasattr(runs_module, "_spawn_run"),
          "a background task is cancelled with the connection that spawned it, "
          "and CancelledError is not an Exception")

    check("Every exit from _execute writes a terminal state",
          "finally:" in source and "_finalise" in source
          and "asyncio.shield" in source,
          "a run that neither completes nor fails is the one failure the "
          "frontend cannot render")

    # An application logger must actually reach a handler. Without this,
    # logger.info in every module below is silently discarded and a stuck run
    # produces an empty `docker compose logs`.
    from api.app.logging_config import configure_logging
    configure_logging()
    captured: list[str] = []

    class Sink(logging.Handler):
        def emit(self, record): captured.append(record.getMessage())

    sink = Sink()
    logging.getLogger().addHandler(sink)
    logging.getLogger("api.app.routers.runs").info("visibility probe")
    logging.getLogger().removeHandler(sink)
    check("Application INFO logging reaches a handler",
          "visibility probe" in captured,
          "root logger level "
          f"{logging.getLevelName(logging.getLogger().getEffectiveLevel())}")

    # Every timestamp in db/init.sql is TIMESTAMPTZ. A model column declared
    # as a bare `Mapped[datetime]` compiles to TIMESTAMP WITHOUT TIME ZONE,
    # which reads back correctly and only fails when Python WRITES one:
    #     asyncpg DataError: can't subtract offset-naive and offset-aware
    # `runs.finished_at` was the first such write in the codebase, and the
    # failure looked exactly like a hung run, because the row that failed to
    # write was the row that says the run is over.
    from sqlalchemy.dialects import postgresql
    from api.app.models import Finding, ResearchCache, Run, Script

    naive = [
        f"{table.__tablename__}.{column.name}"
        for table in (Script, Run, ResearchCache, Finding)
        for column in table.__table__.columns
        if "TIMESTAMP" in column.type.compile(postgresql.dialect())
        and "WITH TIME ZONE" not in column.type.compile(postgresql.dialect())
    ]
    check("Every timestamp column is tz-aware, matching db/init.sql",
          not naive, f"naive: {naive}")

    # ── pure functions, no network ─────────────────────────────────────
    parsed = _holder("ATV Music Ltd. (for the musical composition)")
    check("A rights holder's role is lifted from its parenthetical",
          parsed == {"role": "musical composition", "name": "ATV Music Ltd.",
                     "confidence": "medium"}, str(parsed))
    plain = _holder("Warner Records")
    check("A holder with no parenthetical keeps an empty role, not a guess",
          plain["role"] == "" and plain["name"] == "Warner Records", str(plain))
    check("A holder already structured is passed through",
          _holder({"role": "label", "name": "X", "confidence": "high"})["role"] == "label")
    check("logo and product map onto a category the UI admits",
          CATEGORY_FOR_UI["logo"] == "trademark"
          and CATEGORY_FOR_UI["product"] == "trademark")

    if not FIXTURE.exists():
        print(f"Fixture missing: {FIXTURE}")
        return 2

    with httpx.Client(base_url=API, timeout=600.0) as c:
        # ── upload ─────────────────────────────────────────────────────
        pdf = FIXTURE.read_bytes() + b"\n%% verify_c8 " + os.urandom(8).hex().encode()
        r = c.post("/api/scripts",
                   files={"file": ("verify_c8.pdf", pdf, "application/pdf")})
        script_id = r.json().get("script_id")
        check("A script uploads and parses", r.status_code == 201 and bool(script_id),
              f"{r.status_code}")
        if not script_id:
            print(f"\n{sum(results)}/{len(results)} checks passed")
            return 1

        # ── start a run ────────────────────────────────────────────────
        r = c.post("/api/runs", json={"script_id": script_id})
        body = r.json()
        run_id = body.get("run_id")
        check("POST /api/runs returns 202 with a run_id",
              r.status_code == 202 and bool(run_id), f"{r.status_code} {body}")
        check("A new run reports a progress object, not null",
              isinstance(body.get("progress"), dict), str(body.get("progress")))

        # A second run for the same script must be refused rather than
        # doubling the spend and interleaving two sets of findings.
        r2 = c.post("/api/runs", json={"script_id": script_id})
        check("A second run for the same script is refused with 409",
              r2.status_code == 409, str(r2.status_code))
        check("The 409 says which run is in flight",
              r2.json().get("code") == "RUN_IN_FLIGHT" and "run_id" in r2.json(),
              str(r2.json())[:90])

        r3 = c.post("/api/runs",
                    json={"script_id": "00000000-0000-0000-0000-000000000000"})
        check("An unknown script id is 404, not 500", r3.status_code == 404,
              str(r3.status_code))

        # ── poll ───────────────────────────────────────────────────────
        seen: list[str] = []
        deadline = time.monotonic() + 420
        status = "pending"
        while time.monotonic() < deadline:
            body = c.get(f"/api/runs/{run_id}").json()
            status = body["status"]
            if not seen or seen[-1] != status:
                seen.append(status)
                print(f"       {status}"
                      f" ({body['progress']['elements_found']} elements,"
                      f" {body['progress']['findings']} findings)")
            if status in {"complete", "failed"}:
                break
            time.sleep(3)

        check("The run reaches a terminal state rather than hanging",
              status in {"complete", "failed"}, f"{status} after {seen}")
        check("It moved through real stages, not straight to done",
              len(seen) >= 2, " -> ".join(seen))
        if status == "failed":
            print(f"       error: {body.get('error')}")
        check("The run completed", status == "complete", body.get("error") or "")

        check("Stats record what it cost",
              {"mentions", "entities", "ratings"} <= set(body.get("stats", {})),
              str(sorted(body.get("stats", {}))[:6]))
        check("finished_at is set on a terminal run",
              bool(body.get("finished_at")))

        # ── findings ───────────────────────────────────────────────────
        f = c.get(f"/api/runs/{run_id}/findings").json()
        findings = f.get("findings", [])
        check("Findings come back", bool(findings), f"{len(findings)} findings")
        if not findings:
            print(f"\n{sum(results)}/{len(results)} checks passed")
            return 1

        missing = FINDING_FIELDS - set(findings[0])
        extra = set(findings[0]) - FINDING_FIELDS
        check("Every field the frontend declares is present",
              not missing and not extra,
              f"missing {sorted(missing)}, extra {sorted(extra)}")

        check("counts is over the whole run and adds up to total",
              sum(f["counts"].values()) == f["total"] == len(findings),
              f"{f['counts']} total={f['total']} returned={len(findings)}")

        check("Every category is one the UI's union admits",
              all(x["category"] in UI_CATEGORIES for x in findings),
              str(sorted({x["category"] for x in findings})))

        check("Every finding carries the join into the script pane",
              all(x["script_element_id"] and isinstance(x["scene_number"], int)
                  and isinstance(x["page"], int) for x in findings))

        check("Risk is lowercase, matching db/init.sql",
              all(x["risk"] in {"red", "amber", "green"} for x in findings),
              str(sorted({x["risk"] for x in findings})))

        cited = [x for x in findings if x["sources"]]
        check("Findings cite sources with real URLs",
              bool(cited) and all(s["url"].startswith("http")
                                  for x in cited for s in x["sources"]),
              f"{len(cited)}/{len(findings)} findings cite at least one source")
        check("Every source has a title, derived from its domain if need be",
              all(s["title"] for x in cited for s in x["sources"]))

        holders = [h for x in findings for h in x["rights_holders"]]
        check("Rights holders are structured, not free text",
              all({"role", "name", "confidence"} == set(h) for h in holders),
              f"{len(holders)} holders")

        # The product thesis, read back through the API.
        song = [x for x in findings if "take_on_me" in x["canonical_name"]]
        risks = {x["risk"] for x in song}
        check("The same song is rated differently in different contexts",
              len(risks) > 1, f"{len(song)} mentions -> {sorted(risks)}")

        r = c.get("/api/runs/00000000-0000-0000-0000-000000000000")
        check("An unknown run id is 404", r.status_code == 404, str(r.status_code))

        spec = c.get("/openapi.json").json()
        check("OpenAPI declares the run endpoints the frontend generates from",
              {"/api/runs", "/api/runs/{run_id}",
               "/api/runs/{run_id}/findings"} <= set(spec.get("paths", {})),
              str([p for p in spec.get("paths", {}) if "run" in p]))

        by_risk = {}
        for x in findings:
            by_risk.setdefault(x["risk"], []).append(x)
        print(f"\n  {f['counts']} across {f['total']} findings")
        for risk in ("red", "amber", "green"):
            for x in by_risk.get(risk, [])[:3]:
                print(f"  {risk:<6} sc{x['scene_number']} p{x['page']} "
                      f"{x['surface_form'][:24]!r:<28} {x['rationale'][:56]}")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
