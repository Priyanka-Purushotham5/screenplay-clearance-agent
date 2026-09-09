# Script to Clearance

**An agent that finds every rights issue in a screenplay, and shows its sources.**

Upload a PDF screenplay. Get back every song, brand, artwork, location and real
person in it — each rated **RED / AMBER / GREEN**, with the rights holders named
and the sources the rating was decided from.

Built for the [Agentic Cinema hackathon](https://agentic-cinema.devpost.com/),
**Parallel track**.

| | |
|---|---|
| **Live app** | https://screenplay-clearance-web.onrender.com |
| **API** | https://screenplay-clearance-api.onrender.com ([OpenAPI](https://screenplay-clearance-api.onrender.com/openapi.json)) |
| **License** | MIT |

---

## The problem

Script clearance is the pass a production makes over a screenplay to find
everything that needs a licence, a release, or a rewrite before it can be shot.
A lyric quoted in dialogue, a brand on a t-shirt, a painting on a wall, a real
person named in a scene — each one is a cost, and each one is cheaper to find at
script stage than on set.

Done by hand it is a line-by-line read of 100+ pages, and the expensive part is
not spotting the mentions. It is the research behind each one: *who owns this,
what does it cost, is it even a problem?*

Two things make it hard to automate, and they are what this project is actually
about:

1. **The same name is not the same thing twice.** "Take On Me" playing off a
   turntable is a sync + master licence. A character asking *"you know that
   song?"* is a title, and titles are not copyrightable. Same string, two
   ratings — context decides, not keyword matching.
2. **A rating with no source is worthless.** Nobody takes "RED, trust me" to an
   E&O carrier. Every finding here carries the searches that produced it and the
   excerpts they returned.

---

## How it works

```
extract  →  group  →  research (fan-out)  →  assess  →  compose
```

| Stage | What it does | Runs on |
|---|---|---|
| **extract** | Reads the parsed screenplay and pulls every clearance-relevant mention with its scene and character offsets | ADK `LlmAgent` on Gemini Flash |
| **group** | Canonicalises and dedupes mentions into entities — pure Python, no model | — |
| **research** | One dossier per entity: who owns it, what rights apply. Fans out under a semaphore and a shared rate limit | ADK `LlmAgent` + the Parallel search tool |
| **assess** | Rates each *mention* against its dossier and a written rubric. Splits a group when two mentions of the same entity rate differently | ADK `LlmAgent` on Gemini Pro |
| **compose** | Writes findings, sources, and honest run stats to Postgres | — |

Deliberately **not** an ADK `SequentialAgent`: grouping is pure Python and the
research and assess stages are loops that call ADK inside. The orchestration
exists to enforce a concurrency cap and a shared rate limit, which wrapping the
stages as framework agents would give away. See
[`api/app/agents/workflow.py`](api/app/agents/workflow.py) for the reasoning.

**Nothing raises.** Every stage is caught, recorded in `warnings`, and the run
continues with what it has. An entity whose research failed still gets rated —
against a dossier marked `failed`, which the rubric tells the model to treat
conservatively and *say so*. Failed research is pinned above RED in the UI as
"needs manual review", because a silent gap is worse than a loud one.

---

## Google Cloud and Parallel, in code

Both are imported and called at runtime, not just named here.

**Google — Agent Development Kit + Gemini**

Every model call in the project goes through an ADK `LlmAgent` driven by an
`InMemoryRunner`:

- [`api/app/agents/extract.py`](api/app/agents/extract.py) — `LlmAgent` on `gemini-2.5-flash`, no tools
- [`api/app/agents/research.py`](api/app/agents/research.py) — `LlmAgent` with the Parallel tool attached
- [`api/app/agents/assess.py`](api/app/agents/assess.py) — `LlmAgent` on `gemini-2.5-pro` for rating

Flash for extraction (high volume, structural). Pro for assessment (low volume,
judgement-heavy). Models are pinned exactly — an A2 probe found `gemini-2.0-flash`
silently resolves to `gemini-2.5-flash`, which would make runs incomparable.

**Parallel — the only route to the open web**

[`api/app/agents/tools.py`](api/app/agents/tools.py) wraps `parallel.Parallel(...).search(...)`
as an ADK tool. It is the *only* way any agent here reaches the internet.

The tool does real work beyond the API call: it strips markdown furniture from
returned page content (~19% of bytes outright), caps snippets, and batches two
to four queries into a single call — the API bills one search unit per call, so
batching is both cheaper and faster. **It never raises**; a failed search returns
a structured error the agent can reason about, so one bad lookup cannot take
down a twelve-entity fan-out.

---

## Run it locally

**Prerequisites:** Docker, a [Gemini API key](https://aistudio.google.com/apikey),
and a [Parallel API key](https://parallel.ai).

```bash
git clone https://github.com/Priyanka-Purushotham5/screenplay-clearance-agent.git
cd screenplay-clearance-agent
cp .env.example .env
```

Put your keys in `.env`:

```
GEMINI_API_KEY=...
PARALLEL_API_KEY=...
GOOGLE_GENAI_USE_VERTEXAI=0
DATABASE_URL=postgresql+asyncpg://clearance:clearance@localhost:5432/clearance
```

Then:

```bash
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8080 (docs at `/docs`)

`.env` is gitignored and must stay that way.

### Vertex AI instead of an API key

Set `GOOGLE_GENAI_USE_VERTEXAI=true` and `GOOGLE_CLOUD_PROJECT`, then run
`gcloud auth application-default login` on the host. Compose mounts your ADC
read-only — no service-account key file, nothing secret to leak. On Windows ADC
lives in `%APPDATA%\gcloud`, so set `GCLOUD_CONFIG_DIR` explicitly.

### Rate limits

The limiter defaults are conservative, sized for a free API key:

| Var | Default |
|---|---|
| `GEMINI_RPM` | 10 |
| `GEMINI_DAILY` | 20 |
| `PARALLEL_RPM` | 30 |
| `PARALLEL_DAILY` | 500 |

A full run over a feature-length script will exhaust a 20-call Gemini budget and
degrade gracefully into conservatively-rated findings. Raise `GEMINI_DAILY` if
your key is billed.

---

## Verifying it

Each build block has a verification script that checks its done-when criterion
against real infrastructure rather than mocks:

```bash
docker compose exec api python api/scripts/verify_c8.py   # end-to-end run over HTTP
docker compose exec api python api/scripts/verify_c4.py   # the Parallel tool
docker compose exec api python api/scripts/verify_c6.py   # rubric vs. ground truth
```

[`docs/ground-truth.md`](docs/ground-truth.md) is a hand-written answer key for
`docs/test_screenplay.pdf` — every clearance-relevant item with the rating it
should receive and why. `verify_b7.py` checks the key against the parsed
screenplay and against its machine-readable twin, so neither can drift.

---

## Limitations

Stated plainly, because a clearance tool that oversells itself is worse than none.

- **Not legal advice.** It tells you what to clear and who to ask. Real clearance
  is done by counsel with a script-clearance report and an E&O carrier. The UI
  says so on every screen.
- **Needs a text layer.** A scanned PDF with no extractable text is rejected with
  a clear `NO_TEXT_LAYER` error rather than a bad parse. No OCR.
- **Research is only as good as the open web.** Obscure rights holders and
  unregistered works come back thin. Those surface as low-confidence findings
  pinned for manual review, not as confident guesses.
- **Confidence is reported as confirmed / verify / uncertain**, never as a
  decimal. A number implies a precision the underlying evidence does not have.
- **The hosted demo runs on a free tier** — services sleep after inactivity, so
  the first request may take ~50s to wake, and uploaded PDFs do not survive a
  restart (parsed content lives in Postgres and does).

---

## License

MIT — see [LICENSE](LICENSE).

Built by Priyanka Purushotham and Rohit B V.
