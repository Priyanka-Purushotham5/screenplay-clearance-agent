"use client";

import { useEffect, useRef, useState } from "react";
import type { Finding } from "@/lib/api-types";
import { useSelection } from "@/components/linking/LinkingProvider";
import { RISK_RING, type Risk } from "@/lib/risk";
import { useReviewFinding } from "@/lib/hooks/useReviewFinding";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * The rating, as a wash bleeding in from the card's left edge.
 *
 * This replaces two things at once: a 4px rule down the side and a flat tint
 * across the whole card. Both were saying the same thing twice, and the flat
 * tint was what made the rule necessary — an even wash gives the eye no edge
 * to follow, so the column needed a hard line to scan.
 *
 * A single class per rating, setting `--risk`; the gradient itself lives in
 * globals.css as .clearance-bleed. See the note there for why it is densest at
 * the edge and gone by 62%.
 */
const RISK_BLEED: Record<string, string> = {
  red: "clearance-bleed risk-red",
  amber: "clearance-bleed risk-amber",
  green: "clearance-bleed risk-green",
};

const RISK_LABEL: Record<string, string> = {
  red: "text-accent-red",
  amber: "text-accent-amber",
  green: "text-accent-green",
};

const CATEGORY_BADGE: Record<string, string> = {
  music: "bg-violet-900 text-violet-200",
  trademark: "bg-blue-900 text-blue-200",
  artwork: "bg-orange-900 text-orange-200",
  person: "bg-pink-900 text-pink-200",
  location: "bg-teal-900 text-teal-200",
  clip: "bg-yellow-900 text-yellow-200",
  literary: "bg-lime-900 text-lime-200",
  other: "bg-slate-700 text-slate-200",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  finding: Finding;
  /** Optional extra behaviour on click — selection happens regardless. */
  onClick?: () => void;
}

