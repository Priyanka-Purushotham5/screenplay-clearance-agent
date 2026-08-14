"use client";

import { use, useRef } from "react";
import { useScript } from "@/lib/hooks/useScript";
import { useScenes } from "@/lib/hooks/useScenes";
import ScriptPane, { type ScriptPaneHandle } from "@/components/screenplay/ScriptPane";

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function ScriptHeader({
  title,
  pageCount,
  sceneCount,
}: {
  title: string;
  pageCount: number;
  sceneCount: number;
}) {
  return (
    <header className="flex items-center gap-6 border-b border-slate-800 bg-slate-900 px-6 py-3 shrink-0">
      <h1 className="font-semibold text-slate-100 truncate">{title}</h1>
      <span className="text-sm text-slate-500 whitespace-nowrap">{pageCount} pages</span>
      <span className="text-sm text-slate-500 whitespace-nowrap">{sceneCount} scenes</span>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

// Rendered without a LinkingProvider — the selection and finding-index contexts
// fall back to inert defaults, so the script reads with no highlights at all.
// That is the correct pre-run view.

export default function ScriptPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const paneRef = useRef<ScriptPaneHandle>(null);

  const scriptQuery = useScript(id);
  const scenesQuery = useScenes(id);

  if (scriptQuery.isPending || scenesQuery.isPending) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950 text-slate-500 text-sm">
        Loading script…
      </div>
    );
  }

  if (scriptQuery.isError || scenesQuery.isError) {
    const errorMsg =
      scriptQuery.error?.message ?? scenesQuery.error?.message ?? "Unknown error";
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950 text-red-400 text-sm">
        Failed to load script: {errorMsg}
      </div>
    );
  }

  const script = scriptQuery.data;
  const scenes = scenesQuery.data?.scenes;

  if (!script || !scenes) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950 text-slate-500 text-sm">
        Script not found.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-950">
      <ScriptHeader
        title={script.title}
        pageCount={script.page_count}
        sceneCount={script.scene_count}
      />
      <div className="flex-1 min-h-0 max-w-3xl w-full mx-auto px-4 py-2">
        <ScriptPane ref={paneRef} scenes={scenes} />
      </div>
    </div>
  );
}
