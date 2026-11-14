"use client";

import dynamic from "next/dynamic";

import { mockingEnabled } from "./ready";

// msw/browser cannot be resolved for the server render (its "node" export is
// null), so the worker module is kept out of the SSR bundle entirely.
// The literal NODE_ENV test is what lets production builds drop the chunk and
// its fixtures; the bundler does not see through the imported mockingEnabled.
const StartMockWorker =
  process.env.NODE_ENV !== "production" && mockingEnabled
    ? dynamic(() => import("./start-mock-worker"), { ssr: false })
    : null;

export function MockWorker() {
  return StartMockWorker ? <StartMockWorker /> : null;
}
