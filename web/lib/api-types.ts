/**
 * The names the app imports, sourced from the generated OpenAPI schema.
 *
 * `lib/api-schema.ts` is written by `npm run gen:types` straight from the
 * running API's /openapi.json and must never be edited by hand. This file is
 * the thin layer above it: it gives the generated shapes the short names the
 * components already use, so `import type { Finding } from "@/lib/api-types"`
 * keeps working while the definition behind it becomes generated truth.
 *
 * Why not simply generate into this file
 * --------------------------------------
 * That is what package.json used to do, and it would have broken eleven files
 * at once. openapi-typescript emits `paths` and `components` — it does not
 * emit `Finding`, `Script` or `Scene`, which is what every component imports.
 * Pointing the generator at this path replaces those names with nothing.
 *
 * Keeping the alias layer separate also makes drift loud instead of silent.
 * If the API stops sending `FindingOut`, or renames a field a component reads,
 * the failure is a TypeScript error here or at the point of use — not a page
 * that renders `undefined` at a demo.
 *
 * Checked when this layer was introduced: of the ten string-literal unions the
 * hand-written stub declared, generation preserved nine. The tenth,
 * `Finding.category`, was widened to `string` by a `category: str` in
 * api/app/schemas.py, and was fixed there rather than patched here — a union
 * restated in TypeScript is a union that can disagree with the server.
 */

import type { components, paths } from "./api-schema";

export type { paths };

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Domain shapes
// ---------------------------------------------------------------------------

export type Script = Schemas["ScriptOut"];
export type Scene = Schemas["SceneOut"];
export type ScriptElement = Schemas["ScriptElementOut"];
export type Run = Schemas["RunOut"];
export type Finding = Schemas["FindingOut"];
export type RightsHolder = Schemas["RightsHolderOut"];
export type Source = Schemas["SourceOut"];

// ---------------------------------------------------------------------------
// Envelopes and errors
// ---------------------------------------------------------------------------

export type RunProgress = Schemas["RunProgressOut"];
export type ScenesResponse = Schemas["ScenesOut"];
export type ScriptsResponse = Schemas["ScriptsOut"];
export type ScriptSummary = Schemas["ScriptSummaryOut"];
export type ScriptRun = Schemas["ScriptRunOut"];
export type FindingsResponse = Schemas["FindingsOut"];
export type ApiError = Schemas["ApiErrorOut"];
export type NoTextLayerError = Schemas["NoTextLayerOut"];

// ---------------------------------------------------------------------------
// Convenience unions, derived rather than restated
// ---------------------------------------------------------------------------

export type Risk = Finding["risk"];
export type Category = Finding["category"];
export type ReviewStatus = Finding["review_status"];
export type RunStatus = Run["status"];
