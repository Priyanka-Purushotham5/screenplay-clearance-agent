import type { CSSProperties, ReactNode } from "react";

/**
 * Shared contract for the six screenplay block components.
 *
 * They render whatever children they're given and own nothing but their own
 * layout classes — highlight state is decided upstream in ScriptElement and
 * arrives as `className`/`style`.
 */
export interface BlockProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  "data-element-id"?: string;
}
