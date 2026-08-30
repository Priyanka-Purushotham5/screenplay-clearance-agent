"""SQLAlchemy 2 async declarative models.

Column names and types mirror db/init.sql exactly.  Any schema change must
be reflected in both files and then captured in a new Alembic migration.

Timestamps
----------
Every timestamp column in db/init.sql is TIMESTAMPTZ, so every one of them
here must be declared `DateTime(timezone=True)`. A bare `Mapped[datetime]`
maps to `DateTime()`, which SQLAlchemy compiles as TIMESTAMP WITHOUT TIME
ZONE — and that disagreement is not caught at startup, because nothing
compares the model against the live schema.

It is not caught at runtime either, until the first time Python WRITES a
timestamp. Reads are unaffected: asyncpg returns an aware datetime and
SQLAlchemy passes it through, so `started_at` came back correctly as
`...+00:00` for months. But binding an aware datetime to a parameter
SQLAlchemy has typed as naive gives

    asyncpg.exceptions.DataError: invalid input for query argument $3
    (can't subtract offset-naive and offset-aware datetimes)

Every timestamp except `runs.finished_at` and `findings.reviewed_at` is
written by Postgres itself through `server_default=func.now()`, which is why
this survived from B1 to C8 undetected: C8 is the first code to assign one
from Python. It cost a debugging session in which a run that had completely
succeeded looked like it was hanging, because the only row that failed to
write was the row that says the run is over.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# One shared instance; SQLAlchemy type objects are immutable and reusable.
# Named so that a new timestamp column has an obvious right answer to copy.
TIMESTAMPTZ = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# PARSED LAYER — written by the parser during upload
# ---------------------------------------------------------------------------


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_format: Mapped[str] = mapped_column(Text, nullable=False)  # pdf | fdx | fountain
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_count: Mapped[int] = mapped_column(Integer, nullable=False)
    parse_warnings: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'::jsonb"
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )

    scenes: Mapped[list["Scene"]] = relationship(
        "Scene", back_populates="script", cascade="all, delete-orphan"
    )
    runs: Mapped[list["Run"]] = relationship(
        "Run", back_populates="script", cascade="all, delete-orphan"
    )


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        Index("idx_scenes_script", "script_id", "number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    int_ext: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    time_of_day: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)

    script: Mapped["Script"] = relationship("Script", back_populates="scenes")
    elements: Mapped[list["ScriptElement"]] = relationship(
        "ScriptElement", back_populates="scene", cascade="all, delete-orphan"
    )


class ScriptElement(Base):
    __tablename__ = "script_elements"
    __table_args__ = (
        Index("idx_selements_scene", "scene_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scene_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # scene_heading | action | character | dialogue | parenthetical | transition
    character: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    scene: Mapped["Scene"] = relationship("Scene", back_populates="elements")


# ---------------------------------------------------------------------------
# AGENT LAYER — written per run
# ---------------------------------------------------------------------------


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    stats: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="'{}'::jsonb"
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMPTZ, nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    script: Mapped["Script"] = relationship("Script", back_populates="runs")
    elements: Mapped[list["Element"]] = relationship(
        "Element", back_populates="run", cascade="all, delete-orphan"
    )


class Element(Base):
    """One row per mention — many elements may share a canonical_name."""

    __tablename__ = "elements"
    __table_args__ = (
        Index("idx_elements_run", "run_id"),
        Index("idx_elements_canonical", "run_id", "canonical_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    script_element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("script_elements.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    surface_form: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    element_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # denormalised from script_elements.type
    char_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    run: Mapped["Run"] = relationship("Run", back_populates="elements")
    finding: Mapped[Optional["Finding"]] = relationship(
        "Finding",
        back_populates="element",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ResearchCache(Base):
    """Keyed on canonical_name — shared across all scripts and runs forever."""

    __tablename__ = "research_cache"

    # TEXT primary key — this is the cache key, not a UUID
    canonical_name: Mapped[str] = mapped_column(Text, primary_key=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    dossier: Mapped[dict] = mapped_column(JSONB, nullable=False)
    queries_run: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'::jsonb"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)  # complete | partial | failed
    researched_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class Finding(Base):
    """One row per mention — parallel to Element."""

    __tablename__ = "findings"
    __table_args__ = (
        Index("idx_findings_element", "element_id"),
        Index("idx_findings_risk", "risk"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("elements.id", ondelete="CASCADE"), nullable=False
    )
    risk: Mapped[str] = mapped_column(Text, nullable=False)  # red | amber | green
    rights_required: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'::jsonb"
    )
    rights_holders: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'::jsonb"
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'::jsonb"
    )
    alternatives: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'::jsonb"
    )
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="unreviewed", server_default="unreviewed"
    )  # unreviewed | accepted | overridden
    override_risk: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMPTZ, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )

    element: Mapped["Element"] = relationship("Element", back_populates="finding")