export default function FindingCard({ finding, onClick }: Props) {
  const effectiveRisk = finding.override_risk ?? finding.risk;
  const isAccepted = finding.review_status === "accepted";
  const isFailed = finding.research_status === "failed";
  const isOverridden = finding.review_status === "overridden";

  // Details are closed by default. The list is for scanning — twenty findings
  // each showing their rights holders and sources is not a list, it is a
  // document. The reviewer opens the one they are deciding about.
  const [open, setOpen] = useState(false);
  const review = useReviewFinding();

  const ref = useRef<HTMLDivElement>(null);
  const { selection, select } = useSelection();
  const isSelected = selection.findingId === finding.id;
  const seenToken = useRef(0);

  const handleClick = () => {
    select(finding.id, "findings");
    onClick?.();
  };

  // The card scrolls itself rather than the parent hunting for it: a collapsed
  // group means this component does not exist yet, so its own mount effect is
  // the only thing guaranteed to run *after* the group expands.
  useEffect(() => {
    if (!isSelected) return;
    // The user clicked this very card — don't move it under their cursor.
    if (selection.source === "findings") return;
    if (selection.token === seenToken.current) return;
    seenToken.current = selection.token;
    ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [isSelected, selection.token, selection.source]);

  return (
    <div
      ref={ref}
      data-finding-id={finding.id}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      onKeyDown={(e) => e.key === "Enter" && handleClick()}
      className={[
        // bg-slate-900 under the bleed, because a gradient that fades to
        // `transparent` fades to whatever is behind it, and the findings pane
        // scrolls over more than one background.
        "rounded-lg overflow-hidden cursor-pointer bg-slate-900 transition-opacity hover:brightness-110",
        RISK_BLEED[effectiveRisk],
        isAccepted ? "opacity-50" : "opacity-100",
        isSelected ? RISK_RING[effectiveRisk as Risk] : "",
      ].join(" ")}
    >
      {/* Failed research banner */}
      {isFailed && (
        <div className="bg-red-900 text-red-200 text-xs font-semibold px-3 py-1 flex items-center gap-1">
          <span>⚠</span>
          <span>Research incomplete. Needs manual review</span>
        </div>
      )}

      {/* Partial research notice */}
      {finding.research_status === "partial" && (
        <div className="bg-amber-900/60 text-amber-200 text-xs px-3 py-1">
          Partial research. Verify before proceeding
        </div>
      )}

      <div className="px-4 py-3">
        {/* Title row */}
        <div className="flex items-start justify-between gap-3 mb-1">
          <div>
            <span className={[
              "text-sm font-semibold",
              isAccepted ? "line-through text-slate-400" : "text-slate-100",
            ].join(" ")}>
              {finding.surface_form}
            </span>
            <span className="ml-2 text-xs text-slate-500">{finding.canonical_name}</span>
          </div>
          <span className={`text-xs font-bold uppercase shrink-0 ${RISK_LABEL[effectiveRisk]}`}>
            {isOverridden ? `↩ ${effectiveRisk}` : effectiveRisk}
          </span>
        </div>

        {/* Rationale — clamped until the card is opened */}
        <p className={`text-xs text-slate-400 mb-2 ${open ? "" : "line-clamp-2"}`}>
          {finding.rationale}
        </p>

        {/* Footer row */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${CATEGORY_BADGE[finding.category]}`}>
            {finding.category}
          </span>
          {finding.sources.length > 0 && (
            <span className="text-xs text-slate-500">
              {finding.sources.length} {finding.sources.length === 1 ? "source" : "sources"}
            </span>
          )}
          <button
            // stopPropagation, or opening the details would also select the
            // finding and scroll the screenplay out from under the reader.
            onClick={(e) => {
              e.stopPropagation();
              setOpen((v) => !v);
            }}
            aria-expanded={open}
            className="text-xs text-slate-500 underline underline-offset-2
                       transition-colors hover:text-slate-300"
          >
            {open ? "details ↑" : "details ↓"}
          </button>
          <span className="text-xs text-slate-600 ml-auto">sc {finding.scene_number}</span>
        </div>

        {open && (
          <div className="mt-3 flex flex-col gap-2.5 border-t border-slate-700 pt-3">
            {finding.rights_required.length > 0 && (
              <Detail label="Rights required">
                {finding.rights_required.join(" · ")}
              </Detail>
            )}

            {finding.alternatives.length > 0 && (
              <Detail label="Alternatives">
                {finding.alternatives.join(" · ")}
              </Detail>
            )}

            {finding.rights_holders.length > 0 && (
              <Detail label="Rights holders">
                {finding.rights_holders
                  .map((h) => (h.role ? `${h.name} (${h.role})` : h.name))
                  .join(" · ")}
              </Detail>
            )}

            <ReviewActions
              finding={finding}
              pending={review.isPending}
              onReview={(status, override) =>
                review.mutate({
                  findingId: finding.id,
                  review_status: status,
                  override_risk: override ?? null,
                })
              }
            />

            {review.isError && (
              <p className="text-xs text-accent-red">{review.error.message}</p>
            )}

            {finding.sources.length > 0 && (
              <Detail label="Sources">
                <span className="flex flex-wrap gap-1.5">
                  {finding.sources.map((source) => (
                    <a
                      key={source.id}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      onClick={(e) => e.stopPropagation()}
                      title={source.claim}
                      className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5
                                 text-[10px] text-slate-300 transition-colors
                                 hover:border-slate-600 hover:text-slate-100"
                    >
                      {source.title || "source"}
                    </a>
                  ))}
                </span>
              </Detail>
            )}

            {/*
              The research trail, last in the panel on purpose. Sources are
              what the agent found, and they belong next to the rating. The
              queries are what it went looking for, which is a question a
              reviewer only asks once a rating has surprised them — usually a
              GREEN they expected to be RED. Reading them turns "it found
              nothing" into "it searched for these five things and none of
              them exist", which is a claim you can actually argue with.
            */}
            {finding.queries_run.length > 0 && (
              <Detail label={`Searches run (${finding.queries_run.length})`}>
                <span className="flex flex-col gap-0.5 font-mono text-[10px]
                                 leading-relaxed text-slate-500">
                  {finding.queries_run.map((query, i) => (
                    // Indexed key: the agent can legitimately repeat a query
                    // across refinement passes, so the string alone is not
                    // unique and React would warn on the duplicate.
                    <span key={`${i}-${query}`}>{query}</span>
                  ))}
                </span>
              </Detail>
            )}
          </div>
        )}

        {/* Override note */}
        {isOverridden && finding.review_note && (
          <p className="mt-2 text-xs text-slate-400 italic border-t border-slate-700 pt-2">
            Note: {finding.review_note}
          </p>
        )}
      </div>
    </div>
  );
}

/** One labelled row inside the expanded card. */
function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-0.5 text-[9.5px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <div className="text-xs text-slate-300">{children}</div>
    </div>
  );
}

const OVERRIDE_BUTTON: Record<Risk, string> = {
  red: "border-red-700 text-red-300 hover:bg-red-950",
  amber: "border-amber-700 text-amber-300 hover:bg-amber-950",
  green: "border-emerald-700 text-emerald-300 hover:bg-emerald-950",
};

/**
 * Accept the rating, override it, or undo.
 *
 * Inside the expanded card rather than on every row: a reviewer should have
 * read the rationale and the sources before deciding, and putting an Accept
 * button on a collapsed two-line summary invites agreeing with something
 * nobody read. Opening the card is the cost of having an opinion about it.
 */
function ReviewActions({
  finding,
  pending,
  onReview,
}: {
  finding: Finding;
  pending: boolean;
  onReview: (status: "accepted" | "overridden" | "unreviewed", override?: Risk) => void;
}) {
  const stop = (fn: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    fn();
  };
  const reviewed = finding.review_status !== "unreviewed";

  return (
    <div>
      <p className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-slate-500">
        {reviewed
          ? finding.review_status === "accepted"
            ? "Accepted"
            : `Overridden to ${finding.override_risk}`
          : "Your call"}
      </p>

      <div className="flex flex-wrap items-center gap-1.5">
        {reviewed ? (
          <button
            disabled={pending}
            onClick={stop(() => onReview("unreviewed"))}
            className="rounded border border-slate-700 px-2 py-0.5 text-[11px]
                       text-slate-300 transition-colors hover:bg-slate-800
                       disabled:opacity-50"
          >
            Undo
          </button>
        ) : (
          <>
            <button
              disabled={pending}
              onClick={stop(() => onReview("accepted"))}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-0.5
                         text-[11px] font-medium text-slate-100 transition-colors
                         hover:bg-slate-700 disabled:opacity-50"
            >
              Accept
            </button>
            <span className="text-[10px] text-slate-500">or override to</span>
            {(["red", "amber", "green"] as Risk[])
              .filter((r) => r !== (finding.override_risk ?? finding.risk))
              .map((r) => (
                <button
                  key={r}
                  disabled={pending}
                  onClick={stop(() => onReview("overridden", r))}
                  className={`rounded border px-2 py-0.5 text-[11px] font-medium
                              transition-colors disabled:opacity-50 ${OVERRIDE_BUTTON[r]}`}
                >
                  {r}
                </button>
              ))}
          </>
        )}
      </div>
    </div>
  );
}
