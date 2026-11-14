import { randomBytes } from "node:crypto";
import { defineConfig } from "@playwright/test";

const PORT = 3100;

// These tests never reach WorkOS or a gateway. The cookie password is random
// per run so there is no literal credential to commit.
const testEnv = {
  WORKOS_CLIENT_ID: "client_e2e_placeholder",
  WORKOS_COOKIE_PASSWORD: randomBytes(32).toString("hex"),
  NEXT_PUBLIC_WORKOS_REDIRECT_URI: `http://localhost:${PORT}/callback`,
  GATEWAY_URL: "http://127.0.0.1:9",
};

export default defineConfig({
  testDir: "e2e",
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: `http://localhost:${PORT}` },
  webServer: {
    command: `pnpm build && pnpm start --port ${PORT}`,
    url: `http://localhost:${PORT}/sign-in`,
    env: testEnv,
    timeout: 180_000,
    reuseExistingServer: false,
  },
});
