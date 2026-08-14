import type { BlockProps } from "./block";

export default function DialogueLine({ children, className, ...rest }: BlockProps) {
  return (
    <div
      {...rest}
      className={["font-mono mx-auto w-3/5 my-1", className ?? ""].join(" ")}
    >
      {children}
    </div>
  );
}
