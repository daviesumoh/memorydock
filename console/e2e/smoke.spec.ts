import { expect, test } from "@playwright/test";

function authorizeRedirect(location: string | undefined) {
  expect(location).toBeDefined();
  return new URL(location!);
}

test("a signed-out visit to the console is sent to AuthKit to sign in", async ({ request, baseURL }) => {
  const response = await request.get("/", { maxRedirects: 0 });

  expect([302, 303, 307]).toContain(response.status());
  const target = authorizeRedirect(response.headers()["location"]);
  expect(target.pathname).toBe("/user_management/authorize");
  expect(target.searchParams.get("client_id")).toBe("client_e2e_placeholder");
  expect(target.searchParams.get("redirect_uri")).toBe(`${baseURL}/callback`);
  expect(target.searchParams.get("code_challenge_method")).toBe("S256");
});

test("the initiate-login route starts a sign-in without a session", async ({ request }) => {
  const response = await request.get("/sign-in", { maxRedirects: 0 });

  expect([302, 303, 307]).toContain(response.status());
  expect(authorizeRedirect(response.headers()["location"]).pathname).toBe("/user_management/authorize");
});

test("the gateway proxy answers 401 JSON, not a redirect, without a session", async ({ request }) => {
  const response = await request.get("/api/gateway/v1/me", { maxRedirects: 0 });

  expect(response.status()).toBe(401);
  const body = await response.json();
  expect(body.code).toBe("not_signed_in");
  expect(body.request_id).toBe(response.headers()["x-request-id"]);
});
