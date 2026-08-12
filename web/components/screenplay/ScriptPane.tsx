"use client";

import {
  forwardRef,
  useImperativeHandle,
  useRef,
  useMemo,
} from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Scene, ScriptElement as ScriptElementType } from "@/lib/api-types";
import ScriptElementComponent from "./ScriptElement";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ScriptPaneHandle {
  scrollToPage(page: number): void;
  scrollToElement(id: string): void;
}

interface Props {
  scenes: Scene[];
  highlightedElementId?: string;
}

// ---------------------------------------------------------------------------
// Flatten scenes into a single ordered list of elements
// ---------------------------------------------------------------------------

interface FlatItem {
  element: ScriptElementType;
}

function flattenScenes(scenes: Scene[]): FlatItem[] {
  const items: FlatItem[] = [];
  for (const scene of scenes) {
    // scene_heading is already the first element in scene.elements (seq 0),
    // but if the API omits it we synthesise one so scenes are always visually separated.
    const hasHeading = scene.elements.some((e) => e.type === "scene_heading");
    if (!hasHeading) {
      items.push({
        element: {
          id: `heading-${scene.id}`,
          scene_id: scene.id,
          seq: -1,
          type: "scene_heading",
          character: null,
          page: scene.page_start,
          text: scene.heading,
        },
      });
    }
    const sorted = [...scene.elements].sort((a, b) => a.seq - b.seq);
    for (const el of sorted) {
      items.push({ element: el });
    }
  }
  return items;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ScriptPane = forwardRef<ScriptPaneHandle, Props>(
  function ScriptPane({ scenes, highlightedElementId }, ref) {
    const parentRef = useRef<HTMLDivElement>(null);

    const items = useMemo(() => flattenScenes(scenes), [scenes]);

    const virtualizer = useVirtualizer({
      count: items.length,
      getScrollElement: () => parentRef.current,
      estimateSize: () => 40,
      overscan: 10,
    });

    // -----------------------------------------------------------------------
    // Imperative handle
    // -----------------------------------------------------------------------

    useImperativeHandle(ref, () => ({
      scrollToPage(page: number) {
        const index = items.findIndex((item) => item.element.page >= page);
        if (index !== -1) {
          virtualizer.scrollToIndex(index, { align: "start" });
        }
      },
      scrollToElement(id: string) {
        const index = items.findIndex((item) => item.element.id === id);
        if (index !== -1) {
          virtualizer.scrollToIndex(index, { align: "center" });
        }
      },
    }));

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------

    const virtualItems = virtualizer.getVirtualItems();
    const totalSize = virtualizer.getTotalSize();

    return (
      <div
        ref={parentRef}
        className="h-full overflow-y-auto bg-white"
      >
        {/* Spacer that gives the virtualiser its full height */}
        <div style={{ height: totalSize, position: "relative" }}>
          {virtualItems.map((vItem) => {
            const { element } = items[vItem.index];
            return (
              <div
                key={element.id}
                data-index={vItem.index}
                ref={virtualizer.measureElement}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${vItem.start}px)`,
                }}
              >
                <ScriptElementComponent
                  element={element}
                  highlighted={element.id === highlightedElementId}
                />
              </div>
            );
          })}
        </div>
      </div>
    );
  }
);

export default ScriptPane;
