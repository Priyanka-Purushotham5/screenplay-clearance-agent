# D2 · Script Pane — Implementation Plan

## Overview

D2 replaces the `/scripts/[id]` placeholder with a working screenplay
reader. The rendered output is parsed text from `GET /api/scripts/{id}/scenes`
— not the original PDF. This is intentional: only text you control can
have spans highlighted (needed for D4), and the rendering is proof the
parser is working correctly.

The three hard constraints from the checklist:
1. **Screenplay CSS** — monospace, character cues centred, dialogue
   indented, scene headings in caps. This is visual identity, not polish.
2. **Virtualisation** — a 118-page script is thousands of DOM nodes. Must
   use TanStack Virtual so scrolling stays smooth.
3. **`scrollToPage(n)` and `scrollToElement(id)`** — programmatic scroll
   targets, needed by D4's bidirectional linking.

The backend is not yet live. D2 is built against a fixture file so it can
be developed and verified independently.

**Done when:** a full script scrolls smoothly and looks like a screenplay.

---

## Sub-tasks

---

### ST-1 · Install TanStack Virtual

**Intent**
Add the one missing runtime dependency before writing any component code.

**Expected Outcomes**
- `web/package.json` lists `@tanstack/react-virtual`

**Todo List**
1. In `web/`, run `npm install @tanstack/react-virtual`

**Relevant Context**
- [`web/package.json`](web/package.json) — already has `@tanstack/react-query`; same org, same install pattern

**Status:** `[ ] pending`

---

### ST-2 · Fixture data

**Intent**
Create a static JSON fixture that mirrors the `GET /api/scripts/{id}/scenes`
response shape. The script pane must be fully developable and visually
verifiable without the backend running.

The fixture should exercise all element types and edge cases: scene
headings, action blocks, character cues, dialogue, parentheticals,
transitions, a page-split dialogue block, and a `INT./EXT.` heading.

**Expected Outcomes**
- `web/lib/fixtures/script-scenes.json` exists with ~4–6 scenes, all
  element types represented
- A matching `web/lib/fixtures/script-meta.json` with a `Script` object

**Todo List**
1. Create `web/lib/fixtures/script-scenes.json` — `{ "scenes": [...] }`
   using the `Scene` / `ScriptElement` shapes from `api-types.ts`
2. Create `web/lib/fixtures/script-meta.json` — a `Script` object with
   realistic values (`page_count`, `scene_count`, etc.)
3. Cover every `ScriptElement.type`: `scene_heading`, `action`,
   `character`, `dialogue`, `parenthetical`, `transition`

**Relevant Context**
- [`web/lib/api-types.ts`](web/lib/api-types.ts) — `Scene` and `ScriptElement` interfaces
- [`technical-spec.md`](technical-spec.md:306) §6 Stage 1 — example scene JSON

**Status:** `[ ] pending`

---

### ST-3 · Data-fetching hooks

**Intent**
Create two TanStack Query hooks that the script page uses to fetch script
metadata and scenes. Keeping fetch logic in hooks (not in the page
component) makes them reusable for D3–D5 and keeps the component tree
clean.

**Expected Outcomes**
- `web/lib/hooks/useScript.ts` — `useQuery` for `GET /api/scripts/{id}`
- `web/lib/hooks/useScenes.ts` — `useQuery` for
  `GET /api/scripts/{id}/scenes` (fetches all scenes; no pagination needed
  for D2 — virtualisation handles the rendering side)
- Both hooks accept a `scriptId: string` parameter and return the
  TanStack Query result object

**Todo List**
1. Create `web/lib/hooks/useScript.ts` using `apiClient.GET` typed against
   `/api/scripts/{id}`
2. Create `web/lib/hooks/useScenes.ts` using `apiClient.GET` typed against
   `/api/scripts/{id}/scenes`
3. Both hooks should have `enabled: !!scriptId` so they don't fire with an
   empty ID

**Relevant Context**
- [`web/lib/api.ts`](web/lib/api.ts) — `apiClient` export
- [`web/lib/api-types.ts`](web/lib/api-types.ts) — path types for both endpoints

**Status:** `[ ] pending`

---

### ST-4 · Screenplay element components

**Intent**
Build the per-element rendering components with the correct screenplay
CSS. Each `ScriptElement.type` maps to a distinct visual style. These
are the atoms that the virtualised list renders.

**Expected Outcomes**
- `web/components/screenplay/SceneHeading.tsx` — ALL CAPS, monospace,
  full-width, top margin
- `web/components/screenplay/ActionBlock.tsx` — monospace, full-width
- `web/components/screenplay/CharacterCue.tsx` — centred, monospace
- `web/components/screenplay/DialogueLine.tsx` — indented ~25% from left,
  monospace, ~60% width
