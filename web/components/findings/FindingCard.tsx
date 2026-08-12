import type { Finding } from "@/lib/api-types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RISK_STRIPE: Record<string, string> = {
  red: "border-l-4 border-red-500",
  amber: "border-l-4 border-amber-400",
  green: "border-l-4 border-emerald-500",
};

const RISK_TINT: Record<string, string> = {
  red: "bg-red-950/40",
  amber: "bg-amber-950/25",
  green: "bg-emerald-950/25",
};

const RISK_LABEL: Record<string, string> = {
  red: "text-red-400",
  amber: "text-amber-400",
  green: "text-emerald-400",
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
  onClick?: () => void;
}

export default function FindingCard({ finding, onClick }: Props) {
  const effectiveRisk = finding.override_risk ?? finding.risk;
  const isAccepted = finding.review_status === "accepted";
  const isFailed = finding.research_status === "failed";
  const isOverridden = finding.review_status === "overridden";

  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === "Enter" && onClick() : undefined}
      className={[
        "rounded-lg overflow-hidden cursor-pointer transition-opacity",
        RISK_STRIPE[effectiveRisk],
        RISK_TINT[effectiveRisk],
        isAccepted ? "opacity-50" : "opacity-100",
        onClick ? "hover:brightness-110" : "",
      ].join(" ")}
    >
      {/* Failed research banner */}
      {isFailed && (
        <div className="bg-red-900 text-red-200 text-xs font-semibold px-3 py-1 flex items-center gap-1">
          <span>⚠</span>
          <span>Research incomplete — needs manual review</span>
        </div>
      )}

      {/* Partial research notice */}
      {finding.research_status === "partial" && (
        <div className="bg-amber-900/60 text-amber-200 text-xs px-3 py-1">
          Partial research — verify before proceeding
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

        {/* Rationale — 2-line clamp */}
        <p className="text-xs text-slate-400 line-clamp-2 mb-2">
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
          <span className="text-xs text-slate-600 ml-auto">sc {finding.scene_number}</span>
        </div>

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
