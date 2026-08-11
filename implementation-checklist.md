# Implementation Checklist

Every task has a **done-when** you can verify. If you can't verify it,
it isn't done. Tasks marked **[A]** are backend/agent, **[B]** are
frontend/delivery — the split between the two of you.

A note on ADK: it is on 2.x, which broke the 1.x agent API, event model,
and session schema. Nearly every tutorial online targets 1.x. Where this
document describes ADK intent rather than exact signatures, check
`adk.dev` for the current API rather than guessing.

---

# BLOCK A — Foundations · Aug 10–11

## A1 · Repo and stack **[B]**

- [ ] Create the public repo with `LICENSE` (MIT) at root. Open the
      GitHub page and confirm the About sidebar shows "MIT license" —
      it fails silently
- [ ] Directory tree: `api/app/{agents,routers}`, `api/scripts`,
      `web/`, `db/`, `docs/`
- [ ] `.gitignore` written and committed **before** the first `git add`
      (`.env`, `__pycache__`, `node_modules`, `.next`, `uploads/*`)
- [ ] `docker-compose.yml`, `api/Dockerfile`, `api/requirements.txt`,
      `web/Dockerfile`, `db/init.sql`, `.env.example`
- [ ] `npx create-next-app@latest web --ts --tailwind --app --no-src-dir`
- [ ] `api/app/main.py` with a `/health` endpoint returning `{"ok": true}`
- [ ] `gcloud auth application-default login` on both machines

**Done when:** `docker compose up` starts all three services,
`localhost:8080/docs` renders, `localhost:3000` renders, and
`git log --stat` shows no `.env`.

## A2 · Probe scripts **[A]** ← start here

Bare scripts. No FastAPI, no Docker, no agent. You are learning the
response shapes that every downstream contract is designed around.

- [ ] `api/scripts/probe_parallel.py` — one Parallel Search call via
      `parallel-web`. Print the **raw** response, then
      `json.dumps(..., indent=2)`
- [ ] Note: what fields come back? Snippets or full text? How are
      results ranked? Is there a token/result cap?
