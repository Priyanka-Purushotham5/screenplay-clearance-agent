interface Props {
  text: string;
  "data-element-id"?: string;
  highlighted?: boolean;
}

export default function CharacterCue({ text, highlighted, ...rest }: Props) {
  return (
    <div
      {...rest}
      className={[
        "font-mono text-center mt-4 mb-0 uppercase",
        highlighted ? "bg-yellow-200" : "",
      ].join(" ")}
    >
      {text}
    </div>
  );
}
