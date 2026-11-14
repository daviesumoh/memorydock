"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { GatewayError } from "@/lib/api/errors";

export function QueryProvider({ children }: { children: ReactNode }) {
  // One client per browser session; created in state so a re-render never
  // replaces it and drops the cache.
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            // A 4xx will not fix itself on retry; network and 5xx errors might.
            retry: (failureCount, error) =>
              failureCount < 2 && !(error instanceof GatewayError && error.status < 500),
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
