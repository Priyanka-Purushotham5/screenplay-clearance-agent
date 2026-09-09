"""Wire-format models.

These are the API's contract with the frontend. web/package.json runs

    openapi-typescript http://localhost:8080/openapi.json -o lib/api-types.ts

so whatever is declared here becomes the frontend's TypeScript verbatim.
Field names and nullability must match web/lib/api-types.ts exactly, or the
generated types silently stop matching the components that consume them.
"""

from __future__ import annotations

import uuid
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ScriptOut(BaseModel):
    """Mirrors the `Script` interface in web/lib/api-types.ts."""

    script_id: uuid.UUID
    title: str
    source_format: Literal["pdf", "fdx", "fountain"]
    page_count: int
    scene_count: int

    # No defaults on these two, deliberately. A Pydantic field with a
    # default is omitted from OpenAPI's `required` list, which makes
    # openapi-typescript emit `parse_warnings?: string[]` — optional, where
    # the frontend's hand-written interface says required. Every response
    # sets both explicitly, so requiring them costs nothing and keeps the
    # generated client honest.
    parse_warnings: list[str]

    # Non-null when this upload matched an existing script by SHA-256.
    # When set, `script_id` is that existing script — the caller gets the
    # original back rather than a second copy.
    duplicate_of: Optional[uuid.UUID]

class ScriptRunOut(BaseModel):
    """The most recent run over a script, or nothing if it has never been run.

    Denormalised onto the list row on purpose. The sidebar shows a dot per
    script — never run, working, done, failed — and doing that with one request
    per script would be N+1 queries to render a list.
    """

    run_id: uuid.UUID
    status: Literal["pending", "extracting", "researching", "assessing",
                    "composing", "complete", "failed"]
    findings: int
    started_at: str


class ScriptSummaryOut(BaseModel):
    """One row in the scripts sidebar. Deliberately not `ScriptOut`.

    `ScriptOut` carries `parse_warnings` and `duplicate_of`, which the detail
    view needs and a list does not; sending them for every script would grow
    the payload with text nobody reads. What a list row needs is enough to
    label itself and enough to say what state it is in.
    """

    script_id: uuid.UUID
    title: str
    page_count: int
    scene_count: int
    uploaded_at: str
    latest_run: Optional[ScriptRunOut]


class ScriptsOut(BaseModel):
    """An object, not a bare array, matching ScenesOut.

    A top-level JSON array cannot grow a field later without breaking every
    client; an object can.
    """

    scripts: list[ScriptSummaryOut]


class ScriptElementOut(BaseModel):
    """Mirrors the `ScriptElement` interface in web/lib/api-types.ts."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scene_id: uuid.UUID
    seq: int
    type: Literal[
        "scene_heading", "action", "character", "dialogue",
        "parenthetical", "transition",
    ]
    character: Optional[str]
    page: int
    text: str


class SceneOut(BaseModel):
    """Mirrors the `Scene` interface in web/lib/api-types.ts."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    script_id: uuid.UUID
    number: int
    int_ext: Optional[Literal["INT", "EXT", "INT/EXT"]]
    location: Optional[str]
    time_of_day: Optional[str]
    heading: str
    page_start: int
    page_end: int
    elements: list[ScriptElementOut]


class ScenesOut(BaseModel):
    """The scenes endpoint returns an object, not a bare array."""

    scenes: list[SceneOut]

class ApiErrorOut(BaseModel):
    """Mirrors `ApiError` in the frontend, plus a machine-readable `code`."""

    code: str
    detail: str

class NoTextLayerOut(BaseModel):
    """Mirrors `NoTextLayerError` — the one 422 the upload screen special-cases.

    web/app/page.tsx reads `body.code` and shows a specific message telling
    the user to re-export, rather than the generic upload failure.
    """

    code: Literal["NO_TEXT_LAYER"]
    detail: str
    pages_checked: int


ERROR_RESPONSES: dict = {
    413: {"model": ApiErrorOut, "description": "File exceeds the 25 MB cap"},
    415: {"model": ApiErrorOut, "description": "Not a PDF"},
    422: {
        "model": Union[NoTextLayerOut, ApiErrorOut],
        "description": "Scanned PDF (NO_TEXT_LAYER), or unparseable",
    },
}

# ---------------------------------------------------------------------------
# RUNS AND FINDINGS — the shapes the review UI reads
#
# `web/lib/api-types.ts` declares these by hand today, with a STUB banner on
# line 1 and a note to run `npm run gen:types` once the API is live. These
# models are what that generator will produce, so the field names below are
# load-bearing: they were read off the frontend's interfaces, not invented.
#
# The enrichment is the point. `findings` on its own is unreadable — risk and
# rationale and nothing to say WHAT was rated. Everything a reviewer needs to
# see sits one or two joins away: the mention on `elements`, the line and the
# page on `script_elements`, the scene on `scenes`, and how well the research
# went on `research_cache`. Doing those joins here rather than in the client
# is what lets the findings pane render from a single request.
# ---------------------------------------------------------------------------


