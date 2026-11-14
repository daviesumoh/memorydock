import { createPublicKey } from "node:crypto";
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { parseConfig } from "./config.ts";
import { buildManifest, extensionIdFromPublicKey } from "./manifest.ts";

const pem = readFileSync(new URL("../extension-key.pub.pem", import.meta.url), "utf8");
const spkiDer = createPublicKey(pem).export({ type: "spki", format: "der" });

const config = parseConfig({
  GATEWAY_URL: "https://gateway.example.com/base",
  AUTHKIT_DOMAIN: "https://example.authkit.app",
  CONSOLE_URL: "https://console.example.com",
});

describe("extensionIdFromPublicKey", () => {
  it("gives the id derived from the committed key with openssl and shasum", () => {
    expect(extensionIdFromPublicKey(spkiDer)).toBe("ohlflggckmdbbaooockgncafhecpjboc");
  });
});

describe("buildManifest", () => {
  const manifest = buildManifest(config, spkiDer, "0.1.0");

  it("is a Manifest V3 extension carrying the public key that pins its id", () => {
    expect(manifest.manifest_version).toBe(3);
    expect(Buffer.from(manifest.key, "base64").equals(spkiDer)).toBe(true);
  });

  it("asks only for storage and identity", () => {
    expect(manifest.permissions).toEqual(["storage", "identity"]);
  });

  it("limits host access to chatgpt.com, the gateway origin and the AuthKit origin", () => {
    expect(manifest.host_permissions).toEqual([
      "https://chatgpt.com/*",
      "https://gateway.example.com/*",
      "https://example.authkit.app/*",
    ]);
  });

  it("runs the content script on chatgpt.com only", () => {
    expect(manifest.content_scripts).toEqual([
      { matches: ["https://chatgpt.com/*"], js: ["content.js"], run_at: "document_idle" },
    ]);
  });
});
