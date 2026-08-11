# Parallel Web Systems — Consolidated Reference

Source: [Agentic Cinema: The Blockbuster Hackathon — Parallel Resources](https://agentic-cinema.devpost.com/details/parallel-resources)
Compiled by reading that page plus every Parallel/Google sublink it lists, and the supporting docs pages those link to.
Compiled: 2026-08-10.

---

## 1. Hackathon context and the hard requirement

**Hackathon:** Agentic Cinema: The Blockbuster Hackathon ("Lights. Camera. Code.")
**Submission deadline:** September 7, 2026 @ 2:00pm PDT
**Participants at time of reading:** 5,242

**About Parallel (as described on the sponsor page):** Parallel builds web infrastructure for AI agents — a full stack spanning proprietary crawling and indexing, search, extraction, reasoning, and monitoring, purpose-built for AI systems rather than retrofitted from consumer search.

### ⚠️ Eligibility requirement — read this first

> Projects must **actively integrate Parallel's Search API at runtime**. Merely mentioning or referencing Parallel in your documentation/README is **not sufficient**.

Accepted integration paths:

| Path | What counts |
|---|---|
| Official SDK | `parallel-web` (Python or TypeScript) calling `/v1/search` |
| Supported integrations | Vercel AI SDK, LangChain (`langchain-parallel`) |
| Grounding configurations | Gemini `parallel_ai_search` tool / Google Cloud grounding provider |

Practical implication: there must be a live HTTP call to Parallel's Search API in the running application's code path — not a cached JSON dump, not a screenshot.

### Links listed on the sponsor resources page

| Resource | URL |
|---|---|
| Grounding with Parallel Search (Google Cloud) | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-parallel |
| Gemini Enterprise integration guide | https://docs.parallel.ai/integrations/google-gemini-enterprise |
| Search API quickstart | https://docs.parallel.ai/search/search-quickstart |
| Search & Extract MCP Server | https://docs.parallel.ai/integrations/mcp/search-mcp |
| Parallel CLI | https://docs.parallel.ai/integrations/cli |
| Extract API | https://docs.parallel.ai/extract/extract-quickstart |
| Task API | https://docs.parallel.ai/task-api/task-quickstart |
| Monitor API | https://docs.parallel.ai/monitor-api/monitor-quickstart |
| Parallel Playground | https://platform.parallel.ai/login?redirectTo=%2F |
| Parallel homepage | http://parallel.ai |

Other hackathon pages: [Rules](https://agentic-cinema.devpost.com/rules) · [Resources](https://agentic-cinema.devpost.com/resources) · [Updates](https://agentic-cinema.devpost.com/updates) · [Discussions](https://agentic-cinema.devpost.com/forum_topics) · [Project gallery](https://agentic-cinema.devpost.com/project-gallery)

---

## 2. Company positioning and benchmarks (parallel.ai)

- Product suite: **Search, Extract, Responses, Task, FindAll, Monitor** APIs over a proprietary web index of billions of pages, refreshed daily.
- Positioning: built for agentic workflows first; targets high-stakes verticals (law, finance, healthcare) where precision matters.
- **Basis** framework: every answer carries source citations, confidence scores, and reasoning traces.
- Compliance: SOC 2 Type II, HIPAA-ready, GDPR.
- Benchmarks claimed on the site:
  - **SimpleQA:** Parallel Turbo 91% accuracy at $8 CPM, vs. competitors 72–89% at $6–23 CPM.
  - **BrowseComp** (harder multi-hop browsing): Parallel 51% vs. competitors 19–39%.
- Entry pricing from $1 per 1,000 requests; new accounts get signup credit plus a recurring $5/month free allowance (free tier up to ~5,000 requests/month).

---

## 3. Product map — which API to use when

| API | One-line purpose | Reach for it when |
|---|---|---|
| **Search** | One round trip: natural-language objective + keyword queries → ranked URLs with LLM-optimized excerpts | The model needs current facts or specific entities to ground an answer |
| **Extract** | URL → clean markdown (handles JS-heavy pages and PDFs) | You already know the page, or Search narrowed the candidates |
| **Task** | Multi-hop research agent; runs seconds to hours, webhooks on long tiers | Deep research synthesized across sources with cited, structured output |
| **FindAll** | Natural-language criteria → verified list of matching entities | Building a list from scratch with per-match condition verification |
| **Entity Search** | One round trip: NL people/company query → matching results | Latency-sensitive people/company discovery |
| **Monitor** | Scheduled NL query + webhook on change | Continuous watchlists (news, regulatory, competitive, pricing) |
| **Chat / Responses** | OpenAI-compatible chat + responses surfaces backed by live web | Drop-in replacement for an OpenAI-style client that needs grounding |

**SDKs**

```bash
pip install "parallel-web>=1.0.1"
```

```bash
npm install "parallel-web@^1.0.1"
```

TypeScript import is a default export: `import Parallel from "parallel-web"`.

**Auth:** API key from https://platform.parallel.ai. Direct HTTP uses the `x-api-key` header; SDKs read `PARALLEL_API_KEY` from the environment.

**Machine-readable docs:** `https://docs.parallel.ai/llms.txt` (index), `https://docs.parallel.ai/llms-full.txt` (full text), `https://docs.parallel.ai/public-openapi.json` (OpenAPI spec).

---

## 4. Search API (the required integration)

### 4.1 Endpoint

`POST /v1/search`

Headers: `Content-Type: application/json`, `x-api-key: <YOUR_KEY>`

### 4.2 Request body — `V1SearchRequest`

| Field | Type | Required | Notes |
|---|---|---|---|
| `search_queries` | `string[]` | **yes** | Concise keyword queries, 3–6 words each. At least one required; max 5. Each ≤ 200 chars. |
| `objective` | `string \| null` | no | Natural-language description of the underlying question or goal. Up to 5,000 chars. |
| `mode` | `"turbo" \| "basic" \| "advanced"` | no | Defaults to `advanced`. |
| `max_chars_total` | `int \| null` | no | Upper bound on total characters across all excerpts. |
| `session_id` | `string` (≤1000) `\| null` | no | Groups related Search/Extract calls into one logical task. |
| `client_model` | `string \| null` | no | Which model generated the request (e.g. `claude-opus-4-7`). |
| `advanced_settings` | object `\| null` | no | See below. |

### 4.3 `advanced_settings`

| Field | Type | Default | Notes |
|---|---|---|---|
| `source_policy` | object | none | `include_domains` / `exclude_domains` / `after_date` |
| `fetch_policy` | object | indexed content | `max_age_seconds` — cached (faster) vs. live (fresher) |
| `excerpt_settings` | object | system default | `max_chars_per_result` |
| `location` | string | none | ISO 3166-1 alpha-2 (`us`, `gb`, `de`, `jp`). Invalid codes ignored with a warning. |
| `max_results` | int | 10 | Must be > 0; public modes cap at 20 |

Docs are explicit that most callers should **not** set these — defaults are tuned for best results, and `source_policy` / `location` / `max_results` restrict the candidate pool and can degrade quality. Apply only when there's a real product need.

### 4.4 Response — `V1SearchResponse`

| Field | Type | Notes |
|---|---|---|
| `search_id` | string | e.g. `search_cad0a6d2dec046bd95ae900527d880e7` |
| `results` | `V1WebSearchResult[]` | Ordered by decreasing relevance |
| `warnings` | `Warning[] \| null` | Non-blocking input validation notices |
| `usage` | `UsageItem[] \| null` | SKU counts for billing |
| `session_id` | string | Echoed back if provided |

`V1WebSearchResult`: `url` (string), `title` (string\|null), `publish_date` (string\|null, `YYYY-MM-DD`), `excerpts` (`string[]`, markdown-formatted).

Example response:

```json
{
  "search_id": "search_fcb2b4f3c75e418687bccaa1a8381331",
  "results": [
    {
      "url": "https://www.example.com",
      "title": "Sample webpage title",
      "publish_date": "2024-01-15",
      "excerpts": ["Sample excerpt 1", "Sample excerpt 2"]
    }
  ],
  "session_id": "session_fcb2b4f3c75e418687bccaa1a8381331"
}
```

Validation error (422):

```json
{
  "type": "error",
  "error": {
    "ref_id": "search_fcb2b4f3c75e418687bccaa1a8381331",
    "message": "Request validation error"
  }
}
```

### 4.5 Modes

| Mode | Latency | Price | Use for |
|---|---|---|---|
| `turbo` | ~200 ms (p50) | $1 / 1k requests | Latency-sensitive, high-volume workloads; chat and web-search tools; "built to ground every call". **English and Japanese queries only.** |
| `basic` | ~1 s | $5 / 1k requests | Most agent applications. Works best with 2–3 good queries. Docs recommend starting here. |
| `advanced` | ~3 s | $5 / 1k requests | Multi-hop background agents that can absorb latency for depth. **Default if `mode` is omitted.** |

Switching modes only requires changing `mode`; every other parameter is identical. `basic`/`advanced` have broader language coverage than `turbo`.

### 4.6 Best practices (from the Search best-practices page)

**Objective**
- Natural language, up to 5,000 chars.
- Include source guidance, freshness guidance, and broader task context.

**Search queries**
- Concise keywords, **3–6 words each**; 2–3 queries is the sweet spot, 5 is the max.
- Make them *diverse* — vary entity names, synonyms, and angles.
- **Never** write sentences, instructions, or `site:` operators.

**Both together** outperform either alone.

**Excerpts**
- Results are ranked, LLM-optimized excerpts meant to go straight into a prompt — minimal post-processing needed.
- Bound total context with `max_chars_total`, per-result with `excerpt_settings.max_chars_per_result`.

**Sessions**
- Reuse one `session_id` across all Search and Extract calls belonging to the same task; mint a new one per task.

**Cost framing from the docs:** better retrieval routinely saves more in downstream inference tokens than the search call itself costs.

### 4.7 Source policy (shared by Search and Task)

| Field | Type | Applies to | Purpose |
|---|---|---|---|
| `include_domains` | `string[]` | Task, Search | Hard allowlist — *only* these domains |
| `exclude_domains` | `string[]` | Task, Search | Blocklist |
| `after_date` | `YYYY-MM-DD` | Search only | Content published on/after this date |

Constraints and behavior:
- Combined `include_domains` + `exclude_domains` ≤ **200** domains.
- Use allowlist *or* blocklist per query; if both are present the allowlist takes precedence.
- Apex domains cover subdomains automatically (`example.com` → `docs.example.com`).
- Leading `www.` is normalized away. Bare extensions (`.org`, `.co.uk`) match that TLD.
- No schemes, paths, ports, or literal wildcards (`*.org` unsupported).
- `include_domains` is a **hard allowlist, not a preference** — reserve it for compliance or single-publisher cases. Otherwise reshape the objective or use `exclude_domains`.

```json
{
  "source_policy": {
    "include_domains": ["linkedin.com"],
    "exclude_domains": ["reddit.com"],
    "after_date": "2026-01-01"
  }
}
```

---

## 5. Extract API

Turns public URLs into clean, LLM-ready markdown. Handles JavaScript-heavy sites and PDFs. Returns either objective-focused excerpts or complete page content.

**Response fields**

| Field | Type | Purpose |
|---|---|---|
| `url` | string | Source URL |
| `title` | string (optional) | Page title |
| `publish_date` | string (optional) | `YYYY-MM-DD` |
| `excerpts` | `string[]` | Markdown passages relevant to the objective |
| `full_content` | string (optional) | Complete markdown, when requested |

Example from the docs: extracting `https://www.un.org/en/about-us/history-of-the-un` with objective *"When was the United Nations established?"* returns just the passages answering that question.

**`advanced_settings`**

| Param | Type | Default | Notes |
|---|---|---|---|
| `fetch_policy` | object | cached | Indexed content (faster) vs. live fetch (fresher) |
| `excerpt_settings` | object | system default | `max_chars_per_result` |
| `full_content` | bool \| object | `false` | `true`, or an object with its own `max_chars_per_result` |

**`fetch_policy` sub-fields**

| Field | Type | Default | Notes |
|---|---|---|---|
| `max_age_seconds` | int | dynamic | Minimum **600** (10 min); older than this triggers a live fetch |
| `timeout_seconds` | number | dynamic | Typically 15–60 s; applies to live retrieval |
| `disable_cache_fallback` | bool | `false` | `true` errors on failed live fetch instead of falling back to the index |

```json
{
  "advanced_settings": {
    "excerpt_settings": { "max_chars_per_result": 5000 },
    "full_content": { "max_chars_per_result": 50000 }
  }
}
```

Output is markdown (links, headings, lists intact) — strip it yourself if you need plain text. Responses carry session tracking and usage metrics.

---

## 6. Task API

Combines AI inference with web search and live crawling to turn complex research into repeatable, programmable workflows. Outputs arrive with citations and confidence levels.

**Use cases:** data enrichment (CRM/contact augmentation), market and competitor research, due diligence / compliance / background verification, research-backed content generation.

**Workflow:** create a task run → await completion → retrieve results. (Long tiers should use webhooks rather than polling.)

**Output schema options**

| Type | Purpose |
|---|---|
| Text string | Simple lookups, single-field answers |
| JSON schema | Structured enrichment with typed fields |
| Text schema | Markdown reports with inline citations |
| Auto | Processor picks the structure |

**Supported input→output patterns:** question→answer, question→report, question→auto-structured, structured→structured.

### Processors

| Processor | Latency | Strengths | Approx. max output fields | Price / 1k runs |
|---|---|---|---|---|
| `lite` | 10 s – 60 s | Basic metadata, fallback, low latency | ~2 | $5 |
| `base` | 15 s – 100 s | Reliable standard enrichments | ~5 | $10 |
| `core` | 60 s – 5 min | Cross-referenced, moderately complex output | ~10 | $25 |
| `core2x` | 60 s – 10 min | High-complexity cross-referenced output | ~10 | $50 |
| `pro` | 2 – 10 min | Exploratory web research | ~20 | $100 |
| `ultra` | 5 – 25 min | Advanced multi-source deep research | ~20 | $300 |
| `ultra2x` | 5 – 50 min | Difficult deep research | ~25 | $600 |
| `ultra4x` | 5 – 90 min | Very difficult deep research | ~25 | $1,200 |
| `ultra8x` | 5 min – 2 hr | The most difficult deep research | ~25 | $2,400 |

**`-fast` variants** exist for every processor: 2–5× faster at **identical price**, trading some data freshness for speed. Examples: `lite-fast` 10–20 s, `core-fast` 15 s–100 s, `ultra-fast` 1–10 min.

Selection guidance: `lite`/`base` for simple tasks, `core` for reliable accuracy across several fields, `pro`/`ultra` when deep reasoning matters. Append `-fast` for latency-sensitive paths.

**Related capabilities:** webhooks, task groups, ingest API, SSE streaming events, MCP tool calling, Task MCP, interactions/interactive research, research basis (citations + reasoning access), source policy.

---

## 7. Monitor API

Continuous web tracking via scheduled queries with webhook notifications — removes manual polling and hand-rolled deduplication.

**Use cases:** finance (fund activity, M&A signals), people/companies (executive changes, hiring), sciences (clinical trials), legal/policy (regulatory changes), eCommerce (price moves), real estate (listing changes).

**Lifecycle**

1. **Create** — `POST /v1/monitors` with `type`, `frequency`, `processor`, `settings` (containing the query), `webhook` URL, optional `metadata`.
2. **Receive** — webhook fires with `monitor_id` and `event_group_id`.
3. **Retrieve** — `GET /v1/monitors/{monitor_id}/events` returns detected changes with citations, reasoning, and confidence levels.

Update frequency/webhook/metadata any time; cancel to stop future executions.

**Best practices**
- Write intent-heavy natural language, not keyword soup. Good: `Parallel Web Systems (parallel.ai) funding announcements`. Avoid keyword combinations and date-restricted phrasing.
- Frequency: hourly for fast-moving topics, daily for news, weekly for slow-changing subjects.
- Processor: `lite` (default) for routine queries; `base` for harder queries needing higher recall.
- Prefer webhooks over polling for lower latency.
- Cancel unused monitors — they cost money on every execution.
- For *historical/retrospective* questions use the Deep Research (Task) API instead; Monitor is forward-looking.

**Advanced config**
- **Source policy** — restrict/prioritize domains where authority matters.
- **Geo filtering** — scope by ISO 3166-1 alpha-2 country codes.

**Monitor types:** `event_stream` (search-query driven) and `snapshot` (task-output driven). Slack integration and follow-up tasks are supported.

---

## 8. Search & Extract MCP Server

Real-time web search and content extraction for MCP-speaking agents; a simplified surface over Search + Extract, tuned for agent reasoning loops.

**Endpoints**

| URL | Access |
|---|---|
| `https://search.parallel.ai/mcp` | Free, anonymous, lower rate limits |
| `https://search.parallel.ai/mcp-oauth` | Authenticated (Bearer token or OAuth) |

**Auth:** none required for basic use. For higher limits send `Authorization: Bearer <YOUR-KEY>` with a key from https://platform.parallel.ai.

**Tools**

| Tool | Purpose |
|---|---|
| `web_search` | General web search inside an agent reasoning loop; current information across many sources |
| `web_fetch` | Token-efficient markdown for a specific URL — after search narrows candidates, or when the URL is already known |

Both run in low-latency **basic** mode, with output capped near **25,000 characters per call** to respect MCP client limits.

**Configuration**

Cursor — `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "Parallel Search MCP": {
      "url": "https://search.parallel.ai/mcp"
    }
  }
}
```

VS Code — `.vscode/mcp.json`:

```json
{
  "servers": {
    "Parallel Search MCP": {
      "type": "http",
      "url": "https://search.parallel.ai/mcp"
    }
  }
}
```

Claude Desktop: Settings → Connectors → Add Custom Connector, URL `https://search.parallel.ai/mcp`.

Claude (non-admin), via `mcpServers`:

```json
{
  "command": "npx",
  "args": ["-y", "mcp-remote", "https://search.parallel.ai/mcp"]
}
```

Configs are also documented for Codex CLI, Windsurf, Gemini CLI, Zed, Warp and 25+ other clients.

**Notes**
- Put date and domain filters **in the query text** — the MCP tools don't expose them as separate parameters.
- Org admins can disable Claude's native web search so traffic routes through this MCP instead.

---

## 9. Parallel CLI

**Install** (`parallel-cli`, six paths):

```bash
pipx install "parallel-web-tools[cli]" && pipx ensurepath
```

```bash
uv tool install "parallel-web-tools[cli]"
```

```bash
brew install parallel-web/tap/parallel-cli
```

```bash
pip install parallel-web-tools
```
(optional extras: `[cli]`, `[duckdb]`, `[all]`)

```bash
npm install -g parallel-web-cli
```

```bash
curl -fsSL https://parallel.ai/install.sh | bash
```

**Auth**

```bash
parallel-cli login
```
```bash
parallel-cli login --device
```
(device flow for SSH / containers / CI)

Or set `PARALLEL_API_KEY`. Check state with `parallel-cli auth`.

**Commands**

| Command | Capabilities |
|---|---|
| `search` | Modes `turbo` / `basic` (default) / `advanced`; `--include-domains`, `--exclude-domains`, `--after-date YYYY-MM-DD`; result-count and excerpt controls |
| `extract` | `--objective` to narrow scope, `--full-content` for whole pages, repeatable `-q` for keyword prioritization |
| `research` | Processor tiers `lite`, `base`, `core`, `pro` (default), `ultra` plus `-fast` variants; async via `--no-wait` with `poll` / `status`; configurable timeout |
| `enrich` | Enrich CSV/JSON via web research; `suggest` subcommand lets AI propose columns; inline `--data`; YAML configs; processor tier selection |
| `findall` | Discover entities from a natural-language description; generators `base` / `core` (default) / `pro`; 5–1000 matches (default 10); entity exclusion via JSON array; `--no-wait` |
| `monitor` | Frequencies `1h` / `1d` / `1w`; types `event_stream` or `snapshot`; webhooks; `trigger` forces an off-schedule check |

**Output & integration:** `--json` for structured output, `-o/--output` to write a file, `-` to read stdin — designed to be driven by scripts and agents.

**Exit codes:** `0` success, `2` input error, `3` auth failure, `4` API error, `5` timeout.

**Updates:** `parallel-cli update` (binary), `pipx upgrade parallel-web-tools`, or your package manager's equivalent. Disable checks with `parallel-cli config auto-update-check off`.

---

## 10. Google Gemini Enterprise / Grounding with Parallel Search

Parallel Web Search acts as an **external grounding provider** for Google's Gemini Enterprise Agent Platform, so Gemini answers can be anchored in current web data instead of stale training data. The docs' example: asked who won the 2025 Las Vegas F1 Grand Prix, a grounded response names Max Verstappen with citations, while an ungrounded one claims the event hasn't happened.

In the Google Cloud console this sits under **Grounding**, alongside Grounding with Google Search, Google Maps, Agent Search, your own search API, RAG, Elasticsearch, Exa, and Web Grounding for Enterprise.

### Setup options

**Google Cloud Marketplace (recommended)** — subscribe via the Marketplace listing; auth happens automatically through your Google Cloud project, **no API key needed**. A separate Zero Data Retention offering exists for sensitive workloads.

**Bring your own key** — sign up at the Parallel Platform, generate a key, include it in requests. Billing goes through Parallel, not Google Cloud.

Both paths default to a **200 prompts/minute** quota.

### Supported models

Gemini 2.5 Flash · 2.5 Flash-Lite · 2.5 Pro · 3.1 Pro (preview) · 3.1 Flash-Lite · 3.5 Flash

### `customConfigs` fields (all optional)

| Field | Default | Range |
|---|---|---|
| `max_results` | 10 | 1–20 |
| `excerpts.max_chars_per_result` | 30,000 | 1,000–100,000 |
| `excerpts.max_chars_total` | 100,000 | 1,000–1,000,000 |
| `location` | — | ISO country code (e.g. `us`) |
| `mode` | `basic` | `basic` or `advanced` |
| `source_policy.include_domains` / `exclude_domains` | — | Domain names or extensions, max 200 combined |

### Python (google-genai)

```python
from google import genai
from google.genai import types

client = genai.Client()
response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="Who won the 2025 Las Vegas F1 Grand Prix?",
    config=types.GenerateContentConfig(
        tools=[
            types.Tool(
                parallel_ai_search=types.ToolParallelAiSearch(
                    custom_configs={
                        "mode": "basic",
                        "max_results": 10,
                        "source_policy": {"include_domains": ["wikipedia.org"]}
                    }
                )
            )
        ]
    )
)
```

### REST (Marketplace)

```json
{
  "contents": [{
    "role": "user",
    "parts": [{"text": "YOUR_PROMPT"}]
  }],
  "tools": [{
    "parallelAiSearch": {
      "enable_zero_data_retention": false,
      "customConfigs": {
        "mode": "basic",
        "max_results": 10
      }
    }
  }],
  "model": "projects/PROJECT_ID/locations/LOCATION/publishers/google/models/gemini-3.5-flash"
}
```

### Response structure

Grounded responses include `groundingMetadata`:

- `webSearchQueries` — the queries Gemini sent to Parallel
- `groundingChunks` — source URIs, titles, domains
- `groundingSupports` — maps answer segments to supporting sources
- `usageMetadata.toolUsePromptTokensDetails` — tokens consumed by grounding

**Gotchas**
- Gemini decides autonomously whether to search — `groundingMetadata` may be **absent** on ungrounded answers. Don't assume it's there.
- Byte offsets in `groundingSupports` need careful handling for non-ASCII text.
- Agent Studio offers a no-code way to experiment.
- Pricing = Gemini token charges **plus** Parallel Search API usage.

---

## 11. Framework integrations

### Vercel AI SDK

Three paths:

1. **Vercel AI Gateway (recommended)** — use `parallelSearch` as a built-in tool inside AI Gateway; works with any model provider. Wire it into your `streamText` / `generateText` call. See [Vercel AI Gateway web search docs](https://vercel.com/docs/ai-gateway/capabilities/web-search#using-parallel-search).
2. **NPM package** — `@parallel-web/ai-sdk-tools` exposes `searchTool` and `extractTool`, usable with any compatible provider (OpenAI, Anthropic, …). [npm](https://www.npmjs.com/package/@parallel-web/ai-sdk-tools)
3. **Vercel Marketplace** — install Parallel directly; API key is auto-provisioned and billing runs through your Vercel account.

Template/example: https://parallel-vercel-template-cookbook.vercel.app

### LangChain

```bash
pip install langchain-parallel
```
```bash
export PARALLEL_API_KEY="your-api-key-here"
```

**Chat model — `ChatParallelWeb`**

```python
from langchain_parallel.chat_models import ChatParallelWeb
from langchain_core.messages import HumanMessage, SystemMessage

chat = ChatParallelWeb(model="speed")

messages = [
    SystemMessage(content="You are a helpful assistant with access to real-time web information."),
    HumanMessage(content="What are the latest developments in artificial intelligence?")
]

response = chat.invoke(messages)
```

Parameters: `model` (default `"speed"`), `api_key` (falls back to `PARALLEL_API_KEY`), `base_url` (default `https://api.parallel.ai`), `timeout`, `max_retries`. **`temperature` and `max_tokens` are ignored by Parallel.**

Streaming and async both supported: `chat.stream(...)`, `await chat.ainvoke(...)`, `async for chunk in chat.astream(...)`.

**Search tool — `ParallelWebSearchTool`**

```python
from langchain_parallel import ParallelWebSearchTool

search_tool = ParallelWebSearchTool()

result = search_tool.invoke({
    "search_queries": ["renewable energy 2024", "solar power developments"],
    "objective": "What are the latest renewable energy developments?",
    "mode": "advanced"
})
```

Params: `search_queries` (required, 1–5, ≤200 chars each), `objective`, `max_results` (cap 20), `mode` (`turbo`/`basic`/`advanced`), `excerpts.max_chars_per_result`, `fetch_policy`.

**Extract tool — `ParallelExtractTool`**

```python
from langchain_parallel import ParallelExtractTool

extract_tool = ParallelExtractTool()

result = extract_tool.invoke({
    "urls": ["https://en.wikipedia.org/wiki/Artificial_intelligence"],
    "search_objective": "AI applications and ethical concerns",
    "excerpts": {"max_chars_per_result": 2000}
})
```

Params: `urls` (required), `search_objective`, `search_queries`, `excerpts` (bool or settings), `full_content` (bool or settings), `fetch_policy`, `max_chars_per_extract`.

**In a chain**

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a research assistant with real-time web access."),
    ("human", "{question}")
])

chain = prompt | chat | StrOutputParser()
result = chain.invoke({"question": "Latest AI breakthroughs?"})
```

**In an agent**

```python
from langchain.agents import create_openai_functions_agent, AgentExecutor

tools = [search_tool]
prompt = ChatPromptTemplate.from_messages([
    ("system", "Use tools to find current information."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}")
])

agent = create_openai_functions_agent(chat, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
result = executor.invoke({"input": "Latest AI developments?"})
```

### Anthropic Claude tool calling

```bash
pip install anthropic parallel-web
export PARALLEL_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
```

```bash
npm install @anthropic-ai/sdk parallel-web
```

Tool schema — note Anthropic uses `input_schema`, not OpenAI's `parameters`:

```json
{
  "name": "search_web",
  "description": "Searches the web for current and factual information, returning relevant results with titles, URLs, and content snippets.",
  "input_schema": {
    "type": "object",
    "properties": {
      "objective": {
        "type": "string",
        "description": "A concise, self-contained search query with the key entity or topic."
      },
      "search_queries": {
        "type": "array",
        "description": "Exactly 3 keyword search queries (3-6 words each), diverse and including the key entity.",
        "items": {"type": "string"},
        "minItems": 3,
        "maxItems": 3
      }
    },
    "required": ["objective", "search_queries"]
  }
}
```

Agentic loop:

1. Send the user message with `tools` available.
2. Claude returns `tool_use` blocks when `stop_reason == "tool_use"`.
3. Execute the search, collect results.
4. Reply with a `user` message containing `tool_result` blocks — **`tool_result` must come first in the content array**, before any text.
5. Repeat until `stop_reason` indicates completion.

Differences from OpenAI-style calling: Claude's tool inputs arrive as parsed dicts (not JSON strings), and it uses `stop_reason` rather than `finish_reason`. Add `"strict": true` to enforce schema compliance. Default `advanced` mode maximizes quality; `turbo` (~200 ms) is the low-latency option.

### Other integrations available

OpenAI tool calling · Ollama tool calling · Claude Code plugin · Cursor plugin · OpenCode plugin · Agent Skills · OpenClaw/ClawHub skills · OAuth provider · Account API · Pi extension · Agentic payments · AWS Marketplace · Google Cloud Marketplace · Google Sheets · Browser Use · n8n · OpenRouter · Superhuman · Zapier

**Data integrations:** Apache Spark · DuckDB · Google BigQuery · Polars · Snowflake · Supabase

---

## 12. Pricing (full table)

### Web tools

| Product | Price |
|---|---|
| Search — `turbo` | $1 / 1,000 requests (10 results default) |
| Search — `basic` / `advanced` | $5 / 1,000 requests (10 results default) |
| Search — extra results | $1 / 1,000 excerpts |
| Extract | $1 / 1,000 URLs |

### Web agents

**Task API** (per 1,000 task runs) — `-fast` variants cost the same as their base tier:

| Processor | Price | Latency |
|---|---|---|
| lite | $5 | 10 s – 60 s |
| base | $10 | 15 s – 100 s |
| core | $25 | 60 s – 5 min |
| core2x | $50 | 60 s – 10 min |
| pro | $100 | 2 – 10 min |
| ultra | $300 | 5 – 25 min |
| ultra2x | $600 | 5 – 50 min |
| ultra4x | $1,200 | 5 – 90 min |
| ultra8x | $2,400 | 5 min – 2 hr |

**Responses API** (per 1,000 requests): low effort $10 (~5–10 s) · medium $50 (~15–20 s) · high $250 (~30–60 s)

**Monitor API** (per 1,000 executions): `lite` $3 · `base` $10

**FindAll API**: preview $0.10 fixed, no per-match · base $0.25 fixed + $0.03/match · core $2.00 fixed + $0.15/match · pro $10.00 fixed + $1.00/match

**Entity Search** (per 1,000 requests, 100 results default): $5 base + $0.05 per 1,000 additional results

**Chat API** (per 1,000 requests): speed $5 · lite $5 · base $10 · core $25

The pricing page itself doesn't enumerate the free tier; the marketing site states signup credit plus a recurring $5/month free allowance (~5,000 requests/month).

---

## 13. Rate limits

| Product | Limit | Endpoint |
|---|---|---|
| Search | 600/min | `POST /v1/search` |
| Extract | 600/min | `POST /v1/extract` |
| Tasks / Task Groups | 2,000/min | `POST /v1/tasks/runs` (and task group runs) |
| Chat | 300/min | `POST /v1beta/chat/completions` |
| FindAll | 300/**hour** | `POST /v1beta/findall/runs` |
| Entity Search | 600/min | `POST /v1beta/findall/entity-search` |
| Monitor | 300/min | `POST /v1alpha/monitors` |

- Only **POST requests that create resources** count. GET requests (fetching results, checking status, e.g. `GET /v1/tasks/runs/{run_id}`) are free of rate limiting.
- Rate limits are independent of pricing tiers.
- Need more? Email support@parallel.ai with the use case.

---

## 14. Errors and warnings

| Status | Type | Retry? | Guidance |
|---|---|---|---|
| 401 | Unauthorized | No | Invalid/missing credentials — check the API key |
| 402 | Payment Required | No | Insufficient credits; check balance minus in-flight reservations |
| 403 | Forbidden | No | Invalid processor or missing permissions |
| 404 | Not Found | No | Run ID or resource doesn't exist |
| 408 | Request Timeout | Yes | Synchronous request timed out — switch to async polling |
| 422 | Unprocessable Content | No | Validation failed; inspect schema details |
| 429 | Too Many Requests | Yes | Rate limited — exponential backoff |
| 500 | Internal Server Error | Yes | Retry with backoff; escalate if persistent |
| 502 | Bad Gateway | Yes | Upstream issue, usually transient |
| 503 | Service Unavailable | Yes | Retry with backoff |

**Non-blocking warnings**
1. Input fails validation — input doesn't match the schema.
2. Task spec + input over size limit — exceeds the character threshold.
3. Too many output fields.
4. FieldBasis properties — you asked for citations/reasoning/sources in the output schema, but basis already provides them automatically.

**402 troubleshooting:** available balance = total minus in-flight reservations. Look at concurrent task count and processor tier, or top up at platform.parallel.ai.

---

## 15. Recommended integration for this hackathon

Cheapest compliant path that satisfies "Search API at runtime":

```python
import os
from parallel import Parallel

client = Parallel(api_key=os.environ["PARALLEL_API_KEY"])

result = client.beta.search(
    objective="Current spot pricing and availability for GPU render instances across cloud providers",
    search_queries=["cloud GPU spot pricing", "render farm GPU hourly cost"],
    mode="basic",
    max_chars_total=20000,
    session_id="render-gateway-pricing-001",
)

for r in result.results:
    print(r.url, r.title)
    for excerpt in r.excerpts:
        print(excerpt)
```

Notes for judging and cost control:
- `mode="basic"` at $5/1k requests, ~1 s — the docs' recommended starting point. Drop to `turbo` ($1/1k, ~200 ms) if the call sits on a user-facing hot path.
- Feed `excerpts` straight into the model prompt; no scraping or cleanup layer needed.
- Reuse one `session_id` per user task across Search and Extract calls.
- Cache nothing you need to prove is live — the requirement is a runtime call.
- Free allowance (~5,000 requests/month) comfortably covers hackathon-scale demos.

**Additional reference pages worth reading if you go deeper:** [Glossary](https://docs.parallel.ai/getting-started/glossary.md) · [Search migration guide](https://docs.parallel.ai/search/migrate-to-parallel.md) · [Task best practices](https://docs.parallel.ai/task-api/best-practices.md) · [Research basis](https://docs.parallel.ai/task-api/guides/access-research-basis.md) · [Webhook setup](https://docs.parallel.ai/resources/webhook-setup.md) · [FAQs](https://docs.parallel.ai/resources/faqs.md) · [Changelog](https://docs.parallel.ai/resources/changelog.md) · [Status](https://docs.parallel.ai/resources/status.md)
