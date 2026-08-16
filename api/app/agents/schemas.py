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
