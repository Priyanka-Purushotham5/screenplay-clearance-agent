"""The clearance report — a run, rendered as the document a producer files.

This is the deliverable the rest of the pipeline exists to produce. Everything
upstream ends at a database row; a production company's clearance process ends
at a PDF that goes to a distributor, an E&O insurer, or counsel. Handing them
a web app and a login is not the same thing, and it is not what anyone in that
chain will accept.

Three decisions worth stating, because they are the ones a reviewer will
notice:

RIGHTS-HOLDER BULLETS, NOT PROSE. Each finding lists what has to be cleared
and who is likely to hold it as separate lines. A paragraph reads better and
is useless to work from: clearance is a task list, and someone will tick these
off one at a time over weeks.

SOURCES CARRY THEIR EXCERPTS. A bare URL asks the reader to go and re-do the
research; the excerpt is what the agent actually read, so a reviewer can judge
the claim without leaving the page. The queries follow for the same reason —
they say what was looked for, which is the only way to read an absence of
findings as evidence rather than as silence.

THE OVERRIDE WINS, AND SAYS SO. Where a reviewer disagreed with the model the
report leads with the reviewer's rating and prints the model's underneath,
struck through, with the note. A clearance document that quietly replaced a
human decision with a machine's would be worse than useless; one that hides
that a human overrode it is just as bad.

Rendering is pure and synchronous: `build_report` takes plain dataclasses and
returns bytes, so it can be exercised without a database or an event loop —
which is how the fixtures in api/scripts/verify_e1.py test it. The router does
the querying and runs this in a worker thread, the same way scripts.py treats
pdfplumber.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

DISCLAIMER = (
    "Not a legal determination. This report is machine-generated research "
    "intended for review by qualified counsel, and no part of it should be "
    "relied on as clearance advice."
)

# The same three values the UI uses, not a separate print palette.
#
# There used to be one here, because the app's old ratings were picked to read
# on a near-black screen and went muddy on paper. The current three were chosen
# against BOTH grounds (3.98:1, 3.01:1 and 3.02:1 on white), so the report and
# the screen can finally agree. A reviewer comparing a printed page against the
# findings pane should not have to wonder whether two different ambers mean two
# different things.
RISK_COLOUR = {
    "red": colors.HexColor("#FF0022"),
    "amber": colors.HexColor("#E27900"),
    "green": colors.HexColor("#00AB56"),
}
INK = colors.HexColor("#14181c")
MUTED = colors.HexColor("#5b666f")
RULE = colors.HexColor("#c9d1d6")
PANEL = colors.HexColor("#f2f5f6")

# The order sections appear in. Deliberately not alphabetical and not by
# volume: it is roughly descending cost-and-lead-time to clear. Music sits
# first because sync and master licences are the two that most often come back
# months later and force a re-cut, so they are what a producer needs to start
# on today.
CATEGORY_ORDER = [
    "music", "clip", "artwork", "literary",
    "trademark", "person", "location", "other",
]
CATEGORY_TITLE = {
    "music": "Music",
    "clip": "Film and television clips",
    "artwork": "Artwork and design",
    "literary": "Literary and quoted text",
    "trademark": "Trademarks and brands",
    "person": "Names and likenesses",
    "location": "Locations and venues",
    "other": "Other",
}

RISK_RANK = {"red": 0, "amber": 1, "green": 2}


# ---------------------------------------------------------------------------
# input
#
# Plain dataclasses rather than the SQLAlchemy rows or the Pydantic wire
# models. The report should not care which of those it came from, and taking
# ORM objects would mean a lazy load could fire inside the worker thread —
# on a session owned by the event loop that is no longer running.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportSource:
    title: str
    url: str
    excerpt: str


@dataclass(frozen=True)
class ReportFinding:
    canonical_name: str
    surface_form: str
    category: str
    risk: str
    override_risk: Optional[str]
    review_status: str
    review_note: Optional[str]
    scene_number: int
    page: int
    rationale: str
    rights_required: list[str]
    rights_holders: list[str]
    sources: list[ReportSource]
    alternatives: list[str]
    research_status: str
    queries_run: list[str]

    @property
    def effective_risk(self) -> str:
        """What this finding actually rates, once a reviewer has had their say.

        Everything that sorts, counts or colours reads this rather than
        `risk`, so an override moves the finding in the report exactly as it
        moves it in the UI. A report whose summary disagreed with its own body
        would be the first thing anyone noticed.
        """
        return self.override_risk or self.risk


@dataclass(frozen=True)
class ReportRun:
    script_title: str
    page_count: int
    scene_count: int
    run_id: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    rubric_version: str = ""
    findings: list[ReportFinding] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {"red": 0, "amber": 0, "green": 0}
        for f in self.findings:
            if f.effective_risk in out:
                out[f.effective_risk] += 1
        return out

    def reviewed(self) -> int:
        return sum(1 for f in self.findings if f.review_status != "unreviewed")


# ---------------------------------------------------------------------------
# small flowables
# ---------------------------------------------------------------------------


class RiskBar(Flowable):
    """The three counts as one proportional bar.

    A stacked bar rather than three numbers in a row because the useful fact
    is the ratio — 6 red out of 84 is a manageable afternoon, 6 red out of 9
    is a different film. Numbers alone make the reader do that division; the
    bar has already done it. The counts are printed inside each band, so the
    bar never becomes the only place a number appears.
    """

    def __init__(self, counts: dict[str, int], width: float, height: float = 26):
        super().__init__()
        self.counts = counts
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        total = sum(self.counts.values())
        if total == 0:
            c.setFillColor(PANEL)
            c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 9)
            c.drawString(8, self.height / 2 - 3, "No findings in this run")
            return
        x = 0.0
        for risk in ("red", "amber", "green"):
            n = self.counts.get(risk, 0)
            if n == 0:
                continue
            w = self.width * n / total
            c.setFillColor(RISK_COLOUR[risk])
            c.rect(x, 0, w, self.height, stroke=0, fill=1)
            # Only label a band wide enough to hold the text. A number half
            # outside its own colour reads as belonging to the next one.
            label = f"{n} {risk}"
            c.setFont("Helvetica-Bold", 9)
            if c.stringWidth(label, "Helvetica-Bold", 9) + 12 <= w:
                c.setFillColor(colors.white)
                c.drawString(x + 6, self.height / 2 - 3, label)
            x += w


class Rule(Flowable):
    """A hairline. Thinner than reportlab's HRFlowable default, which prints heavy."""

    def __init__(self, width: float, colour=RULE, thickness: float = 0.5):
        super().__init__()
        self.width = width
        self.height = thickness
        self.colour = colour
        self.thickness = thickness

    def draw(self):
        self.canv.setStrokeColor(self.colour)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.width, 0)


