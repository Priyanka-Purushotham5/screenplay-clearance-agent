"use client";

import { useState } from "react";
import Link from "next/link";
import Logo from "@/components/brand/Logo";
import {
  ContextArt,
  ExtractArt,
  ResearchArt,
  UploadArt,
} from "@/components/landing/Illustrations";

export default function LandingPage() {
  return (
    <div className="flex-1 overflow-y-auto bg-slate-950">
      <Hero />
      <Problem />
      <HowItWorks />
      <Anatomy />
      <Savings />
      <Audience />
      <AboutAndContact />
      <LandingFooter />
    </div>
  );
}

function Section({
  id,
  eyebrow,
  title,
  lede,
  children,
}: {
  id?: string;
  eyebrow?: string;
  title: string;
  lede?: string;
  children?: React.ReactNode;
}) {
  return (
    <section id={id} className="border-t border-slate-800 px-6 py-16 sm:py-20">
      <div className="mx-auto max-w-5xl">
        {eyebrow && (
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.15em] text-emerald-500">
            {eyebrow}
          </p>
        )}
        <h2 className="text-2xl font-semibold tracking-tight text-slate-100 sm:text-3xl">
          {title}
        </h2>
        {lede && (
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-400">{lede}</p>
        )}
        {children}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero() {
  return (
    <section className="px-6 pb-16 pt-14 sm:pb-20 sm:pt-20">
      <div className="mx-auto grid max-w-5xl items-center gap-12 lg:grid-cols-[1.1fr_1fr]">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-700
                           bg-slate-900 px-3 py-1 text-xs text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Every finding cites its sources
          </span>

          <h1 className="mt-5 text-4xl font-semibold leading-[1.1] tracking-tight
                         text-slate-100 sm:text-5xl">
            Find every rights issue in a screenplay
            <span className="text-slate-500">, before it costs you.</span>
          </h1>

          <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-400">
            Upload a script. Get back every song, brand, artwork, location and
            real person in it, each rated red, amber or green, each with the
            rights holders named and the sources it was decided from.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/upload"
              className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold
                         text-white transition-colors hover:bg-emerald-500"
            >
              Upload a screenplay
            </Link>
            <a
              href="#how"
              className="rounded-lg border border-slate-700 px-5 py-2.5 text-sm
                         font-medium text-slate-300 transition-colors
                         hover:border-slate-600 hover:text-slate-100"
            >
              See how it works
            </a>
          </div>

          <p className="mt-5 text-xs text-slate-500">
            Research, not legal advice. It tells you what to clear and who to ask.
          </p>
        </div>

        <SplitRatingDemo />
      </div>
    </section>
  );
}

/**
 * The product's whole argument, in one card.
 *
 * Not a feature list: two real lines from a real screenplay, the same song in
 * both, rated opposite ways. Anyone who has cleared a script recognises the
 * distinction immediately, and anyone who has not learns what the tool is for
 * without reading a word of marketing copy.
 */
function SplitRatingDemo() {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 shadow-2xl">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-xs font-semibold text-slate-300">Take On Me</span>
        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px]
                         text-slate-400">
          split rating
        </span>
        <span className="ml-auto text-[10px] text-slate-500">music</span>
      </div>

      <div className="space-y-2">
        <DemoLine
          risk="red"
          scene="scene 1 · action"
          line="On a battered turntable, 'Take On Me' by a-ha plays loudly."
          verdict="Sync + master use licence"
        />
        <DemoLine
          risk="green"
          scene="scene 2 · dialogue"
          line="You know that song? Take On Me? I actually love that song."
          verdict="Nothing to clear. A title is not the work"
        />
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
        The same title, twice in one script. Context decides, not keyword
        matching.
      </p>
    </div>
  );
}

