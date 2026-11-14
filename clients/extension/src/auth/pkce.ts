// PKCE (RFC 7636, S256) and the OAuth state value, using Web Crypto so the
// same code runs in the service worker and in tests.

function base64url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

export function randomToken(byteLength = 32): string {
  return base64url(crypto.getRandomValues(new Uint8Array(byteLength)));
}

// 32 random bytes encode to 43 characters, the shortest verifier RFC 7636 allows.
export function createVerifier(): string {
  return randomToken(32);
}

export async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}
