interface Props {
  text: string;
  "data-element-id"?: string;
  highlighted?: boolean;
}

export default function Transition({ text, highlighted, ...rest }: Props) {
  return (
    <div
      {...rest}
      className={[
        "font-mono text-right my-4 px-2",
        highlighted ? "bg-yellow-200" : "",
      ].join(" ")}
    >
      {text}
    </div>
  );
}
