import { RISK_RANK, type Risk } from "./risk";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** One mention of a finding inside one script element. */
export interface Mention {
  findingId: string;
  scriptElementId: string;
  surfaceForm: string;
  /** Already the effective risk (override_risk ?? risk). */
  risk: Risk;
  charStart: number | null;
  charEnd: number | null;
}

export type Segment =
  | { kind: "text"; key: string; text: string }
  | { kind: "mark"; key: string; text: string; findingId: string; risk: Risk };

export interface SegmentedText {
  segments: Segment[];
  /** Mentions with no usable span — the caller falls back to element level. */
  unresolved: Mention[];
  /** Count of spans that needed repairing. A health metric for extraction. */
  repaired: number;
}

type ResolveOutcome = "exact" | "repaired-exact" | "repaired-ci";

// ---------------------------------------------------------------------------
// Range resolution
// ---------------------------------------------------------------------------

/**
 * Find the occurrence of `needle` closest to `near`.
 *
 * Offsets from the extractor are usually off by a few characters rather than
 * wholly wrong, so the nearest occurrence is far more likely to be the intended
 * one than the first. This matters: "this" appears three times in one line of
 * dialogue, and "PATSY CLINE" twice in the script.
 */
function nearestIndexOf(hay: string, needle: string, near: number): number {
  let best = -1;
  let bestDist = Infinity;
  for (let i = hay.indexOf(needle); i !== -1; i = hay.indexOf(needle, i + 1)) {
    const d = Math.abs(i - near);
    if (d < bestDist) {
      best = i;
      bestDist = d;
    }
  }
  return best;
}

function resolveRange(
  text: string,
  m: Mention
): { start: number; end: number; outcome: ResolveOutcome } | null {
  const { charStart: s, charEnd: e, surfaceForm } = m;

  // 1. Trust the offsets only if they are structurally sane AND the text at
  //    that position is actually the surface form.
  const sane =
    typeof s === "number" &&
    typeof e === "number" &&
    Number.isInteger(s) &&
    Number.isInteger(e) &&
    s >= 0 &&
    e > s &&
    e <= text.length;

  if (sane && text.slice(s, e) === surfaceForm) {
    return { start: s, end: e, outcome: "exact" };
  }

  if (!surfaceForm) return null;

  // 2. Exact search, biased toward where the model claimed the span was.
  const hit = nearestIndexOf(text, surfaceForm, s ?? 0);
  if (hit !== -1) {
    return { start: hit, end: hit + surfaceForm.length, outcome: "repaired-exact" };
  }

  // 3. Case-insensitive. Script text is frequently ALL CAPS while the model
  //    echoes title case ("Coca-Cola" vs "COCA-COLA"). toLowerCase is
  //    length-preserving across the ranges screenplays use, so the index maps
  //    back to the original string.
  const ciHit = nearestIndexOf(
    text.toLowerCase(),
    surfaceForm.toLowerCase(),
    s ?? 0
  );
  if (ciHit !== -1) {
    return { start: ciHit, end: ciHit + surfaceForm.length, outcome: "repaired-ci" };
  }

  // 4. Give up. The caller applies whole-element treatment.
  return null;
}

// ---------------------------------------------------------------------------
// Segmentation
// ---------------------------------------------------------------------------

const NO_MENTIONS: Mention[] = [];

/**
 * Split one element's text into plain runs and marked runs.
 *
 * The single-cursor sweep makes overlapping marks structurally impossible: a
 * range starting before the cursor is dropped to `unresolved` rather than
 * nested or duplicated.
 */
export function segmentElementText(
  text: string,
  mentions: Mention[] = NO_MENTIONS
): SegmentedText {
  if (mentions.length === 0) {
    return {
      segments: [{ kind: "text", key: "t0", text }],
      unresolved: [],
      repaired: 0,
    };
  }

  const resolved: Array<Mention & { start: number; end: number }> = [];
  const unresolved: Mention[] = [];
  let repaired = 0;

  for (const m of mentions) {
    const r = resolveRange(text, m);
    if (!r) {
      unresolved.push(m);
      continue;
    }
    if (r.outcome !== "exact") {
      repaired++;
      if (process.env.NODE_ENV !== "production") {
        console.warn(
          `[highlight] repaired offsets (${r.outcome}) for ${JSON.stringify(
            m.surfaceForm
          )} in element ${m.scriptElementId}: ` +
            `claimed ${m.charStart}–${m.charEnd}, using ${r.start}–${r.end}`
        );
      }
    }
    resolved.push({ ...m, start: r.start, end: r.end });
  }

  // start asc → higher risk wins a tie → longer span next → stable by id
  resolved.sort(
    (a, b) =>
      a.start - b.start ||
      RISK_RANK[a.risk] - RISK_RANK[b.risk] ||
      b.end - b.start - (a.end - a.start) ||
      a.findingId.localeCompare(b.findingId)
  );

  const segments: Segment[] = [];
  let cursor = 0;

  for (const r of resolved) {
    if (r.start < cursor) {
      // Overlaps a mark already emitted — the lower-risk one loses the DOM but
      // stays clickable from the findings pane via the element-level fallback.
      unresolved.push(r);
      continue;
    }
    if (r.start > cursor) {
      segments.push({
        kind: "text",
        key: `t${cursor}`,
        text: text.slice(cursor, r.start),
      });
    }
    segments.push({
      kind: "mark",
      key: `m${r.findingId}`,
      text: text.slice(r.start, r.end),
      findingId: r.findingId,
      risk: r.risk,
    });
    cursor = r.end;
  }

  if (cursor < text.length) {
    segments.push({ kind: "text", key: `t${cursor}`, text: text.slice(cursor) });
  }

  return { segments, unresolved, repaired };
}
