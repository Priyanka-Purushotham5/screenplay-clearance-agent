# API Notes — A2 Probe Findings

**Fill this in after running the three probe scripts.**
This document is the Aug 11 gate deliverable: "Probes return real data; API contract agreed in writing."
It becomes the reference for `api/app/agents/schemas.py` (C1) and `api/app/agents/tools.py` (C4).

---

## 1. Parallel Search API (`probe_parallel.py`)

### 1.1 SDK details (confirmed)

| Item | Value |
|---|---|
| Package | `parallel-web>=1.0.1` |
| Import | `from parallel import Parallel` |
| Auth env var | `PARALLEL_API_KEY` |
| Search method | `client.search(objective, search_queries, mode)` |
| Mode used | `basic` (~1 s, $5/1k requests) |

### 1.2 Response shape

| Field | Type | Notes |
|---|---|---|
| `search_id` | str | e.g. `search_ac6e9b75...` — unique per call |
| `session_id` | str | Always returned, even when not sent — server auto-generates one |
| `results` | list[WebSearchResult] | 10 results by default, ordered by decreasing relevance |
| `warnings` | None | Was `null` on all three queries — no non-blocking notices triggered |
| `usage` | list[UsageItem] | Always present; one entry: `UsageItem(count=1, name='sku_search')` — counts one Search SKU per call regardless of result count |

Per result (`WebSearchResult`):

| Field | Type | Observed behaviour |
|---|---|---|
| `url` | str | Always present |
| `title` | str \| None | **Present on most results**; `null` on Spotify pages and some Discogs entries (sites with JS-heavy or thin meta titles) |
| `publish_date` | str \| None | YYYY-MM-DD; **frequently None** (~50% of results across all three queries). Present when indexed from editorial/news pages; absent on e-commerce, Spotify, Discogs, Wikidata |
| `excerpts` | list[str] | Always exactly **one excerpt per result** in all three observed calls. Excerpt is long, markdown-formatted (headers, tables, bold, links). Length varies widely: ~150 chars (Spotify) to ~4,000+ chars (Discogs, Wikipedia) |

### 1.3 Observed result counts

| Query shape | Results returned | Notes |
|---|---|---|
| Easy ("Take On Me…") | 10 | Strong results; Discogs, Spotify, FT, Wikipedia, Quora, WaPo — rights-relevant |
| Obscure (Gordon Matta-Clark) | 10 | High quality; CCA archive, Guggenheim, Met, SFMOMA, Wikidata — all directly on-topic |
| Ambiguous ("Alien" brand) | 10 | Disambiguated toward the film franchise correctly; Justia trademark, Wikipedia, CLRN — useful |

### 1.4 Quality observations

**Easy query:**
> Results are immediately rights-relevant. Top results include a Discogs vinyl listing with the full label/publisher breakdown (Published By: ATV Music Ltd; ℗ WEA International Inc.), a Spotify page confirming "℗ 2004 Rhino Entertainment Company / WEA International Inc.", and a Washington Post article quoting the exact publishing split (Morten 16.6%, Paul + Magne 83.4%). Ranking is excellent. One result (EasySong) matched "A-Ha" as a different song by Ricky Gardiner — **the API does not guarantee all results are about the exact entity queried**; downstream assessment must filter.

