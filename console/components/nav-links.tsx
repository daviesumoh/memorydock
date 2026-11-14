"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/memories", label: "Memories" },
  { href: "/audit", label: "Audit" },
] as const;

// Rendered without a current page while the pathname is unknown (the static
// shell of a dynamic route), then with it.
export function NavLinkList({ pathname }: { pathname: string | null }) {
  return (
    <nav aria-label="Console" className="flex gap-4 text-sm">
      {LINKS.map(({ href, label }) => {
        const current = pathname !== null && (pathname === href || pathname.startsWith(`${href}/`));
        return (
          <Link
            key={href}
            href={href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "rounded-sm underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2",
              current ? "font-medium underline" : "text-muted-foreground",
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function NavLinks() {
  return <NavLinkList pathname={usePathname()} />;
}
