// STUB — run `npm run gen:types` once the API is live to replace this file

// ---------------------------------------------------------------------------
// Shared domain shapes (from technical-spec.md §5)
// ---------------------------------------------------------------------------

export interface Script {
  script_id: string;
  title: string;
  source_format: "pdf" | "fdx" | "fountain";
  page_count: number;
  scene_count: number;
  parse_warnings: string[];
  /** Non-null when this upload matched an existing script by SHA-256. */
  duplicate_of: string | null;
}

export interface Scene {
  id: string;
  script_id: string;
  number: number;
  int_ext: "INT" | "EXT" | "INT/EXT" | null;
  location: string | null;
  time_of_day: string | null;
  heading: string;
  page_start: number;
  page_end: number;
  elements: ScriptElement[];
}

export interface ScriptElement {
  id: string;
  scene_id: string;
  seq: number;
  type:
    | "scene_heading"
    | "action"
    | "character"
    | "dialogue"
    | "parenthetical"
    | "transition";
  character: string | null;
  page: number;
  text: string;
}

export interface Run {
  run_id: string;
  script_id: string;
  status:
    | "pending"
    | "extracting"
    | "researching"
    | "assessing"
    | "composing"
    | "complete"
    | "failed";
  progress: {
    elements_found: number;
    researched: number;
    assessed: number;
  };
  stats: {
    cache_hits?: number;
    tokens_in?: number;
    tokens_out?: number;
  };
  started_at: string;
  finished_at: string | null;
  error: string | null;
}

export interface Finding {
  id: string;
  element_id: string;
  risk: "red" | "amber" | "green";
  rights_required: string[];
  rights_holders: RightsHolder[];
  rationale: string;
  sources: Source[];
  alternatives: string[];
  review_status: "unreviewed" | "accepted" | "overridden";
  override_risk: "red" | "amber" | "green" | null;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
  // Enriched fields — denormalised from the elements table for display
  canonical_name: string;
  surface_form: string;
  category: "music" | "trademark" | "artwork" | "person" | "location" | "clip" | "literary" | "other";
  scene_number: number;
  research_status: "complete" | "partial" | "failed";
}

export interface RightsHolder {
  role: string;
  name: string;
  confidence: "high" | "medium" | "low";
}

export interface Source {
  id: string;
  claim: string;
  url: string;
  title: string;
  excerpt: string;
}

export interface ApiError {
  detail: string;
}

export interface NoTextLayerError {
  code: "NO_TEXT_LAYER";
  pages_checked: number;
}

// ---------------------------------------------------------------------------
// paths — openapi-typescript convention
// ---------------------------------------------------------------------------

export interface paths {
  // -----------------------------------------------------------------------
  // Scripts
  // -----------------------------------------------------------------------

  "/api/scripts": {
    post: {
      requestBody: {
        content: {
          "multipart/form-data": {
            /** The screenplay PDF file (≤ 25 MB). */
            file: Blob;
          };
        };
      };
      responses: {
        /** Created — parsed successfully. */
        201: {
          content: {
            "application/json": Script;
          };
        };
        /** Payload Too Large — file exceeds the 25 MB cap. */
        413: {
          content: {
            "application/json": ApiError;
          };
        };
        /** Unsupported Media Type — not a valid PDF. */
        415: {
          content: {
            "application/json": ApiError;
          };
        };
        /** Unprocessable Entity — scanned / no text layer, or unparseable. */
        422: {
          content: {
            "application/json": NoTextLayerError | ApiError;
          };
        };
      };
    };
  };

  "/api/scripts/{id}": {
    get: {
      parameters: {
        path: { id: string };
      };
      responses: {
        200: {
          content: {
            "application/json": Script;
          };
        };
        404: {
          content: {
            "application/json": ApiError;
          };
        };
      };
    };
  };

  "/api/scripts/{id}/scenes": {
    get: {
      parameters: {
        path: { id: string };
        query?: {
          /** First scene number to include (inclusive). */
          from?: number;
          /** Last scene number to include (inclusive). */
          to?: number;
        };
      };
      responses: {
        200: {
          content: {
            "application/json": {
              scenes: Scene[];
            };
          };
        };
        404: {
          content: {
            "application/json": ApiError;
          };
        };
      };
    };
  };

  // -----------------------------------------------------------------------
  // Runs
  // -----------------------------------------------------------------------

  "/api/runs": {
    post: {
      requestBody: {
        content: {
          "application/json": {
            script_id: string;
          };
        };
      };
      responses: {
        /** Accepted — background task started. */
        202: {
          content: {
            "application/json": {
              run_id: string;
              status: "pending";
            };
          };
        };
        /** Unknown script. */
        404: {
          content: {
            "application/json": ApiError;
          };
        };
        /** A run is already in flight for this script. */
        409: {
          content: {
            "application/json": ApiError;
          };
        };
      };
    };
  };

  "/api/runs/{id}": {
    get: {
      parameters: {
        path: { id: string };
      };
      responses: {
        200: {
          content: {
            "application/json": Run;
          };
        };
        404: {
          content: {
            "application/json": ApiError;
          };
        };
      };
    };
  };

  "/api/runs/{id}/findings": {
    get: {
      parameters: {
        path: { id: string };
        query?: {
          risk?: "red" | "amber" | "green";
          category?: string;
          review_status?: "unreviewed" | "accepted" | "overridden";
          /** Filter to a specific scene number. */
          scene?: number;
          limit?: number;
          offset?: number;
        };
      };
      responses: {
        200: {
          content: {
            "application/json": {
              findings: Finding[];
              total: number;
              counts: {
                red: number;
                amber: number;
                green: number;
              };
            };
          };
        };
        404: {
          content: {
            "application/json": ApiError;
          };
        };
      };
    };
  };

  // -----------------------------------------------------------------------
  // Findings
  // -----------------------------------------------------------------------

  "/api/findings/{id}": {
    get: {
      parameters: {
        path: { id: string };
      };
      responses: {
        200: {
          content: {
            "application/json": Finding;
          };
        };
        404: {
          content: {
            "application/json": ApiError;
          };
        };
      };
    };

    patch: {
      parameters: {
        path: { id: string };
      };
      requestBody: {
        content: {
          "application/json": {
            review_status: "unreviewed" | "accepted" | "overridden";
            override_risk?: "red" | "amber" | "green";
            review_note?: string;
          };
        };
      };
      responses: {
        200: {
          content: {
            "application/json": Finding;
          };
        };
        404: {
          content: {
            "application/json": ApiError;
          };
        };
      };
    };
  };
}
