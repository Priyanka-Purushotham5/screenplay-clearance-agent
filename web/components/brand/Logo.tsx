"use client";

import { useId } from "react";

/**
 * The mark: a film camera whose body is a length of film, three frames wide,
 * one per risk rating. Neutral parts use `currentColor`, so one component
 * serves both themes — inlined SVG inherits colour, which is exactly why this
 * is a component and not `<img src="/logo.svg">` (through an img tag,
 * currentColor has nothing to inherit from and falls back to black).
 *
 * Two motion states, and they are deliberately different things:
 *
 *   spinning  — the reels turn. Cheap, small, and used in the header while a
 *               run is in flight, so the mark doubles as a status light.
 *   animated  — the film itself runs through the gate, red / amber / green
 *               cycling past. This is the camera recording.
 *
 * Neither is ever on at rest. A mark that always moves stops meaning
 * anything, and constant motion in persistent chrome is tiring.
 * `prefers-reduced-motion` disables both, which is why every screen that uses
 * them also states the stage in words.
 */

// ---------------------------------------------------------------------------
// The strip
// ---------------------------------------------------------------------------

/** One frame plus its gap, in the logo's user units. */
const PITCH = 6.3;
const FRAME_W = 5.5;

/**
 * red / amber / green, matching --risk-* in globals.css.
 *
 * Literal values rather than var() references because this is the brand mark:
 * it has to look the same in a favicon, an OG image and a printed slide, none
 * of which have our stylesheet. Keep them in step with the tokens by hand;
 * they are the same three colours, chosen to clear 3:1 on white as well as on
 * the dark app.
 */
const RISK = ["#FF0022", "#E27900", "#00AB56"];

/**
 * The distance the strip travels per animation cycle, which has to be a whole
 * number of COLOUR periods, not frame periods.
 *
 * Translating by one PITCH would loop seamlessly for the sprocket holes and
 * visibly jump for the frames: at the reset, the amber that had scrolled into
 * a given slot would be replaced by the red that started there. Three pitches
 * is the first distance at which both the holes and the colour cycle land
 * back on themselves.
 */
const CYCLE = PITCH * 3; // 18.9 — keep `clearance-film` in globals.css in step

/** Continuous film: sprockets at half-pitch, frames cycling through the three risks. */
function Strip({ x0, count }: { x0: number; count: number }) {
  const cells = Array.from({ length: count }, (_, i) => i);
  return (
    <>
      <g fill="currentColor" opacity=".55">
        {cells.map((i) =>
          [0, PITCH / 2].map((offset, j) => {
            const x = x0 + i * PITCH + offset;
            return (
              <g key={`s${i}-${j}`}>
                <rect x={x} y="16.3" width="1.7" height="1.5" rx=".4" />
                <rect x={x} y="23.9" width="1.7" height="1.5" rx=".4" />
              </g>
            );
          })
        )}
      </g>
      {cells.map((i) => (
        <rect
          key={`f${i}`}
          x={x0 + i * PITCH}
          y="18.6"
          width={FRAME_W}
          height="3.2"
          rx=".7"
          fill={RISK[i % 3]}
        />
      ))}
    </>
  );
}

/**
 * The mark at rest — the original three frames, at their original positions.
 *
 * Kept as its own drawing rather than freezing `Strip`, so the static logo is
 * byte-for-byte what it always was. The animated variant repositions frames
 * by a fraction of a unit to make the loop seamless, and a brand mark that
 * shifts when a run starts would be worse than one that does not move at all.
 */
function StaticFrames() {
  return (
    <>
      <g fill="currentColor" opacity=".55">
        {[8.8, 12.2, 15.6, 19, 22.4].map((x) => (
          <rect key={`t${x}`} x={x} y="16.3" width="1.7" height="1.5" rx=".4" />
        ))}
        {[8.8, 12.2, 15.6, 19, 22.4].map((x) => (
          <rect key={`b${x}`} x={x} y="23.9" width="1.7" height="1.5" rx=".4" />
        ))}
      </g>
      <rect x="8.8" y="18.6" width="5.5" height="3.2" rx=".7" fill={RISK[0]} />
      <rect x="15.1" y="18.6" width="5.5" height="3.2" rx=".7" fill={RISK[1]} />
      <rect x="21.4" y="18.6" width="2.7" height="3.2" rx=".7" fill={RISK[2]} />
    </>
  );
}

function Reel() {
  return (
    <>
      <circle r="6" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <g stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
        <path d="M0 -3.9V-1.5" />
        <path d="M3.38 1.95 1.3 .75" />
        <path d="M-3.38 1.95 -1.3 .75" />
      </g>
      <circle r="1.5" fill="currentColor" />
    </>
  );
}

