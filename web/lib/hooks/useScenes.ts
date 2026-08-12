import { useQuery } from "@tanstack/react-query";
import apiClient from "../api";

export function useScenes(scriptId: string) {
  return useQuery({
    queryKey: ["scenes", scriptId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/scripts/{id}/scenes",
        { params: { path: { id: scriptId } } }
      );
      if (error) throw new Error("Failed to fetch scenes");
      return data;
    },
    enabled: !!scriptId,
  });
}
