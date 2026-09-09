import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Providers from "./providers";
import AppShell from "@/components/shell/AppShell";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Script to Clearance",
  description:
    "Find every rights issue in a screenplay, with the evidence behind each call.",
};

/**
 * Applied before the first paint, so a returning dark-mode user never sees a
 * white flash. It has to be a blocking inline script: anything that runs after
 * hydration runs after the browser has already painted the wrong colours.
 */
const THEME_SCRIPT = `
(function () {
  try {
    var t = localStorage.getItem("theme");
    if (!t) t = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    document.documentElement.dataset.theme = t;
  } catch (e) {
    document.documentElement.dataset.theme = "dark";
  }
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      // THEME_SCRIPT below sets data-theme on this element before React
      // hydrates — that is what stops a returning dark-mode user seeing a white
      // flash. It also means the DOM React finds no longer matches the HTML the
      // server sent, and React reports that as a hydration error.
      //
      // This suppression covers ONLY this element's own attributes. A real
      // mismatch anywhere inside the tree still warns, which is the difference
      // between silencing a warning and answering it.
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="h-full flex flex-col">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
