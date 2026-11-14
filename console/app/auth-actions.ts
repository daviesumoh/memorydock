"use server";

import { signOut } from "@workos-inc/authkit-nextjs";

// A server action (POST) rather than a GET route, so link prefetching or an
// <img> pointed at it cannot end someone's session.
export async function signOutAction() {
  await signOut();
}
