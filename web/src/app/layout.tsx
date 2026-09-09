import type { Metadata } from "next";
import { Inter, Lora } from "next/font/google";

import "./globals.css";
import "@/theme/tokens.css";

/**
 * Lora for headings, Inter for body copy and every number -- the pairing
 * `core/design.py` defines and `apps/dashboard` already uses. Both are self-hosted by
 * `next/font`, so the app stays legible with Google Fonts blocked, which is the same
 * reason `core/design.py` carries real fallback stacks.
 */
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const lora = Lora({
  variable: "--font-lora",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kardamow",
  description: "Energy and macro research — data.kardamow.com",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // No measure wrapper here: the masthead and ticker rail tint the full window width
    // while their contents stay on the page measure, and a container around everything
    // would stop the tint at 1200px and turn the shell into a box. `main` carries the
    // measure instead -- see globals.css.
    <html lang="en-GB" className={`${inter.variable} ${lora.variable}`}>
      <body>{children}</body>
    </html>
  );
}
