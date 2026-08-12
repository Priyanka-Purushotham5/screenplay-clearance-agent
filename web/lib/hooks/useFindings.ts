import { useQuery } from "@tanstack/react-query";
import type { Finding } from "@/lib/api-types";

export interface FindingsFilters {
  risk?: "red" | "amber" | "green";
  category?: string;
  review_status?: "unreviewed" | "accepted" | "overridden";
}

export interface FindingsResponse {
  findings: Finding[];
  total: number;
  counts: { red: number; amber: number; green: number };
}

export function useFindings(runId: string, filters?: FindingsFilters) {
  return useQuery({
    queryKey: ["findings", runId, filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.risk) params.set("risk", filters.risk);
      if (filters?.category) params.set("category", filters.category);
      if (filters?.review_status) params.set("review_status", filters.review_status);
      const qs = params.toString();
      const res = await fetch(`/api/runs/${runId}/findings${qs ? `?${qs}` : ""}`);
      if (!res.ok) throw new Error("Failed to fetch findings");
      return res.json() as Promise<FindingsResponse>;
    },
    enabled: !!runId,
  });
}
