// Kept free of msw imports so the API client can depend on it in server and
// client bundles alike.

// Production builds never mock, even if the variable is set by mistake:
// mocked data must not be shown as real.
export const mockingEnabled =
  process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_API_MOCKING === "enabled";

let markReady!: () => void;
const workerReady = new Promise<void>((resolve) => {
  markReady = resolve;
});

export function markWorkerReady(): void {
  markReady();
}

// Gateway calls wait here while mocking, so none reaches the real gateway
// before the service worker is intercepting.
export function waitForMocks(): Promise<void> {
  return mockingEnabled ? workerReady : Promise.resolve();
}
