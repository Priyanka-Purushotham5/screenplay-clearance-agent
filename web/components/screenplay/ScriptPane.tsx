"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useMemo,
} from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Scene, ScriptElement as ScriptElementType } from "@/lib/api-types";
import { useFindingIndex, useSelection } from "@/components/linking/LinkingProvider";
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
    // NOTE: a synthesised id can never match a finding's script_element_id, so a
    // finding located on an omitted heading falls back to page-level scrolling.
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

// A flat 40px estimate lands scrollToIndex badly off: action blocks wrap to
// three or four lines in this column width. Per-type estimates plus
// align: "center" give the reconcile loop enough tolerance.
const ESTIMATE: Record<ScriptElementType["type"], number> = {
  scene_heading: 60,
  action: 76,
  dialogue: 52,
  character: 24,
  parenthetical: 24,
  transition: 40,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ScriptPane = forwardRef<ScriptPaneHandle, Props>(
  function ScriptPane({ scenes }, ref) {
    const parentRef = useRef<HTMLDivElement>(null);

    const items = useMemo(() => flattenScenes(scenes), [scenes]);

    // O(1) element → row. The old items.findIndex() was an O(n) scan per call
    // on a list meant to hold thousands of rows.
    const indexByElementId = useMemo(() => {
      const m = new Map<string, number>();
      items.forEach((it, i) => m.set(it.element.id, i));
      return m;
    }, [items]);

    const virtualizer = useVirtualizer({
      count: items.length,
      getScrollElement: () => parentRef.current,
      estimateSize: (i) => ESTIMATE[items[i].element.type] ?? 40,
      overscan: 10,
    });

    const scrollToPage = (page: number) => {
      const index = items.findIndex((item) => item.element.page >= page);
      if (index !== -1) {
        virtualizer.scrollToIndex(index, { align: "start", behavior: "auto" });
      }
    };

    const scrollToElement = (id: string) => {
      const index = indexByElementId.get(id);
      if (index !== undefined) {
        virtualizer.scrollToIndex(index, { align: "center", behavior: "auto" });
      }
    };

    useImperativeHandle(ref, () => ({ scrollToPage, scrollToElement }));

    // -----------------------------------------------------------------------
    // Selection → scroll
    // -----------------------------------------------------------------------

    const { selection } = useSelection();
    const { byId } = useFindingIndex();
    const handledToken = useRef(0);
    // The retry chain deliberately outlives the effect that starts it: React
    // runs cleanup on every dependency change (and twice at mount under
    // StrictMode), which would otherwise cancel the retry a frame after it
    // begins — while the token guard prevents it from ever re-arming.
    const pendingRaf = useRef(0);

    useEffect(() => () => cancelAnimationFrame(pendingRaf.current), []);

    useEffect(() => {
      // The script pane scrolls only when the *other* pane started it —
      // otherwise clicking a mark would yank the text you're already reading.
      if (!selection.findingId || selection.source === "script") return;
      // The scroll is idempotent, but without this the effect would re-fire on
      // any unrelated dependency change and yank the reader back.
      if (selection.token === handledToken.current) return;
      handledToken.current = selection.token;

      const f = byId.get(selection.findingId);
      if (!f) return;

      const idx = f.script_element_id
        ? indexByElementId.get(f.script_element_id)
        : undefined;

      // Fallback: land on the page. The checklist only promises the page.
      const target =
        idx !== undefined
          ? { index: idx, align: "center" as const }
          : (() => {
              const p = items.findIndex((it) => it.element.page >= f.page);
              return p === -1 ? null : { index: p, align: "start" as const };
            })();

      if (!target) return;

      cancelAnimationFrame(pendingRaf.current);
      let frames = 0;

      // On a cold deep link (?finding=…) this effect runs in the commit that
      // mounts the pane, before the virtualiser has measured its scroll
      // element — the scroll is silently dropped. Retry until it takes.
      // behavior: "auto" throughout: virtual-core downgrades "smooth" to
      // "auto" itself once dynamic measurement moves the target, and an
      // instant jump plus the flash reads better than a long smooth scroll.
      const attempt = () => {
        const el = parentRef.current;
        if (!el) return;
        virtualizer.scrollToIndex(target.index, {
          align: target.align,
          behavior: "auto",
        });
        frames += 1;
        // scrollTop === 0 while aiming at a row that is not the first one means
        // the scroll did not land. Bounded so a genuine top-of-script target
        // costs a few harmless frames rather than spinning.
        if (el.scrollTop === 0 && target.index > 0 && frames < 20) {
          pendingRaf.current = requestAnimationFrame(attempt);
        }
      };

      // Deferred rather than called inline: scrollToIndex flushes synchronously,
      // and React warns when that happens inside a lifecycle method.
      pendingRaf.current = requestAnimationFrame(attempt);
    }, [
      selection.token,
      selection.findingId,
      selection.source,
      byId,
      indexByElementId,
      items,
      virtualizer,
    ]);

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------

    const virtualItems = virtualizer.getVirtualItems();
    const totalSize = virtualizer.getTotalSize();

    return (
      <div
        ref={parentRef}
        className="h-full overflow-y-auto bg-slate-950 text-slate-200"
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
                <ScriptElementComponent element={element} />
              </div>
            );
          })}
        </div>
      </div>
    );
  }
);

export default ScriptPane;
