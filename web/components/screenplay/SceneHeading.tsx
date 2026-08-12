interface Props {
  text: string;
  "data-element-id"?: string;
  highlighted?: boolean;
}

export default function SceneHeading({ text, highlighted, ...rest }: Props) {
  return (
    <div
      {...rest}
      className={[
        "font-mono font-bold uppercase w-full mt-8 mb-2 px-2 py-1 rounded",
        highlighted ? "bg-yellow-200" : "bg-zinc-100",
      ].join(" ")}
    >
      {text}
    </div>
  );
}
