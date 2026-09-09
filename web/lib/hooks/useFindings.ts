import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { detail } from "@/lib/hooks/useScript";
import type { Finding, FindingsResponse, Risk, ReviewStatus } from "@/lib/api-types";

export type { FindingsResponse };

export interface FindingsFilters {
  risk?: Risk;
  review_status?: ReviewStatus;
}

/**
 * Every finding for a run, with the run-wide counts.
 *
 * `category` is deliberately not sent. The API filters on risk and review
 * status; category filtering happens in the page, over the full list, because
 * the category dropdown is built from the categories actually present and
 * would otherwise have to round-trip to discover them.
 *
 * `poll` exists because findings appear all at once, at the end of the run —
 * C8 writes them in the compose stage. Polling them forever after that is
 * waste, and not polling at all means a finished run shows an empty panel
 * until the user reloads. The page passes the run's own in-flight state.
 */
export function useFindings(
  runId: string,
  filters?: FindingsFilters,
  options?: { poll?: boolean },
) {
  return useQuery<FindingsResponse>({
    queryKey: ["findings", runId, filters],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/runs/{run_id}/findings", {
        params: {
          path: { run_id: runId },
          query: {
            ...(filters?.risk ? { risk: filters.risk } : {}),
            ...(filters?.review_status ? { review_status: filters.review_status } : {}),
          },
        },
      });
      if (error || !data) throw new Error(detail(error) ?? "Failed to fetch findings");
      return data;
    },
    enabled: !!runId,
    refetchInterval: options?.poll ? 2500 : false,
  });
}

export type { Finding };