# ---------------------------------------------------------------------------
# styles
# ---------------------------------------------------------------------------


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]
    def s(name, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, parent=base, **kw)

    return {
        "cover_title": s("cover_title", fontName="Helvetica-Bold", fontSize=26,
                         leading=30, textColor=INK, spaceAfter=6),
        "cover_sub": s("cover_sub", fontName="Helvetica", fontSize=11.5,
                       leading=16, textColor=MUTED),
        "h1": s("h1", fontName="Helvetica-Bold", fontSize=15, leading=19,
                textColor=INK, spaceBefore=4, spaceAfter=2),
        "h2": s("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                textColor=INK, spaceAfter=1),
        "body": s("body", fontName="Helvetica", fontSize=9.5, leading=13.5,
                  textColor=INK, alignment=TA_LEFT),
        "muted": s("muted", fontName="Helvetica", fontSize=8.5, leading=12,
                   textColor=MUTED),
        "label": s("label", fontName="Helvetica-Bold", fontSize=7.5, leading=10,
                   textColor=MUTED),
        "mono": s("mono", fontName="Courier", fontSize=8, leading=11.5,
                  textColor=MUTED),
        "quote": s("quote", fontName="Helvetica-Oblique", fontSize=8.5,
                   leading=12, textColor=INK, leftIndent=8),
        "disclaimer": s("disclaimer", fontName="Helvetica-Oblique", fontSize=8.5,
                        leading=12, textColor=MUTED),
    }


def _esc(text: str) -> str:
    """Escape for reportlab's mini-HTML paragraph parser.

    Every string in here is model output or scraped page text, so an unescaped
    `&` or `<` is not hypothetical — one raises a paragraph parse error and
    takes the whole report down with it. This is the same reason the UI never
    interpolates these fields as HTML.
    """
    return html.escape(text or "", quote=False)


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------


def _cover(run: ReportRun, st: dict, width: float) -> list:
    counts = run.counts()
    total = len(run.findings)
    when = run.finished_at or run.started_at

    out: list = [
        Spacer(1, 0.9 * inch),
        Paragraph("Rights clearance report", st["cover_title"]),
        Paragraph(_esc(run.script_title), st["cover_sub"]),
        Spacer(1, 0.35 * inch),
        Rule(width),
        Spacer(1, 0.28 * inch),
        Paragraph("FINDINGS BY RISK", st["label"]),
        Spacer(1, 5),
        RiskBar(counts, width),
        Spacer(1, 0.3 * inch),
    ]

    meta = [
        ("Screenplay", f"{run.page_count} pages · {run.scene_count} scenes"),
        ("Findings", f"{total} across {len({f.canonical_name for f in run.findings})} entities"),
        ("Reviewed", f"{run.reviewed()} of {total}"),
        ("Run", run.run_id),
        ("Completed", when.strftime("%d %B %Y at %H:%M UTC") if when else "not recorded"),
    ]
    if run.rubric_version:
        meta.append(("Rubric", run.rubric_version))

    table = Table(
        [[Paragraph(k.upper(), st["label"]), Paragraph(_esc(v), st["body"])]
         for k, v in meta],
        colWidths=[1.5 * inch, width - 1.5 * inch],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    # The cover has no running footer; everything after it does. The switch
    # has to be queued BEFORE the page break that lands on the first body
    # page, which is what NextPageTemplate does.
    out += [table, Spacer(1, 0.45 * inch), Rule(width), Spacer(1, 8),
            Paragraph(DISCLAIMER, st["disclaimer"]),
            NextPageTemplate("body"), PageBreak()]
    return out


def _finding_block(f: ReportFinding, st: dict, width: float) -> list:
    """One finding. Wrapped in KeepTogether by the caller.

    Laid out as a task rather than a record: the rating and what it applies to
    first, then what has to be cleared and who from, then the reasoning, then
    the evidence. A reader working through a list of eighty of these needs the
    first two lines to be enough to triage, and the rest to be there when one
    of them stops them.
    """
    risk = f.effective_risk
    colour = RISK_COLOUR.get(risk, MUTED)

    heading = Table(
        [[
            # hexval() gives '0xa5252b'; reportlab's paragraph markup wants
            # '#a5252b'.
            Paragraph(
                f'<font color="#{colour.hexval()[2:]}"><b>{risk.upper()}</b></font>',
                st["h2"],
            ),
            Paragraph(f"<b>{_esc(f.canonical_name)}</b>", st["h2"]),
            Paragraph(f"scene {f.scene_number} · p.{f.page}", st["muted"]),
        ]],
        colWidths=[0.72 * inch, width - 2.32 * inch, 1.6 * inch],
        hAlign="LEFT",
    )
    heading.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    out: list = [heading]

    if f.surface_form and f.surface_form.strip() != f.canonical_name.strip():
        out.append(Paragraph(f'appears as "{_esc(f.surface_form)}"', st["muted"]))

    # An override is the single most important thing on the block when it is
    # present: it is a person's decision replacing a machine's. It goes above
    # the rationale, because the rationale below argues for the rating the
    # reviewer just rejected.
    if f.override_risk and f.override_risk != f.risk:
        out += [Spacer(1, 3), Paragraph(
            f"Reviewer set this to <b>{f.override_risk.upper()}</b>; "
            f"the model rated it {f.risk.upper()}."
            + (f" Note: {_esc(f.review_note)}" if f.review_note else ""),
            st["muted"])]
    elif f.review_status == "accepted":
        out += [Spacer(1, 3), Paragraph("Reviewed and accepted." + (
            f" Note: {_esc(f.review_note)}" if f.review_note else ""), st["muted"])]

    if f.research_status != "complete":
        out += [Spacer(1, 3), Paragraph(
            f"<b>Research {f.research_status}.</b> Needs manual review.",
            st["muted"])]

    out += [Spacer(1, 6), Paragraph(_esc(f.rationale), st["body"])]

    if f.rights_required:
        out += [Spacer(1, 6), Paragraph("RIGHTS REQUIRED", st["label"])]
        out += [Paragraph(f"• {_esc(r)}", st["body"]) for r in f.rights_required]

    if f.rights_holders:
        out += [Spacer(1, 5), Paragraph("LIKELY RIGHTS HOLDERS", st["label"])]
        out += [Paragraph(f"• {_esc(h)}", st["body"]) for h in f.rights_holders]

    if f.alternatives:
        out += [Spacer(1, 5), Paragraph("ALTERNATIVES", st["label"]),
                Paragraph(_esc(" · ".join(f.alternatives)), st["body"])]

    if f.sources:
        out += [Spacer(1, 6), Paragraph("SOURCES", st["label"])]
        for s in f.sources:
            out.append(Paragraph(f"<b>{_esc(s.title)}</b>", st["body"]))
            if s.excerpt:
                out.append(Paragraph(f"“{_esc(s.excerpt)}”", st["quote"]))
            if s.url:
                out.append(Paragraph(_esc(s.url), st["mono"]))
            out.append(Spacer(1, 3))

    if f.queries_run:
        out += [Spacer(1, 3), Paragraph("SEARCHES RUN", st["label"])]
        out += [Paragraph(_esc(" · ".join(f.queries_run)), st["mono"])]

    out += [Spacer(1, 9), Rule(width, RULE), Spacer(1, 9)]
    return out


def _sections(run: ReportRun, st: dict, width: float) -> list:
    by_category: dict[str, list[ReportFinding]] = {}
    for f in run.findings:
        by_category.setdefault(f.category, []).append(f)

    out: list = []
    # Unknown categories should still print rather than vanish, so anything
    # outside CATEGORY_ORDER is appended after it in a stable order.
    ordered = CATEGORY_ORDER + sorted(set(by_category) - set(CATEGORY_ORDER))
    for category in ordered:
        items = by_category.get(category)
        if not items:
            continue
        # Risk first, then script order — the same sort as the findings pane,
        # so someone reading both is not re-orienting between them.
        items.sort(key=lambda f: (RISK_RANK.get(f.effective_risk, 9),
                                  f.scene_number, f.page))
        counts = {r: sum(1 for i in items if i.effective_risk == r)
                  for r in ("red", "amber", "green")}
        summary = " · ".join(f"{n} {r}" for r, n in counts.items() if n)

        out += [
            # Without this a section heading lands at the foot of a page and
            # its first finding starts the next one, which reads as an empty
            # category. Two inches is enough for the heading, the rule and the
            # first two lines of a finding; less than that and the section
            # starts on a fresh page instead.
            CondPageBreak(2 * inch),
            Paragraph(CATEGORY_TITLE.get(category, category.title()), st["h1"]),
            Paragraph(summary or f"{len(items)} findings", st["muted"]),
            Spacer(1, 4), Rule(width, INK, 1), Spacer(1, 10),
        ]
        # KeepTogether per finding so a rating never lands on one page with
        # its reasoning on the next. Long ones still split — that is better
        # than reportlab silently dropping a flowable too tall for a frame.
        for f in items:
            out.append(KeepTogether(_finding_block(f, st, width)))
        out.append(Spacer(1, 6))
    return out


# ---------------------------------------------------------------------------
# document
# ---------------------------------------------------------------------------


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 0.55 * inch, doc.report_title)
    canvas.drawRightString(LETTER[0] - doc.rightMargin, 0.55 * inch,
                           f"page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 0.75 * inch,
                LETTER[0] - doc.rightMargin, 0.75 * inch)
    canvas.restoreState()


def build_report(run: ReportRun) -> bytes:
    """Render one run as a PDF. Pure: no database, no event loop, no I/O."""
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.85 * inch, rightMargin=0.85 * inch,
        topMargin=0.85 * inch, bottomMargin=0.95 * inch,
        title=f"Clearance report: {run.script_title}",
        author="Script to Clearance",
        subject="Machine-generated rights clearance research",
    )
    # Stashed on the doc because reportlab's page callbacks take (canvas, doc)
    # and nothing else; a closure would work too, but this keeps _footer a
    # plain function that can be read on its own.
    doc.report_title = f"Rights clearance: {run.script_title}"

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="body", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame]),
        PageTemplate(id="body", frames=[frame], onPage=_footer),
    ])

    st = _styles()
    story = _cover(run, st, doc.width)
    if run.findings:
        story += _sections(run, st, doc.width)
    else:
        story += [
            Paragraph("No findings", st["h1"]),
            Paragraph(
                "This run completed without rating anything. That is a real "
                "result for a screenplay with no third-party material in it, "
                "and it is also what a run that failed part-way looks like. Check "
                "the run's status before treating it as a clean bill.",
                st["body"]),
        ]
    doc.build(story)
    return buffer.getvalue()
