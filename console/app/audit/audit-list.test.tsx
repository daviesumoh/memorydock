// @vitest-environment jsdom
import { cleanup, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/mocks/node";
import { renderWithQueries } from "@/test/render";

import { AuditList } from "./audit-list";

let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
  usePathname: () => "/audit",
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("@/lib/api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api/client")>();
  const { testGateway } = await import("@/test/gateway-client");
  return { ...original, gateway: testGateway };
});

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
beforeEach(() => {
  searchParams = new URLSearchParams();
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

describe("audit list", () => {
  it("shows each decision as a word, not only a colour", async () => {
    renderWithQueries(<AuditList />);
    expect(await screen.findByText("deny")).toBeTruthy();
    expect(screen.getByText("approval required")).toBeTruthy();
    expect(screen.getAllByText("allow").length).toBeGreaterThan(0);
  });

  it("shows another user's personal activity as a placeholder without ids", async () => {
    renderWithQueries(<AuditList />);
    const placeholder = await screen.findByText("Personal activity");
    const row = placeholder.closest("tr")!;
    expect(row.textContent).not.toMatch(/usr_|mem_|ses_/);
  });

  it("applies filters from the URL", async () => {
    searchParams = new URLSearchParams("action=lease.acquire");
    renderWithQueries(<AuditList />);
    expect(await screen.findByText("lease.acquire")).toBeTruthy();
    expect(screen.queryByText("memory.forget")).toBeNull();
  });

  it("shows an empty state when nothing matches", async () => {
    searchParams = new URLSearchParams("task_id=tsk_none");
    renderWithQueries(<AuditList />);
    expect(await screen.findByText("No entries match these filters")).toBeTruthy();
  });

  it("shows the error code and request id when the gateway cannot be reached", async () => {
    server.use(
      http.get("*/api/gateway/v1/audit", () =>
        HttpResponse.json(
          { error: { code: "gateway_unreachable", message: "The gateway could not be reached", request_id: "req_audit_1" } },
          { status: 502 },
        ),
      ),
    );
    renderWithQueries(<AuditList />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("gateway_unreachable");
    expect(alert.textContent).toContain("req_audit_1");
  });
});
