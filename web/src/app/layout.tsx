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
    <html lang="en-GB" className={`${inter.variable} ${lora.variable}`}>
      <body>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 1.25rem 3rem" }}>
          {children}
        </div>
      </body>
    </html>
  );
}
