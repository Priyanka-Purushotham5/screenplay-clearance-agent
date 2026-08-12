interface Props {
  text: string;
  "data-element-id"?: string;
  highlighted?: boolean;
}

export default function DialogueLine({ text, highlighted, ...rest }: Props) {
  return (
    <div
      {...rest}
      className={[
        "font-mono mx-auto w-3/5 my-1",
        highlighted ? "bg-yellow-200" : "",
      ].join(" ")}
    >
      {text}
    </div>
  );
}
