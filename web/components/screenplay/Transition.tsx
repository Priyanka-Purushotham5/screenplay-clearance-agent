import type { BlockProps } from "./block";

export default function Transition({ children, className, ...rest }: BlockProps) {
  return (
    <div
      {...rest}
      className={["font-mono text-right my-4 px-2", className ?? ""].join(" ")}
    >
      {children}
    </div>
  );
}
