"use client";

interface Counts {
  red: number;
  amber: number;
  green: number;
}

export type RiskFilter = "all" | "red" | "amber" | "green";
export type SortMode = "risk" | "scene";

interface Props {
  counts: Counts;
  riskFilter: RiskFilter;
  onRiskFilter: (r: RiskFilter) => void;
  categoryFilter: string;
  categories: string[];
  onCategoryFilter: (c: string) => void;
  unreviewedOnly: boolean;
  onUnreviewedOnly: (v: boolean) => void;
  sort: SortMode;
  onSort: (s: SortMode) => void;
  total: number;
}

const RISK_CHIP: Record<RiskFilter, string> = {
  all: "bg-slate-700 text-slate-200 hover:bg-slate-600",
  red: "bg-red-900 text-red-200 hover:bg-red-800",
  amber: "bg-amber-900 text-amber-200 hover:bg-amber-800",
  green: "bg-emerald-900 text-emerald-200 hover:bg-emerald-800",
};

const RISK_ACTIVE: Record<RiskFilter, string> = {
  all: "ring-2 ring-slate-400",
  red: "ring-2 ring-red-400",
  amber: "ring-2 ring-amber-400",
  green: "ring-2 ring-emerald-400",
};

export default function FindingsFilterBar({
  counts,
  riskFilter,
  onRiskFilter,
  categoryFilter,
  categories,
  onCategoryFilter,
  unreviewedOnly,
  onUnreviewedOnly,
  sort,
  onSort,
  total,
}: Props) {
  return (
    <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex flex-wrap items-center gap-3">
      {/* Risk chips */}
      <div className="flex items-center gap-1.5">
        {(["all", "red", "amber", "green"] as RiskFilter[]).map((r) => (
          <button
            key={r}
            onClick={() => onRiskFilter(r)}
            className={[
              "text-xs font-semibold px-2.5 py-1 rounded-full transition-all",
              RISK_CHIP[r],
              riskFilter === r ? RISK_ACTIVE[r] : "",
            ].join(" ")}
          >
            {r === "all"
              ? `All · ${total}`
              : `${r.charAt(0).toUpperCase() + r.slice(1)} · ${counts[r]}`}
          </button>
        ))}
      </div>

      {/* Divider */}
      <div className="h-5 w-px bg-slate-700" />

      {/* Category filter */}
      <select
        value={categoryFilter}
        onChange={(e) => onCategoryFilter(e.target.value)}
        className="text-xs bg-slate-800 text-slate-300 border border-slate-700 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-slate-500"
      >
        <option value="">All types</option>
        {categories.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>

      {/* Unreviewed only */}
      <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={unreviewedOnly}
          onChange={(e) => onUnreviewedOnly(e.target.checked)}
          className="accent-slate-400 w-3 h-3"
        />
        Unreviewed only
      </label>

      {/* Sort toggle — pushed right */}
      <div className="ml-auto flex items-center gap-1 text-xs">
        <span className="text-slate-500">Sort:</span>
        {(["risk", "scene"] as SortMode[]).map((s) => (
          <button
            key={s}
            onClick={() => onSort(s)}
            className={[
              "px-2.5 py-1 rounded transition-colors",
              sort === s
                ? "bg-slate-600 text-slate-100"
                : "text-slate-500 hover:text-slate-300",
            ].join(" ")}
          >
            {s === "risk" ? "Risk order" : "Script order"}
          </button>
        ))}
      </div>
    </div>
  );
}
