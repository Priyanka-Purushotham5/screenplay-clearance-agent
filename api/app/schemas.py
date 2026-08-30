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
    category: str
    research_status: Literal["complete", "partial", "failed"]

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


class FindingsOut(BaseModel):
    findings: list[FindingOut]
    total: int
    counts: dict = Field(
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
