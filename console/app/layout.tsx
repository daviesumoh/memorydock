import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { AuthKitProvider } from "@workos-inc/authkit-nextjs/components";

import { ConsoleHeader } from "@/components/console-header";
import { cn } from "@/lib/utils";
import { MockWorker } from "@/mocks/mock-worker";

import { QueryProvider } from "./query-provider";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "memorydock console",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={cn("h-full font-sans antialiased", geist.variable)}>
      <body className="flex min-h-full flex-col">
        <AuthKitProvider>
          <QueryProvider>
            <ConsoleHeader />
            <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-6 py-8">{children}</main>
          </QueryProvider>
        </AuthKitProvider>
        <MockWorker />
      </body>
    </html>
  );
}
