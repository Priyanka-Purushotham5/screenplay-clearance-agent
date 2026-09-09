import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { detail } from "@/lib/hooks/useScript";
import type { ScenesResponse } from "@/lib/api-types";

export type { ScenesResponse };

/** Every scene of a script, with its elements. */
export function useScenes(scriptId: string) {
  return useQuery<ScenesResponse>({
    queryKey: ["scenes", scriptId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/scripts/{id}/scenes", {
        params: { path: { id: scriptId } },
      });
      if (error || !data) throw new Error(detail(error) ?? "Failed to fetch scenes");
      return data;
    },
    enabled: !!scriptId,
    // A parsed script does not change. Refetching it while polling a run would
    // re-download the whole screenplay every few seconds for nothing.
    staleTime: Infinity,
  });
}
