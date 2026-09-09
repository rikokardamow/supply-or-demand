import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "Kardamow — independent research on energy, macro and geopolitics",
  description:
    "Independent, irreverent research on energy, macro and geopolitics, built on primary sources.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB" className={inter.variable}>
      <body>
        {/* Lighting first, grain over it, content above both. */}
        <div className="aurora" aria-hidden>
          <div className="orb orb-a" />
          <div className="orb orb-b" />
          <div className="orb orb-c" />
        </div>
        <div className="grain" aria-hidden />
        <div className="layer">{children}</div>
      </body>
    </html>
  );
}
