import { useQuery } from "@tanstack/react-query";
import type { Scene } from "@/lib/api-types";

export interface ScenesResponse {
  scenes: Scene[];
}

/**
 * Fetches through the Next route handler, matching useRun/useFindings.
 *
 * The route handler is a fixture shim; when the real API lands, all three
 * hooks should move onto `apiClient` together and the handlers under
 * app/api/** go away.
 */
export function useScenes(scriptId: string) {
  return useQuery({
    queryKey: ["scenes", scriptId],
    queryFn: async () => {
      const res = await fetch(`/api/scripts/${scriptId}/scenes`);
      if (!res.ok) throw new Error("Failed to fetch scenes");
      return res.json() as Promise<ScenesResponse>;
    },
    enabled: !!scriptId,
  });
}
