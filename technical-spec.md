# Script-to-Clearance Agent — Technical Specification

**Agentic Cinema: The Blockbuster Hackathon · Parallel track**
Deadline: Sep 7, 2026, 10:00pm GMT+1

This is the working reference for the build. Where it disagrees with an
earlier conversation, this document wins.

---

## 1. What the product is

An agent that reads a screenplay and produces a **rights clearance
report**: every music cue, trademark, artwork, real person, real
location, film clip, and quoted work in the script, researched for
ownership and risk-rated with cited sources.

**Where it sits in production:** pre-production, in the four-to-eight
week prep window after the script locks and before principal
photography.

**Why it matters commercially:** a production cannot obtain Errors &
Omissions insurance without a script clearance report, and without E&O
no distributor or streamer will take the film. Today this is done by
specialist clearance houses — a few thousand dollars and five to ten
business days per feature, most of it a researcher reading line by line
and running searches.

**Posture:** the tool flags and cites. It does not make legal
determinations. Every finding is reviewable and overridable by a human.
This is both honest about what a model can do and how real clearance
reports work.

---

## 2. How this maps to the judging criteria

| Criterion | How we earn it |
|---|---|
| **Quality of the idea** | A workflow that exists only in film and TV. Research is the task, so the Parallel integration is load-bearing rather than decorative |
| **Technological implementation** | Deterministic outer workflow graph, one bounded autonomous loop, tool isolation enforcing citation integrity |
| **Potential impact** | Replaces a real paid service with a measurable time and cost delta. No simulated components anywhere in the demo |
| **Design** | Split-pane review interface, live agent reasoning, human accept/override. Our weakest criterion by default — budget accordingly |

---

## 3. Architecture

```
Browser (Next.js)
    │  REST + SSE
    ▼
FastAPI ──────────────► Postgres
    │                       ▲
    │ background task       │
    ▼                       │
ADK workflow ───────────────┘
    ├── parser        (code, no model)
    ├── extraction    (Flash, no tools)
    ├── dedup         (code, no model)
    ├── research      (Flash + Parallel Search)
    ├── assessment    (Pro, no tools)
    └── composer      (code, optional Pro summary)
```

Three services: `web`, `api`, `db`. The agent runs in-process in the API
as an async background task. No message broker — everything is IO-bound
and a queue would be one more thing to operate instead of building the
review interface.

### The architectural decision, stated once

**Multi-agent, with a deterministic orchestrator that is code, not a
model.**

Do not build a manager agent that decides which sub-agent to call. The
control flow is known in advance — extract, research, assess, compose —
so it belongs in an ADK `SequentialAgent` wrapping a `ParallelAgent`.
The model decides content; the graph decides control flow. This is also
what makes "deterministic, multi-step agent" a true claim.

Autonomy belongs in exactly one place: **inside the research agent**,
where the number of steps genuinely isn't knowable ahead of time. Give
it a loop with a hard cap of six tool calls.

### Tool isolation is a correctness property, not organisation

| Agent | Tools | Why |
|---|---|---|
| Extraction | none | An extraction agent with search will find elements that aren't in the script |
| Research | Parallel Search only | Its whole job |
| Assessment | none | Cannot cite a source it wasn't handed. Every citation is verifiable by construction |

This is the honest answer to "how do we know it isn't making this up,"
and it should be on a slide.

---

## 4. Input formats

| Format | Notes |
|---|---|
| **PDF** | Primary. What productions actually distribute |
| **`.fdx`** | Final Draft XML. Elements explicitly tagged — free structure |
| **`.fountain`** | Plain-text markup. Trivially parseable |

**Sizes:** text-based PDF 200–500 KB; watermarked 3–20 MB (common —
studios watermark per recipient); scanned 10–50 MB and unusable. A
120-page feature is ~30–40k tokens. **Cap uploads at 25 MB.**

**Scanned files are rejected at upload.** OCR is out of scope.

```python
def has_text_layer(pdf, sample=10) -> bool:
    pages = pdf.pages[:sample]
    chars = sum(len((p.extract_text() or "").strip()) for p in pages)
    return chars / max(len(pages), 1) > 100
```

A real screenplay page yields 800–1,500 characters. Under ~100 means no
text layer. `extract_text()` returns an empty string rather than
raising, so this check must be explicit.

### Parsing rules

**Slug lines** open every scene: `INT. DINER - NIGHT`. Detection is an
ALL-CAPS line at the left margin starting with `INT`, `EXT`, `I/E`, or
`INT./EXT`. A scene runs from one slug to the next.

