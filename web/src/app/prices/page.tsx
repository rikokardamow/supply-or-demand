import { redirect } from "next/navigation";

/** Crude is the default ticker; the rest are reachable from the ticker nav. */
export default function PricesIndex() {
  redirect("/prices/cl");
}
