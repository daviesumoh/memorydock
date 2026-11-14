import type { Metadata } from "next";
import { AuthKitProvider } from "@workos-inc/authkit-nextjs/components";

import { MockWorker } from "@/mocks/mock-worker";
import "./globals.css";

export const metadata: Metadata = {
  title: "memorydock console",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <AuthKitProvider>{children}</AuthKitProvider>
        <MockWorker />
      </body>
    </html>
  );
}
