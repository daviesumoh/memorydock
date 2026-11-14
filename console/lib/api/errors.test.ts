import { describe, expect, it } from "vitest";

import { GatewayError, unwrap } from "./errors";

function response(status: number, requestId?: string) {
  return new Response(null, { status, headers: requestId ? { "x-request-id": requestId } : {} });
}

describe("unwrap", () => {
  it("returns the data of a successful response", () => {
    expect(unwrap({ data: { ok: true }, response: response(200) })).toEqual({ ok: true });
  });

  it("carries the gateway's code, message and request id", () => {
    const error = { error: { code: "session_revoked", message: "Session revoked", request_id: "req_1" } };
    expect(() => unwrap({ error, response: response(403, "req_header") })).toThrow(
      expect.objectContaining({ status: 403, code: "session_revoked", message: "Session revoked", requestId: "req_1" }),
    );
  });

  it("falls back to the status and header request id for a body that is not the error shape", () => {
    let thrown: unknown;
    try {
      unwrap({ error: "<html>Bad gateway</html>", response: response(502, "req_header") });
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(GatewayError);
    expect(thrown).toMatchObject({ status: 502, code: "http_502", requestId: "req_header" });
  });

  it("treats a 2xx without data as an error rather than returning undefined", () => {
    expect(() => unwrap({ response: response(200) })).toThrow(GatewayError);
  });
});
