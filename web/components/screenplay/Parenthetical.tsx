import type { BlockProps } from "./block";

export default function Parenthetical({ children, className, ...rest }: BlockProps) {
  return (
    <div
      {...rest}
      className={["font-mono italic mx-auto w-2/5 my-0", className ?? ""].join(" ")}
    >
      {children}
    </div>
  );
}
