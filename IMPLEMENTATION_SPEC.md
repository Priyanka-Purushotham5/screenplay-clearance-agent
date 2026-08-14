# Script-to-Clearance Agent — Implementation Specification

> **For the implementing model.** Each task below is self-contained: it
> states its context, the exact files to create, the interfaces to
> implement, the domain rules you cannot infer, and a verifiable
> done-condition. Read §0 (Project Context) and §1 (Domain Rules)
> before implementing any task — several tasks are impossible to get
> right without them.
>
> **Do not invent behaviour not specified here.** Where a decision is
> genuinely open, the task says so explicitly.

---

# §0 · Project Context

## What is being built

A web application that accepts a screenplay PDF and produces a **rights
clearance report**: every music cue, trademark, artwork, real person,
real location, film clip, and quoted work in the script, researched for
ownership and risk-rated with cited sources.

This is a real pre-production workflow. A film cannot obtain Errors &
Omissions insurance without a clearance report, and without E&O no
distributor will take the film. Today it is done manually by clearance
houses: five to ten business days and a few thousand dollars per
feature.

## Non-negotiable constraints

| Constraint | Value |
|---|---|
| Backend | Python 3.12, FastAPI, async throughout |
| Frontend | Next.js 15 App Router, TypeScript, Tailwind |
| Database | PostgreSQL 16, SQLAlchemy 2 async + asyncpg |
| Models | Gemini **only**. Flash for extraction/research, Pro for assessment |
| Agent framework | Google ADK (`google-adk`) — **not** LangChain or LangGraph |
| Search | Parallel Search via the `parallel-web` SDK — the only external research tool |
| Validation | Pydantic v2 at every stage boundary |
| Repo | Monorepo: `api/` and `web/` |

**No other AI vendor may be used anywhere in the project at runtime.**

## Repository layout

```
clearance/
├── docker-compose.yml
├── .env.example
├── LICENSE                      # MIT, at root
├── README.md
├── db/init.sql
├── docs/
│   ├── api-notes.md             # written by A2
│   └── ground-truth.md          # written by B7
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── scripts/                 # standalone probes, not part of the app
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── db.py
│       ├── models.py            # SQLAlchemy
│       ├── schemas.py           # Pydantic API models
│       ├── bus.py               # in-memory pub/sub for SSE
│       ├── storage.py
│       ├── parser/
│       │   ├── pdf.py           # pdfplumber → lines with coordinates
│       │   ├── classify.py      # lines → typed elements
│       │   ├── scenes.py        # elements → scenes
│       │   └── types.py         # parser-internal Pydantic models
│       ├── agents/
│       │   ├── schemas.py       # stage-boundary contracts
│       │   ├── extract.py
│       │   ├── canonical.py
│       │   ├── tools.py         # Parallel Search ADK tool
│       │   ├── research.py
│       │   ├── rubric.py
│       │   ├── assess.py
│       │   ├── workflow.py
│       │   └── runner.py        # background task orchestration
│       └── routers/
│           ├── scripts.py
│           ├── runs.py
│           ├── findings.py
│           └── stream.py
└── web/
    └── app/, components/, lib/
```

## Architecture in one diagram

```
POST /api/scripts  ──► parser (deterministic, NO AI) ──► scripts,
                                                          scenes,
                                                          script_elements
                        ▲ synchronous: returns 201 with parsed structure

POST /api/runs     ──► 202, starts background task
                            │
                            ▼
                     ADK SequentialAgent
                       ├─ extract     Flash, NO tools
                       ├─ dedup       plain Python, no model
                       ├─ research    ParallelAgent fan-out (cap 5–8)
                       │                Flash + Parallel Search
                       ├─ assess      Pro, NO tools, batched ~10
                       └─ compose     plain Python
                            │
                            ▼
                     elements, research_cache, findings
                            │
GET /api/runs/{id}/stream ◄─┘  SSE progress events
```

## The two rules that define correctness

**Rule 1 — the orchestrator is code, not a model.** Control flow is
known in advance: extract → dedup → research → assess → compose. Do
**not** build a manager agent that decides which sub-agent to call.
Use ADK `SequentialAgent` and `ParallelAgent`. The model decides
content; the graph decides control flow.

Autonomy exists in exactly one place: inside the research agent, which
loops search → evaluate → refine with a hard cap of 6 tool calls.

**Rule 2 — tool isolation is a correctness property.**

| Agent | Tools | Reason |
|---|---|---|
| Extraction | **none** | An extraction agent with search will report elements that are not in the script |
| Research | Parallel Search only | Its entire job |
| Assessment | **none** | It can only cite evidence IDs it was handed, so every citation is verifiable by construction |

Do not add tools to extraction or assessment for any reason.

## ADK version warning

`google-adk` is on 2.x. Version 2.0 broke the 1.x agent API, event
model, and session schema. Most tutorials and blog posts target 1.x and
will not run. Where this spec describes ADK *intent* rather than exact
signatures, consult the current official documentation rather than
guessing at an API.

---

