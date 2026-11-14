import { describe, expect, it } from "vitest";

import { parseConfig } from "./config.ts";

const valid = {
  GATEWAY_URL: "https://gateway.example.com",
  AUTHKIT_DOMAIN: "https://example.authkit.app",
  CONSOLE_URL: "https://console.example.com",
  CLIENT_ID: "client_01EXTENSIONTEST",
};

describe("parseConfig", () => {
  it("reads all three URLs", () => {
    const config = parseConfig(valid);
    expect(config.gatewayUrl.origin).toBe("https://gateway.example.com");
    expect(config.authkitDomain.origin).toBe("https://example.authkit.app");
    expect(config.consoleUrl.origin).toBe("https://console.example.com");
  });

  it("allows plain http for a local gateway and console", () => {
    const config = parseConfig({
      ...valid,
      GATEWAY_URL: "http://127.0.0.1:8000",
      CONSOLE_URL: "http://localhost:3000",
    });
    expect(config.gatewayUrl.protocol).toBe("http:");
    expect(config.consoleUrl.protocol).toBe("http:");
  });

  it.each(["GATEWAY_URL", "AUTHKIT_DOMAIN", "CONSOLE_URL", "CLIENT_ID"])("names %s when it is missing or empty", (name) => {
    expect(() => parseConfig({ ...valid, [name]: undefined })).toThrow(name);
    expect(() => parseConfig({ ...valid, [name]: "" })).toThrow(name);
  });

  it("reads the client id", () => {
    expect(parseConfig(valid).clientId).toBe("client_01EXTENSIONTEST");
  });

  it("refuses a client id that could change the authorize URL", () => {
    expect(() => parseConfig({ ...valid, CLIENT_ID: "client&redirect_uri=x" })).toThrow("unexpected characters");
  });

  it("rejects a value that is not a URL", () => {
    expect(() => parseConfig({ ...valid, GATEWAY_URL: "gateway.example.com" })).toThrow(
      "GATEWAY_URL is not a valid URL",
    );
  });

  it.each([
    ["GATEWAY_URL", "http://gateway.example.com"],
    ["CONSOLE_URL", "http://console.example.com"],
    ["AUTHKIT_DOMAIN", "http://localhost:4000"],
    ["GATEWAY_URL", "ftp://127.0.0.1"],
  ])("refuses %s=%s, which is not https", (name, value) => {
    expect(() => parseConfig({ ...valid, [name]: value })).toThrow(`${name} must use https`);
  });
});