Three traps:
- **Mini-slugs** (`ANGLE ON THE JUKEBOX`, `BACK TO SCENE`, `LATER`) are
  ALL-CAPS but lack the INT/EXT prefix. Not new scenes. The prefix is
  the discriminator
- **Production drafts** carry mirrored scene numbers in both margins.
  Strip leading and trailing numeric tokens before matching
- **Page furniture** — `CONTINUED:`, `(CONTINUED)`, page numbers,
  revision asterisks — must be dropped before scene text is assembled

**Element type comes from x-indentation**, deterministically, no model
required. `pdfplumber` gives every word's coordinates in points (72/inch):

| Element | Approx. left margin |
|---|---|
| Scene heading, action | 1.5" |
| Dialogue | 2.5" |
| Parenthetical | 3.1" |
| Character cue | 3.7" |
| Transition | right-aligned |

Strip `(V.O.)`, `(O.S.)`, `(CONT'D)` from character cues. Stitch
dialogue split across pages by `(MORE)` / `NAME (CONT'D)`.

**Element type is the single most important field in the system.** It is
what makes the same song RED in an action line and GREEN in dialogue. It
must survive from parser to assessment intact.

---

## 5. Data model

Two layers. The **parsed layer** is deterministic, free, and written
during upload. The **agent layer** sits on top and is written per run.

```sql
-- ============ PARSED LAYER — written by the parser ============

CREATE TABLE scripts (
    id            UUID PRIMARY KEY,
    title         TEXT NOT NULL,
    filename      TEXT NOT NULL,
    storage_path  TEXT NOT NULL,        -- object storage, not the DB
    sha256        TEXT NOT NULL UNIQUE, -- dedup on re-upload
    source_format TEXT NOT NULL,        -- pdf | fdx | fountain
    page_count    INTEGER NOT NULL,
    scene_count   INTEGER NOT NULL,
    parse_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scenes (
    id          UUID PRIMARY KEY,
    script_id   UUID NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,
    number      INTEGER NOT NULL,       -- ordinal, or the printed number
    int_ext     TEXT,                   -- INT | EXT | INT/EXT
    location    TEXT,
    time_of_day TEXT,
    heading     TEXT NOT NULL,          -- the raw slug line
    page_start  INTEGER NOT NULL,
    page_end    INTEGER NOT NULL
);

CREATE TABLE script_elements (
    id         UUID PRIMARY KEY,
    scene_id   UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    seq        INTEGER NOT NULL,        -- order within the scene
    type       TEXT NOT NULL,           -- scene_heading | action | character
                                        -- | dialogue | parenthetical | transition
    character  TEXT,                    -- speaker, for dialogue
    page       INTEGER NOT NULL,
    text       TEXT NOT NULL
);

-- ============ AGENT LAYER — written per run ============

CREATE TABLE runs (
    id          UUID PRIMARY KEY,
    script_id   UUID NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'pending',
                -- pending | extracting | researching | assessing
                -- | composing | complete | failed
    stats       JSONB NOT NULL DEFAULT '{}'::jsonb,
                -- token counts, cache hit rate, wall time
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    error       TEXT
);

CREATE TABLE elements (            -- one row per MENTION
    id                UUID PRIMARY KEY,
    run_id            UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    script_element_id UUID NOT NULL REFERENCES script_elements(id),
    category          TEXT NOT NULL,   -- music | trademark | artwork | person
                                       -- | location | clip | literary | logo
                                       -- | product | character_name | other
    surface_form      TEXT NOT NULL,   -- as written in the script
    canonical_name    TEXT NOT NULL,   -- dedup + cache key
    element_type      TEXT NOT NULL,   -- denormalised from script_elements
    char_start        INTEGER,         -- offset into the element text
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
    id               UUID PRIMARY KEY,
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

CREATE INDEX idx_scenes_script      ON scenes(script_id, number);
CREATE INDEX idx_selements_scene    ON script_elements(scene_id, seq);
CREATE INDEX idx_elements_run       ON elements(run_id);
CREATE INDEX idx_elements_canonical ON elements(run_id, canonical_name);
CREATE INDEX idx_findings_element   ON findings(element_id);
CREATE INDEX idx_findings_risk      ON findings(risk);
```

### Three decisions worth defending

**Files live in object storage, never in Postgres.** Docker volume
locally, GCS in production, at `scripts/{script_id}/original.{ext}`.
Signed URLs only — never a public bucket. Unreleased screenplays are
among the most confidential documents in the industry, and a leak is a
real incident.

**Never mutate the original.** It is the provenance record every finding
traces back to.

**`runs` is separate from `scripts`** so the same script can be analysed
repeatedly. This gives you the re-run + diff demo for free, and it is
the hook for incremental re-clearance later (a film gets 3–8 clearance
passes as drafts revise).

