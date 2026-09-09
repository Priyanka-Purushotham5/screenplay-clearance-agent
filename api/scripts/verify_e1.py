"""E1 gate: the clearance report renders, and says what it should.

Run from the repo root, inside the api container:

    docker compose exec api python api/scripts/verify_e1.py

No database and no API keys. api/app/report.py is deliberately pure — it
takes dataclasses and returns bytes — so this drives it with fixtures that
cover the cases that actually break a PDF: an ampersand and an angle bracket
in model output, a reviewer override, failed research, an entity with no
sources, and a run with no findings at all.

The assertions read the produced PDF back with pdfplumber rather than
trusting that build_report returned without raising. A report that renders
cleanly and silently omits the rights holders is the failure worth catching,
and only reading the text finds it.
"""

from __future__ import annotations

import io
import sys
from datetime import datetime, timezone

import pdfplumber

sys.path.insert(0, ".")

from api.app.report import (  # noqa: E402
    DISCLAIMER, ReportFinding, ReportRun, ReportSource, build_report,
)

PASS, FAIL = "\033[32m  ok  \033[0m", "\033[31m FAIL \033[0m"
_results: list[bool] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    _results.append(bool(condition))
    print(f"[{PASS if condition else FAIL}] {label}" + (f"  — {detail}" if detail and not condition else ""))


