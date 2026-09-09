import { NotBuiltYet } from "@/components/chrome/NotBuiltYet";

export default function HormuzPage() {
  return (
    <NotBuiltYet
      title="Hormuz"
      href="/hormuz"
      session="Spec 33.01, Session C"
      summary="The strait map needs serving.vessel_latest, and the GRP panel needs serving.grp_scores — both tables exist but are empty, blocked on Spec 11 (AIS) and Spec 28 (GRP), neither of which is built in this repo."
    />
  );
}