class RightsHolderOut(BaseModel):
    role: str = Field(description="publisher, master, estate, owner — or empty.")
    name: str
    confidence: Literal["high", "medium", "low"] = "medium"


class SourceOut(BaseModel):
    id: str
    claim: str
    url: str
    title: str
    excerpt: str


class FindingOut(BaseModel):
    """One rated mention, with everything the review UI needs to show it."""

    id: uuid.UUID
    element_id: uuid.UUID = Field(
        description="The MENTION id, on `elements`. Never a script_elements id."
    )
    risk: Literal["red", "amber", "green"]
    rights_required: list[str]
    rights_holders: list[RightsHolderOut]
    rationale: str
    sources: list[SourceOut]
    alternatives: list[str]
    review_status: Literal["unreviewed", "accepted", "overridden"]
    override_risk: Optional[Literal["red", "amber", "green"]]
    review_note: Optional[str]
    reviewed_at: Optional[str]
    created_at: str

    # Denormalised from `elements`
    canonical_name: str
    surface_form: str
    # A Literal, not a str, and this list must stay identical to
    # api/app/routers/runs.py:UI_CATEGORIES. `str` typechecks fine in Python
    # and generates `category: string` in TypeScript, which silently removes
    # compile-time checking from the one field the review UI filters, groups
    # and colours by — a typo like "tradmark" would pass tsc and then match
    # nothing at runtime. The router already guarantees the union
    # (`category if category in UI_CATEGORIES else "other"`); this is the
    # schema finally saying so, and it is the only literal union of the ten
    # in web/lib/api-types.ts that generation would otherwise have lost.
    category: Literal["music", "trademark", "artwork", "person", "location",
                      "clip", "literary", "other"]
    research_status: Literal["complete", "partial", "failed"]

    # The searches the research agent actually ran for this entity, in order.
    # C5 caps that loop at six calls and already records every query it made
    # on `research_cache.queries_run`; the findings query has been joining
    # that table for `status` and reading straight past this column.
    #
    # It is exposed because a rating a reviewer cannot audit is a rating they
    # have to take on trust. "Rated RED" invites the question "on what
    # basis?", and `sources` answers half of it — what the agent found. The
    # queries answer the other half: what it went looking for, and therefore
    # what it would have found had it been there. GREEN after six searches
    # that all came back empty is a different claim from GREEN after one
    # vague query, and this is the only field that tells them apart.
    queries_run: list[str]

    # The join the script pane needs. `element_id` above is the mention;
    # this is the screenplay line it sits in, and the offsets index into
    # THAT line's text, not the whole script. Nullable because they are
    # model output and are not always resolvable — web/lib/highlight.ts
    # repairs what it can and falls back to a whole-block highlight.
    script_element_id: uuid.UUID
    char_start: Optional[int]
    char_end: Optional[int]
    scene_number: int
    page: int


class FindingReviewIn(BaseModel):
    """A reviewer's verdict on one finding.

    The three states are not interchangeable and the combinations matter:

        accepted    — the reviewer agrees with the rating as it stands.
                      An override_risk here would be contradictory.
        overridden  — the reviewer disagrees and supplies their own rating.
                      override_risk is required; without it the row would
                      claim a disagreement and not say what with.
        unreviewed  — undo. Clears the override, the note and the timestamp,
                      so a mistaken click leaves no trace behind.

    Validated on the server rather than trusted from the client, because these
    rows are the record of who decided what, which is the part of a clearance
    report that matters if anyone ever asks.
    """

    review_status: Literal["unreviewed", "accepted", "overridden"]
    override_risk: Optional[Literal["red", "amber", "green"]] = None
    review_note: Optional[str] = Field(default=None, max_length=2000)


class RiskCountsOut(BaseModel):
    """The three numbers the summary header shows.

    A model rather than `dict`, for the same reason `FindingOut.category` is a
    Literal rather than `str`: a bare dict generates as
    `{[key: string]: unknown}` in TypeScript, so the component that renders
    `counts.red` stops type-checking and a renamed key becomes a blank space in
    the UI instead of a compile error.
    """

    red: int = 0
    amber: int = 0
    green: int = 0


class FindingsOut(BaseModel):
    findings: list[FindingOut]
    total: int
    counts: RiskCountsOut = Field(
        description="red/amber/green counts across the WHOLE run, not the page. "
                    "A summary header that changed when you paged would be a lie."
    )


class RunProgressOut(BaseModel):
    """Counts the run header renders. Derived, not stored.

    `runs` has no progress column; the frontend's RunHeader dereferences
    `run.progress.elements_found` unguarded, so this exists to keep that
    working rather than to add a column that would need maintaining in two
    places.
    """

    elements_found: int = 0
    entities: int = 0
    findings: int = 0
    dossiers_complete: int = 0
    dossiers_failed: int = 0


class RunOut(BaseModel):
    run_id: uuid.UUID
    script_id: uuid.UUID
    status: Literal["pending", "extracting", "researching", "assessing",
                    "composing", "complete", "failed"]
    progress: RunProgressOut
    stats: dict
    started_at: str
    finished_at: Optional[str]
    error: Optional[str]


class RunCreateIn(BaseModel):
    script_id: uuid.UUID
