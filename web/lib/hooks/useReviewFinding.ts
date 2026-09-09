import { useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { detail } from "@/lib/hooks/useScript";
import type { Finding, ReviewStatus, Risk } from "@/lib/api-types";

export interface ReviewInput {
  findingId: string;
  review_status: ReviewStatus;
  override_risk?: Risk | null;
  review_note?: string | null;
}

/**
 * Record a reviewer's verdict on one finding.
 *
 * `review_status` has existed on the table since B1 and nothing has ever
 * written to it, which is why the "Unreviewed only" filter appeared broken:
 * it worked correctly and every finding was unreviewed.
 *
 * The whole findings list is invalidated on success rather than the single
 * row being patched in place. The run-wide counts in the header are computed
 * server-side from the EFFECTIVE risk, so overriding one finding from red to
 * green changes two numbers besides this row's own. Refetching keeps the
 * header and the list from disagreeing; the request is one cheap query.
 */
export function useReviewFinding() {
  const queryClient = useQueryClient();

  return useMutation<Finding, Error, ReviewInput>({
    mutationFn: async (input) => {
      const { data, error } = await apiClient.PATCH("/api/findings/{finding_id}", {
        params: { path: { finding_id: input.findingId } },
        body: {
          review_status: input.review_status,
          override_risk: input.override_risk ?? null,
          review_note: input.review_note ?? null,
        },
      });
      if (error || !data) throw new Error(detail(error) ?? "Could not save the review");
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["findings"] });
    },
  });
}