---

## 6. Pipeline contracts

Each boundary is a validated Pydantic schema. Agents never talk to each
other — they write structured data the next stage reads. Persist after
every stage: a stage-3 failure should cost stage 3 only.

### Stage 0 · Parser — code, no model

**In:** the uploaded file
**Out:** `scripts`, `scenes`, `script_elements` rows, committed before
the upload response returns

In memory this is Pydantic objects; "rows" means the parser's job isn't
done until they are in Postgres. The run is a separate request in a
separate task — the database is the only channel between them.

### Stage 1 · Extraction — Flash, no tools

**In:** a chunk of 8–10 scenes with element types preserved

```json
{"chunk_id": "ch_2", "scenes": [{
  "scene_id": "sc_014", "number": 14, "heading": "INT. DINER - NIGHT",
  "elements": [
    {"id": "el_2", "type": "action", "page": 22,
     "text": "Sarah drops a coin in the jukebox. \"TAKE ON ME\" fills the room. MARCUS watches from the counter, nursing a COCA-COLA."},
    {"id": "el_4", "type": "dialogue", "character": "SARAH", "page": 22,
     "text": "God, I haven't heard this since high school."}
  ]}]}
```

**Out:** one record per mention

```json
{"elements": [
  {"script_element_id": "el_2", "category": "music",
   "surface_form": "TAKE ON ME", "canonical_name": "music:take_on_me:a-ha",
   "char_start": 35, "char_end": 45, "confidence": 0.95},
  {"script_element_id": "el_2", "category": "trademark",
   "surface_form": "COCA-COLA", "canonical_name": "trademark:coca_cola",
   "char_start": 108, "char_end": 117, "confidence": 0.99},
  {"script_element_id": "el_4", "category": "music",
   "surface_form": "this", "canonical_name": "music:take_on_me:a-ha",
   "char_start": 22, "char_end": 26, "confidence": 0.72}
]}
```

The third record resolves `"this"` to the song from context.
Canonicalisation happens here because this is the only stage with the
surrounding context to do it.

**Writes:** `elements`

### Stage 1.5 · Dedup — code, no model

Collapse mentions by `canonical_name`. Twelve Coca-Cola mentions become
one research task. Typically halves the element count.

### Stage 2 · Research — Flash + Parallel Search, capped at 6 calls

**In:** one canonical element with all its mention contexts

**Out:** an evidence dossier — facts and citations, **no risk rating**

```json
{"canonical_name": "music:take_on_me:a-ha",
 "identified_as": "Song, released 1985, performed by a-ha",
 "rights_holders": [
   {"role": "publisher", "name": "…", "confidence": "high"},
   {"role": "master owner", "name": "…", "confidence": "high"}],
 "public_domain": false,
 "notable_disputes": [],
 "evidence": [{"id": "ev_1", "claim": "…", "url": "…",
               "title": "…", "excerpt": "…"}],
 "queries_run": ["Take On Me a-ha publishing administrator",
                 "Take On Me master recording owner"],
 "search_calls": 3,
 "status": "complete"}
```

**This agent never sees the rubric.** If it knows what makes something
RED it will gather evidence toward a conclusion rather than gathering
evidence. Every claim carries its citation inline, so an unsupported
claim is structurally impossible rather than merely discouraged.

`status` may be `complete`, `partial`, or `failed`. A failure marks the
element; the run continues.

**Writes:** `research_cache` — nothing script-specific, so it is
reusable across every script forever

### Stage 3 · Assessment — Pro, no tools, batched ~10 elements

**In:** element + dossier + mention contexts + the rubric

**Out:**

```json
{"findings": [{
  "canonical_name": "music:take_on_me:a-ha",
  "per_mention": [
    {"script_element_id": "el_2", "risk": "red",
     "rights_required": ["synchronization", "master_use"],
     "rationale": "Specified to play on screen in an action line, so both the composition and the specific master recording are implicated — two licences from two rightsholders."},
    {"script_element_id": "el_4", "risk": "green",
     "rights_required": [],
     "rationale": "Referenced in dialogue only. Titles are not copyrightable and no recording is used."}],
  "alternatives": [
    "Re-record as a cover — clears the master, publishing still required",
    "Substitute a production-library track in a similar style"],
  "cited_evidence_ids": ["ev_1", "ev_2"]}]}
```

One research task, two ratings, because `element_type` differs. This is
the split that makes the product correct.

**Writes:** `findings`

### Stage 4 · Composer — code, optional Pro summary

Grouping, sorting and counting are deterministic. If you generate an
executive summary, the numbers in it come from your code, not the model.

