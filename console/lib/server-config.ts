import "server-only";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is not set; see console/.env.example`);
  }
  return value;
}

export function gatewayBaseUrl(): URL {
  const raw = requireEnv("GATEWAY_URL");
  try {
    return new URL(raw);
  } catch {
    throw new Error("GATEWAY_URL is not a valid URL");
  }
}
