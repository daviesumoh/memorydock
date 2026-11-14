import { getSignInUrl } from "@workos-inc/authkit-nextjs";
import { redirect } from "next/navigation";

// WorkOS's Initiate login URI points here, so invitations and password resets
// that start outside the console can begin a sign-in.
export async function GET() {
  redirect(await getSignInUrl());
}
