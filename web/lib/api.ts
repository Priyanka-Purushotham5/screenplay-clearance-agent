import createClient from "openapi-fetch";
import type { paths } from "./api-types";

/**
 * Where the browser reaches the API.
 *
 * This resolves in the BROWSER, not in the container, so it cannot be
 * `http://api:8080` — that hostname only exists on the compose network.
 * `npm run gen:types` talks to `api:8080` for exactly the opposite reason.
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

const apiClient = createClient<paths>({ baseUrl: API_BASE });

/**
 * The clearance report for a run, as a URL rather than a fetch.
 *
 * Deliberately not routed through `apiClient`: the response is a PDF, and
 * pulling it into JavaScript to hand back to the browser would mean holding
 * a multi-megabyte blob in memory, minting an object URL and revoking it
 * later — all to reproduce what an anchor already does natively, minus the
 * browser's own progress indicator and PDF viewer.
 */
export function reportUrl(runId: string): string {
  return `${API_BASE}/api/runs/${runId}/report?format=pdf`;
}

export default apiClient;
