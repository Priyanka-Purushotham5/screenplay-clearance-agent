import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { detail } from "@/lib/hooks/useScript";
import type { Run, RunStatus } from "@/lib/api-types";

/** The stages a run passes through before it settles. */
const IN_FLIGHT: RunStatus[] = [
  "pending", "extracting", "researching", "assessing", "composing",
];

export function isInFlight(status: RunStatus | undefined): boolean {
  return !!status && IN_FLIGHT.includes(status);
}

/** What each stage is doing, in words a producer would use. */
export const STAGE_LABEL: Record<string, string> = {
  pending: "Queued",
  extracting: "Reading the screenplay",
  researching: "Researching rights holders",
  assessing: "Assessing each mention",
  composing: "Writing up findings",
  complete: "Analysis complete",
  failed: "The run did not complete",
};

/**
 * How far along a run is, 0–100.
 *
 * Weighted by where the time actually goes rather than by counting stages
 * equally: research is most of the wall clock, and it is the one stage with
 * real sub-progress, because `dossiers_complete` climbs entity by entity as
 * each dossier lands.
 *
 * Assessment has no sub-progress to report — findings are written all at once
 * in the compose stage, so there is nothing to count while it works. Rather
 * than creep the number on a timer, which would be inventing progress, it
 * holds at 78 and the stage label carries the meaning. A bar that lies about
 * being nearly finished is worse than one that admits it cannot tell.
 */
export function runPercent(run: Run | undefined): number {
  if (!run) return 0;
  const p = run.progress;
  switch (run.status) {
    case "pending":
      return 2;
    case "extracting":
      return 8;
    case "researching": {
      const share = p.entities > 0 ? p.dossiers_complete / p.entities : 0;
      return 15 + Math.round(Math.min(1, share) * 55);
    }
    case "assessing":
      return 78;
    case "composing":
      return 94;
    default:
      return 100;
  }
}

/**
 * One run, polled while it is still working.
 *
 * Polling stops the moment the run reaches `complete` or `failed`, which is
 * why `refetchInterval` is a function rather than a number: a fixed interval
 * would keep asking forever about a run that finished ten minutes ago.
 *
 * C9 replaces this with a Server-Sent Events stream. Until then a run that
 * takes two minutes still shows its stages moving, which is most of the value.
 */
export function useRun(runId: string) {
  return useQuery<Run>({
    queryKey: ["run", runId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/runs/{run_id}", {
        params: { path: { run_id: runId } },
      });
      if (error || !data) throw new Error(detail(error) ?? "Failed to fetch run");
      return data;
    },
    enabled: !!runId,
    refetchInterval: (query) =>
      isInFlight(query.state.data?.status) ? 2500 : false,
  });
}