/** Body outline and lens cone. Identical in both variants. */
function Camera() {
  return (
    <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
      <path d="M7 18.4 1.9 15.2V26.4L7 23.2Z" />
      <rect x="7" y="15" width="20.5" height="11.6" rx="1.6" />
    </g>
  );
}

// ---------------------------------------------------------------------------
// The mark
// ---------------------------------------------------------------------------

export default function Logo({
  size = 30,
  spinning = false,
  animated = false,
  className = "",
}: {
  size?: number;
  /** Turn the reels. Used in the header while a run is in flight. */
  spinning?: boolean;
  /** Run the film through the gate. Implies the reels turn too. */
  animated?: boolean;
  className?: string;
}) {
  // Unique per instance: the header mark and the one inside the run overlay
  // are on the page together, and two elements sharing an id is invalid
  // markup that browsers resolve by first-match — fine until one of them
  // renders at a different size and silently clips the other.
  const clipId = `film-window-${useId().replace(/:/g, "")}`;
  const turning = spinning || animated;
  const reel = turning ? "clearance-reel clearance-reel-spin" : "clearance-reel";

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={className}
      role="img"
      aria-label="Script to Clearance"
    >
      {animated && (
        <defs>
          {/*
            The gate. The strip is drawn far wider than the camera and shows
            only through the body's interior, inset by the stroke so the film
            never paints over its own outline.
          */}
          <clipPath id={clipId}>
            <rect x="7.9" y="15.9" width="18.7" height="9.8" rx="1.1" />
          </clipPath>
        </defs>
      )}

      <Camera />

      {animated ? (
        <g clipPath={`url(#${clipId})`}>
          <g className="clearance-film">
            <Strip x0={7.9 - CYCLE} count={10} />
          </g>
        </g>
      ) : (
        <StaticFrames />
      )}

      <g className={reel} style={{ transformOrigin: "21.6px 10.4px" }}>
        <g transform="translate(21.6 10.4) scale(.72)">
          <Reel />
        </g>
      </g>
      <g className={reel} style={{ transformOrigin: "12px 9.6px" }}>
        <g transform="translate(12 9.6)">
          <Reel />
        </g>
      </g>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// The recording mark
// ---------------------------------------------------------------------------

/**
 * The same camera, same film, same animation — but the strip carries on past
 * the body and trails off to the right, so the mark reads as recording rather
 * than merely running.
 *
 * A separate export rather than another prop on `Logo`, because the wider
 * viewBox changes the silhouette. The header mark has to stay square and stay
 * the size it has always been; this one has room to spend, and is only used
 * where there is space for it — currently the middle of the run overlay's
 * progress ring.
 */
export function LogoRecording({
  width = 104,
  className = "",
}: {
  width?: number;
  className?: string;
}) {
  const uid = useId().replace(/:/g, "");
  const fadeId = `film-fade-${uid}`;
  const maskId = `film-mask-${uid}`;

  return (
    <svg
      width={width}
      height={width * (32 / 58)}
      viewBox="0 0 58 32"
      className={className}
      aria-hidden
      focusable="false"
    >
      <defs>
        {/*
          The tail has to end somewhere, and a hard edge would read as the
          film being cut. Fading it out instead says "this continues past the
          frame", which is what a camera mid-take is doing.
        */}
        <linearGradient id={fadeId} x1="0" x2="1">
          <stop offset="0.55" stopColor="#fff" stopOpacity="1" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <mask id={maskId}>
          <rect x="0" y="0" width="58" height="32" fill={`url(#${fadeId})`} />
        </mask>
        <clipPath id={`in-${uid}`}>
          <rect x="7.9" y="15.9" width="18.7" height="9.8" rx="1.1" />
        </clipPath>
      </defs>

      <Camera />

      {/* Inside the camera: clipped to the body, exactly as the header mark. */}
      <g clipPath={`url(#in-${uid})`}>
        <g className="clearance-film">
          <Strip x0={7.9 - CYCLE} count={10} />
        </g>
      </g>

      {/* Outside the camera: the same strip, same animation, no clip. */}
      <g mask={`url(#${maskId})`}>
        <g className="clearance-film">
          <Strip x0={27.5 - CYCLE} count={14} />
        </g>
        {/* Film edges, drawn outside the animated group so they hold still. */}
        <g stroke="currentColor" strokeWidth=".9" opacity=".45" strokeLinecap="round">
          <path d="M27.5 15.9H58" />
          <path d="M27.5 25.7H58" />
        </g>
      </g>

      <g className="clearance-reel clearance-reel-spin"
         style={{ transformOrigin: "21.6px 10.4px" }}>
        <g transform="translate(21.6 10.4) scale(.72)">
          <Reel />
        </g>
      </g>
      <g className="clearance-reel clearance-reel-spin"
         style={{ transformOrigin: "12px 9.6px" }}>
        <g transform="translate(12 9.6)">
          <Reel />
        </g>
      </g>
    </svg>
  );
}