# §1 · Domain Rules

These are facts about screenwriting and rights clearance that cannot be
inferred from the code. Several tasks are impossible to implement
correctly without them.

## 1.1 Screenplay structure

A screenplay is composed of typed blocks. **The type is encoded in
horizontal indentation**, because the format is rigidly standardised
(Courier 12pt, fixed margins).

| Block type | Approx. left margin | Example |
|---|---|---|
| `scene_heading` | 1.5″ | `INT. DINER - NIGHT` |
| `action` | 1.5″ | `Sarah drops a coin in the jukebox.` |
| `dialogue` | 2.5″ | `God, I haven't heard this in years.` |
| `parenthetical` | 3.1″ | `(not looking up)` |
| `character` | 3.7″ | `SARAH` |
| `transition` | right-aligned | `CUT TO:` |

**Do not hard-code these margins.** Real scripts come from different
software with different margins. Derive the clusters per document from
a histogram of left x-coordinates (see B4).

## 1.2 Scene headings ("slug lines")

Every scene opens with a slug line. A scene runs from one slug line to
the next.

```
INT. DINER - NIGHT
│    │       └── time of day
│    └────────── location
└─────────────── interior or exterior
```

Variants that must be handled:

```
EXT. PARKING LOT - DAY
INT./EXT. CAR - MOVING - NIGHT
I/E. WAREHOUSE - CONTINUOUS
INT. DINER - KITCHEN - NIGHT        (sub-location)
INT. DINER - LATER                  (relative time)
EXT. BEACH - MAGIC HOUR
```

**Detection rule:** an ALL-CAPS line at the leftmost margin that starts
with `INT`, `EXT`, `I/E`, or `INT./EXT`.

### Three traps

**Mini-slugs are NOT new scenes.** Lines like `ANGLE ON THE JUKEBOX`,
`BACK TO SCENE`, `LATER`, `MOMENTS LATER` are ALL-CAPS and at the left
margin but redirect the camera *within* a scene. The INT/EXT prefix is
the discriminator — this is why you check the prefix rather than
merely "is this line uppercase".

**Production drafts carry mirrored scene numbers** in both margins:

```
14      INT. DINER - NIGHT                                      14
```

Strip leading and trailing numeric tokens before matching.

**Page furniture must be dropped:** `CONTINUED:` at page tops,
`(CONTINUED)` at page bottoms, bare page numbers, and revision
asterisks in the right margin.

## 1.3 Character cue suffixes

Character cues carry suffixes that must be stripped to get the name:

- `(V.O.)` — voiceover
- `(O.S.)` — off-screen
- `(CONT'D)` — continuing after an interruption
- Combinations: `SARAH (V.O.) (CONT'D)`

When dialogue breaks across a page you will see `(MORE)` at the bottom
of one page and `SARAH (CONT'D)` at the top of the next. These two
blocks must be stitched into one.

## 1.4 The clearance rule that defines the product

**Where an element appears changes its legal character.** This is the
single most important domain fact in the system.

```
Sarah drops a coin in the jukebox. "TAKE ON ME" fills the room.
```
→ `element_type = action` → the song plays on screen → requires a
**synchronization licence** (composition, from the publisher) **and** a
**master use licence** (that recording, from the label) → **RED**

```
                    SARAH
        God, I haven't heard "Take On Me" since high school.
```
→ `element_type = dialogue` → the title is merely referenced → titles
are not copyrightable, no recording is used → **GREEN**

Same string. Opposite ratings. The only distinguishing factor is
`element_type`, which is why that field must survive from parser to
assessment intact.

## 1.5 Element categories

| Category | What it covers | Typical rating logic |
|---|---|---|
| `music` | Songs, scores, cues | Action = sync + master. Dialogue = title reference only |
| `trademark` | Brands, products, logos | Depiction is legal; **disparaging use is not**. Visible on camera → clearance |
| `artwork` | Paintings, sculptures, photographs | Copyright = life + 70 years. Rothko d.1970 → protected until 2040 |
| `person` | Real named individuals | Passing non-defamatory mention = low. Portrayal as a character = high |
| `location` | Real businesses, landmarks | Trademark + trade dress → location agreement |
| `clip` | Film/TV footage | Always requires a footage licence |
| `literary` | Quoted text, poems, books | Public domain cutoff applies |
| `logo` | Visible marks | As trademark |
| `product` | Product placement | As trademark, plus possible placement revenue |
| `character_name` | Fictional names that may match real people | Defamation exposure — see below |
| `other` | Anything else clearable | — |

## 1.6 The non-obvious category

Real clearance reports check things that are not obviously "clearable":

```
DR. RAYMOND KESSLER, 50s, a Boston oncologist, reviews the chart.
```

Nothing here is licensed. But if a real Boston oncologist named Raymond
Kessler exists, that is a defamation exposure. Clearance research checks
fictional character names against real people in the same profession and
city. The same applies to phone numbers (hence the 555 convention),
licence plates, street addresses, and URLs.

This is `category = character_name` and it is a legitimate Parallel
Search task.

