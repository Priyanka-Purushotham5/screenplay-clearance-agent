"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "@/components/brand/Logo";
import ThemeToggle from "@/components/shell/ThemeToggle";
import ScriptSidebar from "@/components/shell/ScriptSidebar";
import RunStatusBar from "@/components/shell/StatusBar";
import Footer from "@/components/shell/Footer";
import { useRun, isInFlight } from "@/lib/hooks/useRun";

/**
 * One frame around every page: mark and name top left, theme toggle top right,
 * scripts down the left, a bottom strip, content in the middle.
 *
 * The shell owns the bottom strip and decides what belongs there. On a run it
 * is a live status bar; everywhere else it is a footer. Letting each page
 * supply its own would mean threading a slot through three routes to end up
 * with the same two answers.
 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";

  // The landing page is a front door, not a workspace. A first-time visitor
  // has no scripts, so the sidebar would be an empty box explaining nothing,
  // and the page brings its own footer. Same header either way, so the
  // identity does not change under someone walking in.
  const marketing = pathname === "/";

  const runId = pathname.startsWith("/runs/") ? pathname.split("/")[2] : undefined;
  const scriptFromPath = pathname.startsWith("/scripts/")
    ? pathname.split("/")[2]
    : undefined;

  // On a run page the active script is not in the URL — the run knows it.
  // `useRun` is already fetching for the page itself, and React Query serves
  // both callers from one request.
  const { data: run } = useRun(runId ?? "");
  const activeScriptId = scriptFromPath ?? run?.script_id;

  return (
    <div className="flex h-full flex-col bg-slate-950">
      <header className="flex shrink-0 items-center gap-4 border-b border-slate-800
                         bg-slate-900 px-5 py-3">
        <Link href="/" className="flex items-center gap-3 text-slate-100">
          {/* The film runs while a run does, so the mark is also the status
              light. At rest it is the plain three-frame logo. */}
          <Logo size={64} animated={isInFlight(run?.status)} />
          {/*
            The wordmark carries the same three ratings as a gradient, left to
            right across the whole phrase. Per-word colouring was the obvious
            alternative and it reads as three labels; one pass reads as film.
            See .clearance-wordmark in globals.css, which also sets the solid
            fallback for browsers without background-clip:text.
          */}
          <span className="clearance-wordmark text-2xl font-bold tracking-tight
                           whitespace-nowrap sm:text-[1.9rem]">
            Script to Clearance
          </span>
        </Link>
        <div className="ml-auto flex items-center gap-2">
          {marketing && (
            <Link
              href="/upload"
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold
                         text-white transition-colors hover:bg-emerald-500"
            >
              Open the app
            </Link>
          )}
          <ThemeToggle />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {!marketing && <ScriptSidebar activeScriptId={activeScriptId} />}
        <main className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</main>
      </div>

      {marketing ? null : runId ? <RunStatusBar runId={runId} /> : <Footer />}
    </div>
  );
}
