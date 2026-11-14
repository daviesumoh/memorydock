import type { Schemas } from "./client";

// One error type for everything the typed client can fail with, so every view
// can show the gateway's code and request id the same way.
export class GatewayError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;

  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message);
    this.name = "GatewayError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function isErrorResponse(value: unknown): value is Schemas["ErrorResponse"] {
  const error = (value as { error?: unknown } | null)?.error;
  return typeof error === "object" && error !== null && typeof (error as { code?: unknown }).code === "string";
}

// Returns the data of a successful openapi-fetch result, or throws a
// GatewayError carrying the error body's code and request id. A body that is
// not the error shape still yields a GatewayError, keyed by HTTP status.
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  const { data, error, response } = result;
  if (response.ok && data !== undefined) return data;
  const headerId = response.headers.get("x-request-id");
  if (isErrorResponse(error)) {
    const body = error.error;
    throw new GatewayError(response.status, body.code, body.message, body.request_id ?? headerId);
  }
  throw new GatewayError(response.status, `http_${response.status}`, "The gateway sent an unexpected response", headerId);
}