## 1.7 Product posture

The tool **flags and cites**. It does not make legal determinations.
Every finding must be reviewable and overridable by a human. All report
output carries: *"Not a legal determination — for review by qualified
counsel."*

---

# §2 · Database Schema

The complete schema is in `db/init.sql`. Two layers:

- **Parsed layer** (`scripts`, `scenes`, `script_elements`) — written
  by the parser during upload. Deterministic, no AI.
- **Agent layer** (`runs`, `elements`, `research_cache`, `findings`) —
  written per run.

## Fields whose purpose is not obvious

| Field | Why it exists |
|---|---|
| `elements.canonical_name` | Dedup key **and** research cache key. Format `{category}:{slug}[:{qualifier}]`, e.g. `music:take_on_me:a-ha` |
| `elements.element_type` | Denormalised from `script_elements.type` **on purpose**. Drives the rubric (§1.4) and must not change retroactively if a re-parse alters classification |
| `elements.char_start/char_end` | Offsets into `script_elements.text`, so the UI highlights the exact phrase, not the whole paragraph |
| `research_cache.canonical_name` (PK) | Keyed on the element, **not** on run or script. "Take On Me" resolves identically for every production forever — so marginal cost falls with volume |
| `findings.risk = 'unresearched'` | Fourth state for failed research. Pinned **above** RED in the UI. A report that silently drops items is dangerous because the production believes it is covered |
| `findings` `UNIQUE (element_id)` | One finding per mention. Re-running assessment updates rather than accumulating duplicates |
| `runs.rubric_version` | So results stay comparable across runs after prompt changes |

**Cache TTL:** rights change hands. Ownership facts should be
re-researched after ~6 months; public-domain determinations never
expire. Implement as a staleness check on `researched_at`, not a
deletion job.

---

# §3 · Stage Contracts

Every boundary is a validated Pydantic model. Agents never talk to each
other — each writes structured data the next stage reads. **Persist
after every stage**, so a stage-3 failure costs stage 3 only.

## 3.1 Extraction

**Input** — a chunk of 8–10 scenes with element types preserved:

```json
{
  "chunk_id": "ch_2",
  "scenes": [{
    "scene_id": "sc_014",
    "number": 14,
    "heading": "INT. DINER - NIGHT",
    "elements": [
      {"id": "el_2", "type": "action", "page": 22,
       "text": "Sarah drops a coin in the jukebox. \"TAKE ON ME\" fills the room. MARCUS watches from the counter, nursing a COCA-COLA."},
      {"id": "el_4", "type": "dialogue", "character": "SARAH", "page": 22,
       "text": "God, I haven't heard this since high school."}
    ]
  }]
}
```

**Output** — one record per *mention*:

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

The third record resolves the pronoun `"this"` to the song using
surrounding context. Canonicalisation happens here because this is the
only stage with the context to do it.

## 3.2 Research

**Input** — one canonical element with all its mention contexts.

**Output** — an evidence dossier. Facts and citations, **no risk
rating**:

```json
{
  "canonical_name": "music:take_on_me:a-ha",
  "identified_as": "Song, released 1985, performed by a-ha",
  "rights_holders": [
    {"role": "publisher", "name": "...", "confidence": "high"},
    {"role": "master_owner", "name": "...", "confidence": "high"}
  ],
  "public_domain": false,
  "notable_disputes": [],
  "evidence": [
    {"id": "ev_1", "claim": "...", "url": "...", "title": "...", "excerpt": "..."}
  ],
  "queries_run": ["Take On Me a-ha publishing administrator",
                  "Take On Me master recording owner"],
  "search_calls": 3,
  "status": "complete"
}
```

**Critical:** the research agent must **never see the rubric**. If it
knows what makes something RED, it gathers evidence toward a conclusion
instead of gathering evidence. Every claim carries its citation inline,
making an unsupported claim structurally impossible.

## 3.3 Assessment

**Input** — element + dossier + mention contexts + rubric.

**Output** — batched, ~10 elements per call:

```json
{"findings": [{
  "canonical_name": "music:take_on_me:a-ha",
  "per_mention": [
    {"script_element_id": "el_2", "risk": "red",
     "rights_required": ["synchronization", "master_use"],
     "rationale": "Specified to play on screen in an action line, so both the composition and the specific master recording are implicated — two licences from two rightsholders."},
    {"script_element_id": "el_4", "risk": "green",
     "rights_required": [],
     "rationale": "Referenced in dialogue only. Titles are not copyrightable and no recording is used."}
  ],
  "alternatives": [
    "Re-record as a cover — clears the master, publishing still required",
    "Substitute a production-library track in a similar style"
  ],
  "cited_evidence_ids": ["ev_1", "ev_2"]
}]}
```

One research task, two ratings, because `element_type` differs.

**Validation requirement:** every ID in `cited_evidence_ids` must exist
in the dossier that was passed in. Reject the batch if not.

---

# §4 · API Specification

Base path `/api`. JSON unless stated.