- `web/components/screenplay/Parenthetical.tsx` — indented slightly more
  than dialogue, monospace
- `web/components/screenplay/Transition.tsx` — right-aligned, monospace
- `web/components/screenplay/ScriptElement.tsx` — dispatcher: receives a
  `ScriptElement` object and renders the correct component by `type`

All components accept a `data-element-id` attribute (for D4 scroll
targeting) and an optional `highlighted` boolean prop (for D4 flash).

**Todo List**
1. Add a `web/components/screenplay/` directory
2. Implement each of the six typed components
3. Implement the `ScriptElement` dispatcher component
4. Use Tailwind utility classes; font must be `font-mono` throughout

**Relevant Context**
- [`technical-spec.md`](technical-spec.md:139) — indentation table: action/scene ~1.5",
  dialogue ~2.5", parenthetical ~3.1", character ~3.7", transition right-aligned
- [`web/app/globals.css`](web/app/globals.css) — `--font-mono` is Geist Mono

**Status:** `[ ] pending`

---

### ST-5 · Virtualised script pane

**Intent**
Build the virtualised list that renders scenes and their elements. TanStack
Virtual handles row recycling so thousands of elements render at 60 fps.
The list rows are the `ScriptElement` atoms from ST-4.

This component also exposes `scrollToPage(n)` and `scrollToElement(id)` as
an imperative handle (via `useImperativeHandle` + `forwardRef`) so D4 can
call them from outside.

**Expected Outcomes**
- `web/components/screenplay/ScriptPane.tsx` — virtualised list of all
  scene elements, with the scene heading as the first item in each scene
  group
- Exports a `ScriptPaneHandle` type with `{ scrollToPage(n: number): void; scrollToElement(id: string): void }`
- `scrollToPage(n)` scrolls to the first element on page `n`
- `scrollToElement(id)` scrolls to the element with that `script_element_id`

**Todo List**
1. Flatten `Scene[]` into a single `VirtualItem[]` array (scene heading
   first, then each element in `seq` order) — this is the list TanStack
   Virtual iterates
2. Use `useVirtualizer` from `@tanstack/react-virtual` with
   `estimateSize: () => 40` as a starting estimate
3. Wrap in `forwardRef`, expose `scrollToPage` and `scrollToElement` via
   `useImperativeHandle`
4. `scrollToPage`: find the index of the first item whose `page ===  n`,
   call `virtualizer.scrollToIndex`
5. `scrollToElement`: find the index by `id`, call
   `virtualizer.scrollToIndex`

**Relevant Context**
- [`web/lib/api-types.ts`](web/lib/api-types.ts) — `Scene.page_start`, `ScriptElement.page`,
  `ScriptElement.id`
- TanStack Virtual docs: `useVirtualizer`, `scrollToIndex`

**Status:** `[ ] pending`

---

### ST-6 · Script page assembly

**Intent**
Replace the placeholder `web/app/scripts/[id]/page.tsx` with the real
page. It fetches script metadata and scenes, shows a loading state while
fetching, an error state on failure, and renders the `ScriptPane` once
data arrives. In the absence of a live backend, it falls back to the
fixture data.

**Expected Outcomes**
- `web/app/scripts/[id]/page.tsx` renders:
  - A narrow header bar: script title, page count, scene count
  - The `ScriptPane` filling the remaining viewport height
  - A skeleton/spinner while loading
  - An error message if the fetch fails
- When the script ID is `"demo"`, load from fixture files instead of the
  API (so the page is always demonstrable offline)

**Todo List**
1. Rewrite `web/app/scripts/[id]/page.tsx` as a `"use client"` component
2. Use `useScript(id)` and `useScenes(id)` hooks from ST-3
3. If `id === "demo"`, import and use the fixture JSON directly (bypassing
   the hooks)
4. Render a fixed header with title and counts
5. Render `<ScriptPane ref={paneRef} scenes={scenes} />` below the header
6. Run `npm run build` — must pass with zero errors

**Relevant Context**
- [`web/app/scripts/[id]/page.tsx`](web/app/scripts/[id]/page.tsx) — current placeholder to replace
- Fixture files from ST-2

**Status:** `[ ] pending`

---

## Dependency order

```
ST-1
  ↓
ST-2  →  ST-3
              ↘
         ST-4  →  ST-5  →  ST-6
```

ST-2 and ST-3 can run in parallel after ST-1. ST-4 can start as soon as
ST-2 is done (it renders fixture data directly). ST-5 depends on ST-4.
ST-6 is the final integration step.
