"""Pydantic models for every agent stage boundary.

Agents never call each other — they emit validated structures the next stage
reads.  This module owns those structures.  The vocabulary here (categories,
element types) mirrors db/init.sql exactly; changing one means changing both.

C1 defines the extraction boundary.  C5 and C6 extend this file with the
research and assessment boundaries.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared vocabulary — mirrors db/init.sql
# ---------------------------------------------------------------------------

Category = Literal[
    "music",
    "trademark",
    "artwork",
    "person",
    "location",
    "clip",
    "literary",
    "logo",
    "product",
    "character_name",
    "other",
]

ElementType = Literal[
    "scene_heading",
    "action",
    "character",
    "dialogue",
    "parenthetical",
    "transition",
]

OffsetStatus = Literal["exact", "repaired", "unresolved"]


# ---------------------------------------------------------------------------
# Stage 1 INPUT — a chunk of parsed screenplay
#
# Produced by the parser (Block B) or, until that lands, by a fixture.  Shape
# matches the Stage 1 contract in technical-spec.md §6.
# ---------------------------------------------------------------------------


class ChunkElement(BaseModel):
    """One parsed block of screenplay text — the unit offsets index into."""

    id: str
    type: ElementType
    page: int
    character: Optional[str] = None
    text: str


class ChunkScene(BaseModel):
    scene_id: str
    number: int
    heading: str
    elements: list[ChunkElement]


class ExtractionChunk(BaseModel):
    chunk_id: str
    scenes: list[ChunkScene]

    def element_index(self) -> dict[str, tuple[ChunkElement, ChunkScene]]:
        """Flat id → (element, scene) lookup, for joining model output back."""
        return {
            element.id: (element, scene)
            for scene in self.scenes
            for element in scene.elements
        }


# ---------------------------------------------------------------------------
# Stage 1 MODEL OUTPUT — what Gemini is asked to return
#
# Deliberately minimal and flat.  Every field the model does not have to
# produce is a field it cannot get wrong, and this is what goes into
# `response_schema`, which tolerates unions and nesting poorly.
# ---------------------------------------------------------------------------


class ExtractedElement(BaseModel):
    script_element_id: str = Field(
        description="The `id` of the chunk element this mention appears in."
    )
    category: Category
    surface_form: str = Field(description="The mention exactly as written in the text.")
    canonical_name: str = Field(
        description="Stable identity as {category}:{slug}[:{qualifier}]."
    )
    char_start: int = Field(description="Zero-based index into that element's text.")
    char_end: int = Field(description="End-exclusive index into that element's text.")
    confidence: float = Field(description="0-1 certainty of the identification.")


class ExtractionResult(BaseModel):
    elements: list[ExtractedElement]


# ---------------------------------------------------------------------------
# Stage 1 RESOLVED OUTPUT — model output plus the fields code derives
#
# `element_type` is joined from the chunk rather than asked for, because C6's
# rubric turns on it: action line = appears on screen = clearance needed;
# dialogue = reference only.  It is too load-bearing to let a model guess.
# These fields map 1:1 onto the `elements` table (models.Element), which C2
# persists.
# ---------------------------------------------------------------------------


class ResolvedElement(BaseModel):
    script_element_id: str
    scene_id: str
    category: Category
    surface_form: str
    canonical_name: str
    element_type: ElementType
    page: int
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    confidence: Optional[float] = None
    offset_status: OffsetStatus


class ExtractionStats(BaseModel):
    elements_returned: int = 0
    elements_kept: int = 0
    orphan_elements: int = 0
    offsets_exact: int = 0
    offsets_repaired: int = 0
    offsets_unresolved: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    wall_ms: int = 0
    attempts: int = 0


class ExtractionOutcome(BaseModel):
    chunk_id: str
    elements: list[ResolvedElement]
    stats: ExtractionStats
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 2 — RESEARCH
#
# One dossier per ENTITY, not per mention.  C3 groups 30 mentions into 12
# entities; this stage runs once per entity and C6 rates every mention against
# the dossier its entity produced.
#
# Nothing here carries a rating.  A dossier records what was found and where it
# came from; what that implies is C6's job and lives in the rubric.  Keeping
# the two apart is the point — an agent that knows what makes something RED
# stops gathering evidence and starts building a case.
#
# Flat and union-free on purpose.  `response_schema` tolerates nesting poorly,
# so `public_domain` is a three-way string rather than Optional[bool]: it also
# happens to be more honest, because "we could not establish it" is a real
# answer and null is not.
# ---------------------------------------------------------------------------

ResearchStatus = Literal["complete", "partial", "failed"]
PublicDomain = Literal["yes", "no", "unknown"]


class EvidenceItem(BaseModel):
    """One cited fact.  C6 must reference these by id, and every id it cites
    is validated against the dossier — a rating whose support does not exist
    is worse than no rating."""

    id: str = Field(description="Stable within one dossier: ev_1, ev_2, ...")
    claim: str = Field(description="One sentence, the fact this supports.")
    url: str = Field(description="Where it came from.")
    excerpt: str = Field(description="The words on that page that carry it.")


class ResearchTurn(BaseModel):
    """What the agent returns on each pass of the loop.

    One model call per pass does two jobs: fold the latest search results into
    evidence, and decide whether another search would add anything. Splitting
    those into separate calls doubles the cost for no gain, because the same
    context answers both.
    """

    note: str = Field(description="One line: what this pass established.")
    new_evidence: list[EvidenceItem]
    identified_as: str = Field(description="What this thing is. Empty until known.")
    rights_holders: list[str]
    public_domain: PublicDomain
    notable_disputes: list[str]
    done: bool = Field(description="True when further searching would add nothing.")
    next_queries: list[str] = Field(
        description="Keyword queries for the next search. Empty when done."
    )


class ResearchDossier(BaseModel):
    """The stage boundary C6 reads.  Persisted to research_cache."""

    canonical_name: str
    category: Category
    identified_as: str
    rights_holders: list[str]
    public_domain: PublicDomain
    notable_disputes: list[str]
    evidence: list[EvidenceItem]
    queries_run: list[str]
    search_calls: int
    status: ResearchStatus
    # Recorded so a dossier read from cache months later can be judged against
    # the wording that produced it, the way runs record the rubric version.
    prompt_version: str = ""


# ---------------------------------------------------------------------------
# Stage 3 — ASSESSMENT
#
# One rating per MENTION, not per entity.  Research collapsed thirty mentions
# into twelve dossiers; this expands back out, because the same song is RED
# playing in an action line and GREEN named in dialogue and that difference is
# the product.
#
# `risk` is lowercase to match db/init.sql (`risk TEXT -- red | amber | green`)
# and models.Finding.  docs/ground-truth.md writes RED/AMBER/GREEN for
# readability; the scorer folds case rather than either side changing.
# ---------------------------------------------------------------------------

Risk = Literal["red", "amber", "green"]


class MentionRating(BaseModel):
    """Maps 1:1 onto a row in `findings`."""

    mention_id: str = Field(
        description="Echo the mention_id you were given, exactly. This is the "
                    "only unique handle on a mention."
    )
    script_element_id: str
    surface_form: str = Field(description="Echoed back so a misalignment is visible.")
    risk: Risk
    rights_required: list[str] = Field(
        description="The specific rights to obtain: 'synchronisation licence', "
                    "'master use licence', 'location agreement'. Empty for green."
    )
    rationale: str = Field(description="Two or three sentences a reviewer can check.")
    cited_evidence_ids: list[str] = Field(
        description="Evidence ids from the dossier. Every one is validated."
    )
    alternatives: list[str] = Field(
        description="Concrete changes that would lower the rating. Empty for green."
    )


class AssessmentBatch(BaseModel):
    """What the model returns for one batch of mentions."""

    ratings: list[MentionRating]


class AssessmentOutcome(BaseModel):
    """The stage boundary C7 persists into `findings`."""

    ratings: list[MentionRating]
    warnings: list[str] = Field(default_factory=list)
    batches: int = 0
    # Citations the model made up. Counted rather than hidden: a rating whose
    # support does not exist reads as though it was checked, which is worse
    # than one that admits it was not.
    invalid_citations: int = 0
    unrated: list[str] = Field(
        default_factory=list,
        description="Mentions no batch returned a rating for.",
    )
    rubric_version: str = ""
