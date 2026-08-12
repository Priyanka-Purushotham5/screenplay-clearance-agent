interface Props {
  text: string;
  "data-element-id"?: string;
  highlighted?: boolean;
}

export default function Parenthetical({ text, highlighted, ...rest }: Props) {
  return (
    <div
      {...rest}
      className={[
        "font-mono italic mx-auto w-2/5 my-0",
        highlighted ? "bg-yellow-200" : "",
      ].join(" ")}
    >
      {text}
    </div>
  );
}
