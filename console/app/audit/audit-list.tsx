"use client";

import Link from "next/link";

import { FilterForm, useFilterValues, type FilterField } from "@/components/filter-form";
import { EffectBadge } from "@/components/memory-badges";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingRows } from "@/components/view-states";
import type { Schemas } from "@/lib/api/client";
import { useAudit } from "@/lib/api/queries";
import { formatTimestamp } from "@/lib/format";

const AUDIT_FILTERS = [
  { name: "action", label: "Action", kind: "text", placeholder: "memory.forget" },
  { name: "user_id", label: "User", kind: "text" },
  { name: "session_id", label: "Session", kind: "text" },
  { name: "resource_id", label: "Resource", kind: "text" },
  { name: "task_id", label: "Task", kind: "text" },
] as const satisfies readonly FilterField[];

function Actor({ actor }: { actor: Schemas["AuditActor"] }) {
  if (!actor.user_id) return <span className="text-muted-foreground">{actor.via}</span>;
  return (
    <div className="flex flex-col">
      <span className="font-mono text-xs">{actor.user_id}</span>
      <span className="text-muted-foreground text-xs">
        {actor.client ?? "unknown client"} via {actor.via}
      </span>
    </div>
  );
}

function Resource({ resource }: { resource: Schemas["AuditResource"] }) {
  const label = resource.path ?? resource.id;
  if (resource.type === "memory" && resource.id) {
    return (
      <Link href={`/memories/${resource.id}`} className="font-mono text-xs underline underline-offset-4">
        {resource.id}
      </Link>
    );
  }
  return (
    <span className="font-mono text-xs">
      {resource.type}
      {label ? ` ${label}` : null}
    </span>
  );
}

export function AuditList() {
  const filters = useFilterValues(AUDIT_FILTERS);
  const query = useAudit(filters);
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];
  const filtered = Object.keys(filters).length > 0;

  return (
    <>
      <FilterForm fields={AUDIT_FILTERS} />
      {query.isPending ? (
        <LoadingRows label="Loading audit entries" />
      ) : query.isError && rows.length === 0 ? (
        <ErrorState title="Could not load the audit log" error={query.error} />
      ) : rows.length === 0 ? (
        <EmptyState
          title={filtered ? "No entries match these filters" : "No audit entries yet"}
          detail={filtered ? "Change or clear the filters." : "Every governed action is recorded here."}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Seq</TableHead>
                <TableHead>Time (UTC)</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>Decision</TableHead>
                <TableHead>Policy</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((entry) =>
                entry.action === "personal_activity" ? (
                  // Another user's personal-scope activity: the gateway sends no ids.
                  <TableRow key={entry.id}>
                    <TableCell className="font-mono text-xs">{entry.seq}</TableCell>
                    <TableCell className="whitespace-nowrap">{formatTimestamp(entry.ts)}</TableCell>
                    <TableCell colSpan={5} className="text-muted-foreground italic">
                      Personal activity
                    </TableCell>
                  </TableRow>
                ) : (
                  <TableRow key={entry.id}>
                    <TableCell className="font-mono text-xs">{entry.seq}</TableCell>
                    <TableCell className="whitespace-nowrap">{formatTimestamp(entry.ts)}</TableCell>
                    <TableCell className="font-mono text-xs">{entry.action}</TableCell>
                    <TableCell>
                      <Actor actor={entry.actor} />
                    </TableCell>
                    <TableCell>
                      <Resource resource={entry.resource} />
                    </TableCell>
                    <TableCell>
                      <EffectBadge effect={entry.decision.effect} />
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {entry.decision.policy_ids.join(", ") || "None"}
                    </TableCell>
                  </TableRow>
                ),
              )}
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
          {query.isFetchNextPageError ? <ErrorState title="Could not load more entries" error={query.error} /> : null}
        </>
      )}
    </>
  );
}
