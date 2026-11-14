"use client";

import Link from "next/link";

import { FilterForm, useFilterValues, type FilterField } from "@/components/filter-form";
import { StatusBadge, TypeBadge } from "@/components/memory-badges";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingRows } from "@/components/view-states";
import { useMemories } from "@/lib/api/queries";
import { formatTimestamp } from "@/lib/format";

export const MEMORY_FILTERS = [
  { name: "scope", label: "Scope", kind: "text", placeholder: "project:acme/lantern" },
  {
    name: "type",
    label: "Type",
    kind: "select",
    options: ["fact", "decision", "preference", "procedure", "finding", "open_question", "episode"],
  },
  {
    name: "status",
    label: "Status",
    kind: "select",
    options: ["active", "proposed", "superseded", "conflict", "disputed", "expired", "forgotten"],
  },
  { name: "category", label: "Category", kind: "text" },
  {
    name: "source_client",
    label: "Source client",
    kind: "select",
    options: ["claude-code", "codex", "claude-app", "chatgpt", "console", "worker", "other"],
  },
  { name: "project", label: "Project", kind: "text", placeholder: "lantern" },
] as const satisfies readonly FilterField[];

export function MemoryList() {
  const filters = useFilterValues(MEMORY_FILTERS);
  const query = useMemories(filters);
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];
  const filtered = Object.keys(filters).length > 0;

  return (
    <>
      <FilterForm fields={MEMORY_FILTERS} />
      {query.isPending ? (
        <LoadingRows label="Loading memories" />
      ) : query.isError && rows.length === 0 ? (
        <ErrorState title="Could not load memories" error={query.error} />
      ) : rows.length === 0 ? (
        <EmptyState
          title={filtered ? "No memories match these filters" : "No memories yet"}
          detail={filtered ? "Change or clear the filters." : "Memories appear here once your agents capture them."}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Memory</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Scope</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((memory) => (
                <TableRow key={memory.id}>
                  <TableCell className="max-w-md">
                    <Link href={`/memories/${memory.id}`} className="block truncate underline-offset-4 hover:underline">
                      {/* Agent-written text: rendered as text, never as HTML. */}
                      {memory.content ?? <span className="text-muted-foreground italic">Content forgotten</span>}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <TypeBadge type={memory.type} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={memory.status} />
                  </TableCell>
                  <TableCell className="font-mono text-xs">{memory.scope_key}</TableCell>
                  <TableCell>{memory.source_client}</TableCell>
                  <TableCell className="whitespace-nowrap">{formatTimestamp(memory.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {query.hasNextPage ? (
            <Button
              variant="outline"
              className="self-start"
              onClick={() => void query.fetchNextPage()}
              disabled={query.isFetchingNextPage}
            >
              {query.isFetchingNextPage ? "Loading…" : "Load more"}
            </Button>
          ) : null}
          {/* A failed "Load more" keeps the rows already shown. */}
          {query.isFetchNextPageError ? <ErrorState title="Could not load more memories" error={query.error} /> : null}
        </>
      )}
    </>
  );
}