**Obscure query:**
> Quality does **not** degrade significantly. CCA (the authoritative archive holding Matta-Clark's estate collection), Guggenheim, the Met, SFMOMA all returned with clear copyright notices: `© 2023 Estate of Gordon Matta-Clark / Artists Rights Society (ARS), New York`. This is a well-institutionalised artist — the API found the estate rights holder in results 3 and 4. For a truly obscure figure with no museum presence, quality would likely be lower.

**Ambiguous query:**
> The API correctly disambiguated toward the *Alien* film franchise despite "Alien" having many unrelated meanings (immigration, biology, general brand names). Results covered the trademark owner (Twentieth Century Fox Film Corporation, now under Disney via the Fox acquisition), franchise history, and active trademark registrations. No confusion with unrelated "Alien" brands. The objective text drove disambiguation effectively.

### 1.5 Implications for C4 (`api/app/agents/tools.py`)

- Parallel returns `excerpts: list[str]` — in practice always a **single-item list** (one long excerpt). The C4 wrapper should use `result.excerpts[0]` as `snippet`, with a guard for the empty-list case.
- `title` is None on ~50% of results (Spotify, Discogs, Wikidata, etc.). The C4 wrapper must handle `None` — fall back to the URL domain (`urllib.parse.urlparse(url).netloc`).
- `publish_date` is None on ~50% of results — treat as optional context only; do not require it for research decisions.
- `session_id` is **always returned by the server**, even if you didn't send one. Reuse the server-generated session_id for subsequent Extract calls within the same research task.
- `usage` is a list of `UsageItem` objects — use `str(item)` for logging; they are not plain dicts.
- `warnings` was `null` on all three test queries — appears to be rare in normal usage.
- Use `mode="basic"` as the default. The objective text is the primary disambiguation signal — write it carefully.

---

## 2. Gemini Structured Output (`probe_gemini.py`)

### 2.1 SDK details (confirmed)

| Item | Value |
|---|---|
| Package | `google-genai` (2.x) |
| Model | **`gemini-2.5-flash`** (reported by `response.usage_metadata`; SDK resolved `gemini-2.0-flash` alias to this) |
| Structured output params | `response_mime_type="application/json"` + `response_schema=<PydanticModel>` |
| Validation | `Model.model_validate_json(response.text)` |

### 2.2 Schema enforcement

- [x] **Both prompts returned valid JSON** — `model_validate_json` succeeded without exceptions on both
- [x] **`confidence` Literal stayed within `["high","medium","low"]`** — both responses used `"high"`; the Literal constraint was respected
- [x] **`notes` was correctly `null` when omitted** — prompt 2 said "do not include notes if nothing to add"; the model omitted the key in the raw JSON; Pydantic defaulted it to `null` in the validated output (not `""`, not an error)
- [x] **`sources` was always a non-empty list** — both responses included exactly one `Source` object with `url` and `excerpt`
- [x] **No commentary outside the JSON** — the raw `response.text` in both cases was a bare JSON object starting with `{`. The prompt that explicitly asked for a "caveat note" before answering was handled inside the schema (`notes` field) rather than prepended as free text. **Enforcement is real, not just requested.**

### 2.3 Optional field behaviour

Two distinct behaviours observed depending on whether `notes` was populated:

- **Prompt 1 (Standard):** The model populated `notes` with the caveat text it was asked to provide: `"My knowledge cutoff is early 2023. As of the 2016 legal settlement, 'Happy Birthday to You' is in the public domain."` — it correctly routed the requested caveat *into* the schema field rather than outside JSON.
- **Prompt 2 (Stress):** `notes` was omitted entirely from the raw JSON response. Pydantic's `Optional[str] = None` default resolved it to `null` in the validated model dump. The raw response contained no `"notes"` key at all — confirmed safe.

**Conclusion:** when `Optional[str] = None` is present, the model omits the key when it has nothing to say. Pydantic fills it with `null`. No empty-string false positives.

### 2.4 Token usage

| Prompt | Input tokens | Output tokens | Thinking tokens | Total tokens |
|---|---|---|---|---|
| Standard ("Happy Birthday") | 39 | 194 | 641 | 874 |
| Stress ("Wavelength" film) | 50 | 113 | 1,076 | 1,239 |

**Key observations:**
- The model reports **`thoughts_token_count`** — this is the internal chain-of-thought reasoning (`gemini-2.5-flash` uses built-in thinking). These tokens are **billed** even though they are not visible in `response.text`.
- Thinking tokens were **3–10× the output tokens** in both cases. For high-volume runs (C2 runs 80+ elements), thinking token cost dominates. Budget accordingly.
- Output tokens were modest (113–194) for simple single-entity queries. C1 extraction batches over a scene with many elements will be significantly larger.
- `prompt_tokens_details` confirms all input was `TEXT` modality — no multimodal surcharges.

### 2.5 Implications for C1 (`api/app/agents/extract.py`) and C6 (`api/app/agents/assess.py`)

- **Schema enforcement is reliable — no retry loop needed for schema compliance.** Both responses parsed cleanly on the first call. The model routes requested commentary into schema fields rather than escaping the JSON envelope.
- **`Optional` fields are safe:** omitted key in raw JSON → `null` after Pydantic validation. Use `Optional[str] = None` freely; guard downstream code for `None`, not `""`.
- **Thinking tokens are real cost.** At ~10 thinking tokens per output token for the stress prompt, a 100-element run at 200 output tokens/element = ~200k thinking tokens. Factor this into the rate-limiter budget in C7.
- **Model alias resolution:** requesting `gemini-2.0-flash` resolved to `gemini-2.5-flash` at runtime. Pin the exact model string if reproducibility across runs matters for C6's rubric versioning.
- **Nested list (`sources: list[Source]`) serialised correctly** — no special handling needed. Pydantic's `model_validate_json` round-trips it cleanly.
- C6 uses Pro (not Flash) for assessment — run a separate probe against `gemini-2.5-pro` when available to confirm thinking token ratios and schema behaviour are consistent.

---

## 3. Gemini PDF Ingestion (`probe_gemini_pdf.py`)

### 3.1 SDK details (confirmed)

| Item | Value |
|---|---|
| Delivery method | `types.Part.from_bytes(data=bytes, mime_type="application/pdf")` |
| Inline size limit | ~20 MB (larger files need `client.files.upload()`) |
| Model | `gemini-2.5-flash` (alias `gemini-2.0-flash` resolves to this) |

### 3.2 Extraction quality

- **File tested:** `docs/test_screenplay.pdf` — 3 pages, 4.8 KB
- **Token breakdown:** 58 text tokens (prompt) + 774 document tokens (PDF) = 832 input tokens; 92 output tokens; 61 thinking tokens; **985 total**
- **Scene headings in PDF:** 5 real scene headings (`INT. RECORD LABEL OFFICE - DAY`, `INT. RECORD LABEL OFFICE - CONTINUOUS`, `INT./EXT. DIANA'S CAR…`, `INT. LAW FIRM…`, `I/E. PARKING GARAGE…`)
- **Extracted by model:** 6 items — the 5 real headings **plus `ANGLE ON -- THE TURNTABLE`** (a mini-slug that is NOT a scene heading)
- **Did the response parse as valid JSON?** ❌ **No — JSON parse failed.** The model wrapped its output in ` ```json ``` ` markdown fences despite the prompt saying "nothing else, no commentary". `json.loads()` choked on the backtick fence. **The fence must be stripped before parsing.**
- **Did Gemini hallucinate headings not in the PDF?** Partially — `ANGLE ON -- THE TURNTABLE` exists in the PDF as a mini-slug (all-caps, bold), which Gemini misclassified as a scene heading. No fully invented headings.

### 3.3 Size behaviour

| File size | Delivery method | Document tokens | Outcome |
|---|---|---|---|
| 4.8 KB (3 pages) | Inline (`Part.from_bytes`) | 774 | ✅ Success — model read all content |

> File was well within the ~20 MB inline limit. No `client.files.upload()` needed at this size.
> Document tokens (774) were ~13× higher than text tokens (58) for 3 pages — expect ~250 document tokens/page as a rough budget estimate for full-length scripts.

### 3.4 Critical findings and implications for B2 (`api/app/parser/pdf.py`)

**Finding 1 — Markdown fence wrapping (affects ALL Gemini PDF calls without `response_schema`)**

When calling `generate_content` for a PDF without a `response_schema`, the model wraps JSON in ` ```json ``` ` fences even when told not to. Two fixes:

- **Option A (preferred for B2 fallback):** Add a fence-stripping step before `json.loads()`:
  ```python
  import re
  text = re.sub(r"^```[a-z]*\n?|\n?```$", "", response.text.strip())
  headings = json.loads(text)
  ```
- **Option B:** Pass `response_mime_type="application/json"` and a `response_schema` (as in `probe_gemini.py`) — this **enforces** bare JSON with no fences. For structured extraction this is the right approach.

**Finding 2 — Mini-slug misclassification (affects scene-heading extraction)**

`ANGLE ON -- THE TURNTABLE` was classified as a scene heading because it is all-caps and bold in the rendered PDF, visually identical to a scene heading to the model. Gemini cannot distinguish typographic role from visual appearance without INT/EXT prefix context.

- The B2 Gemini fallback **must post-filter** extracted headings through the INT/EXT/I/E prefix check — same rule the text-based parser uses.
- Do **not** rely on Gemini alone for scene segmentation in the fallback path; use it only to recover raw text, then apply the same classifier as B4.

**Finding 3 — Document token cost**

At ~250 document tokens/page, a 120-page script = ~30,000 document tokens per Gemini PDF call. At `gemini-2.5-flash` pricing this is non-trivial. Reserve the PDF fallback for individual failed pages, not whole-script ingestion.

**Primary path:** `pdfplumber` — deterministic, no API cost, works offline.
**Fallback path:** Gemini PDF — viable for recovering text from problem pages, but requires fence-stripping and INT/EXT post-filtering. Not a drop-in replacement for pdfplumber.

---

## 4. API Contract Agreement (Aug 11 gate)

The shapes below are what C1, C4, and C5 are built against. Do not change these without
updating the downstream agents.

### 4.1 Parallel Search normalised result (for C4)

```python
# After normalisation in api/app/agents/tools.py
{
    "title": str | None,   # result.title — None on ~50% of results; fall back to urlparse(url).netloc
    "url": str,            # result.url — always present
    "snippet": str,        # result.excerpts[0] if result.excerpts else ""  (always 1 item in practice)
}
```

### 4.2 Gemini structured output pattern (for C1, C6)

```python
response = client.models.generate_content(
    model="gemini-2.0-flash",        # resolves to gemini-2.5-flash at runtime
    contents=prompt_text,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=YourPydanticModel,
    ),
)
validated = YourPydanticModel.model_validate_json(response.text)
# Notes:
#   - response.text is a bare JSON object ONLY when response_schema is set
#   - WITHOUT response_schema, model wraps JSON in ```json fences — strip them first
#   - Optional fields omitted by the model default to None via Pydantic, not ""
#   - response.usage_metadata.thoughts_token_count is billed — include in rate-limiter budget
```

### 4.3 Gemini PDF inline delivery pattern (for B2 fallback)

```python
import re

pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=[pdf_part, prompt_text],
)
# Always strip markdown fences — model wraps output in ```json``` even when told not to:
raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", response.text.strip())
result = json.loads(raw)
# Then post-filter: keep only lines starting with INT. / EXT. / I/E. / INT./EXT.
HEADING_RE = re.compile(r"^(INT\.|EXT\.|I/E\.|INT\./EXT\.)", re.IGNORECASE)
scene_headings = [h for h in result if HEADING_RE.match(h)]
```

---

*Last updated: 2026-08-10 (A2 probe run — Parallel + Gemini structured output + Gemini PDF)*
