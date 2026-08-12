# D3 · Findings Pane — Implementation Plan

## Overview

D3 builds the findings pane on the `/runs/[id]` page. It displays all
clearance findings for a completed run, grouped by canonical element,
with filters, sorting, and risk-colour coding.

The reference image shows a split-pane layout (script left, findings right)
but the spec says D4 handles the bidirectional link between the two panes.
D3 therefore builds the findings pane in isolation on `/runs/[id]` — a
dedicated route — and leaves the split-pane wiring for D4.

**Visual direction:** distinct from the reference image. The reference uses
warm beige / soft card styling. This implementation uses a dark sidebar
aesthetic: slate-950 background, risk chips in bold saturated colours
(crimson red, amber-500, emerald-500), clean sans-serif typography. Cards
are borderless with a subtle left-coloured accent stripe.

**Done when:** eighty-odd findings are navigable without scrolling fatigue,
and failures are impossible to miss.

---

## Key design decisions

### Grouping model
The `Finding` type in `api-types.ts` covers one mention. Groupings require
`canonical_name`, `surface_form`, and `category` — which live on the
`elements` table, not `findings`. The fixture and the enriched type stub
must include these fields. When the backend is built, the
`GET /api/runs/{id}/findings` response will be updated to include them.

A **group** = all findings that share a `canonical_name`. A group is
**split** when its mentions have different effective risks (e.g. one RED,
one GREEN for the same song in different contexts). The split is the
product's key differentiator and must be visually obvious.

### Failed research
Findings with `research_status: "failed"` pin above RED regardless of
their computed risk. They render with a distinct "Needs manual review"
label.

---

## Sub-tasks

---

### ST-1 · Extend api-types and fixture with enriched finding shape

**Intent**
The findings pane needs `canonical_name`, `surface_form`, `category`,
`scene_number`, and `research_status` on each `Finding`. Extend the stub
type and create a findings fixture so the pane is buildable without a
backend.

**Expected Outcomes**
- `Finding` in `web/lib/api-types.ts` gains five new fields:
  `canonical_name: string`, `surface_form: string`,
  `category: string` (values: `music | trademark | artwork | person | location | clip | literary | other`),
  `scene_number: number`, `research_status: "complete" | "partial" | "failed"`
- `web/lib/fixtures/run-findings.json` — 12–15 findings that exercise:
  - A same-song split (one RED action-line mention + one GREEN dialogue mention, same `canonical_name`)
  - A trademark with 4 mentions (all AMBER, same `canonical_name`)
  - A person mention (AMBER)
  - A painting (RED)
  - A `research_status: "failed"` entry pinned above the list
  - Mix of `review_status` values: unreviewed, accepted, overridden
- `web/lib/fixtures/run-meta.json` — a `Run` object in `complete` status

**Todo List**
1. Edit `web/lib/api-types.ts` to add the five fields to `Finding`
2. Create `web/lib/fixtures/run-meta.json` — `Run` with `status: "complete"`,
   realistic `progress` and `stats`
3. Create `web/lib/fixtures/run-findings.json` — `{ findings, total, counts }` shape
   matching `paths["/api/runs/{id}/findings"]` 200 response
4. Run `npx tsc --noEmit` — zero errors

**Relevant Context**
- [`web/lib/api-types.ts`](web/lib/api-types.ts:73) — `Finding` interface to extend
- [`technical-spec.md`](technical-spec.md:380) — assessment output shape, `per_mention` with `canonical_name`

**Status:** `[ ] pending`

---

### ST-2 · Data-fetching hooks for runs and findings

**Intent**
Add two TanStack Query hooks that mirror the pattern established in D2,
so the run page can fetch its data cleanly.

**Expected Outcomes**
- `web/lib/hooks/useRun.ts` — query for `GET /api/runs/{id}`
- `web/lib/hooks/useFindings.ts` — query for `GET /api/runs/{id}/findings`,
  accepts an optional `filters` param object (`risk`, `category`,
  `review_status`) that is passed through as query params

**Todo List**
1. Create `web/lib/hooks/useRun.ts`
2. Create `web/lib/hooks/useFindings.ts` with filter params

**Relevant Context**
- [`web/lib/hooks/useScript.ts`](web/lib/hooks/useScript.ts) — pattern to follow
- [`web/lib/api-types.ts`](web/lib/api-types.ts) — `paths["/api/runs/{id}"]` and `paths["/api/runs/{id}/findings"]`

**Status:** `[ ] pending`

---

### ST-3 · FindingCard component

**Intent**
The atom of the findings list. One card per finding (mention). Shows:
- A left-border accent stripe coloured by effective risk (red / amber / green)
- `surface_form` as the title, `canonical_name` in muted text below
- `rationale` — truncated to 2 lines, expandable
- Category badge (colour-coded pill)
- Source count + scene number in a muted footer
- "Needs manual review" banner when `research_status === "failed"`
- Dimmed / strikethrough style when `review_status === "accepted"`

**Expected Outcomes**
- `web/components/findings/FindingCard.tsx` renders correctly for all
  risk levels, failed research, and accepted status
- Accepts an `onClick` prop (for D4 navigation)

**Todo List**
1. Create `web/components/findings/FindingCard.tsx`
2. Effective risk = `override_risk ?? risk`
3. Risk stripe colours:
   - RED → `border-l-4 border-red-500` + `bg-red-950/30` tint
   - AMBER → `border-l-4 border-amber-400` + `bg-amber-950/20` tint
   - GREEN → `border-l-4 border-emerald-500` + `bg-emerald-950/20` tint
4. Category badge: small pill, colour per category
   (music=violet, trademark=blue, artwork=orange, person=pink, others=slate)
