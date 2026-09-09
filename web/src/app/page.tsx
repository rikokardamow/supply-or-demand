import { redirect } from "next/navigation";

/** Balances is the landing screen -- the report an analyst opens first. */
export default function Home() {
  redirect("/balances");
}
