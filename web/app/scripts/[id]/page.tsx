"use client";

import { use, useRef } from "react";
import { useScript } from "@/lib/hooks/useScript";
import { useScenes } from "@/lib/hooks/useScenes";
import ScriptPane, { type ScriptPaneHandle } from "@/components/screenplay/ScriptPane";
import type { Scene, Script } from "@/lib/api-types";

// ---------------------------------------------------------------------------
// Fixture imports (used when id === "demo")
// ---------------------------------------------------------------------------
import fixtureMeta from "@/lib/fixtures/script-meta.json";
import fixtureScenes from "@/lib/fixtures/script-scenes.json";

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function ScriptHeader({ script }: { script: Script }) {
  return (
    <header className="flex items-center gap-6 border-b border-zinc-200 bg-white px-6 py-3 shrink-0">
      <h1 className="font-semibold text-zinc-900 truncate">{script.title}</h1>
      <span className="text-sm text-zinc-500 whitespace-nowrap">
        {script.page_count} pages
      </span>
      <span className="text-sm text-zinc-500 whitespace-nowrap">
        {script.scene_count} scenes
      </span>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ScriptPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const paneRef = useRef<ScriptPaneHandle>(null);

  // Demo mode — bypass API entirely
  const isDemo = id === "demo";

  const scriptQuery = useScript(isDemo ? "" : id);
  const scenesQuery = useScenes(isDemo ? "" : id);

  const script: Script | undefined = isDemo
    ? (fixtureMeta as Script)
    : scriptQuery.data;

  const scenes: Scene[] | undefined = isDemo
    ? (fixtureScenes as { scenes: Scene[] }).scenes
    : scenesQuery.data?.scenes;

  // Loading state
  const isLoading = !isDemo && (scriptQuery.isPending || scenesQuery.isPending);

  // Error state
  const isError = !isDemo && (scriptQuery.isError || scenesQuery.isError);
  const errorMsg =
    scriptQuery.error?.message ?? scenesQuery.error?.message ?? "Unknown error";

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center text-zinc-400 text-sm">
        Loading script…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-1 items-center justify-center text-red-500 text-sm">
        Failed to load script: {errorMsg}
      </div>
    );
  }

  if (!script || !scenes) {
    return (
      <div className="flex flex-1 items-center justify-center text-zinc-400 text-sm">
        Script not found.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <ScriptHeader script={script} />
      <div className="flex-1 min-h-0 max-w-3xl w-full mx-auto px-4 py-2 h-full">
        <ScriptPane ref={paneRef} scenes={scenes} />
      </div>
    </div>
  );
}