def text_of(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def page_count(pdf_bytes: bytes) -> int:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

FINDINGS = [
    ReportFinding(
        canonical_name="Take On Me",
        surface_form="TAKE ON ME",
        category="music",
        risk="red",
        override_risk=None,
        review_status="unreviewed",
        review_note=None,
        scene_number=4,
        page=7,
        rationale=(
            "Played as source music over the action, which needs both a sync "
            "licence for the composition & a master licence for the recording."
        ),
        rights_required=["Synchronisation licence", "Master use licence"],
        rights_holders=["Warner Chappell Music (publisher)",
                        "Warner Music Group (master)"],
        sources=[ReportSource(
            title="ASCAP repertory",
            url="https://www.ascap.com/repertory#/ace/search/title/Take%20On%20Me",
            excerpt="Writers: Furuholmen, Harket, Waaktaar. Publisher: Warner Chappell.",
        )],
        alternatives=["Commission a soundalike", "Use a production-library cue"],
        research_status="complete",
        queries_run=["Take On Me a-ha publishing rights",
                     "Take On Me master recording owner",
                     "a-ha Warner Chappell catalogue"],
    ),
    # The same song in dialogue — the element_type rule from C6, and the
    # single most demo-relevant pair in the ground truth.
    ReportFinding(
        canonical_name="Take On Me",
        surface_form="that a-ha song",
        category="music",
        risk="green",
        override_risk=None,
        review_status="accepted",
        review_note="Agreed — title reference only.",
        scene_number=11,
        page=19,
        rationale="Referred to by name in dialogue and never heard. Titles are "
                  "not protected by copyright, so no licence arises.",
        rights_required=[],
        rights_holders=[],
        sources=[],
        alternatives=[],
        research_status="complete",
        queries_run=["song title copyright dialogue reference"],
    ),
    ReportFinding(
        canonical_name="Coca-Cola",
        surface_form="a Coke bottle",
        category="trademark",
        risk="amber",
        override_risk="red",
        review_status="overridden",
        review_note="Held to camera for a full beat and the label is legible.",
        scene_number=6,
        page=11,
        rationale="Held to camera in close-up. Prominent branded product "
                  "placement usually needs clearance <or> set dressing.",
        rights_required=["Product placement clearance"],
        rights_holders=["The Coca-Cola Company"],
        sources=[ReportSource(
            title="USPTO TSDR",
            url="https://tsdr.uspto.gov/#caseNumber=71017935",
            excerpt="Registrant: The Coca-Cola Company. Live registration.",
        )],
        alternatives=["Dress with a generic bottle", "Turn the label away"],
        research_status="complete",
        queries_run=["Coca-Cola trademark registration status"],
    ),
    ReportFinding(
        canonical_name="Dr. Alan Reeve",
        surface_form="DR. ALAN REEVE",
        category="person",
        risk="amber",
        override_risk=None,
        review_status="unreviewed",
        review_note=None,
        scene_number=9,
        page=15,
        rationale="A fictional character with a plausible real name. Research "
                  "could not establish whether a living cardiologist of this "
                  "name practises in the film's setting.",
        rights_required=["Name clearance report"],
        rights_holders=[],
        sources=[],
        alternatives=["Change the surname"],
        research_status="failed",
        queries_run=["Dr Alan Reeve cardiologist",
                     "Alan Reeve physician Chicago"],
    ),
]

RUN = ReportRun(
    script_title="The Long Way Down",
    page_count=112,
    scene_count=64,
    run_id="8f1c4a2e-0b77-4b1e-9a3d-2c5e7f901234",
    started_at=datetime(2026, 9, 4, 21, 12, tzinfo=timezone.utc),
    finished_at=datetime(2026, 9, 4, 21, 16, tzinfo=timezone.utc),
    rubric_version="v3",
    findings=FINDINGS,
)

EMPTY_RUN = ReportRun(
    script_title="Nothing To Clear",
    page_count=8, scene_count=3,
    run_id="00000000-0000-0000-0000-000000000000",
    started_at=None, finished_at=None, findings=[],
)


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

print("\n\033[1mE1 · clearance report\033[0m\n")

pdf = build_report(RUN)
body = text_of(pdf)

print("  rendering")
check("returns bytes", isinstance(pdf, bytes) and len(pdf) > 2000, f"{len(pdf)} bytes")
check("is a PDF", pdf[:5] == b"%PDF-")
check("more than one page", page_count(pdf) > 1, f"{page_count(pdf)} pages")

print("\n  cover")
check("script title on the cover", "The Long Way Down" in body)
check("page and scene counts", "112 pages" in body and "64 scenes" in body)
check("review progress", "2 of 4" in body, "expected '2 of 4' reviewed")
check("rubric version recorded", "v3" in body)
check("disclaimer present", DISCLAIMER.split(".")[0] in body)

print("\n  findings")
check("every entity appears",
      all(n in body for n in ["Take On Me", "Coca-Cola", "Dr. Alan Reeve"]))
check("category sections", "Music" in body and "Trademarks and brands" in body)
check("music sorts before trademark",
      body.index("Music") < body.index("Trademarks and brands"))
check("scene and page cited", "scene 4" in body and "p.7" in body)
check("rights required listed", "Synchronisation licence" in body)
check("rights holders listed", "Warner Chappell Music" in body)
check("sources with excerpts", "ASCAP repertory" in body and "Furuholmen" in body)
check("alternatives listed", "Commission a soundalike" in body)

print("\n  the parts that are easy to lose")
check("D6 · searches printed", "Take On Me master recording owner" in body)
check("failed research flagged", "Research failed" in body)
check("override shows the reviewer's rating",
      "RED" in body and "Reviewer set this to" in body)
check("override keeps the model's rating visible", "the model rated it AMBER" in body)
check("reviewer note carried", "legible" in body)
check("ampersand survived escaping", "sync licence for the composition & a master" in body
      or "composition & a master" in body)
check("angle brackets survived escaping", "clearance <or> set dressing" in body)
check("an entity with no sources still renders", "that a-ha song" in body)

print("\n  effective risk")
# Coca-Cola is AMBER overridden to RED. The cover bar and the section ordering
# must both count it as RED, or the summary disagrees with its own body.
check("override counted as red on the cover", "2 red" in body,
      "expected the override to move Coca-Cola into the red count")

print("\n  empty run")
empty = build_report(EMPTY_RUN)
empty_text = text_of(empty)
check("renders without findings", empty[:5] == b"%PDF-")
check("says so plainly", "No findings" in empty_text)
check("does not claim a clean bill", "failed part-way" in empty_text)

total, passed = len(_results), sum(_results)
print(f"\n\033[1m{passed}/{total} checks passed\033[0m\n")
sys.exit(0 if passed == total else 1)
