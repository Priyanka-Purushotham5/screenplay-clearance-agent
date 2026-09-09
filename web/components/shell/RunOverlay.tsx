"use client";

import { runPercent, STAGE_LABEL } from "@/lib/hooks/useRun";
import RunMark from "@/components/brand/RunMark";
import type { Run } from "@/lib/api-types";

const STAGES = ["extracting", "researching", "assessing", "composing"] as const;

const DETAIL: Record<string, string> = {
  extracting: "Finding every real-world reference in the screenplay",
  researching: "Establishing who owns what, with sources",
  assessing: "Deciding each mention on its context",
  composing: "Collecting the findings",
};

/**
 * Covers the review area from the moment a run starts until its findings land.
 *
 * Two kinds of motion here, and the distinction is the point. The ARC is
 * determinate: it moves only when real work completes, so it can be trusted.
 * The orbiting ring behind it is decorative and constant, so the screen never
 * looks frozen during the stages that have no sub-progress to report. Using
 * the arc for both — creeping it on a timer — would make the one trustworthy
 * number untrustworthy.
 */
export default function RunOverlay({
  run,
  onHide,
}: {
  run: Run;
  onHide?: () => void;
}) {
  const percent = runPercent(run);
  const p = run.progress;
  const index = STAGES.indexOf(run.status as (typeof STAGES)[number]);

  return (
    <div
      // `overflow-y-auto` is the safety net, not the layout. The content is
      // laid out to fit; this only guarantees that on a window shorter than
      // anything anticipated, the stage list stays reachable instead of being
      // silently clipped the way it was.
      className="absolute inset-0 z-20 flex items-center justify-center overflow-y-auto
                 bg-slate-950/92 px-6 py-4 backdrop-blur-[3px]"
      role="status"
      aria-live="polite"
      aria-label={`${STAGE_LABEL[run.status] ?? "Working"}, ${percent}% complete`}
    >
      {/*
        Two columns from `md` (768px) up, one below it.

        Stacked, this asked for about 650px of height and a 13-inch laptop
        offers roughly 580 once the header and status bar are taken out, so
        the last stage and the hide link were being cut off. Shrinking the
        ring far enough to fix that would have taken it back under 160px,
        where the camera inside loses its detail.

        The height was never the scarce dimension. The overlay is over a
        thousand pixels wide and every element was in one narrow centred
        column; side by side the tallest thing is the ring at ~300px, which
        fits with room to spare.

        The breakpoint is 768px rather than 1024 because at 900px wide the
        single column still overflowed, and two columns need only 224 + 32 +
        448 = 704px of the 720 a 768px window leaves after padding.
      */}
      <div className="flex w-full max-w-3xl flex-col items-center gap-6
                      md:flex-row md:items-center md:gap-8">
        <Ring percent={percent} />

        <div className="flex w-full flex-col gap-3 md:max-w-md">
          <div className="text-center md:text-left">
            <p className="text-base font-semibold text-slate-100">
              {STAGE_LABEL[run.status] ?? "Working"}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {DETAIL[run.status] ?? "Starting the clearance run"}
            </p>
          </div>

          <ol className="flex w-full flex-col gap-2">
            {STAGES.map((stage, i) => {
              const done = i < index;
              const active = i === index;
              return (
                <li
                  key={stage}
                  className={[
                    "flex items-center gap-3 rounded-lg border px-3 py-2 text-xs transition-colors",
                    active
                      ? "border-emerald-500/45 bg-emerald-500/10 text-slate-100"
                      : done
                        ? "border-slate-800 text-slate-400"
                        : "border-slate-800/60 text-slate-600",
                  ].join(" ")}
                >
                  <span
                    className={[
                      "grid h-4 w-4 shrink-0 place-items-center rounded-full text-[9px] font-bold",
                      done
                        ? "bg-emerald-500 text-slate-950"
                        : active
                          ? "clearance-orbit bg-emerald-500/15 text-emerald-500 ring-1 ring-emerald-500"
                          : "bg-slate-800 text-slate-600",
                    ].join(" ")}
                  >
                    {done ? "✓" : i + 1}
                  </span>
                  <span className="font-medium">{STAGE_LABEL[stage]}</span>
                  {active && stage === "researching" && p.entities > 0 && (
                    <span className="ml-auto tabular-nums text-emerald-500">
                      {p.dossiers_complete}/{p.entities}
                    </span>
                  )}
                  {active && stage === "extracting" && p.elements_found > 0 && (
                    <span className="ml-auto tabular-nums text-emerald-500">
                      {p.elements_found} found
                    </span>
                  )}
                </li>
              );
            })}
          </ol>

          <p className="text-center text-[11px] leading-relaxed text-slate-500 md:text-left">
            Findings are written once every mention has been assessed, so they
            all appear together rather than trickling in.
          </p>

          {onHide && (
            <button
              onClick={onHide}
              className="text-[11px] text-slate-500 underline underline-offset-4
                         transition-colors hover:text-slate-300 md:self-start"
            >
              Hide and read the screenplay
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * The ring, with the run mark turning inside it.
 *
 * The mark is a wide, short drawing, and the largest rectangle of its aspect
 * that fits inside a circle is about 0.81 of the diameter, so the mark is 56%
 * of the ring and the ring has to stay reasonably large or the sprocket holes
 * and the badge tick turn to mush.
 *
 * Size is a ceiling, not a fixed value: `clamp(9.5rem, 26vh, 12.5rem)` lets a
 * short window shrink the ring rather than push the stage list off the bottom.
 * The ceiling came down from 14rem once it was clear some windows still get
 * the stacked layout, where the ring and the stages share the height.
 *
 * The arc is 5 units wide, not 9. That is a look, not a fix: the stroke is
 * centred on the radius and the decorative orbit at r=66 is what reaches
 * furthest, so thickness does not change the footprint at all. It matters
 * because a thick arc on a smaller ring reads as a doughnut.
 *
 * The percentage sits below the ring rather than inside it. Stacked within the
 * circle, the mark and the numerals together needed a chord the circle does
 * not have, and shrinking the camera to make room defeated the purpose of
 * putting it there.
 */
function Ring({ percent }: { percent: number }) {
  const radius = 56;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.min(100, Math.max(0, percent)) / 100);

  return (
    <div className="flex shrink-0 flex-col items-center gap-3">
      <div className="relative aspect-square w-[clamp(9.5rem,26vh,12.5rem)]">
        {/* Decorative, constant, and deliberately not tied to progress. */}
        <svg viewBox="0 0 140 140" className="clearance-orbit absolute inset-0 h-full w-full" aria-hidden>
          <circle cx="70" cy="70" r="66" fill="none"
                  className="stroke-slate-800/70" strokeWidth="1" />
          <circle cx="70" cy="70" r="66" fill="none"
                  className="stroke-emerald-500/60" strokeWidth="2"
                  strokeLinecap="round" strokeDasharray="3 60" />
        </svg>

        <svg viewBox="0 0 140 140" className="absolute inset-0 h-full w-full -rotate-90" aria-hidden>
          {/* A ground for the mark, so it is not floating on the page colour. */}
          <circle cx="70" cy="70" r="51" className="rm-disc" />
          <circle cx="70" cy="70" r={radius} fill="none"
                  className="stroke-slate-800" strokeWidth="5" />
          <circle
            cx="70" cy="70" r={radius} fill="none"
            className="stroke-emerald-500 transition-[stroke-dashoffset] duration-700 ease-out"
            strokeWidth="5" strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={offset}
            style={{ filter: "drop-shadow(0 0 5px color-mix(in srgb, var(--risk-green) 55%, transparent))" }}
          />
        </svg>

        {/* 56% of the ring: the widest this aspect can be inside the circle
            with margin, whatever the ring's current size. */}
        <span className="absolute inset-0 flex items-center justify-center">
          <RunMark className="w-[56%]" />
        </span>
      </div>

      <span className="text-3xl font-bold tabular-nums tracking-tight text-slate-100">
        {percent}
        <span className="ml-0.5 text-lg font-medium text-slate-500">%</span>
      </span>
    </div>
  );
}
