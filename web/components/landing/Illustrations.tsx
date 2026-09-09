"use client";

/**
 * The app, drawn rather than screenshotted.
 *
 * These are miniature recreations of the real interface in SVG and CSS, not
 * captures of it. Three reasons that is the better choice here: they follow
 * the theme, they stay sharp at any size, and — the one that matters — they
 * cannot go stale. A screenshot of a UI still being built is out of date by
 * the next drop, and nobody notices until a visitor sees a version of the
 * product that no longer exists.
 *
 * Every animation is behind `prefers-reduced-motion` in globals.css.
 */

/** Step 1 — a PDF becoming parsed scenes. */
export function UploadArt() {
  return (
    <Frame>
      <g className="clearance-fade-1">
        <rect x="18" y="14" width="52" height="66" rx="4"
              className="fill-slate-900 stroke-slate-700" strokeWidth="1.5" />
        {[24, 32, 40, 48, 56, 64].map((y, i) => (
          <rect key={y} x="26" y={y} width={i % 3 === 0 ? 30 : 36} height="3" rx="1.5"
                className="fill-slate-700" />
        ))}
      </g>
      <path d="M78 47h22" className="stroke-slate-600" strokeWidth="1.5"
            strokeDasharray="3 3" />
      <path d="M96 43l5 4-5 4" className="stroke-slate-600" strokeWidth="1.5"
            fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <g className="clearance-fade-2">
        {[14, 36, 58].map((y, i) => (
          <g key={y}>
            <rect x="110" y={y} width="62" height="18" rx="3"
                  className="fill-slate-900 stroke-slate-700" strokeWidth="1.5" />
            <rect x="116" y={y + 5} width="26" height="3" rx="1.5"
                  className="fill-emerald-500/70" />
            <rect x="116" y={y + 11} width={44 - i * 8} height="2.5" rx="1.25"
                  className="fill-slate-700" />
          </g>
        ))}
      </g>
    </Frame>
  );
}

/** Step 2 — mentions found in the text, then resolved to fewer entities. */
export function ExtractArt() {
  return (
    <Frame>
      <g>
        {[
          { y: 16, w: 150 }, { y: 26, w: 132 }, { y: 36, w: 146 },
          { y: 46, w: 118 }, { y: 56, w: 152 }, { y: 66, w: 96 },
        ].map((l) => (
          <rect key={l.y} x="18" y={l.y} width={l.w} height="3.5" rx="1.75"
                className="fill-slate-800" />
        ))}
      </g>
      <g className="clearance-fade-2">
        <rect x="52" y="14.5" width="34" height="7" rx="2" className="fill-red-500/35" />
        <rect x="96" y="34.5" width="28" height="7" rx="2" className="fill-amber-400/35" />
        <rect x="34" y="54.5" width="30" height="7" rx="2" className="fill-emerald-500/35" />
        <rect x="120" y="24.5" width="22" height="7" rx="2" className="fill-emerald-500/35" />
        <rect x="30" y="44.5" width="26" height="7" rx="2" className="fill-red-500/35" />
      </g>
      <text x="18" y="86" className="fill-slate-500" fontSize="8">
        24 mentions
      </text>
      <text x="112" y="86" className="fill-slate-300" fontSize="8">
        13 entities
      </text>
      <path d="M74 83h30" className="stroke-slate-600" strokeWidth="1.2" />
      <path d="M100 80l4 3-4 3" className="stroke-slate-600" strokeWidth="1.2"
            fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Frame>
  );
}

/** Step 3 — each entity researched against sources on the open web. */
export function ResearchArt() {
  return (
    <Frame>
      <circle cx="95" cy="47" r="17" className="fill-slate-900 stroke-slate-600"
              strokeWidth="1.5" />
      <text x="95" y="51" textAnchor="middle" className="fill-slate-300" fontSize="9">
        entity
      </text>
      <g className="clearance-orbit" style={{ transformOrigin: "95px 47px" }}>
        <circle cx="95" cy="47" r="31" fill="none"
                className="stroke-emerald-500/50" strokeWidth="1.5"
                strokeDasharray="3 26" strokeLinecap="round" />
      </g>
      {[
        { x: 20, y: 20, label: "registry" },
        { x: 20, y: 66, label: "catalogue" },
        { x: 132, y: 20, label: "estate" },
        { x: 132, y: 66, label: "archive" },
      ].map((s) => (
        <g key={s.label}>
          <rect x={s.x} y={s.y - 7} width="46" height="14" rx="3"
                className="fill-slate-900 stroke-slate-700" strokeWidth="1.2" />
          <text x={s.x + 23} y={s.y + 2.5} textAnchor="middle"
                className="fill-slate-400" fontSize="7">
            {s.label}
          </text>
        </g>
      ))}
      <g className="stroke-slate-700" strokeWidth="1.2" strokeDasharray="2 3">
        <path d="M66 22h-1M68 25 78 38" /><path d="M68 69 78 56" />
        <path d="M132 25 112 38" /><path d="M132 69 112 56" />
      </g>
    </Frame>
  );
}

/** Step 4 — the same title, rated two different ways by context. */
export function ContextArt() {
  return (
    <Frame>
      <g>
        <rect x="14" y="12" width="76" height="70" rx="4"
              className="fill-slate-900 stroke-red-500/40" strokeWidth="1.5" />
        <text x="24" y="27" className="fill-red-400" fontSize="8" fontWeight="700">RED</text>
        <text x="24" y="41" className="fill-slate-300" fontSize="7">the record</text>
        <text x="24" y="51" className="fill-slate-300" fontSize="7">plays in the</text>
        <text x="24" y="61" className="fill-slate-300" fontSize="7">scene</text>
        <text x="24" y="74" className="fill-slate-500" fontSize="6.5">sync + master</text>
      </g>
      <g>
        <rect x="100" y="12" width="76" height="70" rx="4"
              className="fill-slate-900 stroke-emerald-500/40" strokeWidth="1.5" />
        <text x="110" y="27" className="fill-emerald-400" fontSize="8" fontWeight="700">GREEN</text>
        <text x="110" y="41" className="fill-slate-300" fontSize="7">a character</text>
        <text x="110" y="51" className="fill-slate-300" fontSize="7">says the title</text>
        <text x="110" y="61" className="fill-slate-300" fontSize="7">out loud</text>
        <text x="110" y="74" className="fill-slate-500" fontSize="6.5">nothing to clear</text>
      </g>
      <text x="95" y="94" textAnchor="middle" className="fill-slate-500" fontSize="7.5">
        same song, same script
      </text>
    </Frame>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 190 100" className="h-auto w-full" role="img" aria-hidden>
      {children}
    </svg>
  );
}
