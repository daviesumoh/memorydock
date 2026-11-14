import { Suspense } from "react";
import { connection } from "next/server";
import { withAuth } from "@workos-inc/authkit-nextjs";

import { signOutAction } from "./auth-actions";

async function SignedInAs() {
  // Unsealing the session checks its expiry against the clock, so this must
  // render per request rather than in a prefetch.
  await connection();
  const { user } = await withAuth({ ensureSignedIn: true });
  return (
    <div className="flex items-center gap-4">
      <p>
        Signed in as <span className="font-medium">{user.email}</span>
      </p>
      <form action={signOutAction}>
        <button
          type="submit"
          className="rounded border border-foreground/20 px-3 py-1 hover:bg-foreground/5 focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          Sign out
        </button>
      </form>
    </div>
  );
}

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <h1 className="text-2xl font-semibold">memorydock</h1>
      <Suspense fallback={<p>Checking your session…</p>}>
        <SignedInAs />
      </Suspense>
    </main>
  );
}
