// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { sessions } from "@/mocks/fixtures";
import { server } from "@/mocks/node";
import { renderWithQueries } from "@/test/render";

import { SessionList } from "./session-list";

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

async function row(client: string) {
  const cell = await screen.findByRole("cell", { name: client });
  return cell.closest("tr")!;
}

function recordPosts() {
  const posts: { path: string; body: unknown }[] = [];
  server.use(
    http.post("*/api/gateway/v1/sessions/:id/:action", async ({ request, params }) => {
      const text = await request.text();
      posts.push({ path: `${params.id}/${params.action}`, body: text ? JSON.parse(text) : null });
      const found = sessions.find((s) => s.id === params.id)!;
      return HttpResponse.json({ ...found, status: "revoked" });
    }),
  );
  return posts;
}

describe("sessions page", () => {
  it("lists each session with its client and status", async () => {
    renderWithQueries(<SessionList />);
    expect(within(await row("codex")).getByText("paused")).toBeTruthy();
    expect(within(await row("claude-app")).getByText("revoked")).toBeTruthy();
  });

  it("offers no controls on the console's own session or a revoked one", async () => {
    renderWithQueries(<SessionList />);
    const own = await row("console");
    expect(within(own).getByText("This console")).toBeTruthy();
    expect(within(own).queryByRole("button")).toBeNull();
    expect(within(await row("claude-app")).queryByRole("button")).toBeNull();
  });

  it("pauses an active session and resumes a paused one", async () => {
    const posts = recordPosts();
    renderWithQueries(<SessionList />);
    fireEvent.click(within(await row("claude-code")).getByRole("button", { name: "Pause" }));
    fireEvent.click(within(await row("codex")).getByRole("button", { name: "Resume" }));
    await waitFor(() =>
      expect(posts.map((p) => p.path).sort()).toEqual(["ses_01JDEMO0A1/pause", "ses_01JDEMO0C3/resume"]),
    );
  });

  it("asks before revoking, then sends the reason", async () => {
    const posts = recordPosts();
    renderWithQueries(<SessionList />);
    fireEvent.click(within(await row("claude-code")).getByRole("button", { name: "Revoke" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("can't be resumed");
    expect(posts).toEqual([]);

    fireEvent.change(within(dialog).getByLabelText("Reason (optional)"), { target: { value: " Laptop lost " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(posts).toEqual([{ path: "ses_01JDEMO0A1/revoke", body: { reason: "Laptop lost" } }]));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows a refusal from the gateway", async () => {
    server.use(
      http.post("*/api/gateway/v1/sessions/:id/:action", () =>
        HttpResponse.json(
          { error: { code: "policy_denied", message: "policy does not allow this", request_id: "req_3" } },
          { status: 403 },
        ),
      ),
    );
    renderWithQueries(<SessionList />);
    fireEvent.click(within(await row("claude-code")).getByRole("button", { name: "Pause" }));
    expect(await screen.findByText("Could not pause this session")).toBeTruthy();
  });
});
