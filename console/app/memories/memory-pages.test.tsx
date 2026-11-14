// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/mocks/node";
import { renderWithQueries } from "@/test/render";

import { MemoryDetail } from "./[id]/memory-detail";
import { MemoryList } from "./memory-list";

let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
  usePathname: () => "/memories",
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

describe("memory list", () => {
  it("shows a loading state, then the memories", async () => {
    renderWithQueries(<MemoryList />);
    expect(screen.getByRole("status", { name: "Loading memories" })).toBeTruthy();
    expect(await screen.findByText(/User research on Project Lantern/)).toBeTruthy();
  });

  it("renders agent-written markup as text, never as elements", async () => {
    const { container } = renderWithQueries(<MemoryList />);
    const cell = await screen.findByText(/<script>alert\("lantern"\)<\/script>/);

    expect(cell.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("cuts long values to one line and opens them in place when clicked", async () => {
    renderWithQueries(<MemoryList />);
    const cell = await screen.findByRole("button", { name: /User research on Project Lantern/ });

    expect(cell.getAttribute("aria-expanded")).toBe("false");
    expect(cell.className).toContain("truncate");
    expect(cell.getAttribute("title")).toContain("handoff notes generated at the end of each session");
    expect(screen.queryByRole("link", { name: "Open memory" })).toBeNull();

    fireEvent.click(cell);
    expect(cell.getAttribute("aria-expanded")).toBe("true");
    expect(cell.className).not.toContain("truncate");
    expect(screen.getByRole("link", { name: "Open memory" }).getAttribute("href")).toBe("/memories/mem_01JDEMO0001");

    fireEvent.click(cell);
    expect(cell.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("link", { name: "Open memory" })).toBeNull();
  });

  it("marks a forgotten memory instead of showing purged content", async () => {
    searchParams = new URLSearchParams("status=forgotten");
    renderWithQueries(<MemoryList />);
    expect(await screen.findByText("Content forgotten")).toBeTruthy();
  });

  it("shows a filtered empty state that says the filters are the reason", async () => {
    // No fixture is proposed, so this filter matches nothing.
    searchParams = new URLSearchParams("status=proposed");
    renderWithQueries(<MemoryList />);
    expect(await screen.findByText("No memories match these filters")).toBeTruthy();
  });

  it("shows the gateway's error code and request id when the list fails", async () => {
    server.use(
      http.get("*/api/gateway/v1/memories", () =>
        HttpResponse.json(
          { error: { code: "session_revoked", message: "Your session was revoked", request_id: "req_list_1" } },
          { status: 403 },
        ),
      ),
    );
    renderWithQueries(<MemoryList />);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Could not load memories")).toBeTruthy();
    expect(alert.textContent).toContain("session_revoked");
    expect(alert.textContent).toContain("req_list_1");
  });
});

describe("memory detail", () => {
  it("shows provenance, trust and the version history", async () => {
    renderWithQueries(<MemoryDetail memoryId="mem_01JDEMO0001" />);

    expect(await screen.findByText("extension")).toBeTruthy();
    expect(screen.getByText("95%")).toBeTruthy();
    expect(await screen.findByText("Version 2")).toBeTruthy();
    expect(screen.getByText("Version 1")).toBeTruthy();
    expect(screen.getByText("Reason: Added when the notes are generated")).toBeTruthy();
  });

  it("explains a forgotten memory and shows no content", async () => {
    renderWithQueries(<MemoryDetail memoryId="mem_01JDEMO0009" />);
    expect(await screen.findByText(/Content and search data were purged/)).toBeTruthy();
    expect(screen.getByText(/Captured by mistake/)).toBeTruthy();
  });

  it("treats a 404 as not found, not as a failure", async () => {
    renderWithQueries(<MemoryDetail memoryId="mem_01JDEMO9999" />);
    expect(await screen.findByText("Memory not found")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