---

## 7. API specification

Base path `/api`. All responses JSON unless noted.

### `POST /api/scripts`

Multipart upload. **Synchronous** — parses before responding, so a
scanned PDF is rejected while the user still has the file in hand.

*Request:* `multipart/form-data`, field `file`

*Steps:* stream to temp with the 25 MB cap enforced during the stream ·
validate `%PDF` magic bytes, not the extension · SHA-256, return the
existing script on match · write to object storage · parse · text-layer
check · classify by indentation · group into scenes · extract title ·
persist in one transaction

*201:*
```json
{"script_id": "…", "title": "THE LONG WAY DOWN",
 "source_format": "pdf", "page_count": 118, "scene_count": 94,
 "parse_warnings": ["Scene 47 heading ambiguous"],
 "duplicate_of": null}
```

*Errors:* `413` too large · `415` unsupported type · `422` no text layer
(`{"code": "NO_TEXT_LAYER", "pages_checked": 10}`) · `422` unparseable

### `GET /api/scripts/{id}`
*200:* script metadata, as above

### `GET /api/scripts/{id}/scenes`
Query: `from`, `to` (scene numbers)
*200:* `{"scenes": [{scene, elements:[…]}]}` — the reading pane renders
from this before any analysis exists

### `POST /api/runs`
*Request:* `{"script_id": "…"}`
*202:* `{"run_id": "…", "status": "pending"}` — returns immediately,
starts the background task
*Errors:* `404` unknown script · `409` a run is already in flight

### `GET /api/runs/{id}`
*200:*
```json
{"run_id": "…", "script_id": "…", "status": "researching",
 "progress": {"elements_found": 84, "researched": 31, "assessed": 0},
 "stats": {"cache_hits": 12, "tokens_in": 210400, "tokens_out": 18900},
 "started_at": "…", "finished_at": null, "error": null}
```

### `GET /api/runs/{id}/stream`
`text/event-stream`. Opened by the client as soon as it has a `run_id`.

**Send a full snapshot on connect, then live events.** A client that
reconnects mid-run recovers correctly without you building event replay.

Events carry IDs only; the frontend fetches the real record. Never trust
the payload as the source of truth.

| Event | Payload |
|---|---|
| `snapshot` | full current run state |
| `stage.started` | `{stage}` |
| `element.extracted` | `{element_id, category, surface_form, scene}` |
| `research.query` | `{canonical_name, query}` |
| `research.result` | `{canonical_name, sources_found, cache_hit}` |
| `finding.created` | `{finding_id, element_id, risk}` |
| `run.complete` | `{counts_by_risk}` |
| `run.failed` | `{error}` |

`research.query` is the demo's best twenty seconds — the actual searches
appearing live is what turns a black box into something a reviewer
trusts.

### `GET /api/runs/{id}/findings`
Query: `risk`, `category`, `review_status`, `scene`, `limit`, `offset`
*200:* `{"findings": […], "total": 84, "counts": {"red": 9, "amber": 31, "green": 44}}`

### `GET /api/findings/{id}`
*200:* the finding with its full dossier, sources, `queries_run`, and
alternatives

### `PATCH /api/findings/{id}`
*Request:* `{"review_status": "overridden", "override_risk": "green", "review_note": "Cleared under existing blanket licence"}`
*200:* the updated finding

### `GET /api/runs/{id}/report`
Query: `format` = `json` | `pdf`
*200:* assembled report grouped by risk then category

### `GET /api/runs/{id}/diff?against={run_id}`
*200:* `{"added": […], "removed": […], "changed": […]}` — P1, and the
evidence for the word *deterministic*

---

## 8. Tools and services

### Mandated by the hackathon

| Thing | Role | Status |
|---|---|---|
| **Gemini** | All model calls | **Required** |
| **Google Cloud Agent Builder / ADK** | Agent framework | **Required** |
| `google-adk` | ADK Python SDK | On the accepted-SDK list |
| `google-cloud-aiplatform[agent_engines,adk]>=1.101.0` | Vertex AI SDK | The install the resources page recommends |
| `google-genai` | Gemini client | On the accepted list |
| **Parallel Search API** | Rights research | **Required for our track** |
| `parallel-web` | Official Parallel SDK | Python or TypeScript; must be called at runtime |
| **Google Cloud Run** | Hosting both services | Satisfies the hosted-URL requirement |
| **GitHub (public)** | Repo | `LICENSE` at root, detected in About |
| **YouTube** | Demo video | Under 3 min, public, English audio or subtitles |

