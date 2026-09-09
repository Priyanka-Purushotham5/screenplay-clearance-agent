"use client";

import { useRun, isInFlight } from "@/lib/hooks/useRun";

/** The stages a run walks through, in order, with what each is doing. */
const STAGES = [
  { key: "extracting", label: "Reading the screenplay" },
  { key: "researching", label: "Researching rights holders" },
  { key: "assessing", label: "Assessing each mention" },
  { key: "composing", label: "Writing up findings" },
] as const;

/**
 * The bottom strip on a run page.
 *
 * It replaces a footer rather than joining one, because a fixed forty pixels
 * of copyright notice at the bottom of a review screen is forty pixels not
 * spent on the screenplay. This says what the run is doing instead.
 *
 * The words matter as much as the motion: the spinning reels in the logo are
 * disabled for anyone whose system asks for reduced motion, so the state has
 * to be legible without them.
 */
export default function RunStatusBar({ runId }: { runId: string }) {
  const { data: run } = useRun(runId);
  if (!run) return null;

  const working = isInFlight(run.status);
  const index = STAGES.findIndex((s) => s.key === run.status);
  const p = run.progress;

  return (
    <footer
      className="flex shrink-0 items-center gap-3 border-t border-slate-800
                 bg-slate-900 px-4 py-2 text-xs text-slate-400"
      aria-live="polite"
    >
      {working ? (
        <>
          <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-amber-400" />
          <span className="text-slate-200">
            {index >= 0 ? STAGES[index].label : "Starting"}
          </span>
          <span className="hidden items-center gap-1.5 sm:flex">
            {STAGES.map((stage, i) => (
              <span
                key={stage.key}
                title={stage.label}
                className={[
                  "h-1 w-8 rounded-full",
                  i < index ? "bg-emerald-500" : i === index ? "bg-amber-400" : "bg-slate-700",
                ].join(" ")}
              />
            ))}
          </span>
        </>
      ) : run.status === "failed" ? (
        <>
          <span className="h-2 w-2 shrink-0 rounded-full bg-red-500" />
          <span className="truncate text-accent-red">
            {run.error ?? "The run did not complete."}
          </span>
        </>
      ) : (
        <>
          <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
          <span className="text-slate-200">Analysis complete</span>
        </>
      )}

      <span className="ml-auto flex shrink-0 items-center gap-3 tabular-nums">
        <span>{p.elements_found} mentions</span>
        <span aria-hidden>·</span>
        <span>
          {p.dossiers_complete}/{p.entities} researched
        </span>
        <span aria-hidden>·</span>
        <span>{p.findings} findings</span>
      </span>
    </footer>
  );
}
