import { authkitProxy } from "@workos-inc/authkit-nextjs";

export default authkitProxy({
  middlewareAuth: {
    enabled: true,
    // The gateway proxy answers 401 itself; a redirect to an HTML sign-in page
    // is no use to a fetch call.
    unauthenticatedPaths: ["/sign-in", "/callback", "/api/gateway/:path*"],
  },
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|mockServiceWorker.js).*)"],
};