5. Failed research banner: `bg-red-900 text-red-200` strip at top of card

**Relevant Context**
- [`web/lib/api-types.ts`](web/lib/api-types.ts:73) — `Finding` interface

**Status:** `[ ] pending`

---

### ST-4 · FindingGroup component

**Intent**
Groups all findings sharing a `canonical_name`. Shows the group header
with the canonical name, the highest-risk badge across all mentions, and
expands/collapses to reveal individual `FindingCard` items.

A **split group** — where mentions have different effective risks — renders
a special "Split rating" indicator in the header (e.g. "RED + GREEN") and
starts expanded by default, because the split is the most important signal
in the product.

**Expected Outcomes**
- `web/components/findings/FindingGroup.tsx`
- Collapsed state: shows group name, mention count, highest risk chip,
  "split" indicator when applicable
- Expanded state: shows all `FindingCard` items beneath the header
- Split groups default to expanded; others default to collapsed

**Todo List**
1. Create `web/components/findings/FindingGroup.tsx`
2. Accept `findings: Finding[]` (already filtered to one canonical group)
3. Detect split: `new Set(findings.map(f => f.override_risk ?? f.risk)).size > 1`
4. Highest risk order: failed > red > amber > green
5. Toggle expand/collapse with a chevron icon

**Relevant Context**
- `FindingCard.tsx` from ST-3

**Status:** `[ ] pending`

---

### ST-5 · Filter and sort bar

**Intent**
A horizontal bar above the findings list with filter chips and a sort
toggle. Purely client-side — filters the in-memory findings array rather
than re-fetching. This keeps the interaction instant.

**Expected Outcomes**
- `web/components/findings/FindingsFilterBar.tsx`
- Filter chips: "All risk" / "RED" / "AMBER" / "GREEN" toggle group
- Category filter: a `<select>` dropdown (all types from the fixture)
- Review status filter: "Unreviewed only" checkbox
- Sort toggle: "Risk order" (default: failed → red → amber → green) vs
  "Script order" (by scene_number ascending)
- Shows counts: "9 red · 31 amber · 44 green" from the `counts` object

**Todo List**
1. Create `web/components/findings/FindingsFilterBar.tsx`
2. Accept `counts`, `filters`, `onFilterChange`, `sort`, `onSortChange` props
3. Style: dark bar `bg-slate-900` with light text, active chip
   highlighted in the risk colour

**Relevant Context**
- `counts` shape from `paths["/api/runs/{id}/findings"]` 200 response

**Status:** `[ ] pending`

---

### ST-6 · Runs page assembly

**Intent**
Replace the `/runs/[id]` placeholder with the real page. Fetches the run
and its findings, applies client-side filters/sort, groups by
`canonical_name`, and renders the filter bar + grouped findings list.
Falls back to fixture data when `id === "demo"`.

**Expected Outcomes**
- `web/app/runs/[id]/page.tsx` renders:
  - A header: run status badge, script title placeholder, progress counts
  - `FindingsFilterBar` with live counts
  - Grouped findings list — failed entries pinned above all groups
  - Loading skeleton and error state
- `id === "demo"` loads `run-meta.json` + `run-findings.json` fixtures
- `npm run build` passes with zero errors

**Todo List**
1. Rewrite `web/app/runs/[id]/page.tsx` as `"use client"`
2. Use `useRun(id)` and `useFindings(id)` hooks; bypass with fixtures on demo
3. Client-side grouping: `Map<canonical_name, Finding[]>`, sorted by highest
   group risk then scene_number
4. Pin failed-research groups at the top of the list
5. Apply filter/sort state from `FindingsFilterBar`
6. Run `npm run build`

**Relevant Context**
- [`web/app/runs/[id]/page.tsx`](web/app/runs/[id]/page.tsx) — current placeholder
- [`web/app/scripts/[id]/page.tsx`](web/app/scripts/[id]/page.tsx) — pattern for demo fallback

**Status:** `[ ] pending`

---

### ST-0 · Mock API route handlers

**Intent**
Add Next.js Route Handlers that serve fixture JSON at the same URL paths
the real API will use. This means `useFindings("demo")` hits
`/api/runs/demo/findings` and gets real-looking data back — no demo
special-casing needed in the hook or page, and the design is verifiable
immediately in the browser without any backend.

**Expected Outcomes**
- `web/app/api/runs/[id]/findings/route.ts` — GET handler returning `run-findings.json`
- `web/app/api/runs/[id]/route.ts` — GET handler returning `run-meta.json`
- Visiting `http://localhost:3000/api/runs/demo/findings` in the browser
  returns the fixture JSON

**Todo List**
1. Create `web/app/api/runs/[id]/findings/route.ts`
2. Create `web/app/api/runs/[id]/route.ts`
3. Both import and return their respective fixture files via `Response.json()`

**Relevant Context**
- Next.js Route Handler convention: `export async function GET() { return Response.json(data) }`
- Fixture files created in ST-1
- Note: these handlers sit at `/api/...` in Next.js but the real API is on
  a separate FastAPI server. The `apiClient` baseUrl points to
  `localhost:8080` — so the hooks will NOT hit these handlers by default.
  ST-6 must configure the page to use a relative fetch (or pass a flag) so
  the mock routes are reachable during local dev without a backend.

**Status:** `[ ] pending`

---

## Dependency order

```
ST-1  →  ST-0  →  ST-2
      ↘
        ST-3  →  ST-4  →  ST-6
                 ST-5  ↗
```

ST-1 must complete first (types + fixture). ST-0 (mock routes) follows
immediately so the page can render real data. ST-2 and ST-3 can run in
parallel. ST-4 and ST-5 depend on ST-3. ST-6 integrates everything.
