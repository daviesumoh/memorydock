import { setupWorker } from "msw/browser";

import { handlers } from "./handlers";

const worker = setupWorker(...handlers);

let started: Promise<unknown> | undefined;

// React runs effects twice in development and fast refresh re-runs them, but
// the worker can only be started once per page.
export function startWorker(): Promise<unknown> {
  started ??= worker.start({ onUnhandledFrame: "bypass" });
  return started;
}
