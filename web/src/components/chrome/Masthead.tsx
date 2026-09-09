import { NavBar } from "@/components/chrome/NavBar";

/**
 * The application bar. A mark, a wordmark, and the sections as pills.
 *
 * The centred display wordmark over a hairline rule is gone. That is a masthead, and a
 * masthead announces a publication once at the top of a document; this is an interface a
 * reader moves around inside, so the identity shrinks into a bar that stays with them and
 * the space goes to the content instead.
 *
 * The wordmark is the document's only `<h1>`; each page's own title is an `<h2>` and each
 * card heading an `<h3>`, giving one valid descending outline with "Kardamow" at its top.
 */

export const SCREENS = [
  { href: "/", label: "Overview" },
  { href: "/balances", label: "Balances" },
  { href: "/oil-math", label: "Oil math" },
  { href: "/prices", label: "Prices" },
  { href: "/supply", label: "Supply" },
  { href: "/gas", label: "Gas" },
  { href: "/flows", label: "Flows" },
  { href: "/curves", label: "Curves" },
  { href: "/positioning", label: "Positioning" },
  { href: "/vessels", label: "Vessels" },
  { href: "/events", label: "Events" },
  { href: "/sanctions", label: "Sanctions" },
] as const;

export function Masthead({ active }: { active?: string }) {
  return <NavBar active={active} />;
}
