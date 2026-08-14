"use client";

import { use, useMemo, useState } from "react";
import { useRun } from "@/lib/hooks/useRun";
import { useFindings } from "@/lib/hooks/useFindings";
import { useScenes } from "@/lib/hooks/useScenes";
import type { Finding, Run } from "@/lib/api-types";
import { buildFindingIndex } from "@/lib/finding-index";
import {
  DeepLinkSeed,
  LinkingProvider,
  useSelection,
} from "@/components/linking/LinkingProvider";
import ScriptPane from "@/components/screenplay/ScriptPane";
import FindingGroup from "@/components/findings/FindingGroup";
import FindingsFilterBar, {
  type RiskFilter,
  type SortMode,
} from "@/components/findings/FindingsFilterBar";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_COLOUR: Record<string, string> = {
  pending: "bg-slate-700 text-slate-300",
  extracting: "bg-blue-900 text-blue-300",
  researching: "bg-violet-900 text-violet-300",
  assessing: "bg-amber-900 text-amber-300",
  composing: "bg-teal-900 text-teal-300",
  complete: "bg-emerald-900 text-emerald-300",
  failed: "bg-red-900 text-red-300",
};

function RunHeader({ run }: { run: Run }) {
  return (
    <header className="flex items-center gap-4 px-6 py-3 bg-slate-900 border-b border-slate-800 shrink-0">
      <span className={`text-xs font-bold uppercase px-2 py-0.5 rounded ${STATUS_COLOUR[run.status] ?? STATUS_COLOUR.pending}`}>
        {run.status}
      </span>
      <div className="flex items-center gap-3 text-xs text-slate-500 ml-auto">
        <span>{run.progress.elements_found} elements</span>
        <span>·</span>
        <span>{run.progress.researched} researched</span>
        <span>·</span>
        <span>{run.progress.assessed} assessed</span>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Grouping helpers
// ---------------------------------------------------------------------------

const RISK_RANK: Record<string, number> = { failed: 0, red: 1, amber: 2, green: 3 };

function groupFindings(findings: Finding[]): Map<string, Finding[]> {
  const map = new Map<string, Finding[]>();
  for (const f of findings) {
    const key = f.canonical_name;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(f);
  }
  return map;
}

function groupRank(findings: Finding[]): number {
  if (findings.some((f) => f.research_status === "failed")) return 0;
  const risks = findings.map((f) => RISK_RANK[f.override_risk ?? f.risk] ?? 3);
  return Math.min(...risks);
}

// ---------------------------------------------------------------------------
// Hidden-by-filter notice
// ---------------------------------------------------------------------------

/**
 * A mark in the script can belong to a finding the current filters exclude —
 * the script pane always highlights everything. Without this the click would
 * select a card that never mounts, and nothing would appear to happen.
 */
function HiddenSelectionBar({
  visible,
  onClear,
}: {
  visible: Finding[];
  onClear: () => void;
}) {
  const { selection } = useSelection();
  if (!selection.findingId) return null;
  if (visible.some((f) => f.id === selection.findingId)) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-slate-800 border-b border-slate-700 text-xs text-slate-300 shrink-0">
      <span>1 selected finding is hidden by the current filters.</span>
      <button
        onClick={onClear}
        className="font-semibold text-slate-100 underline underline-offset-2 hover:text-white"
      >
        Show it
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const runQuery = useRun(id);
  const findingsQuery = useFindings(id);

  const run: Run | undefined = runQuery.data;
  const scenesQuery = useScenes(run?.script_id ?? "");

  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [unreviewedOnly, setUnreviewedOnly] = useState(false);
  const [sort, setSort] = useState<SortMode>("risk");

  const allFindings: Finding[] = useMemo(
    () => findingsQuery.data?.findings ?? [],
    [findingsQuery.data]
  );
  const counts = findingsQuery.data?.counts ?? { red: 0, amber: 0, green: 0 };
  const total = findingsQuery.data?.total ?? 0;

  // Built from the unfiltered list: the script always shows every highlight.
  const index = useMemo(() => buildFindingIndex(allFindings), [allFindings]);

  // Derive unique categories for the dropdown
  const categories = useMemo(
    () => [...new Set(allFindings.map((f) => f.category))].sort(),
    [allFindings]
  );

  // Client-side filtering
  const filtered = useMemo(() => {
    return allFindings.filter((f) => {
      if (riskFilter !== "all" && (f.override_risk ?? f.risk) !== riskFilter) return false;
      if (categoryFilter && f.category !== categoryFilter) return false;
      if (unreviewedOnly && f.review_status !== "unreviewed") return false;
      return true;
    });
  }, [allFindings, riskFilter, categoryFilter, unreviewedOnly]);

  // Group and sort
  const sortedGroups = useMemo(() => {
    const groups = groupFindings(filtered);
    const entries = [...groups.entries()];
    if (sort === "risk") {
      entries.sort((a, b) => groupRank(a[1]) - groupRank(b[1]));
    } else {
      entries.sort((a, b) => {
        const aMin = Math.min(...a[1].map((f) => f.scene_number));
        const bMin = Math.min(...b[1].map((f) => f.scene_number));
        return aMin - bMin;
      });
    }
    return entries;
  }, [filtered, sort]);

  const clearFilters = () => {
    setRiskFilter("all");
    setCategoryFilter("");
    setUnreviewedOnly(false);
  };

  // Loading / error
  if (runQuery.isPending || findingsQuery.isPending) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950 text-slate-500 text-sm">
        Loading run…
      </div>
    );
  }

  if (runQuery.isError || findingsQuery.isError) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950 text-red-400 text-sm">
        Failed to load run.
      </div>
    );
  }

  return (
    <LinkingProvider index={index}>
      <div className="flex flex-col h-full bg-slate-950">
        {run && <RunHeader run={run} />}

        <div className="flex flex-1 min-h-0">
          {/* Script — left */}
          <div className="flex-1 min-w-0 min-h-0 border-r border-slate-800">
            {scenesQuery.data?.scenes ? (
              <div className="h-full max-w-3xl mx-auto px-4 py-2">
                <ScriptPane scenes={scenesQuery.data.scenes} />
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-slate-600 text-sm">
                {scenesQuery.isError ? "Failed to load script." : "Loading script…"}
              </div>
            )}
          </div>

          {/* Findings — right */}
          <div className="w-[440px] shrink-0 flex flex-col min-h-0">
            <FindingsFilterBar
              counts={counts}
              riskFilter={riskFilter}
              onRiskFilter={setRiskFilter}
              categoryFilter={categoryFilter}
              categories={categories}
              onCategoryFilter={setCategoryFilter}
              unreviewedOnly={unreviewedOnly}
              onUnreviewedOnly={setUnreviewedOnly}
              sort={sort}
              onSort={setSort}
              total={total}
            />

            <HiddenSelectionBar visible={filtered} onClear={clearFilters} />

            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
              {sortedGroups.length === 0 ? (
                <p className="text-slate-500 text-sm text-center mt-12">
                  No findings match the current filters.
                </p>
              ) : (
                sortedGroups.map(([canonicalName, findings]) => (
                  <FindingGroup key={canonicalName} findings={findings} />
                ))
              )}
            </div>
          </div>
        </div>

        <DeepLinkSeed ready={!!scenesQuery.data?.scenes && allFindings.length > 0} />
      </div>
    </LinkingProvider>
  );
}
