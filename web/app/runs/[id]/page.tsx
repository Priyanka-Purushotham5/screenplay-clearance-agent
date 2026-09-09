"use client";

import { use, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRun, isInFlight } from "@/lib/hooks/useRun";
import { useFindings } from "@/lib/hooks/useFindings";
import { useScript } from "@/lib/hooks/useScript";
import RunOverlay from "@/components/shell/RunOverlay";
import { useScenes } from "@/lib/hooks/useScenes";
import type { Finding, Run } from "@/lib/api-types";
import { reportUrl } from "@/lib/api";
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

/**
 * The run's own header. The live counts used to live here and now live in the
 * status bar at the bottom of the shell, so this says WHAT is being reviewed
 * rather than repeating how far along it is.
 */
function RunHeader({ run }: { run: Run }) {
  const { data: script } = useScript(run.script_id);
  return (
    <header className="flex items-center gap-4 px-6 py-3 bg-slate-900 border-b border-slate-800 shrink-0">
      <h1 className="truncate text-sm font-semibold text-slate-100">
        {script?.title ?? "Clearance report"}
      </h1>
      {script && (
        <span className="hidden shrink-0 text-xs text-slate-500 sm:inline">
          {script.page_count} pages · {script.scene_count} scenes
        </span>
      )}
      <span
        className={`ml-auto shrink-0 text-xs font-bold uppercase px-2 py-0.5 rounded ${
          STATUS_COLOUR[run.status] ?? STATUS_COLOUR.pending
        }`}
      >
        {run.status}
      </span>
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
  const run: Run | undefined = runQuery.data;

  // Findings are written all at once, in the compose stage, so they are polled
  // while the run works and not after.
  const inFlight = isInFlight(run?.status);
  const findingsQuery = useFindings(id, undefined, { poll: inFlight });

  // ...but that alone leaves the panel empty forever. The findings appear at
  // the very end, and the poll switches off the moment the run reports
  // `complete` -- which is the moment they became available. The last poll
  // returned nothing and no poll follows it, so the user sees "0 findings" for
  // a run that produced twenty-four, until they think to reload.
  //
  // So the transition INTO a terminal state is the trigger: fetch once more,
  // now that there is something to fetch.
  const queryClient = useQueryClient();
  const wasInFlight = useRef(false);
  useEffect(() => {
    if (wasInFlight.current && !inFlight && run?.status) {
      queryClient.invalidateQueries({ queryKey: ["findings", id] });
    }
    wasInFlight.current = inFlight;
  }, [inFlight, run?.status, id, queryClient]);

  const scenesQuery = useScenes(run?.script_id ?? "");

  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [unreviewedOnly, setUnreviewedOnly] = useState(false);
  const [sort, setSort] = useState<SortMode>("risk");
  // Dismissed by the reader, not by the run. It stays hidden for the rest of
  // this run once they have chosen to read the screenplay instead.
  const [overlayHidden, setOverlayHidden] = useState(false);

  const allFindings: Finding[] = useMemo(
    () => findingsQuery.data?.findings ?? [],
    [findingsQuery.data]
  );
  const counts = findingsQuery.data?.counts ?? { red: 0, amber: 0, green: 0 };
  const total = findingsQuery.data?.total ?? 0;

  // Counted from the loaded list rather than served by the API. `total` is the
  // whole run and the list is capped at 500, so on a run larger than that this
  // would undercount — but the same cap already means the pane is not showing
  // every finding either, and adding a column to `FindingsOut` for a number
  // that is right today is not worth the second place it would have to be
  // maintained. Worth revisiting if a script ever exceeds 500 findings.
  const reviewed = useMemo(
    () => allFindings.filter((f) => f.review_status !== "unreviewed").length,
    [allFindings]
  );

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
      <div className="flex flex-1 items-center justify-center bg-slate-950 text-accent-red text-sm">
        Failed to load run.
      </div>
    );
  }

  return (
    <LinkingProvider index={index}>
      <div className="flex flex-col h-full bg-slate-950">
        {run && <RunHeader run={run} />}

        <div className="relative flex flex-1 min-h-0">
          {run && inFlight && !overlayHidden && (
            <RunOverlay run={run} onHide={() => setOverlayHidden(true)} />
          )}

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
              reviewed={reviewed}
              // Only once the run has stopped. The endpoint refuses anything
              // earlier with a 409, and a half-finished clearance report is
              // indistinguishable from a finished one once it is a PDF on
              // somebody's desk.
              reportHref={inFlight ? null : reportUrl(id)}
            />

            <HiddenSelectionBar visible={filtered} onClear={clearFilters} />

            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
              {sortedGroups.length === 0 ? (
                <p className="text-slate-500 text-sm text-center mt-12">
                  {inFlight
                    ? "Still working \u2014 findings appear when the run finishes."
                    : allFindings.length === 0
                      ? "This run produced no findings."
                      : "No findings match the current filters."}
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
