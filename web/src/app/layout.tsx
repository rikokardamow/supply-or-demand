import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import "./globals.css";
import "@/theme/tokens.css";

/**
 * Two families: mono for the terminal, Inter for running prose.
 *
 * JetBrains Mono carries every label, figure, heading and table cell -- the whole terminal
 * chrome, matching `--font` in `theme/tokens.css`. Inter survives only for `.prose`: a page
 * dek or a source note, where a paragraph set in mono is the one piece of the real thing
 * not worth keeping. The serif heading face is gone from this surface entirely -- a Lora
 * heading over an Inter figure is the signature of a document, and this is an interface.
 * `core/design.py` still pairs Lora with Inter for the Streamlit app and the exported
 * exhibits, which are documents and should stay that way.
 *
 * Both self-hosted by `next/font`, so the app stays legible with Google Fonts blocked.
 */
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kardamow",
  description: "Energy and macro research — data.kardamow.com",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-GB" className={`${inter.variable} ${jetBrainsMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
