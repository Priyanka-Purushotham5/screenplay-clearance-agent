import { useQuery } from "@tanstack/react-query";
import type { Script } from "@/lib/api-types";

/** Fetches through the Next route handler — see the note in useScenes. */
export function useScript(scriptId: string) {
  return useQuery({
    queryKey: ["script", scriptId],
    queryFn: async () => {
      const res = await fetch(`/api/scripts/${scriptId}`);
      if (!res.ok) throw new Error("Failed to fetch script");
      return res.json() as Promise<Script>;
    },
    enabled: !!scriptId,
  });
}
