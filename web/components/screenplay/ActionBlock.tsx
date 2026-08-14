import type { BlockProps } from "./block";

export default function ActionBlock({ children, className, ...rest }: BlockProps) {
  return (
    <div
      {...rest}
      className={["font-mono w-full my-2 px-2", className ?? ""].join(" ")}
    >
      {children}
    </div>
  );
}
