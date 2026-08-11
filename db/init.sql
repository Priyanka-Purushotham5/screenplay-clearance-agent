-- Postgres 16 schema for the script-to-clearance agent.
-- Run once on first boot via the Docker volume mount.
-- Alembic handles forward migrations from this baseline.

-- gen_random_uuid() is built-in from Postgres 13+; pgcrypto keeps it safe on older versions.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============ PARSED LAYER — written by the parser ============

CREATE TABLE scripts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title          TEXT NOT NULL,
    filename       TEXT NOT NULL,
    storage_path   TEXT NOT NULL,         -- object storage path, not file bytes
    sha256         TEXT NOT NULL UNIQUE,  -- dedup on re-upload
    source_format  TEXT NOT NULL,         -- pdf | fdx | fountain
    page_count     INTEGER NOT NULL,
    scene_count    INTEGER NOT NULL,
    parse_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    uploaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scenes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id   UUID NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,
    number      INTEGER NOT NULL,         -- ordinal, or the printed number
    int_ext     TEXT,                     -- INT | EXT | INT/EXT
    location    TEXT,
    time_of_day TEXT,
    heading     TEXT NOT NULL,            -- the raw slug line
    page_start  INTEGER NOT NULL,
    page_end    INTEGER NOT NULL
);

CREATE TABLE script_elements (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scene_id  UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    seq       INTEGER NOT NULL,           -- order within the scene
    type      TEXT NOT NULL,              -- scene_heading | action | character
                                          -- | dialogue | parenthetical | transition
    character TEXT,                       -- speaker, for dialogue/parenthetical; nullable
    page      INTEGER NOT NULL,
    text      TEXT NOT NULL
);

-- ============ AGENT LAYER — written per run ============

CREATE TABLE runs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id   UUID NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'pending',
                -- pending | extracting | researching | assessing | composing | complete | failed
    stats       JSONB NOT NULL DEFAULT '{}'::jsonb,
                -- token counts, cache hit rate, wall time
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    error       TEXT
);

CREATE TABLE elements (            -- one row per MENTION
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    script_element_id UUID NOT NULL REFERENCES script_elements(id),
    category          TEXT NOT NULL,   -- music | trademark | artwork | person
                                       -- | location | clip | literary | logo
                                       -- | product | character_name | other
    surface_form      TEXT NOT NULL,   -- as written in the script
    canonical_name    TEXT NOT NULL,   -- dedup + cache key
    element_type      TEXT NOT NULL,   -- denormalised from script_elements.type
    char_start        INTEGER,
    char_end          INTEGER,
    confidence        REAL
);

CREATE TABLE research_cache (      -- keyed on canonical_name, NOT run
    canonical_name TEXT PRIMARY KEY,
    category       TEXT NOT NULL,
    dossier        JSONB NOT NULL,
    queries_run    JSONB NOT NULL DEFAULT '[]'::jsonb,
    status         TEXT NOT NULL,    -- complete | partial | failed
    researched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE findings (            -- one row per MENTION
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    element_id       UUID NOT NULL REFERENCES elements(id) ON DELETE CASCADE,
    risk             TEXT NOT NULL,   -- red | amber | green
    rights_required  JSONB NOT NULL DEFAULT '[]'::jsonb,
    rights_holders   JSONB NOT NULL DEFAULT '[]'::jsonb,
    rationale        TEXT NOT NULL,
    sources          JSONB NOT NULL DEFAULT '[]'::jsonb,
    alternatives     JSONB NOT NULL DEFAULT '[]'::jsonb,
    review_status    TEXT NOT NULL DEFAULT 'unreviewed',
                     -- unreviewed | accepted | overridden
    override_risk    TEXT,
    review_note      TEXT,
    reviewed_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============ INDEXES ============

CREATE INDEX idx_scenes_script      ON scenes(script_id, number);
CREATE INDEX idx_selements_scene    ON script_elements(scene_id, seq);
CREATE INDEX idx_elements_run       ON elements(run_id);
CREATE INDEX idx_elements_canonical ON elements(run_id, canonical_name);
CREATE INDEX idx_findings_element   ON findings(element_id);
CREATE INDEX idx_findings_risk      ON findings(risk);
