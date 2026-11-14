import { describe, expect, it } from "vitest";

import { challengeFor, createVerifier, randomToken } from "./pkce.ts";

describe("PKCE", () => {
  it("matches the S256 example in RFC 7636 appendix B", async () => {
    // Published example values from the RFC, not credentials.
    const verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"; // pragma: allowlist secret
    expect(await challengeFor(verifier)).toBe("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"); // pragma: allowlist secret
  });

  it("creates verifiers within RFC 7636's length and character rules", () => {
    for (let i = 0; i < 50; i++) {
      const verifier = createVerifier();
      expect(verifier.length).toBeGreaterThanOrEqual(43);
      expect(verifier.length).toBeLessThanOrEqual(128);
      expect(verifier).toMatch(/^[A-Za-z0-9\-._~]+$/);
    }
  });

  it("never repeats a state or verifier", () => {
    const values = new Set(Array.from({ length: 200 }, () => randomToken()));
    expect(values.size).toBe(200);
  });
});
