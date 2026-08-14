import type { BlockProps } from "./block";

export default function CharacterCue({ children, className, ...rest }: BlockProps) {
  return (
    <div
      {...rest}
      className={[
        "font-mono text-center mt-4 mb-0 uppercase",
        className ?? "",
      ].join(" ")}
    >
      {children}
    </div>
  );
}
