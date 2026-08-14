import type { BlockProps } from "./block";

export default function SceneHeading({ children, className, ...rest }: BlockProps) {
  return (
    <div
      {...rest}
      className={[
        "font-mono font-bold uppercase w-full mt-8 mb-2 px-2 py-1 rounded",
        "bg-slate-800 text-slate-100",
        className ?? "",
      ].join(" ")}
    >
      {children}
    </div>
  );
}
