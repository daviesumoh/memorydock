import { fileURLToPath } from "node:url";

import { chromium, expect, test, type BrowserContext } from "@playwright/test";

// Run `pnpm build` first; this loads dist/ as an unpacked extension.
const dist = fileURLToPath(new URL("../dist", import.meta.url));
const EXTENSION_ID = "ohlflggckmdbbaooockgncafhecpjboc";

let context: BrowserContext;

test.beforeAll(async () => {
  context = await chromium.launchPersistentContext("", {
    channel: "chromium",
    args: [`--disable-extensions-except=${dist}`, `--load-extension=${dist}`],
  });
  // No real chatgpt.com: the content script runs against a stand-in page.
  await context.route("https://chatgpt.com/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<!doctype html><main>stand-in</main>" }),
  );
});

test.afterAll(async () => {
  await context.close();
});

test("Chrome loads the extension under the id pinned by its public key", async () => {
  const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent("serviceworker"));
  expect(new URL(worker.url()).host).toBe(EXTENSION_ID);
});

test("the popup gets its status from the background script", async () => {
  const popup = await context.newPage();
  await popup.goto(`chrome-extension://${EXTENSION_ID}/popup.html`);

  await expect(popup.getByRole("status")).toHaveText("Capture: paused · not signed in");
  await expect(popup.getByRole("link", { name: "Open the console" })).toHaveAttribute(
    "href",
    "http://localhost:3000/",
  );
});

test("the content script adds its badge on chatgpt.com", async () => {
  const page = await context.newPage();
  await page.goto("https://chatgpt.com/");

  await expect(page.locator("#memorydock-badge")).toBeAttached();
});
