import { NotBuiltYet } from "@/components/chrome/NotBuiltYet";

export default function CurvesPage() {
  return (
    <NotBuiltYet
      title="Curves"
      href="/curves"
      session="Spec 33.04, stubbed"
      summary="The forward strip and spread ladder. serving.spreads holds 132,546 rows, but its EIA source was discontinued in April 2024 — the panel will read as stale until IBKR or a Barchart drop lands."
    />
  );
}
