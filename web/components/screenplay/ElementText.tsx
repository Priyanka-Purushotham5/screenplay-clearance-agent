"use client";

import { Fragment } from "react";
import type { Segment } from "@/lib/highlight";
import { useSelection } from "@/components/linking/LinkingProvider";
import {
  FLASH_CLASS,
  MARK_CLASS,
  MARK_SELECTED_CLASS,
  markVars,
} from "@/lib/risk";

/**
 * Renders pre-segmented element text. The only place <mark> exists in the app.
 */
export default function ElementText({ segments }: { segments: Segment[] }) {
  const { selection, select } = useSelection();

  return (
    <>
      {segments.map((seg) => {
        if (seg.kind === "text") {
          return <Fragment key={seg.key}>{seg.text}</Fragment>;
        }

        const isSelected = seg.findingId === selection.findingId;

        return (
          <mark
            // The token in the key remounts the node on every re-selection, so
            // the CSS animation restarts from frame 0 — including when the same
            // finding is clicked twice. No timers anywhere.
            key={isSelected ? `${seg.key}#${selection.token}` : seg.key}
            data-finding-id={seg.findingId}
            role="button"
            tabIndex={0}
            aria-label={`${seg.risk} risk: ${seg.text}`}
            aria-pressed={isSelected}
            onClick={(e) => {
              e.stopPropagation();
              select(seg.findingId, "script");
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                select(seg.findingId, "script");
              }
            }}
            style={markVars(seg.risk, isSelected)}
            className={[
              MARK_CLASS,
              isSelected ? MARK_SELECTED_CLASS : "",
              isSelected ? FLASH_CLASS : "",
            ].join(" ")}
          >
            {seg.text}
          </mark>
        );
      })}
    </>
  );
}
