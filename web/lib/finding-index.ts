import type { Finding } from "./api-types";
import type { Mention } from "./highlight";
import { effectiveRisk } from "./risk";

export interface FindingIndex {
  byId: Map<string, Finding>;
  /** key = script_element_id */
  mentionsByElement: Map<string, Mention[]>;
}

export const EMPTY_INDEX: FindingIndex = {
  byId: new Map(),
  mentionsByElement: new Map(),
};

/**
 * Build both lookups in one pass.
 *
 * Called with the UNFILTERED findings list: the script pane always shows every
 * highlight, so a mark can never select a card that the current filter has
 * hidden without the run view noticing (see the hidden-by-filter banner).
 *
 * The arrays in `mentionsByElement` are referentially stable for a given
 * `findings` identity, which is what keeps ScriptElement's segmentation memo
 * from recomputing on every selection change.
 */
export function buildFindingIndex(findings: Finding[]): FindingIndex {
  const byId = new Map<string, Finding>();
  const mentionsByElement = new Map<string, Mention[]>();

  for (const f of findings) {
    byId.set(f.id, f);
    if (!f.script_element_id) continue; // tolerate pre-D4 payloads

    const m: Mention = {
      findingId: f.id,
      scriptElementId: f.script_element_id,
      surfaceForm: f.surface_form,
      risk: effectiveRisk(f),
      charStart: f.char_start ?? null,
      charEnd: f.char_end ?? null,
    };

    const list = mentionsByElement.get(f.script_element_id);
    if (list) list.push(m);
    else mentionsByElement.set(f.script_element_id, [m]);
  }

  return { byId, mentionsByElement };
}
