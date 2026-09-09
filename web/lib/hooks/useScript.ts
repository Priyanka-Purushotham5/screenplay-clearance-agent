import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import type { Script } from "@/lib/api-types";

/**
 * One script's metadata, from the real API.
 *
 * Every hook here goes through `apiClient` — the generated openapi-fetch
 * client — rather than `fetch("/api/...")`. The relative path used to reach a
 * Next route handler under app/api/**, which read a JSON fixture. Those
 * handlers are gone; a relative path now reaches nothing.
 *
 * The win beyond "it returns real data" is that the request is type-checked
 * against the server's own schema: a wrong path, a missing path parameter or a
 * query key the API does not accept is a compile error rather than a 404 at
 * two in the morning.
 */
export function useScript(scriptId: string) {
  return useQuery<Script>({
    queryKey: ["script", scriptId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/scripts/{id}", {
        params: { path: { id: scriptId } },
      });
      if (error || !data) throw new Error(detail(error) ?? "Failed to fetch script");
      return data;
    },
    enabled: !!scriptId,
  });
}

/** The API's error envelope carries `detail`; anything else is unknown. */
export function detail(error: unknown): string | undefined {
  if (error && typeof error === "object" && "detail" in error) {
    const value = (error as { detail?: unknown }).detail;
    if (typeof value === "string") return value;
  }
  return undefined;
}
