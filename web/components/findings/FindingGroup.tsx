"use client";

import { useState } from "react";
import type { Finding } from "@/lib/api-types";
import FindingCard from "./FindingCard";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RISK_ORDER = ["failed", "red", "amber", "green"] as const;

function highestRisk(findings: Finding[]): string {
  for (const r of RISK_ORDER) {
    if (r === "failed") {
      if (findings.some((f) => f.research_status === "failed")) return "failed";
    } else {
      if (findings.some((f) => (f.override_risk ?? f.risk) === r)) return r;
    }
  }
  return "green";
}

function isSplit(findings: Finding[]): boolean {
  const risks = new Set(
    findings
      .filter((f) => f.research_status !== "failed")
      .map((f) => f.override_risk ?? f.risk)
  );
  return risks.size > 1;
}

const HIGHEST_RISK_CHIP: Record<string, string> = {
  failed: "bg-red-900 text-red-300 border border-red-700",
  red: "bg-red-900/60 text-red-300",
  amber: "bg-amber-900/60 text-amber-300",
  green: "bg-emerald-900/60 text-emerald-300",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  findings: Finding[];
  onFindingClick?: (finding: Finding) => void;
}

export default function FindingGroup({ findings, onFindingClick }: Props) {
  const split = isSplit(findings);
  const topRisk = highestRisk(findings);
  const [expanded, setExpanded] = useState(split); // split groups start open

  const canonicalName = findings[0].canonical_name;
  const displayName = findings[0].surface_form;

  return (
    <div className="mb-2">
      {/* Group header */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-3 px-4 py-2.5 bg-slate-800 hover:bg-slate-750 rounded-lg text-left transition-colors group"
      >
        {/* Chevron */}
        <svg
          className={`w-3.5 h-3.5 text-slate-500 shrink-0 transition-transform ${expanded ? "rotate-90" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>

        {/* Name */}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-semibold text-slate-100 truncate">{displayName}</span>
          <span className="ml-2 text-xs text-slate-500 truncate">{canonicalName}</span>
        </div>

        {/* Split badge */}
        {split && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300 border border-slate-600 shrink-0">
            split rating
          </span>
        )}

        {/* Mention count */}
        <span className="text-xs text-slate-500 shrink-0">
          {findings.length} {findings.length === 1 ? "mention" : "mentions"}
        </span>

        {/* Risk chip */}
        <span className={`text-xs font-bold uppercase px-2 py-0.5 rounded shrink-0 ${HIGHEST_RISK_CHIP[topRisk]}`}>
          {topRisk === "failed" ? "review" : topRisk}
        </span>
      </button>

      {/* Expanded findings */}
      {expanded && (
        <div className="mt-1 ml-4 flex flex-col gap-1.5">
          {findings.map((f) => (
            <FindingCard
              key={f.id}
              finding={f}
              onClick={onFindingClick ? () => onFindingClick(f) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