### `POST /api/scripts`
Multipart, field `file`. **Synchronous** — parses before responding, so
a scanned PDF is rejected while the user still has the file.

`201`:
```json
{"script_id": "...", "title": "THE LONG WAY DOWN", "source_format": "pdf",
 "page_count": 118, "scene_count": 94,
 "parse_warnings": ["Scene 47 heading ambiguous"], "duplicate_of": null}
```

Errors: `413` too large (>25 MB) · `415` not a PDF ·
`422 {"code": "NO_TEXT_LAYER", "pages_checked": 10}` · `422` unparseable

### `GET /api/scripts/{id}`
Script metadata as above.

### `GET /api/scripts/{id}/scenes?from=&to=`
`{"scenes": [{...scene, "elements": [...]}]}`

### `POST /api/runs`
Body `{"script_id": "..."}` → `202 {"run_id": "...", "status": "pending"}`.
Returns immediately, starts the background task.
`404` unknown script · `409` a run is already in flight.

### `GET /api/runs/{id}`
```json
{"run_id": "...", "script_id": "...", "status": "researching",
 "progress": {"elements_found": 84, "researched": 31, "assessed": 0},
 "stats": {"cache_hits": 12, "tokens_in": 210400, "tokens_out": 18900},
 "started_at": "...", "finished_at": null, "error": null}
```

### `GET /api/runs/{id}/stream`
`text/event-stream`. **Send a full snapshot on connect, then live
events** — a client reconnecting mid-run then recovers without event
replay. Heartbeat every 15s.

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

Events carry **IDs only**; the client fetches the real record. Never
treat the event payload as the source of truth.

### `GET /api/runs/{id}/findings`
Query: `risk`, `category`, `review_status`, `scene`, `limit`, `offset`
→ `{"findings": [...], "total": 84, "counts": {"red": 9, "amber": 31, "green": 44}}`

### `GET /api/findings/{id}`
Finding with full dossier, sources, `queries_run`, alternatives.

### `PATCH /api/findings/{id}`
Body `{"review_status": "overridden", "override_risk": "green", "review_note": "..."}`

### `GET /api/runs/{id}/report?format=json|pdf`

---

# §5 · Task Briefs

Each task states files, interface, rules, and a done-condition.
`[A]` = backend/agent track. `[B]` = frontend/delivery track.

---

## A1 · Repo and stack `[B]`

**Create:** `docker-compose.yml`, `api/Dockerfile`,
`api/requirements.txt`, `web/Dockerfile`, `.env.example`, `.gitignore`,
`LICENSE` (MIT), `api/app/main.py`.

**Rules**
- `.gitignore` must be committed **before** the first `git add`. Must
  include `.env`, `__pycache__`, `node_modules`, `.next`, `uploads/*`.
- `LICENSE` must be named exactly that, at repo root, standard MIT text
  — GitHub only renders the licence badge if it matches a recognised
  licence, and it fails silently.
- Compose: three services `db`, `api`, `web`. **Single uvicorn worker**
  — the SSE event bus is in-process memory and multiple workers would
  split it, silently breaking the live feed for some clients.
- Mount `~/.config/gcloud` read-only into `api` so Application Default
  Credentials work without a service-account key file. No secret enters
  the repo.
- `NEXT_PUBLIC_API_URL=http://localhost:8080` — resolved by the
  **browser**, not the container, so it is not `http://api:8080`.

**Done when:** `docker compose up` starts all three,
`localhost:8080/docs` renders, `localhost:3000` renders,
`git log --stat` shows no `.env`.

---

## A2 · Probe scripts `[A]` ← implement first

Standalone scripts in `api/scripts/`. No FastAPI, no Docker, no agent.
Purpose: discover the real response shapes that every downstream
contract is designed around.

**Create**
- `probe_parallel.py` — one Parallel Search call via `parallel-web`.
  Print the raw response object, then `json.dumps(..., indent=2)`.
- `probe_gemini.py` — one Gemini call via `google-genai` with a Pydantic
  response schema. Confirm structured output is **enforced**, not just
  requested.
- `probe_gemini_pdf.py` — send PDF bytes directly to Gemini. This is a
  fallback path if pdfplumber disappoints.

**Run `probe_parallel.py` with three query shapes** and record how
result quality degrades:
1. Easy: `"Take On Me a-ha publishing rights"`
2. Obscure: a minor 1970s painter
3. Ambiguous: a common-word title

**Write `docs/api-notes.md`** answering: what fields come back? snippets
or full text? how are results ranked? is there a result or token cap?
what does an error look like?

**Done when:** all three print real data and `docs/api-notes.md`
describes the actual shapes.

---

## A3 · Schema and models `[A]`

**Create:** `db/init.sql` (already specified — see §2),
`api/app/models.py`, `api/app/db.py`, `api/app/config.py`, Alembic
baseline.

