"use client";

import { useEffect, useState, type ReactNode } from "react";

// Production builds never mock, even if the variable is set by mistake:
// mocked data must not be shown as real.
export const mockingEnabled =
  process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_API_MOCKING === "enabled";

// Holds the page back until the service worker is intercepting, so no request
// slips past to the real gateway while it starts.
export function MockingGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!mockingEnabled);

  useEffect(() => {
    if (!mockingEnabled) return;
    void import("./browser").then(({ worker }) =>
      worker.start({ onUnhandledFrame: "bypass" }).then(() => setReady(true)),
    );
  }, []);

  return ready ? children : null;
}
