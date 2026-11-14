// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { MemoryDetail } from "@/app/memories/[id]/memory-detail";
import { memories } from "@/mocks/fixtures";
import { server } from "@/mocks/node";
import { renderWithQueries } from "@/test/render";

import { NewMemoryDialog } from "./new-memory-dialog";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/memories",
  useRouter: () => ({ push }),
}));
vi.mock("@/lib/api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api/client")>();
  const { testGateway } = await import("@/test/gateway-client");
  return { ...original, gateway: testGateway };
});

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  push.mockReset();
});
afterAll(() => server.close());

const PROJECT_MEMORY = "mem_01JDEMO0001";
const PERSONAL_MEMORY = "mem_01JDEMO0003";

// Records each POST body and answers with the forgotten stub of that memory.
function captureForget() {
  const bodies: unknown[] = [];
  server.use(
    http.post("*/api/gateway/v1/memories/:id/forget", async ({ request, params }) => {
      bodies.push(await request.json());
      const found = memories.find((m) => m.id === params.id)!;
      return HttpResponse.json({ ...found, status: "forgotten", content: null });
    }),
  );
  return bodies;
}

async function openForget(memoryId: string) {
  renderWithQueries(<MemoryDetail memoryId={memoryId} />);
  fireEvent.click(await screen.findByRole("button", { name: "Forget" }));
  return screen.findByRole("dialog");
}

describe("forget dialog", () => {
  it("needs a reason for a shared memory before it can be sent", async () => {
    const bodies = captureForget();
    const dialog = await openForget(PROJECT_MEMORY);
    const submit = () => dialog.querySelector<HTMLButtonElement>("button[type=submit]")!;

    expect(dialog.textContent).toContain("Backups keep data until their retention period ends");
    expect(submit().disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "  Wrong conclusion  " } });
    expect(submit().disabled).toBe(false);
    fireEvent.click(submit());

    await waitFor(() => expect(bodies).toEqual([{ reason: "Wrong conclusion" }]));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("lets a personal memory go without a reason", async () => {
    const bodies = captureForget();
    const dialog = await openForget(PERSONAL_MEMORY);

    expect(screen.getByLabelText("Reason (optional)")).toBeTruthy();
    fireEvent.click(dialog.querySelector<HTMLButtonElement>("button[type=submit]")!);
    await waitFor(() => expect(bodies).toEqual([{ reason: null }]));
  });

  it("shows the gateway's refusal and stays open", async () => {
    server.use(
      http.post("*/api/gateway/v1/memories/:id/forget", () =>
        HttpResponse.json(
          { error: { code: "policy_denied", message: "policy does not allow this", request_id: "req_1" } },
          { status: 403 },
        ),
      ),
    );
    const dialog = await openForget(PERSONAL_MEMORY);
    fireEvent.click(dialog.querySelector<HTMLButtonElement>("button[type=submit]")!);

    expect(await screen.findByText("Could not forget this memory")).toBeTruthy();
    expect(screen.getByText(/policy_denied/)).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("is not offered for a memory already forgotten", async () => {
    renderWithQueries(<MemoryDetail memoryId="mem_01JDEMO0009" />);
    expect(await screen.findByText(/Content and search data were purged/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Forget" })).toBeNull();
  });
});

describe("new memory dialog", () => {
  it("saves to the project by default and opens the new memory", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post("*/api/gateway/v1/memories", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...memories[0], id: "mem_01JDEMO0NEW" }, { status: 201 });
      }),
    );
    renderWithQueries(<NewMemoryDialog />);
    fireEvent.click(screen.getByRole("button", { name: "New memory" }));
    const dialog = await screen.findByRole("dialog");
    const submit = dialog.querySelector<HTMLButtonElement>("button[type=submit]")!;

    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Memory"), { target: { value: " Ship on Thursdays " } });
    fireEvent.click(submit);

    await waitFor(() => expect(bodies).toEqual([{ content: "Ship on Thursdays", type: "decision", scope: "project" }]));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/memories/mem_01JDEMO0NEW"));
  });

  it("explains a refusal, such as an org memory waiting for approval", async () => {
    server.use(
      http.post("*/api/gateway/v1/memories", () =>
        HttpResponse.json(
          { error: { code: "approval_required", message: "this needs a human approval", request_id: "req_2" } },
          { status: 403 },
        ),
      ),
    );
    renderWithQueries(<NewMemoryDialog />);
    fireEvent.click(screen.getByRole("button", { name: "New memory" }));
    fireEvent.change(await screen.findByLabelText("Memory"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("dialog").querySelector<HTMLButtonElement>("button[type=submit]")!);

    expect(await screen.findByText("this needs a human approval")).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });
});
