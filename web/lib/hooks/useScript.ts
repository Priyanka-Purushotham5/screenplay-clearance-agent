import { useQuery } from "@tanstack/react-query";
import apiClient from "../api";

export function useScript(scriptId: string) {
  return useQuery({
    queryKey: ["script", scriptId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/scripts/{id}", {
        params: { path: { id: scriptId } },
      });
      if (error) throw new Error("Failed to fetch script");
      return data;
    },
    enabled: !!scriptId,
  });
}