Two rules to keep in view: the repo must show the Google Cloud SDK
**and** the partner SDK imported and called at runtime, not merely named
in the README. Do not use LangChain or LangGraph — the resources page
explicitly recommends building natively with ADK rather than external
wrapper libraries.

### Our choices — not mandated

| Thing | Role |
|---|---|
| FastAPI · uvicorn · sse-starlette | API and the live event stream |
| Pydantic v2 · pydantic-settings | Stage contracts and config |
| SQLAlchemy 2 (async) · asyncpg | DB access |
| Postgres 16 | Parsed layer, findings, cache |
| pdfplumber | Page text with word coordinates |
| Google Cloud Storage | Original files, signed URLs |
| Next.js 15 · Tailwind · shadcn/ui · recharts | Review interface |
| Docker · Docker Compose | Local stack |
| uv | Python packaging |
| cloudflared | Tunnel, only if you add inbound webhooks |
| OpenTelemetry | Optional agent tracing |

### Deliberately not used

The other four partner tracks — Grafana, ClickHouse, IBM, Replit — are
alternatives to Parallel, not additions. Judging happens within a single
track. Also skipped: Redis (nothing needs it once the agent runs
in-process), Kubernetes, OCR, and any auth system.

---

## 9. Token and cost budget

**The context window is not the constraint.** A 40k-token script fits in
Gemini's window many times over. You will never chunk for capacity.

The constraint is the fan-out. Naive implementation, ~100 elements:

| Stage | Tokens |
|---|---|
| Extraction | ~46k |
| Research | 1.0–1.5M ← 90% of spend |
| Assessment | ~400k |

Five levers, in order of impact:

1. **Deduplicate before researching.** Twelve mentions, one task.
   Typically halves the element count
2. **Cache by canonical name, across runs and across scripts.**
   "Hallelujah / Leonard Cohen" resolves identically forever. This also
   makes the re-run demo instant, which is what makes the determinism
   story watchable rather than a two-minute wait
3. **Don't accumulate raw search results.** After each search, append to
   a compact evidence note and discard the payload — otherwise turn six
   carries turns one through five
4. **Pass snippets, not full pages.** Let the agent explicitly fetch
   full text when it decides a source matters
5. **Batch assessment ~10 per call.** A 1,500-token rubric sent 100
   times is 150k tokens of pure repetition

After all five, a full feature runs well under a dollar. Without dedup
and caching you are at 10–20× that, plus minutes of wall-clock latency
you cannot fit in a three-minute video.

**Concurrency: cap the research fan-out at 5–8 in flight.** Eighty
simultaneous agents will rate-limit you on both Gemini and Parallel.

---

## 10. Milestones

| Date | Gate |
|---|---|
| Aug 10 | Parallel and Gemini probe scripts return real data |
| Aug 15 | One element end to end: upload → finding with a real source |
| Aug 22 | A full 90–120 page script processes unattended |
| Aug 29 | Someone unfamiliar uses it without narration |
| Sep 3 | Hosted URL completes a run from a phone on cellular |
| Sep 5–6 | Submitted, early |

**Build your own 10-page test script in week one** with planted elements
whose answers you already know — a specific song, a named brand, a
painting, a living public figure, a landmark, a line of Shakespeare.
Without ground truth you can only measure that the agent produced
output, not that it was right. This single artifact will improve
accuracy more than any prompt tuning.

**Aug 29 is the real deadline.** Everything after is deploy, record,
submit.

---

## 11. Submission checklist

- [ ] Public repo, `LICENSE` at root, MIT badge visible in the About
      sidebar (it fails silently — check that it renders)
- [ ] `google-adk` / `google-cloud-aiplatform` imported and called at
      runtime
- [ ] `parallel-web` imported and called at runtime
- [ ] Hosted project URL, reachable
- [ ] Demo video under 3 min, public, showing the product as built
- [ ] `.env` absent from the entire git history
- [ ] README: architecture, setup, and an honest statement of limits

---

## 12. Open decisions

1. `.fdx` and `.fountain` — day-one or post-demo? (~1 day for both)
2. Report export format: PDF or a shareable link?
3. Character-name-vs-real-person checking — high impressiveness, high
   false-positive risk. Include in the demo?
4. Which full-length script to demo. Needs visible clearance texture —
   a period piece or something music-heavy
5. Where the executive summary comes from: template or a Pro call

---

## The two things that decide this project

**The rubric.** Everything else is plumbing. A report that flags every
proper noun is worthless; one that misses a Beatles cue is worse. Two
days tuning against ground truth is the best-spent time in the plan.

**Stopping.** On Aug 29 you will want one more feature. A finished P0
with a good interface beats an unfinished P1 every time, and judges only
see what works on the day.
