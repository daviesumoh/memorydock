// Build-time settings. They are compiled into the bundle and none is a secret.

export interface ExtensionConfig {
  gatewayUrl: URL;
  authkitDomain: URL;
  consoleUrl: URL;
}

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1"]);

function readUrl(env: Record<string, string | undefined>, name: string, allowLocalHttp: boolean): URL {
  const raw = env[name];
  if (!raw) {
    throw new Error(`${name} is not set; see clients/extension/.env.example`);
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`${name} is not a valid URL`);
  }
  const localHttp = allowLocalHttp && url.protocol === "http:" && LOCAL_HOSTS.has(url.hostname);
  if (url.protocol !== "https:" && !localHttp) {
    throw new Error(`${name} must use https (plain http is allowed only for localhost)`);
  }
  return url;
}

export function parseConfig(env: Record<string, string | undefined>): ExtensionConfig {
  return {
    gatewayUrl: readUrl(env, "GATEWAY_URL", true),
    // AuthKit is always hosted, so it is always https.
    authkitDomain: readUrl(env, "AUTHKIT_DOMAIN", false),
    consoleUrl: readUrl(env, "CONSOLE_URL", true),
  };
}
