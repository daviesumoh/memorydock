import { Suspense } from "react";
import { connection } from "next/server";
import { withAuth } from "@workos-inc/authkit-nextjs";

import { signOutAction } from "@/app/auth-actions";
import { Button } from "@/components/ui/button";

import { NavLinkList, NavLinks } from "./nav-links";

async function SignedInUser() {
  // Unsealing the session checks its expiry against the clock, so this must
  // render per request rather than in a prefetch.
  await connection();
  const { user } = await withAuth({ ensureSignedIn: true });
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-muted-foreground">{user.email}</span>
      <form action={signOutAction}>
        <Button type="submit" variant="outline" size="sm">
          Sign out
        </Button>
      </form>
    </div>
  );
}

export function ConsoleHeader() {
  return (
    <header className="border-b">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-6 px-6 py-3">
        <div className="flex items-center gap-6">
          <span className="font-semibold">memorydock</span>
          <Suspense fallback={<NavLinkList pathname={null} />}>
            <NavLinks />
          </Suspense>
        </div>
        <Suspense fallback={<span className="text-muted-foreground text-sm">Checking your session…</span>}>
          <SignedInUser />
        </Suspense>
      </div>
    </header>
  );
}
