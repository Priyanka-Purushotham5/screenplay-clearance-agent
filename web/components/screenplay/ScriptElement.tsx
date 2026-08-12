import type { ScriptElement as ScriptElementType } from "@/lib/api-types";
import SceneHeading from "./SceneHeading";
import ActionBlock from "./ActionBlock";
import CharacterCue from "./CharacterCue";
import DialogueLine from "./DialogueLine";
import Parenthetical from "./Parenthetical";
import Transition from "./Transition";

interface Props {
  element: ScriptElementType;
  highlighted?: boolean;
}

export default function ScriptElement({ element, highlighted }: Props) {
  const sharedProps = {
    "data-element-id": element.id,
    highlighted,
    text: element.text,
  };

  switch (element.type) {
    case "scene_heading":
      return <SceneHeading {...sharedProps} />;
    case "action":
      return <ActionBlock {...sharedProps} />;
    case "character":
      return <CharacterCue {...sharedProps} />;
    case "dialogue":
      return <DialogueLine {...sharedProps} />;
    case "parenthetical":
      return <Parenthetical {...sharedProps} />;
    case "transition":
      return <Transition {...sharedProps} />;
    default:
      return (
        <div data-element-id={element.id} className="font-mono my-1 px-2">
          {element.text}
        </div>
      );
  }
}
