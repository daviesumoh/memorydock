import { Suspense } from "react";

import { LoadingRows } from "@/components/view-states";

import { SessionList } from "./session-list";

export default function SessionsPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold">Sessions</h1>
      <p className="text-muted-foreground text-sm">
        Each agent client you sign in with gets a session. A paused session can still read; a revoked one is refused on
        its next call, for good.
      </p>
      <Suspense fallback={<LoadingRows label="Loading sessions" />}>
        <SessionList />
      </Suspense>
    </>
  );
}
