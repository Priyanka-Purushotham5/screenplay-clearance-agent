"use client";

import Link from "next/link";
import { useScripts } from "@/lib/hooks/useScripts";
import { useScenes } from "@/lib/hooks/useScenes";
import { isInFlight } from "@/lib/hooks/useRun";
import type { ScriptSummary } from "@/lib/api-types";

/**
 * The scripts list, and the scenes of whichever script is open.
 *
 * Everything in the database, because there is one user and it is all theirs.
 * The heading says "Scripts" rather than "your scripts" — the second phrasing
 * would imply an isolation that does not exist yet, and that is not a claim to
 * make casually in a product about rights.
 */
export default function ScriptSidebar({ activeScriptId }: { activeScriptId?: string }) {
  const { data, isPending, isError } = useScripts();
  const scripts = data?.scripts ?? [];

  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-slate-800
                      bg-slate-950 md:flex">
      <div className="flex items-center px-4 pb-2 pt-3 text-[10.5px] font-bold
                      uppercase tracking-wider text-slate-500">
        Scripts
        <Link
          href="/upload"
          title="Upload a screenplay"
          className="ml-auto text-base leading-none text-slate-400 hover:text-slate-100"
        >
          +
        </Link>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        {isPending && <p className="px-2 py-1 text-xs text-slate-500">Loading…</p>}
        {isError && (
          <p className="px-2 py-1 text-xs text-accent-red">Could not load scripts.</p>
        )}
        {!isPending && !isError && scripts.length === 0 && (
          <p className="px-2 py-1 text-xs text-slate-500">
            No scripts yet.{" "}
            <Link href="/upload" className="text-emerald-400 underline underline-offset-2">
              Upload one
            </Link>{" "}
            to begin.
          </p>
        )}
        {scripts.map((script) => (
          <ScriptRow
            key={script.script_id}
            script={script}
            active={script.script_id === activeScriptId}
          />
        ))}
      </div>
    </aside>
  );
}

function ScriptRow({ script, active }: { script: ScriptSummary; active: boolean }) {
  const run = script.latest_run;
  // The most useful destination is the findings, when there are findings to
  // see. Otherwise the script itself, which is where the run button lives.
  const href =
    run && run.findings > 0 ? `/runs/${run.run_id}` : `/scripts/${script.script_id}`;

  return (
    <div className="mb-0.5">
      <Link
        href={href}
        // Several scripts can share a title — the verify harness uploads one
        // called "verify c8" on every run — so the upload time is what tells
        // them apart. In the tooltip rather than the row: at 208px wide, a
        // date and a page count together leave no room for the name.
        title={`${script.title} · uploaded ${new Date(script.uploaded_at).toLocaleString()}`}
        className={[
          "flex items-baseline gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
          active
            ? "bg-slate-900 font-semibold text-slate-100"
            : "text-slate-300 hover:bg-slate-900",
        ].join(" ")}
      >
        <RunDot run={run} />
        <span className="truncate">{script.title}</span>
        <span className="ml-auto shrink-0 text-[10px] text-slate-500">
          {script.page_count}p
        </span>
      </Link>
      {active && <SceneList scriptId={script.script_id} />}
    </div>
  );
}

/** Never run · working · complete · failed, in four pixels. */
function RunDot({ run }: { run: ScriptSummary["latest_run"] }) {
  const colour = !run
    ? "bg-slate-600"
    : isInFlight(run.status)
      ? "bg-amber-400 animate-pulse"
      : run.status === "failed"
        ? "bg-red-500"
        : "bg-emerald-500";
  const label = !run
    ? "Not yet run"
    : isInFlight(run.status)
      ? `Running: ${run.status}`
      : run.status === "failed"
        ? "Last run failed"
        : `${run.findings} findings`;
  return (
    <span
      title={label}
      aria-label={label}
      className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${colour}`}
    />
  );
}

/**
 * Scenes of the open script. Clicking one scrolls the script pane.
 *
 * The pane is virtualised, so an anchor link cannot reach a scene that is not
 * currently rendered. A window event is the smallest thing that crosses from
 * the shell to a pane the shell does not own — see ScriptPane's listener.
 */
function SceneList({ scriptId }: { scriptId: string }) {
  const { data } = useScenes(scriptId);
  const scenes = data?.scenes ?? [];
  if (scenes.length === 0) return null;

  return (
    <ul className="mb-1 ml-3 list-none border-l border-slate-800 pl-2">
      {scenes.map((scene) => (
        <li key={scene.id}>
          <button
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent("clearance:goto-page", { detail: scene.page_start }),
              )
            }
            className="flex w-full items-baseline gap-2 rounded px-2 py-1 text-left
                       text-xs text-slate-400 hover:bg-slate-900 hover:text-slate-200"
          >
            <span className="truncate">Scene {scene.number}</span>
            <span className="ml-auto shrink-0 text-[10px] text-slate-500">
              p{scene.page_start}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
