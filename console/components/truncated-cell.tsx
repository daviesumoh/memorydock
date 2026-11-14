"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { TableCell } from "@/components/ui/table";
import { cn } from "@/lib/utils";

// A table cell cut to one line with an ellipsis; clicking it shows the whole
// value wrapped in place, so the table never needs to scroll sideways.
export function TruncatedCell({
  children,
  fullText,
  href,
  hrefLabel = "Open",
  className,
}: {
  children: ReactNode;
  // Plain-text version of the value, for the hover tooltip.
  fullText: string;
  // Shown as a link once the cell is open.
  href?: string;
  hrefLabel?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <TableCell className={cn("align-top", className)}>
      <button
        type="button"
        aria-expanded={open}
        title={open ? undefined : fullText}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "block w-full cursor-pointer rounded-sm text-left focus-visible:outline-2 focus-visible:outline-offset-2",
          open ? "break-words whitespace-pre-wrap" : "truncate",
        )}
      >
        {children}
      </button>
      {open && href ? (
        <Link href={href} className="mt-1 inline-block text-xs underline underline-offset-4">
          {hrefLabel}
        </Link>
      ) : null}
    </TableCell>
  );
}
