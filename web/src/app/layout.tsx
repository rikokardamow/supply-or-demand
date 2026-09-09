import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";
import "@/theme/tokens.css";

/**
 * One family, Inter, for headings and figures alike.
 *
 * The serif heading face is gone from this surface. A Lora heading over an Inter figure is
 * the signature of a document, and this is an interface -- it was the loudest single thing
 * making the site read as a newspaper someone had put charts in. `core/design.py` still
 * pairs Lora with Inter for the Streamlit app and the exported exhibits, which are
 * documents and should stay that way.
 *
 * Self-hosted by `next/font`, so the app stays legible with Google Fonts blocked.
 */
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kardamow",
  description: "Energy and macro research — data.kardamow.com",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-GB" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
