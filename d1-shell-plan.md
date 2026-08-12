# D1 · Frontend Shell — Implementation Plan

## Overview

Task D1 establishes the frontend foundation the rest of the D-block tasks
build on. The current `web/` directory is a stock Next.js 16 scaffold with
only React, Next, and Tailwind installed.

The goal is a working **shell**: typed API client, data-fetching
infrastructure, an upload screen that accepts PDFs and surfaces API errors
clearly, and the three route placeholders that D2–D7 will fill in.

**Done when:** a real PDF can be dragged onto the upload screen, progress is
shown, the file lands in Postgres via `POST /api/scripts`, and the response
navigates to `/scripts/[id]`.

---

## Sub-tasks

---

### ST-1 · Install dependencies

**Intent**
Add the packages D1 requires before writing any application code. Nothing
else in the plan can proceed until these are resolved.

**Expected Outcomes**
- `web/package.json` lists the new deps
- `web/node_modules` is populated (lock file updated)

**Todo List**
1. In `web/`, install runtime deps:
   - `@tanstack/react-query` — server-state and cache
   - `openapi-typescript` (devDep) + `openapi-fetch` — typed fetch client
   - `react-dropzone` — file drop / click-to-pick
2. Install dev deps:
   - `openapi-typescript` (CLI, to generate types from the OpenAPI spec)

**Relevant Context**
- [`web/package.json`](web/package.json) — current deps; Next 16, React 19, Tailwind 4

**Status:** `[ ] pending`

---

### ST-2 · Hand-stub API types

**Intent**
The backend is not yet implemented, so `openapi-typescript` cannot run
against a live server. Write a `web/lib/api-types.ts` stub by hand,
shaped exactly as the spec describes, covering only the routes D1 needs.
Add the `gen:types` script so that when the backend is ready, one command
replaces the stub with the real generated version.

**Expected Outcomes**
- `web/lib/api-types.ts` exists with hand-authored `paths` types for:
  - `POST /api/scripts` (upload + all error shapes)
  - `GET /api/scripts/{id}` (metadata)
  - `GET /api/scripts/{id}/scenes` (scene list)
  - `POST /api/runs`
  - `GET /api/runs/{id}` (status + progress)
  - `GET /api/runs/{id}/findings`
  - `GET /api/findings/{id}`
  - `PATCH /api/findings/{id}`
- `package.json` has `"gen:types": "openapi-typescript http://localhost:8080/openapi.json -o lib/api-types.ts"` ready to run once the API is up
- A comment at the top of the file marks it as a stub pending regeneration

**Todo List**
1. Add `"gen:types"` script to `web/package.json`
2. Create `web/lib/api-types.ts` with the `paths` interface typed from the
   spec shapes in `technical-spec.md` sections 5 and 7
3. Mark the file with a `// STUB — run npm run gen:types once the API is live` header

**Relevant Context**
- All response and request shapes are in [`technical-spec.md`](technical-spec.md:414) sections 5 (data model) and 7 (API spec)
- When the backend is ready: `npm run gen:types` replaces this file entirely

**Status:** `[ ] pending`

---

### ST-3 · API client module

**Intent**
Create a single `web/lib/api.ts` module that wraps `openapi-fetch` with
the base URL from an env var. All fetch calls in the app go through this
client so the base URL and default headers are set in one place.

**Expected Outcomes**
- `web/lib/api.ts` exports a typed `apiClient` instance
- `NEXT_PUBLIC_API_URL` is read from environment (defaulting to
  `http://localhost:8080`)
- `.env.example` at repo root documents this var

**Todo List**
1. Create `web/lib/api.ts` using `createClient` from `openapi-fetch`,
   passing the generated `Paths` type
2. Set `baseUrl` from `process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"`
3. Add `NEXT_PUBLIC_API_URL=http://localhost:8080` to the root `.env.example`

**Relevant Context**
- Generated types from ST-2 will be the type parameter for `createClient`
- [`.env.example`](.env.example) — already exists at repo root, add the new var

**Status:** `[ ] pending`

---

### ST-4 · TanStack Query provider and error boundary

