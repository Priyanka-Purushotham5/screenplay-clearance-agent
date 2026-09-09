"use client";

import { useId } from "react";

/**
 * The run mark: a movie camera with a red / amber / green reel turning on top,
 * a projector beam out of the lens and a clearance badge beside it.
 *
 * Distinct from `Logo` on purpose. The logo is the product's identity and has
 * to hold at 16px in a browser tab, so it is a flat two-colour silhouette. This
 * one exists at exactly one size, in the middle of the run overlay's progress
 * ring, where there is room for the reel to actually read as three ratings
 * turning past.
 *
 * What it is NOT is a progress indicator. The arc around it advances only when
 * a stage completes; this turns at a constant rate whatever is happening. That
 * separation is the point: during `researching`, which is the longest stage and
 * the one with the least to report, a still ring around a still number is
 * indistinguishable from a hung page. The camera says work is happening. The
 * arc says how much is done. Neither claim is made by the other, and animating
 * the arc on a timer would have collapsed them into one untrustworthy number.
 *
 * Neutrals come from the `rm-*` classes in globals.css rather than fill
 * attributes, so the camera follows the theme. Only the three ratings and the
 * beam are literal colours, and those are the same in both themes by design.
 */
export default function RunMark({ className = "" }: { className?: string }) {
  const beamId = `run-beam-${useId().replace(/:/g, "")}`;

  return (
    <svg
      // Sized by its container, not by a pixel prop. The ring it sits inside
      // is now responsive, and a fixed width would have kept its own size
      // while the circle around it shrank, which is the one way this can
      // still clip.
      width="100%"
      height="100%"
      // Trimmed from the drawing's natural 0 0 150 120 to its actual content
      // bounds. Inside a circle every unit of empty margin costs real size:
      // the largest rectangle of this aspect that fits the ring's interior is
      // barely wider than the artwork itself.
      viewBox="20 6 128 92"
      className={className}
      role="img"
      aria-label="Clearance run in progress"
    >
      <defs>
        <linearGradient id={beamId} x1="98" y1="65" x2="145" y2="65"
                        gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="var(--risk-green)" stopOpacity=".85" />
          <stop offset="100%" stopColor="var(--risk-green)" stopOpacity=".05" />
        </linearGradient>
      </defs>

      <polygon className="clearance-beam" points="98,65 145,45 145,85"
               fill={`url(#${beamId})`} />

      {/* Body, viewfinder and the script lines on its side */}
      <rect className="rm-body" x="25" y="50" width="60" height="42" rx="6" strokeWidth="2.5" />
      <rect className="rm-inset" x="33" y="58" width="18" height="12" rx="2" strokeWidth="1.5" />
      <line className="rm-line" x1="60" y1="62" x2="75" y2="62" strokeWidth="2" strokeLinecap="round" />
      <line className="rm-line" x1="60" y1="70" x2="72" y2="70" strokeWidth="2" strokeLinecap="round" />

      {/* Lens, with the clearance light in it */}
      <path className="rm-inset" d="M 85 58 L 98 52 L 98 78 L 85 72 Z" strokeWidth="2" />
      <circle cx="98" cy="65" r="5" fill="var(--risk-green)" />

      {/* The reel: three arcs, one per rating, turning as one */}
      <g className="clearance-tri-reel">
        <circle className="rm-rim" cx="50" cy="32" r="22" strokeWidth="2" />
        <path d="M 50 12 A 20 20 0 0 1 67 22" fill="none"
              stroke="var(--risk-red)" strokeWidth="5" strokeLinecap="round" />
        <path d="M 67 42 A 20 20 0 0 1 33 42" fill="none"
              stroke="var(--risk-amber)" strokeWidth="5" strokeLinecap="round" />
        <path d="M 33 22 A 20 20 0 0 1 50 12" fill="none"
              stroke="var(--risk-green)" strokeWidth="5" strokeLinecap="round" />
        <g className="rm-dot">
          <circle cx="50" cy="18" r="1.9" /><circle cx="62" cy="25" r="1.9" />
          <circle cx="62" cy="39" r="1.9" /><circle cx="50" cy="46" r="1.9" />
          <circle cx="38" cy="39" r="1.9" /><circle cx="38" cy="25" r="1.9" />
        </g>
        <circle className="rm-inset" cx="50" cy="32" r="6" strokeWidth="1.5" />
      </g>

      {/* Take-up reel, behind */}
      <circle className="rm-body" cx="80" cy="36" r="14" strokeWidth="2" />
      <circle className="rm-hub" cx="80" cy="36" r="4" />

      {/* Cleared badge */}
      <path
        className="rm-shield"
        d="M 125 52 L 140 57 V 73 C 140 81 125 88 125 88 C 125 88 110 81 110 73 V 57 L 125 52 Z"
        stroke="var(--risk-green)"
        strokeWidth="2"
      />
      <path d="M 120 70 L 124 74 L 131 66" fill="none" stroke="var(--risk-green)"
            strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
