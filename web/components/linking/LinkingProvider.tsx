"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { EMPTY_INDEX, type FindingIndex } from "@/lib/finding-index";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Which pane initiated the selection. Keeps the two panes from fighting: each
 *  scrolls only when the *other* one started it. */
export type SelectionSource = "findings" | "script" | "url";

export interface Selection {
  findingId: string | null;
  source: SelectionSource | null;
  /** Monotonic. Changes on EVERY select(), including re-selecting the same
   *  finding — that is what re-triggers the flash and the scroll. */
  token: number;
}

const EMPTY_SELECTION: Selection = { findingId: null, source: null, token: 0 };

interface SelectionApi {
  selection: Selection;
  select: (findingId: string, source: SelectionSource) => void;
  clear: () => void;
}

// Non-throwing defaults are load-bearing: /scripts/[id] renders ScriptPane with
// no provider and must keep working with zero highlights.
const SelectionCtx = createContext<SelectionApi>({
  selection: EMPTY_SELECTION,
  select: () => {},
  clear: () => {},
});

const FindingIndexCtx = createContext<FindingIndex>(EMPTY_INDEX);

export const useSelection = () => useContext(SelectionCtx);
export const useFindingIndex = () => useContext(FindingIndexCtx);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface Props {
  index: FindingIndex;
  children: ReactNode;
}

export function LinkingProvider({ index, children }: Props) {
  const counter = useRef(0);
  const [selection, setSelection] = useState<Selection>(EMPTY_SELECTION);

  const select = useCallback((findingId: string, source: SelectionSource) => {
    setSelection({ findingId, source, token: ++counter.current });
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("finding", findingId);
      // replaceState, not router.replace: a router navigation would trigger an
      // RSC round-trip for what is a purely visual selection. Next syncs this
      // into useSearchParams on its own. replace, not push, so Back leaves the
      // page rather than stepping through every highlight.
      window.history.replaceState(null, "", url);
    }
  }, []);

  const clear = useCallback(() => {
    setSelection({ ...EMPTY_SELECTION, token: ++counter.current });
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("finding");
      window.history.replaceState(null, "", url);
    }
  }, []);

  const api = useMemo<SelectionApi>(
    () => ({ selection, select, clear }),
    [selection, select, clear]
  );

  // Two contexts, not one: the index changes only when the findings query
  // resolves, while selection changes on every click. Splitting them means a
  // click never invalidates anything memoised on the index.
  return (
    <FindingIndexCtx.Provider value={index}>
      <SelectionCtx.Provider value={api}>{children}</SelectionCtx.Provider>
    </FindingIndexCtx.Provider>
  );
}

/**
 * Applies ?finding=<id> once both panes are mounted — the D8 demo landing
 * needs a judge's cold URL to open with the script already positioned.
 *
 * This runs the selection through exactly the same path a click takes, rather
 * than seeding the provider's initial state: at first commit the virtualiser
 * has not measured its scroll element yet and silently drops the scroll.
 * Render inside LinkingProvider, after the panes.
 */
export function DeepLinkSeed({ ready }: { ready: boolean }) {
  const { select } = useSelection();
  const done = useRef(false);

  useEffect(() => {
    if (done.current || !ready) return;
    const id = new URLSearchParams(window.location.search).get("finding");
    if (!id) return;
    done.current = true;
    select(id, "url");
  }, [ready, select]);

  return null;
}
