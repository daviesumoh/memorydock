import { createHash } from "node:crypto";

import type { ExtensionConfig } from "./config.ts";

export const CHATGPT_MATCH = "https://chatgpt.com/*";

// Chrome derives an extension's id from the SHA-256 of its public key: the
// first 32 hex digits, with 0-f written as a-p.
export function extensionIdFromPublicKey(spkiDer: Buffer): string {
  const hex = createHash("sha256").update(spkiDer).digest("hex").slice(0, 32);
  return [...hex].map((digit) => String.fromCharCode(97 + Number.parseInt(digit, 16))).join("");
}

export function buildManifest(config: ExtensionConfig, spkiDer: Buffer, version: string) {
  return {
    manifest_version: 3,
    name: "memorydock",
    version,
    description: "memorydock for ChatGPT. Capture is off until you sign in and opt a project in.",
    // Pins the extension id, so its chromiumapp.org redirect is known before the first load.
    key: spkiDer.toString("base64"),
    permissions: ["storage", "identity"],
    host_permissions: [
      CHATGPT_MATCH,
      `${config.gatewayUrl.origin}/*`,
      `${config.authkitDomain.origin}/*`,
    ],
    background: { service_worker: "background.js" },
    content_scripts: [{ matches: [CHATGPT_MATCH], js: ["content.js"], run_at: "document_idle" }],
    action: { default_popup: "popup.html" },
  };
}