**Interface**
```python
# db.py
engine = create_async_engine(settings.database_url)
async def get_session() -> AsyncGenerator[AsyncSession, None]: ...

# config.py — pydantic-settings
class Settings(BaseSettings):
    database_url: str
    upload_dir: Path
    google_cloud_project: str
    google_cloud_location: str = "us-central1"
    parallel_api_key: str
    extraction_model: str = "gemini-2.5-flash"
    assessment_model: str = "gemini-2.5-pro"
    max_upload_bytes: int = 25 * 1024 * 1024
    research_concurrency: int = 6
    research_call_cap: int = 6
```

**Note:** `init.sql` runs only on an empty volume. `docker compose down -v`
is required to re-apply changes. Once real data exists, use Alembic.

**Done when:** a script writes a `scripts` row and reads it back through
the ORM inside the container.

---

## B1 · Upload endpoint `[A]`

**Create:** `api/app/routers/scripts.py`, `api/app/storage.py`

**Rules**
- Stream to `tempfile`; enforce the 25 MB cap **during** the stream and
  abort mid-write. Do not read the whole file into memory first.
- Validate the `%PDF` magic bytes, **not** the filename extension.
- Compute SHA-256 while streaming. On match, return the existing script
  with `duplicate_of` set — do not re-parse.
- Storage path: `{UPLOAD_DIR}/{script_id}/original.pdf`.
- **Never mutate the original file.** It is the provenance record every
  finding traces back to.
- Parse synchronously (B2–B6) before responding.

**Done when:** curl upload returns a `script_id`; a 30 MB file gets
`413`; a `.docx` gets `415`; re-uploading returns the same `script_id`.

---

## B2 · Page extraction `[A]`

**Create:** `api/app/parser/pdf.py`, `api/app/parser/types.py`

```python
class Word(BaseModel):
    text: str
    x0: float; x1: float; top: float; bottom: float

class Line(BaseModel):
    page: int
    x0: float          # leftmost word's x0 — the classification signal
    text: str
    words: list[Word]

def extract_lines(pdf_path: Path) -> list[Line]: ...
```

**Rules**
- Use `page.extract_words()`, not `extract_text()` — you need
  coordinates.
- Group words into lines by `top` within ~2pt tolerance.
- Preserve reading order.

**Done when:** the test script yields lines whose `x0` values form
visible clusters — action near one value, character cues near a larger
one.

---

## B3 · Text-layer detection `[A]`

```python
def has_text_layer(pdf, sample: int = 10) -> bool:
    pages = pdf.pages[:sample]
    chars = sum(len((p.extract_text() or "").strip()) for p in pages)
    return chars / max(len(pages), 1) > 100
```

**Context:** a scanned PDF is a photograph of a page — the words are
visually present and computationally absent. `extract_text()` returns
an empty string rather than raising, so the check must be explicit. A
real screenplay page yields 800–1,500 characters.

**Rules**
- Wire into B1 **before** storage. Return
  `422 {"code": "NO_TEXT_LAYER", "pages_checked": 10}`.
- Handle the hybrid case — some pages have text, some do not. Record
  which pages failed in `parse_warnings` and continue.
- A watermarked PDF is text-based with an image layer on top; it parses
  fine. You will see a stray text object per page (the recipient's
  name) which is filtered by position.

**Done when:** a scanned PDF is rejected with a clear message and never
reaches the parser.

---

## B4 · Element classification `[A]` ← hardest parser task, allow a full day

**Create:** `api/app/parser/classify.py`

```python
class ScriptElementDraft(BaseModel):
    type: Literal["scene_heading","action","character",
                  "dialogue","parenthetical","transition"]
    character: str | None
    page: int
    text: str

def classify(lines: list[Line]) -> list[ScriptElementDraft]: ...
```

**Algorithm**
1. Build a histogram of `x0` across all lines. **The clusters are the
   margins.** Derive them per document — do not hard-code inches
   (§1.1).
2. Map clusters: leftmost → `action`/`scene_heading`; largest →
   `character`; between → `dialogue`; slightly right of dialogue →
   `parenthetical`; right-aligned or text ending in `TO:` →
   `transition`.
3. `scene_heading` vs `action`: ALL-CAPS **and** starts with
   `INT`/`EXT`/`I/E`/`INT./EXT` (§1.2).
4. Strip `(V.O.)`, `(O.S.)`, `(CONT'D)` and combinations from character
   cues (§1.3).
5. Merge consecutive same-type lines into one block.
6. Stitch page-split dialogue: drop `(MORE)`, merge the following
   `NAME (CONT'D)` block into the previous one (§1.3).

**Done when:** every block in the test script is correctly typed, and a
real feature-length script passes a manual spot check of ten random
pages.

---

## B5 · Scene grouping `[A]`

**Create:** `api/app/parser/scenes.py`

```python
def group_scenes(elements: list[ScriptElementDraft]) -> list[SceneDraft]: ...
def parse_heading(heading: str) -> tuple[str|None, str|None, str|None]:
    """→ (int_ext, location, time_of_day)"""
```

**Rules** — all from §1.2
- Strip leading **and trailing** numeric tokens (mirrored production
  scene numbers).