- [ ] Run three query shapes: an easy one ("Take On Me a-ha publishing
      rights"), an obscure one (a minor 1970s painter), and a
      deliberately ambiguous one. Note how quality degrades
- [ ] `api/scripts/probe_gemini.py` — call Gemini via `google-genai`
      with a Pydantic response schema. Confirm structured output is
      enforced, not just requested
- [ ] `api/scripts/probe_gemini_pdf.py` — send PDF bytes directly to
      Gemini. Confirm it reads them (a fallback if pdfplumber
      disappoints)
- [ ] Write findings into `docs/api-notes.md`

**Done when:** all three print real data and `docs/api-notes.md`
describes the actual response shapes.

## A3 · Schema and models **[A]**

- [ ] `db/init.sql` — the full schema: `scripts`, `scenes`,
      `script_elements`, `runs`, `elements`, `research_cache`, `findings`
- [ ] `api/app/models.py` — SQLAlchemy 2 declarative models
- [ ] `api/app/db.py` — async engine, session factory, `get_session`
      dependency
- [ ] `api/app/config.py` — pydantic-settings reading env vars
- [ ] `alembic init`, baseline migration

**Done when:** a script writes a `scripts` row and reads it back
through the ORM inside the container.

---

# BLOCK B — Parser · Aug 12–15 · zero AI

## B1 · Upload endpoint **[A]**

- [ ] `POST /api/scripts`, `UploadFile`, stream to `tempfile`
- [ ] Enforce 25 MB **during** the stream, not after — abort mid-write
- [ ] Validate magic bytes (`%PDF`), not the extension
- [ ] SHA-256 while streaming; on match return the existing script with
      `duplicate_of` set
- [ ] Move to `{UPLOAD_DIR}/{script_id}/original.pdf`
- [ ] Insert `scripts` row

**Done when:** curl uploads a PDF and gets a `script_id`; a 30 MB file
gets `413`; a `.docx` gets `415`; re-uploading the same file returns
the same `script_id`.

## B2 · Page extraction **[A]**

- [ ] `api/app/parser/pdf.py` — open with pdfplumber, iterate pages
- [ ] Per page: `page.extract_words()` → text, `x0`, `x1`, `top`,
      `bottom`
- [ ] Group words into lines by `top` within a tolerance (~2pt)
- [ ] Each line carries `page`, `x0` (leftmost word), text

**Done when:** your test script yields lines with plausible x0 values —
action lines cluster near one value, character cues near a larger one.

## B3 · Text-layer detection **[A]**

- [ ] `has_text_layer(pdf, sample=10)` — mean stripped chars per page > 100
- [ ] Wire into B1, before storage. Return `422` with
      `{"code": "NO_TEXT_LAYER", "pages_checked": 10}`
- [ ] Handle the hybrid case: some pages have text, some don't. Report
      which pages failed in `parse_warnings`

**Done when:** a scanned PDF is rejected with a clear message and never
reaches the parser.

## B4 · Element classification **[A]** ← fiddly, allow a full day

- [ ] Histogram `x0` across all lines. The clusters *are* your margins
- [ ] **Derive margins per document** rather than hard-coding inches —
      scripts vary and a fixed table will fail on real files
- [ ] Classify: leftmost cluster → `action`/`scene_heading`; largest
      cluster → `character`; between them → `dialogue`; slightly right
      of dialogue → `parenthetical`; right-aligned or ending in `TO:`
      → `transition`
- [ ] `scene_heading` vs `action`: ALL-CAPS **and** starts with
      `INT`/`EXT`/`I/E`/`INT./EXT`
- [ ] Strip `(V.O.)`, `(O.S.)`, `(CONT'D)`, `(V.O.) (CONT'D)` from
      character cues
- [ ] Merge consecutive lines of the same type into one block
- [ ] Stitch page-split dialogue: drop `(MORE)`, merge the following
      `NAME (CONT'D)` block into the previous one

**Done when:** every block in your test script is correctly typed, and
you've run it against one real feature-length script with a manual spot
check of ten random pages.

## B5 · Scene grouping **[A]**

- [ ] Strip leading and trailing numeric tokens (mirrored production
      scene numbers)
- [ ] Drop page furniture: `CONTINUED:`, `(CONTINUED)`, bare page
      numbers, right-margin revision asterisks
- [ ] Start a new scene on each `scene_heading`; everything else
      appends to the current one
- [ ] **Reject mini-slugs** — `ANGLE ON…`, `BACK TO SCENE`, `LATER`,
      `MOMENTS LATER` are ALL-CAPS without the INT/EXT prefix. Not new
      scenes
- [ ] Parse the heading into `int_ext`, `location`, `time_of_day`.
      Handle `INT./EXT.`, `I/E.`, sub-locations (`DINER - KITCHEN`),
      and `CONTINUOUS`/`LATER`/`MAGIC HOUR`
- [ ] Record `page_start`, `page_end` per scene
- [ ] Anything ambiguous → `parse_warnings`, don't fail the upload

**Done when:** scene count on a real script matches a manual count, and
no mini-slug has created a spurious scene.

## B6 · Persist and read **[A]**

- [ ] Write `scenes` + `script_elements` in one transaction inside B1,
      before the response returns
- [ ] `GET /api/scripts/{id}` — metadata + `parse_warnings`
- [ ] `GET /api/scripts/{id}/scenes?from=&to=` — scenes with nested
      elements

**Done when:** upload returns `201` with real page and scene counts,
and the scenes endpoint returns the parsed structure.

## B7 · Test screenplay **[A or B]** ← 2 hours, highest ROI in the plan

Write ~10 pages in correct format with planted elements whose answers
you already know:

- [ ] A specific song playing in an action line (should be RED)
- [ ] The **same song** referenced in dialogue (should be GREEN)
- [ ] A named brand held to camera (AMBER)
- [ ] The same brand used disparagingly (RED)
- [ ] A 20th-century painting on a wall (RED)
- [ ] A living public figure named in dialogue (AMBER)
- [ ] A real restaurant as a location (AMBER)
- [ ] A line of Shakespeare (GREEN)
- [ ] A fictional doctor with a plausible real name (the hard one)
- [ ] A mini-slug, a page-split dialogue block, and a `INT./EXT.`
      heading — parser edge cases in the same document
- [ ] `docs/ground-truth.md` with the expected rating and reasoning for
      each

**Done when:** you can score any pipeline change against a fixed answer
key instead of eyeballing output.

---

# BLOCK C — Agent · Aug 16–22

## C1 · Extraction agent **[A]**

- [ ] `api/app/agents/schemas.py` — Pydantic models for every stage
      boundary
- [ ] `ExtractedElement`: `script_element_id`, `category`,
      `surface_form`, `canonical_name`, `char_start`, `char_end`,
      `confidence`
- [ ] `api/app/agents/extract.py` — ADK agent, Flash, **no tools**
- [ ] Prompt states the categories, requires the exact `char_start`/
      `char_end` offsets, and instructs it to report only what is
      present in the text
- [ ] Enforce structured output against the schema
- [ ] Run on one scene of the test script

**Done when:** one scene yields correct elements with offsets that
actually index the right substring.

## C2 · Chunking and full extraction **[A]**

- [ ] Chunk by scene groups of ~8–10 pages
- [ ] Run chunks concurrently, capped
- [ ] Persist `elements` per chunk as it completes, not at the end
- [ ] Second pass over the whole script for recurring elements set up
      early and paid off late

**Done when:** a full 100+ page script produces elements across all
chunks with no gaps at chunk boundaries.

## C3 · Canonicalization and dedup **[A]**

- [ ] Normalize `canonical_name`: lowercase, strip punctuation, format
      `{category}:{slug}[:{qualifier}]`
- [ ] Group mentions by canonical name
- [ ] Log the reduction ratio — you want roughly 2:1

**Done when:** twelve Coca-Cola mentions collapse to one research task
and the count appears in run stats.

## C4 · Parallel tool **[A]**

- [ ] `api/app/agents/tools.py` — ADK tool wrapping `parallel-web`
- [ ] Normalize results to `{title, url, snippet}`
- [ ] Timeout, retry with backoff, catch and return a structured error
      rather than raising
- [ ] Return snippets by default; full text only on explicit request

**Done when:** the tool is callable from an ADK agent and a forced
API failure returns a clean error instead of killing the run.

## C5 · Research agent **[A]**

- [ ] `api/app/agents/research.py` — Flash, Parallel tool only
- [ ] Loop: search → evaluate → refine → stop. **Hard cap at 6 calls**
- [ ] After each search, append to a compact evidence note and
      **discard the raw payload** — otherwise turn six carries turns
      one through five
- [ ] Output `ResearchDossier`: `identified_as`, `rights_holders`,
      `public_domain`, `notable_disputes`, `evidence[]` (each with
      `id`, `claim`, `url`, `excerpt`), `queries_run`, `search_calls`,
      `status`
- [ ] **The rubric must not appear in this prompt.** If it knows what
      makes something RED it gathers evidence toward a conclusion
- [ ] Cache check before running; cache write after
- [ ] `status` ∈ `complete` | `partial` | `failed`; failures mark the
      element and the run continues

**Done when:** one element produces a dossier with real cited evidence,
and a second run of the same script is a cache hit with zero API calls.

## C6 · Rubric and assessment **[A]** ← two days, the highest-leverage work

- [ ] `api/app/agents/rubric.py` — the rating criteria as a versioned
      constant
- [ ] Encode the decisive rule: **`element_type` changes the rating.**
      Action line = appears on screen = clearance needed. Dialogue =
      reference only
- [ ] Per-category criteria: music (sync vs master), trademark
      (depiction vs disparagement), artwork (death + 70), person
      (mention vs portrayal), location (trade dress), clip (always
      licensed), literary (PD cutoff)
- [ ] `api/app/agents/assess.py` — Pro, **no tools**, batched ~10
- [ ] Input: element + dossier + mention contexts + rubric
- [ ] Output: `per_mention` ratings, `rights_required`, `rationale`,
      `cited_evidence_ids`, `alternatives`
- [ ] **Validate that every cited ID exists in the dossier.** Reject
      the batch if not
- [ ] Score against `docs/ground-truth.md`. Iterate. Target: zero
      missed REDs, and a false-positive rate low enough to be readable
- [ ] Record the rubric version on each run so results stay comparable

**Done when:** the test script scores clean against ground truth, and
your planted same-song-two-contexts pair rates RED and GREEN
respectively.

## C7 · Workflow wiring **[A]**

- [ ] `api/app/agents/workflow.py` — ADK `SequentialAgent` over
      extract → dedup → research → assess → compose
- [ ] Research stage is a `ParallelAgent` fan-out, **concurrency capped
      at 5–8**
- [ ] Shared token-bucket limiter across Gemini and Parallel calls
- [ ] Emit token counts and cache hit rate into `runs.stats`

**Done when:** one call runs the whole graph and eighty elements
don't rate-limit you.

## C8 · Run orchestration **[A]**

- [ ] `POST /api/runs` → `202`, starts an async background task
- [ ] Status transitions: `pending` → `extracting` → `researching` →
      `assessing` → `composing` → `complete` | `failed`
- [ ] `409` if a run is already in flight for that script
- [ ] Persist after every stage — a stage-3 failure costs stage 3 only
- [ ] Top-level exception handler sets `failed` with the error text
- [ ] `GET /api/runs/{id}` with progress counts

**Done when:** killing the API mid-run leaves a coherent partial state
in the database, and the run reports `failed` rather than hanging.

## C9 · Event bus and SSE **[A]**

- [ ] `api/app/bus.py` — in-memory pub/sub, one channel per `run_id`
- [ ] `GET /api/runs/{id}/stream` via sse-starlette
- [ ] **Snapshot on connect**, then live events
- [ ] Events: `stage.started`, `element.extracted`, `research.query`,
      `research.result`, `finding.created`, `run.complete`, `run.failed`
- [ ] Events carry **IDs only** — the client fetches the real record
- [ ] Heartbeat every 15s so proxies don't drop the connection

**Done when:** `curl -N` on the stream endpoint prints events live, and
reconnecting mid-run recovers correct state.

---

# BLOCK D — Frontend · Aug 23–29

Start this on Aug 12 against **stubbed JSON**, not on Aug 23 against a
real API. Agree the response shapes with Person A on Aug 11 and build
from fixtures.

## D1 · Shell **[B]**

- [ ] TanStack Query provider, API client, error boundary
- [ ] `openapi-typescript` against `localhost:8080/openapi.json` —
      generated types, never hand-written
- [ ] Upload screen: dropzone, progress, clear `NO_TEXT_LAYER` message
- [ ] Routes: `/`, `/scripts/[id]`, `/runs/[id]`

**Done when:** a real PDF uploads through the UI and lands in Postgres.

## D2 · Script pane **[B]**

- [ ] Render the **parsed text**, not the PDF — you can only highlight
      spans in text you control, and the rendered script is proof the
      parser works
- [ ] Screenplay CSS: monospace, character cues centred, dialogue
      indented, scene headings caps
- [ ] Virtualize with TanStack Virtual — a 118-page script is thousands
      of nodes
- [ ] `scrollToPage(n)` and `scrollToElement(id)`

**Done when:** a full script scrolls smoothly and looks like a
screenplay.

## D3 · Findings pane **[B]**

- [ ] Group by canonical element, expandable to mentions
- [ ] Split the group when mentions rate differently — that split is
      the interesting part
- [ ] Filters: risk, category, review status, scene range
- [ ] Sort: risk desc then scene, with a script-order toggle
- [ ] **Failed research pinned above RED** as "needs manual review"

**Done when:** eighty-odd findings are navigable without scrolling
fatigue, and failures are impossible to miss.

## D4 · Bidirectional linking **[B]**

- [ ] Click a finding → script scrolls to the page and flashes the
      `char_start`/`char_end` span
- [ ] Click a highlighted span → the finding opens
- [ ] Highlight colour = risk colour

**Done when:** both directions work and the flash is visible without
being annoying.

## D5 · Live run **[B]**

- [ ] `EventSource` on `/runs/{id}/stream`
- [ ] **Never a full-screen spinner.** Show the parsed script
      immediately; findings drop in as events arrive
- [ ] Live query strip: the current `research.query`, plus
      "31 / 84 researched"
- [ ] Reconnect with backoff; fall back to polling `GET /runs/{id}`

**Done when:** starting a run shows the script instantly and findings
populate progressively.

## D6 · Finding detail **[B]**

- [ ] Rationale, `rights_required`, rights holders
- [ ] Sources with excerpts, linked out
- [ ] `queries_run` — the actual searches the agent made
- [ ] `alternatives`
- [ ] Confidence as **confirmed / verify / uncertain**, never a decimal

**Done when:** a judge can trace any rating back to its evidence in two
clicks.

## D7 · Accept and override **[B]**

- [ ] `PATCH /api/findings/{id}` with optimistic update
- [ ] Override risk + free-text note
- [ ] "31 of 84 reviewed" counter

**Done when:** overrides persist across reload and the counter is
correct.

## D8 · Summary header and demo landing **[B]** ← small, decisive

- [ ] Always-visible risk counts and review progress
- [ ] Impact line: this run took N minutes; manual equivalent is
      5–10 business days. Stated flatly, no banner
- [ ] **A judge landing on the hosted URL sees a completed demo run**,
      not an empty dropzone. "Upload your own" is secondary
- [ ] Instant replay of the demo run from cache

**Done when:** someone with no screenplay can use the product in ten
seconds.

---

# BLOCK E — Delivery · Aug 30 – Sep 6

## E1 · Report export **[B]**

- [ ] `GET /api/runs/{id}/report?format=pdf`
- [ ] Shaped like a real clearance report: cover page with counts,
      findings grouped by category, each with scene, page, rights
      required, holders, sources
- [ ] "Not a legal determination — for review by qualified counsel"

## E2 · Deploy **[B]**

- [ ] Multi-stage production Dockerfiles (`npm run build` + `npm start`)
- [ ] Cloud Run for `api` and `web`; Cloud SQL or a managed Postgres
- [ ] Secrets via Secret Manager, not console env vars
- [ ] GCS for uploads with **signed URLs only** — never a public bucket
- [ ] CORS locked to your web origin

**Done when:** a full run completes from a phone on cellular data.

## E3 · Demo prep **[both]**

- [ ] Choose the demo script — needs visible clearance texture
- [ ] Pre-run it; warm the research cache so replay is instant
- [ ] Seed the landing state
- [ ] Rehearse the run three times on the deployed URL

## E4 · Submission **[both]**

- [ ] Video script written **before** recording. 0:00–0:25 problem ·
      0:25–2:15 one continuous run · 2:15–2:45 architecture ·
      2:45–3:00 impact
- [ ] Record at least five takes
- [ ] YouTube, public, English audio or subtitles, under 3:00
- [ ] README: architecture, setup, honest limitations
- [ ] Verify at runtime in the repo: `google-adk` /
      `google-cloud-aiplatform` **and** `parallel-web`, imported and
      called
- [ ] LICENSE badge renders in the About sidebar
- [ ] `.env` absent from the entire git history
- [ ] **Submit Sep 5 or 6.** Deadline is 2:00 PM PT on the 7th

---

# Critical path

```
A2 → B4 → B5 → C1 → C5 → C6 → C7
```

Everything else can slip a day harmlessly. If a critical-path task
slips two days, **cut a D-block feature rather than compressing C6.**

# Gates

| Date | Must be true |
|---|---|
| Aug 11 | Probes return real data; API contract agreed in writing |
| Aug 15 | One element end to end: upload → finding with a real source |
| Aug 22 | A full feature-length script processes unattended |
| Aug 29 | A stranger uses it without narration |
| Sep 3 | Hosted URL completes a run from a phone |

**Aug 29 is the real deadline.** Everything after is deploy, record,
submit.
