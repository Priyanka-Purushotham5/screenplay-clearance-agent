"use client";

import { useMemo } from "react";
import type { ScriptElement as ScriptElementType } from "@/lib/api-types";
import { segmentElementText } from "@/lib/highlight";
import { useFindingIndex, useSelection } from "@/components/linking/LinkingProvider";
import { BLOCK_FLASH_CLASS, blockVars } from "@/lib/risk";
import ElementText from "./ElementText";
import SceneHeading from "./SceneHeading";
import ActionBlock from "./ActionBlock";
import CharacterCue from "./CharacterCue";
import DialogueLine from "./DialogueLine";
import Parenthetical from "./Parenthetical";
import Transition from "./Transition";

interface Props {
  element: ScriptElementType;
}

export default function ScriptElement({ element }: Props) {
  const { mentionsByElement } = useFindingIndex();
  const { selection } = useSelection();

  const mentions = mentionsByElement.get(element.id);

  // Both deps are referentially stable for a given findings payload, so this
  // does not recompute when the selection changes — only the mark classes do.
  const seg = useMemo(
    () => segmentElementText(element.text, mentions),
    [element.text, mentions]
  );

  // Element-level fallback: the selected finding is on this element but its
  // span could not be resolved (null/unrecoverable offsets, or it lost an
  // overlap). Flash the whole block instead of nothing.
  const orphan = selection.findingId
    ? seg.unresolved.find((m) => m.findingId === selection.findingId)
    : undefined;

  const shared = {
    "data-element-id": element.id,
    className: orphan ? `${BLOCK_FLASH_CLASS} rounded` : "",
    style: orphan ? blockVars(orphan.risk) : undefined,
    children: <ElementText segments={seg.segments} />,
  };

  // Remounting restarts the block animation, the same trick ElementText uses
  // for marks. Passed explicitly — React 19 warns on a key spread through props.
  const flashKey = orphan ? `blk#${selection.token}` : "blk";

  switch (element.type) {
    case "scene_heading":
      return <SceneHeading key={flashKey} {...shared} />;
    case "action":
      return <ActionBlock key={flashKey} {...shared} />;
    case "character":
      return <CharacterCue key={flashKey} {...shared} />;
    case "dialogue":
      return <DialogueLine key={flashKey} {...shared} />;
    case "parenthetical":
      return <Parenthetical key={flashKey} {...shared} />;
    case "transition":
      return <Transition key={flashKey} {...shared} />;
    default:
      return (
        <div
          key={flashKey}
          data-element-id={element.id}
          style={shared.style}
          className={["font-mono my-1 px-2", shared.className].join(" ")}
        >
          {shared.children}
        </div>
      );
  }
}