- Drop page furniture: `CONTINUED:`, `(CONTINUED)`, bare page numbers,
  right-margin revision asterisks.
- Start a new scene on each `scene_heading`; everything else appends to
  the current scene.
- **Reject mini-slugs** — `ANGLE ON…`, `BACK TO SCENE`, `LATER`,
  `MOMENTS LATER` are ALL-CAPS without the INT/EXT prefix and are not
  new scenes. This is the most common parser bug.
- Handle `INT./EXT.`, `I/E.`, sub-locations (`DINER - KITCHEN`), and
  `CONTINUOUS` / `LATER` / `MAGIC HOUR`.
- Record `page_start` and `page_end`.
- Anything ambiguous → append to `parse_warnings`; **never fail the
  upload** for an ambiguous heading.

**Done when:** scene count on a real script matches a manual count and
no mini-slug has created a spurious scene.

---

## B6 · Persist and read `[A]`

**Rules**
- Write `scenes` + `script_elements` in **one transaction** inside B1,
  before the response returns.
- `GET /api/scripts/{id}` and `GET /api/scripts/{id}/scenes?from=&to=`.

**Done when:** upload returns `201` with real page and scene counts and
the scenes endpoint returns the parsed structure.

---

## B7 · Test screenplay `[A or B]` ← 2 hours, highest ROI in the project

Write ~10 pages in correct screenplay format with planted elements whose
correct answers are known in advance. Without ground truth you can only
measure that the agent produced output, not that it was right.

**Must contain**

| Planted element | Expected |
|---|---|
| A specific song playing in an **action** line | RED |
| The **same song** referenced in **dialogue** | GREEN |
| A named brand held to camera | AMBER |
| The **same brand** used disparagingly | RED |
| A 20th-century painting on a wall | RED |
| A living public figure named in dialogue | AMBER |
| A real restaurant as a location | AMBER |
| A line of Shakespeare | GREEN |
| A fictional doctor with a plausible real name | the hard case (§1.6) |

**Also plant parser edge cases in the same document:** a mini-slug, a
page-split dialogue block, an `INT./EXT.` heading, and mirrored scene
numbers.

**Write `docs/ground-truth.md`** with the expected rating and reasoning
for each.

**Done when:** any pipeline change can be scored against a fixed answer
key.

---

## C1 · Extraction agent `[A]`

**Create:** `api/app/agents/schemas.py`, `api/app/agents/extract.py`

```python
class ExtractedElement(BaseModel):
    script_element_id: str
    category: Literal["music","trademark","artwork","person","location",
                      "clip","literary","logo","product",
                      "character_name","other"]
    surface_form: str
    canonical_name: str
    char_start: int | None
    char_end: int | None
    confidence: float
```

**Rules**
- Flash. **No tools** (§0 Rule 2).
- Enforce structured output against the schema — do not parse free text.
- The prompt must instruct: report only what is present in the text;
  return exact `char_start`/`char_end` offsets into the element text;
  resolve pronouns to their referent where context allows (§3.1).
- Categories are listed in §1.5.

**Done when:** one scene yields correct elements whose offsets actually
index the right substring — verify by slicing.

---

## C2 · Chunking and full extraction `[A]`

**Rules**
- Chunk by scene groups of ~8–10 pages. Context window is **not** the
  constraint (a 120-page script is ~35k tokens); chunking exists for
  recall and parallelism.
- Run chunks concurrently, capped.
- **Persist `elements` per chunk as it completes**, not at the end.
- Second pass over the whole script for recurring elements set up early
  and paid off late — these must be one finding, not two.

**Done when:** a 100+ page script produces elements across all chunks
with no gaps at chunk boundaries.

---

## C3 · Canonicalisation and dedup `[A]`

**Create:** `api/app/agents/canonical.py`

```python
def canonicalise(category: str, surface_form: str,
                 qualifier: str | None = None) -> str:
    """→ '{category}:{slug}[:{qualifier}]', e.g. 'music:take_on_me:a-ha'"""
```

**Rules**
- Lowercase, strip punctuation, slugify.
- Group mentions by canonical name before research.
- Log the reduction ratio into `runs.stats` — expect roughly 2:1.

**Done when:** twelve Coca-Cola mentions collapse to one research task
and the ratio appears in run stats.

---

## C4 · Parallel Search tool `[A]`

**Create:** `api/app/agents/tools.py`

```python
class SearchResult(BaseModel):
    title: str; url: str; snippet: str

async def parallel_search(query: str) -> list[SearchResult] | ToolError: ...
```

**Rules**
- Wrap the `parallel-web` SDK as an ADK tool.
- Timeout and retry with exponential backoff.
- **Catch exceptions and return a structured error** — never raise into
  the agent loop, which would kill the run.
- Return snippets by default; full page text only on explicit request.
  This is a token-budget rule (§6).

**Done when:** callable from an ADK agent, and a forced API failure
returns a clean error object rather than an exception.

---

## C5 · Research agent `[A]`

**Create:** `api/app/agents/research.py`

