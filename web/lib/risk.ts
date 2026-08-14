import type { CSSProperties } from "react";

// ---------------------------------------------------------------------------
// Risk
// ---------------------------------------------------------------------------

export type Risk = "red" | "amber" | "green";

/** Lower is worse. `failed` research outranks every risk — see groupRank. */
export const RISK_RANK: Record<Risk, number> = { red: 0, amber: 1, green: 2 };

export function effectiveRisk(f: {
  risk: Risk;
  override_risk: Risk | null;
}): Risk {
  return f.override_risk ?? f.risk;
}

// ---------------------------------------------------------------------------
// Inline marks — script pane (dark slate surface)
// ---------------------------------------------------------------------------
//
// Colours are CSS custom properties rather than Tailwind classes because the
// flash keyframes in globals.css consume them. Tailwind's scanner never sees
// inline style values, and arbitrary values inside @keyframes are not
// resolvable at build time, so these must be literal hex.
//
// Text colour is deliberately inherited: the script pane is monospace and any
// per-mark colour or padding would break column alignment.

const MARK_REST: Record<Risk, string> = {
  red: "#4c1d1d",
  amber: "#4a3410",
  green: "#14392c",
};

const MARK_REST_SELECTED: Record<Risk, string> = {
  red: "#6b2020",
  amber: "#6b4a12",
  green: "#17503a",
};

const FLASH_PEAK: Record<Risk, string> = {
  red: "#b91c1c",
  amber: "#b45309",
  green: "#047857",
};

const FLASH_HALO: Record<Risk, string> = {
  red: "#7f1d1d",
  amber: "#78350f",
  green: "#065f46",
};

/**
 * Custom properties for one mark. The flash animation's final keyframe lands
 * exactly on `--mark-rest`, so the selected and unselected rest colours differ
 * here — otherwise the animation ends on a one-frame colour pop.
 */
export function markVars(risk: Risk, selected: boolean): CSSProperties {
  return {
    "--mark-rest": selected ? MARK_REST_SELECTED[risk] : MARK_REST[risk],
    "--flash-peak": FLASH_PEAK[risk],
    "--flash-halo": FLASH_HALO[risk],
  } as CSSProperties;
}

/** Element-level fallback flash, for mentions whose span could not be resolved. */
export function blockVars(risk: Risk): CSSProperties {
  return { "--flash-peak": MARK_REST_SELECTED[risk] } as CSSProperties;
}

export const MARK_CLASS = "clearance-mark";
export const MARK_SELECTED_CLASS = "clearance-mark-selected";
export const FLASH_CLASS = "clearance-flash";
export const BLOCK_FLASH_CLASS = "clearance-flash-block";

// ---------------------------------------------------------------------------
// Findings pane — selected card ring
// ---------------------------------------------------------------------------

export const RISK_RING: Record<Risk, string> = {
  red: "ring-2 ring-red-500 ring-offset-1 ring-offset-slate-950",
  amber: "ring-2 ring-amber-400 ring-offset-1 ring-offset-slate-950",
  green: "ring-2 ring-emerald-500 ring-offset-1 ring-offset-slate-950",
};
