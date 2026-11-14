import { createGatewayClient } from "@/lib/api/client";

// Node's fetch cannot resolve the browser client's relative base URL, so
// component tests swap in a client with an absolute one (see vi.mock calls).
export const testGateway = createGatewayClient("http://localhost:3000/api/gateway");