function DemoLine({
  risk,
  scene,
  line,
  verdict,
}: {
  risk: "red" | "green";
  scene: string;
  line: string;
  verdict: string;
}) {
  // The same treatment the findings pane uses, so the demo on the landing page
  // is a picture of the real thing rather than an idealised version of it.
  const tone =
    risk === "red"
      ? { bleed: "clearance-bleed risk-red", chip: "text-red-400", mark: "bg-red-500/25" }
      : { bleed: "clearance-bleed risk-green", chip: "text-emerald-400", mark: "bg-emerald-500/25" };
  const [before, after] = line.split("Take On Me");

  return (
    <div className={`rounded-lg border border-slate-800 bg-slate-950
                     p-3 ${tone.bleed}`}>
      <div className="mb-1.5 flex items-center gap-2">
        <span className={`text-[10px] font-bold uppercase ${tone.chip}`}>{risk}</span>
        <span className="text-[10px] text-slate-500">{scene}</span>
      </div>
      <p className="font-mono text-[11px] leading-relaxed text-slate-300">
        {before}
        <mark className={`rounded px-1 ${tone.mark} text-slate-100`}>Take On Me</mark>
        {after}
      </p>
      <p className="mt-2 text-[11px] text-slate-400">{verdict}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Problem
// ---------------------------------------------------------------------------

function Problem() {
  return (
    <Section
      eyebrow="The problem"
      title="Clearance is a reading job, done line by line"
      lede="Somebody has to go through every page and notice each song, brand, painting, restaurant and real name, then work out, for each one, whether it needs a licence. Miss one and it surfaces in post, when changing it is expensive, or at an insurer's errors-and-omissions review, when it can stop delivery."
    >
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {[
          {
            t: "It is easy to miss things",
            d: "A brand named once in dialogue on page 74 reads like ordinary conversation until somebody has to clear it.",
          },
          {
            t: "Keyword lists over-flag",
            d: "Search for song titles and every character who says one becomes a red flag. Volume without judgement is its own cost.",
          },
          {
            t: "The reasoning gets lost",
            d: "A spreadsheet cell saying “amber” helps nobody three weeks later. The question is always: why, and says who?",
          },
        ].map((c) => (
          <div key={c.t} className="rounded-lg border border-slate-800 bg-slate-900 p-5">
            <h3 className="text-sm font-semibold text-slate-100">{c.t}</h3>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">{c.d}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------
// How it works
// ---------------------------------------------------------------------------

const STEPS = [
  {
    n: "01",
    t: "Upload the script",
    d: "A PDF goes in. It is parsed into scenes, dialogue, action and transitions: the structure a reader sees, not a wall of text.",
    art: <UploadArt />,
  },
  {
    n: "02",
    t: "Find every mention, then resolve them",
    d: "Each real-world reference is located with its exact position in the line. “Take On Me”, “that song” and “a-ha” are then recognised as one entity, so it is researched once instead of three times.",
    art: <ExtractArt />,
  },
  {
    n: "03",
    t: "Research who actually owns it",
    d: "Every entity is looked up on the open web, across registries, catalogues and estates, and the evidence is kept. Nothing is decided from memory.",
    art: <ResearchArt />,
  },
  {
    n: "04",
    t: "Rate each mention in its own context",
    d: "A recording playing in a scene is not the same as a character naming it, and the rating follows the difference. Every call cites the evidence it rests on.",
    art: <ContextArt />,
  },
];

function HowItWorks() {
  return (
    <Section
      id="how"
      eyebrow="How it works"
      title="Four stages, and you can watch each one"
      lede="The run reports what it is doing while it does it, and the findings arrive with their working shown."
    >
      <div className="mt-10 flex flex-col gap-10">
        {STEPS.map((s, i) => (
          <div
            key={s.n}
            className={`grid items-center gap-8 md:grid-cols-2 ${
              i % 2 ? "md:[&>*:first-child]:order-2" : ""
            }`}
          >
            <div>
              <span className="font-mono text-xs text-emerald-500">{s.n}</span>
              <h3 className="mt-1 text-lg font-semibold text-slate-100">{s.t}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{s.d}</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
              {s.art}
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Anatomy of a finding
// ---------------------------------------------------------------------------

function Anatomy() {
  return (
    <Section
      eyebrow="What you get"
      title="A finding you can act on, or argue with"
      lede="Each one names the rights holders, says what licence is needed, suggests a way around it, and links the sources it was decided from. You can accept it or override it, and the record keeps both."
    >
      <div className="mt-8 grid gap-6 md:grid-cols-[1.2fr_1fr]">
        <div className="clearance-bleed risk-red rounded-xl border border-slate-800
                        bg-slate-900 p-5">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold text-slate-100">Take On Me</span>
            <span className="text-xs text-slate-500">music:take_on_me:a_ha</span>
            <span className="ml-auto text-xs font-bold uppercase text-red-400">red</span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-400">
            A named commercial recording audibly playing in the scene needs two
            separate clearances: a synchronisation licence from the publisher
            for the composition, and a master use licence from the label for
            that specific recording.
          </p>
          <Row label="Rights required">synchronisation licence · master use licence</Row>
          <Row label="Rights holders">
            ATV Music Ltd. (publisher) · Warner Bros. Records (master)
          </Row>
          <Row label="Alternatives">
            Replace with an original composition or a cleared library track ·
            Rewrite so the track is mentioned rather than played
          </Row>
          <Row label="Sources">
            <span className="inline-flex gap-1.5">
              {["discogs.com", "songfacts.com"].map((d) => (
                <span key={d} className="rounded border border-slate-700 bg-slate-950
                                         px-1.5 py-0.5 text-[10px] text-slate-300">
                  {d}
                </span>
              ))}
            </span>
          </Row>
        </div>

        <ul className="flex flex-col gap-3">
          {[
            ["Rated in context", "The same title can be red in one scene and green in the next."],
            ["Sources attached", "Every rating links what it was decided from."],
            ["Alternatives offered", "A way to keep the scene without the licence, where one exists."],
            ["Your call recorded", "Accept the rating or override it; the report keeps who decided what."],
            ["Linked to the page", "Click a finding and the screenplay scrolls to the exact line."],
          ].map(([t, d]) => (
            <li key={t} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <h3 className="text-sm font-semibold text-slate-100">{t}</h3>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">{d}</p>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-3">
      <p className="text-[9.5px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <div className="mt-0.5 text-xs text-slate-300">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Savings
// ---------------------------------------------------------------------------

/**
 * A calculator, not a claim.
 *
 * Every input is visible and editable, including the two assumptions, because
 * a headline number invented by the people selling the tool is worth nothing.
 * This one is the reader's own arithmetic; if they disagree with the
 * assumptions they can change them and watch the answer move.
 */
function Savings() {
  const [items, setItems] = useState(180);
  const [minutes, setMinutes] = useState(12);
  const [rate, setRate] = useState(75);

  const hours = (items * minutes) / 60;
  const cost = hours * rate;
  const money = (n: number) =>
    n.toLocaleString(undefined, { maximumFractionDigits: 0 });

  return (
    <Section
      eyebrow="What it saves"
      title="Work out your own number"
      lede="We are not going to quote you a statistic we cannot source. Put your own figures in. These defaults are assumptions, not findings, and you should change them."
    >
      <div className="mt-8 grid gap-6 md:grid-cols-[1fr_1fr]">
        <div className="flex flex-col gap-4 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <Field label="Items flagged in a feature script" value={items} onChange={setItems}
                 hint="A dense script runs to a few hundred; a contained drama, far fewer." />
          <Field label="Minutes to research and log one, by hand" value={minutes} onChange={setMinutes}
                 hint="Finding the owner, checking the term, writing it up." />
          <Field label="Hourly rate of whoever does it" value={rate} onChange={setRate}
                 hint="Paralegal, clearance co-ordinator, or your own time." />
        </div>

        <div className="flex flex-col justify-center rounded-xl border border-slate-800
                        bg-slate-900 p-6">
          <p className="text-xs uppercase tracking-wider text-slate-500">
            First pass, by hand
          </p>
          <p className="mt-1 text-4xl font-semibold tabular-nums text-slate-100">
            {money(hours)} hours
          </p>
          <p className="mt-1 text-lg tabular-nums text-slate-400">
            ≈ {money(cost)} at your rate
          </p>
          <div className="mt-5 border-t border-slate-800 pt-5">
            <p className="text-xs uppercase tracking-wider text-emerald-500">
              First pass, here
            </p>
            <p className="mt-1 text-2xl font-semibold text-slate-100">Minutes</p>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">
              Our four-page test screenplay produced 24 findings, with sources,
              in about three minutes. What the tool does not do is make the
              judgement calls for you. It does the reading and the looking-up,
              and hands you a list to decide on.
            </p>
          </div>
        </div>
      </div>
    </Section>
  );
}

function Field({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  hint: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-300">{label}</span>
      <input
        type="number"
        min={0}
        value={value}
        onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
        className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2
                   text-sm tabular-nums text-slate-100 outline-none
                   focus:border-emerald-600"
      />
      <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Audience
// ---------------------------------------------------------------------------

function Audience() {
  return (
    <Section
      eyebrow="Who it is for"
      title="Anyone who has to answer “can we actually shoot this?”"
    >
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Screenwriters", "Know which references will survive a rewrite note, while the draft is still yours to change."],
          ["Producers & line producers", "See the licensing exposure in a script before it is scheduled and budgeted."],
          ["Production legal & clearance", "A first pass with the reading already done and the sources attached, to check rather than compile."],
          ["Students & indie filmmakers", "The check that normally needs a firm on retainer, on a script you are making for very little."],
        ].map(([t, d]) => (
          <div key={t} className="rounded-lg border border-slate-800 bg-slate-900 p-5">
            <h3 className="text-sm font-semibold text-slate-100">{t}</h3>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">{d}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------
// About & contact
// ---------------------------------------------------------------------------

function AboutAndContact() {
  return (
    <Section id="about" eyebrow="About" title="Why this exists">
      <div className="mt-6 grid gap-8 md:grid-cols-[1.3fr_1fr]">
        <div className="space-y-4 text-sm leading-relaxed text-slate-400">
          <p>
            Rights clearance is one of the few jobs in production that is
            simultaneously unavoidable, expensive, and mostly reading. The
            expertise is real and the tool does not replace it. What it does take on
            is finding the things that need a decision, and looking up who to
            ask.
          </p>
          <p>
            So that is what this does. It reads the script, resolves the
            mentions, researches each one against real sources, and rates each
            appearance on its own context. Then it hands a reviewer a list with
            the evidence attached, and records what they decided.
          </p>
          <p className="text-slate-500">
            Built for the Agentic Cinema hackathon by Priyanka Purushotham and
            Rohit B V.{" "}
            <span className="text-slate-600">
              Findings are research, not legal advice. The last word belongs
              to a qualified professional.
            </span>
          </p>
        </div>

        <div id="contact" className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h3 className="text-sm font-semibold text-slate-100">Contact</h3>
          <p className="mt-2 text-xs leading-relaxed text-slate-400">
            Questions, a script that broke it, or a rating you disagree with:
            all three are useful.
          </p>
          <dl className="mt-4 space-y-3 text-xs">
            <div>
              <dt className="text-slate-500">Priyanka Purushotham</dt>
              <dd>
                <a
                  href="mailto:priyankapurushotham5@gmail.com"
                  className="text-emerald-400 underline underline-offset-2
                             hover:text-emerald-300"
                >
                  priyankapurushotham5@gmail.com
                </a>
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Rohit B V</dt>
              <dd>
                <a
                  href="mailto:rohitbv.vips@gmail.com"
                  className="text-emerald-400 underline underline-offset-2
                             hover:text-emerald-300"
                >
                  rohitbv.vips@gmail.com
                </a>
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Source</dt>
              <dd>
                <a
                  href="https://github.com/Priyanka-Purushotham5/screenplay-clearance-agent"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-emerald-400 underline underline-offset-2
                             hover:text-emerald-300"
                >
                  github.com/Priyanka-Purushotham5
                </a>
              </dd>
            </div>
          </dl>
          <Link
            href="/upload"
            className="mt-6 block rounded-lg bg-emerald-600 px-4 py-2.5 text-center
                       text-sm font-semibold text-white transition-colors
                       hover:bg-emerald-500"
          >
            Upload a screenplay
          </Link>
        </div>
      </div>
    </Section>
  );
}

function LandingFooter() {
  return (
    <footer className="border-t border-slate-800 px-6 py-8">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3 text-xs
                      text-slate-500">
        <Logo size={20} />
        <span className="font-medium text-slate-300">Script to Clearance</span>
        <span aria-hidden>·</span>
        <span>Screenplay rights clearance, with sources</span>
        <span className="ml-auto">Research, not legal advice.</span>
      </div>
    </footer>
  );
}