**Intent**
Wrap the Next.js app with a `QueryClientProvider` so any page can use
`useQuery` / `useMutation`. Add a top-level error boundary so unhandled
render errors show a recoverable message instead of a blank screen.

**Expected Outcomes**
- `web/app/providers.tsx` — a `"use client"` component holding
  `QueryClientProvider`
- `web/app/error.tsx` — Next.js App Router error boundary
- `web/app/layout.tsx` wraps `{children}` with `<Providers>`

**Todo List**
1. Create `web/app/providers.tsx` with a `QueryClient` instance and
   `QueryClientProvider`
2. Create `web/app/error.tsx` — Next.js `error.tsx` convention; show
   error message and a "Try again" reset button
3. Update `web/app/layout.tsx` to import and render `<Providers>` around
   `{children}`

**Relevant Context**
- [`web/app/layout.tsx`](web/app/layout.tsx) — current shell; just wraps `{children}` in `<body>`

**Status:** `[ ] pending`

---

### ST-5 · Upload screen — home route

**Intent**
Replace the stock Next.js home page with the upload screen. This is the
entry point every user sees. It must handle drag-and-drop, show upload
progress, and surface API errors in plain English — specifically the
`NO_TEXT_LAYER` error code described in the spec.

**Expected Outcomes**
- `web/app/page.tsx` renders a centred dropzone accepting `.pdf` only
- Uploading a valid PDF calls `POST /api/scripts`, shows a progress bar
  while streaming, and on `201` navigates to `/scripts/[id]`
- A 25 MB+ file shows a "File too large (25 MB max)" message
- A non-PDF shows "Only PDF files are accepted"
- A scanned PDF returns `422 NO_TEXT_LAYER` → shows
  "This PDF has no text layer. Re-export or use a text-based PDF."
- Other API errors show the HTTP status and a retry prompt

**Todo List**
1. Rewrite `web/app/page.tsx` as a `"use client"` component
2. Use `react-dropzone` with `accept: {"application/pdf": [".pdf"]}` and
   `maxSize: 25 * 1024 * 1024`
3. On drop: `useMutation` wrapping `apiClient.POST("/api/scripts", …)`
   with `FormData`
4. Track upload progress via `XMLHttpRequest` `onprogress` (fetch does not
   expose upload progress); surface as a percentage bar
5. On success: `router.push("/scripts/" + data.script_id)`
6. Map error codes to user-readable messages (see above)

**Relevant Context**
- API response shape from [`technical-spec.md`](technical-spec.md:428): `{script_id, title, source_format, page_count, scene_count, parse_warnings, duplicate_of}`
- Error codes from [`technical-spec.md`](technical-spec.md:435): `413`, `415`, `422 NO_TEXT_LAYER`

**Status:** `[ ] pending`

---

### ST-6 · Route placeholders

**Intent**
Create the `/scripts/[id]` and `/runs/[id]` route files so navigation
from the upload screen lands somewhere and the app builds cleanly. D2–D7
will fill in the actual content.

**Expected Outcomes**
- `web/app/scripts/[id]/page.tsx` renders a minimal placeholder
  showing the script ID and a "Script pane coming in D2" note
- `web/app/runs/[id]/page.tsx` renders a minimal placeholder showing
  the run ID and a "Run view coming in D5" note
- `npm run build` passes with no TypeScript errors

**Todo List**
1. Create `web/app/scripts/[id]/page.tsx` — basic page component
   receiving `params.id`, displaying it
2. Create `web/app/runs/[id]/page.tsx` — same pattern
3. Run `npm run build` (or `npm run lint`) and fix any type errors

**Relevant Context**
- Next.js App Router dynamic segment convention: `[id]` folder, `page.tsx`
  receives `{ params: { id: string } }` as props

**Status:** `[ ] pending`

---

## Dependency order

```
ST-1  →  ST-2  →  ST-3
                     ↓
ST-4              ST-5  →  ST-6
```

ST-4 and the ST-3 chain can proceed in parallel once ST-1 is done.
ST-6 is the final validation step and should be run last.
