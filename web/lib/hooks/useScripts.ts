import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { detail } from "@/lib/hooks/useScript";
import type { ScriptsResponse } from "@/lib/api-types";

/**
 * Every script in the database, newest first — the sidebar's list.
 *
 * There is no owner filter because there is no owner yet. When authentication
 * lands the server grows a `WHERE user_id = ...` and this hook does not
 * change, because it only ever asked "what can I see?".
 */
export function useScripts() {
  return useQuery<ScriptsResponse>({
    queryKey: ["scripts"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/scripts", {});
      if (error || !data) throw new Error(detail(error) ?? "Failed to fetch scripts");
      return data;
    },
    // A newly uploaded script must appear without a reload, and a run finishing
    // changes the dot beside its script. Cheap query, infrequent refetch.
    refetchInterval: 15000,
  });
}
