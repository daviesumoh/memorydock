// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { fixtures } from "@/mocks/handlers";
import { server } from "@/mocks/node";
import { renderWithQueries } from "@/test/render";

import { VerifyChain } from "./verify-chain";

vi.mock("@/lib/api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api/client")>();
  const { testGateway } = await import("@/test/gateway-client");
  return { ...original, gateway: testGateway };
});

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function asAdmin() {
  server.use(http.get("*/api/gateway/v1/me", () => HttpResponse.json({ ...fixtures.me, roles: ["admin", "member"] })));
}

describe("verify chain", () => {
  it("is not shown to members, whom the gateway would refuse", async () => {
    let asked = false;
    server.use(
      http.get("*/api/gateway/v1/me", () => {
        asked = true;
        return HttpResponse.json(fixtures.me);
      }),
    );
    renderWithQueries(<VerifyChain />);
    await vi.waitFor(() => expect(asked).toBe(true));
    expect(screen.queryByRole("button", { name: "Verify chain" })).toBeNull();
  });

  it("verifies only when asked, then shows PASS", async () => {
    asAdmin();
    let calls = 0;
    server.use(
      http.get("*/api/gateway/v1/audit/verify", () => {
        calls += 1;
        return HttpResponse.json({ ok: true, checked: 12, first_bad_seq: null, reason: "chain verifies" });
      }),
    );
    renderWithQueries(<VerifyChain />);
    const button = await screen.findByRole("button", { name: "Verify chain" });
    expect(calls).toBe(0);

    fireEvent.click(button);
    expect(await screen.findByText("PASS: the chain verifies")).toBeTruthy();
    expect(screen.getByText(/12 entries recomputed/)).toBeTruthy();
    expect(calls).toBe(1);
  });

  it("shows FAIL with the first bad entry", async () => {
    asAdmin();
    server.use(
      http.get("*/api/gateway/v1/audit/verify", () =>
        HttpResponse.json({ ok: false, checked: 6, first_bad_seq: 7, reason: "hash does not match the entry's content" }),
      ),
    );
    renderWithQueries(<VerifyChain />);
    fireEvent.click(await screen.findByRole("button", { name: "Verify chain" }));

    expect(await screen.findByText("FAIL: broken at entry 7")).toBeTruthy();
    expect(screen.getByText(/hash does not match the entry's content\. 6 entries verified before it/)).toBeTruthy();
  });

  it("shows a refusal with its code", async () => {
    asAdmin();
    server.use(
      http.get("*/api/gateway/v1/audit/verify", () =>
        HttpResponse.json(
          { error: { code: "policy_denied", message: "policy does not allow this: forbidden by org-kill-switch", request_id: "req_9" } },
          { status: 403 },
        ),
      ),
    );
    renderWithQueries(<VerifyChain />);
    fireEvent.click(await screen.findByRole("button", { name: "Verify chain" }));
    expect(await screen.findByText("Could not verify the chain")).toBeTruthy();
    expect(screen.getByText(/org-kill-switch/)).toBeTruthy();
  });
});
