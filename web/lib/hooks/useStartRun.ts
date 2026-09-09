import { useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { detail } from "@/lib/hooks/useScript";
import type { Run } from "@/lib/api-types";

/**
 * Start a clearance run over a script.
 *
 * This is the link the frontend never had. Upload posted to /api/scripts and
 * routed to the script page, and there the trail ended: POST /api/runs existed,
 * was tested, and was not reachable from any button in the product.
 *
 * A 409 is not an error to show as one. It means a run for this script is
 * already in flight, and the response carries its id — so the right response is
 * to go and watch that run, which is what the user wanted anyway.
 */
export interface StartRunResult {
  run_id: string;
  already_running: boolean;
}

export function useStartRun() {
  const queryClient = useQueryClient();

  return useMutation<StartRunResult, Error, string>({
    mutationFn: async (scriptId: string) => {
      const { data, error, response } = await apiClient.POST("/api/runs", {
        body: { script_id: scriptId },
      });

      if (response.status === 409) {
        const existing = (error as { run_id?: string } | undefined)?.run_id;
        if (existing) return { run_id: existing, already_running: true };
      }
      if (error || !data) {
        throw new Error(detail(error) ?? "Could not start the clearance run");
      }
      return { run_id: (data as Run).run_id, already_running: false };
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["run", result.run_id] });
    },
  });
}