**Rules**
- Flash. Parallel Search tool **only**.
- Loop: search → evaluate → refine → stop when satisfied. **Hard cap at
  6 tool calls** (`settings.research_call_cap`).
- After each search, append to a compact evidence note and **discard the
  raw payload**. Otherwise turn six carries turns one through five and
  the token cost compounds.
- Output the `ResearchDossier` shape in §3.2.
- **The rubric must not appear in this prompt** (§3.2). This is easy to
  violate accidentally while iterating on prompts and it silently
  destroys citation integrity.
- Check `research_cache` before running; write after. Cache is keyed on
  `canonical_name` only — nothing script-specific goes in it.
- `status` ∈ `complete` | `partial` | `failed`. A failure marks the
  element and **the run continues**.

**Done when:** one element produces a dossier with real cited evidence,
and a second run of the same script is a cache hit with zero API calls.

---

## C6 · Rubric and assessment `[A]` ← two days; highest-leverage task

**Create:** `api/app/agents/rubric.py`, `api/app/agents/assess.py`

**`rubric.py`** holds the criteria as a **versioned constant**
(`RUBRIC_VERSION = "1.0"`, recorded on each run).

The rubric must encode:
- **The decisive rule (§1.4):** `element_type` changes the rating.
  Action line = appears on screen = clearance needed. Dialogue =
  reference only.
- Per-category criteria (§1.5): music (sync vs master), trademark
  (depiction vs disparagement), artwork (death + 70), person (mention vs
  portrayal), location (trade dress), clip (always licensed), literary
  (PD cutoff), character_name (§1.6).
- Rating definitions: **RED** = must be licensed or replaced before
  shooting · **AMBER** = probably clearable, verify before committing ·
  **GREEN** = public domain, de minimis, or nominative use.

**`assess.py`**
- Pro. **No tools** (§0 Rule 2).
- Batched ~10 elements per call — a 1,500-token rubric sent 100 times
  is 150k tokens of pure repetition.
- Output the shape in §3.3.
- **Validate that every ID in `cited_evidence_ids` exists in the passed
  dossier. Reject the batch if not.**

**Tuning loop:** score against `docs/ground-truth.md` and iterate.
Target: **zero missed REDs**, and a false-positive rate low enough that
a reader trusts the report. Over-flagging destroys usefulness faster
than under-flagging.

**Done when:** the test script scores clean against ground truth, and
the planted same-song-two-contexts pair rates RED and GREEN
respectively.

---

## C7 · Workflow wiring `[A]`

**Create:** `api/app/agents/workflow.py`

**Rules**
- ADK `SequentialAgent` over extract → dedup → research → assess →
  compose.
- Research stage is a `ParallelAgent` fan-out, **concurrency capped at
  5–8** (`settings.research_concurrency`). Eighty simultaneous agents
  will rate-limit you on both Gemini and Parallel.
- Shared token-bucket limiter across Gemini and Parallel calls.
- Emit token counts, cache hit rate, and dedup ratio into `runs.stats`.
- **Do not add a manager agent** (§0 Rule 1).

**Done when:** one call runs the whole graph and eighty elements do not
trigger rate limits.

---

## C8 · Run orchestration `[A]`

**Create:** `api/app/agents/runner.py`, `api/app/routers/runs.py`

**Rules**
- `POST /api/runs` → `202`, starts an async background task.
- Status transitions: `pending` → `extracting` → `researching` →
  `assessing` → `composing` → `complete` | `failed`.
- `409` if a run is already in flight for that script.
- **Persist after every stage** — a stage-3 failure must cost stage 3
  only, so assessment can be re-run against dossiers already on disk.
- Top-level exception handler sets `failed` with the error text.

**Done when:** killing the API mid-run leaves a coherent partial state
in the database and the run reports `failed` rather than hanging.

---

## C9 · Event bus and SSE `[A]`

**Create:** `api/app/bus.py`, `api/app/routers/stream.py`

**Rules**
- In-memory pub/sub, one channel per `run_id`.
- `sse-starlette`. **Snapshot on connect, then live events** — a client
  reconnecting mid-run recovers without event replay.
- Event types in §4.
- **Events carry IDs only.** The client fetches the real record; the
  payload is never the source of truth.
- Heartbeat every 15s so proxies do not drop the connection.

**Done when:** `curl -N` on the stream prints events live and
reconnecting mid-run recovers correct state.

---

## D1 · Frontend shell `[B]`

Start this on Aug 12 against **stubbed JSON fixtures**, not on Aug 23
against a real API. Agree response shapes with track A on Aug 11.

**Rules**
- TanStack Query provider, API client, error boundary.
- **Generate types** with `openapi-typescript` against
  `localhost:8080/openapi.json`. Never hand-write them — they will drift.
- Upload screen: dropzone, progress, and a clear message for
  `NO_TEXT_LAYER`.
- Routes: `/`, `/scripts/[id]`, `/runs/[id]`.
- Use the App Router for routing but stay in `"use client"` for
  everything stateful. Do not build around RSC or server actions — every
  screen here is live-state driven.

