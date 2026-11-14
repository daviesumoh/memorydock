import { withAuth } from "@workos-inc/authkit-nextjs";

import { forwardToGateway } from "@/lib/gateway-proxy";
import { gatewayBaseUrl } from "@/lib/server-config";

async function handle(request: Request, ctx: RouteContext<"/api/gateway/[...path]">) {
  const [{ path }, { accessToken }] = await Promise.all([ctx.params, withAuth()]);
  return forwardToGateway({
    request,
    path,
    accessToken: accessToken ?? null,
    gatewayUrl: gatewayBaseUrl(),
  });
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
