interface Props {
  text: string;
  "data-element-id"?: string;
  highlighted?: boolean;
}

export default function ActionBlock({ text, highlighted, ...rest }: Props) {
  return (
    <div
      {...rest}
      className={[
        "font-mono w-full my-2 px-2",
        highlighted ? "bg-yellow-200" : "",
      ].join(" ")}
    >
      {text}
    </div>
  );
}