---

## D2 · Script pane `[B]`

**Rules**
- Render the **parsed text**, not the PDF. Two reasons: you can only
  highlight `char_start`/`char_end` spans in text you control, and the
  rendered script is live proof the parser works.
- Screenplay CSS: monospace, character cues indented ~34%, dialogue
  ~22%, scene headings caps at the left margin.
- Virtualise with TanStack Virtual — a 118-page script is thousands of
  DOM nodes.
- Expose `scrollToPage(n)` and `scrollToElement(id)`.

---

## D3 · Findings pane `[B]`

**Rules**
- **Group by canonical element**, expandable to mentions. A producer
  thinks "we have a Coca-Cola problem", not twelve problems.
- **Split the group when mentions rate differently** — that split is the
  interesting part (§1.4).
- Filters: risk, category, review status, scene range.
- Sort: risk desc then scene, with a script-order toggle.
- **Pin `unresearched` findings above RED** as "needs manual review"
  (§2).

---

## D4 · Bidirectional linking `[B]`

Click a finding → script scrolls to the page and flashes the
`char_start`/`char_end` span. Click a highlighted span → the finding
opens. Highlight colour = risk colour.

---

## D5 · Live run `[B]`

**Rules**
- `EventSource` on `/runs/{id}/stream`.
- **Never show a full-screen spinner.** Show the parsed script
  immediately; findings drop in as events arrive.
- Live query strip showing the current `research.query` and
  "31 / 84 researched".
- Reconnect with backoff; fall back to polling `GET /runs/{id}`.

---

## D6 · Finding detail `[B]`

Rationale · `rights_required` · rights holders · sources with excerpts,
linked out · `queries_run` (the actual searches the agent made) ·
alternatives.

**Confidence renders as `confirmed` / `verify` / `uncertain` — never a
decimal.** Users cannot calibrate `0.72` and it makes everything feel
shaky. Sort uncertain items **up**; never hide a finding for low
confidence in a tool whose purpose is catching things.

---

## D7 · Accept and override `[B]`

`PATCH /api/findings/{id}` with optimistic update. Override risk plus a
free-text note. A "31 of 84 reviewed" counter — this reframes the
product from a document into a task you can finish.

---

## D8 · Summary header and demo landing `[B]` ← small, decisive

**Rules**
- Always-visible risk counts and review progress.
- Impact line, stated flatly: this run took N minutes; the manual
  equivalent is 5–10 business days. **No celebratory banner** — it
  undercuts the professional tone.
- **A visitor landing on the hosted URL must see a completed demo run**,
  not an empty dropzone. "Upload your own" is secondary. Without this, a
  visitor with no screenplay has nothing to do and leaves.
- Demo run replays instantly from cache.

---

## E1 · Report export `[B]`

`GET /api/runs/{id}/report?format=pdf`. Shaped like a real clearance
report: cover page with counts, findings grouped by category, each with
scene, page, rights required, holders, sources. Carries the disclaimer
in §1.7.

---

## E2 · Deploy `[B]`

- Multi-stage production Dockerfiles (`npm run build` + `npm start`, not
  `npm run dev`).
- Cloud Run for `api` and `web`; managed Postgres.
- Secrets via Secret Manager, not console env vars.
- GCS for uploads with **signed URLs only — never a public bucket**.
  Unreleased screenplays are among the most confidential documents in
  the industry.
- CORS locked to the web origin.

**Done when:** a full run completes from a phone on cellular data.

---

# §6 · Token and Cost Budget

**The context window is not the constraint.** A 40k-token script fits in
Gemini's window many times over. You will never chunk for capacity.

The constraint is the research fan-out. Naive, ~100 elements:

| Stage | Tokens |
|---|---|
| Extraction | ~46k |
| Research | 1.0–1.5M ← 90% of spend |
| Assessment | ~400k |

Five levers, in order of impact:

1. **Deduplicate before researching** (C3). Twelve mentions, one task.
   Typically halves the element count.
2. **Cache by canonical name across runs and scripts** (C5). Marginal
   cost falls with volume. Also makes the re-run demo instant.
3. **Do not accumulate raw search results** (C5). Compact evidence note
   after each search; discard the payload.
4. **Pass snippets, not full pages** (C4).
5. **Batch assessment ~10 per call** (C6).

After all five: well under $1 per feature. Without dedup and caching:
10–20× that, plus minutes of latency that will not fit in a 3-minute
demo video.

---

# §7 · Definition of Done

A task is complete only when its done-condition is verifiable. In
addition, the following must hold before submission:

- [ ] `google-adk` / `google-cloud-aiplatform` imported and **called at
      runtime** in the repo
- [ ] `parallel-web` imported and **called at runtime** in the repo
- [ ] No other AI vendor's SDK anywhere in the project
- [ ] Public repo; `LICENSE` badge renders in the GitHub About sidebar
- [ ] `.env` absent from the entire git history
- [ ] Hosted URL completes a full run from a phone on cellular data
- [ ] README states architecture, setup, and honest limitations
