"use client";

import { FilterForm, useFilterValues, type FilterField } from "@/components/filter-form";
import { EffectBadge } from "@/components/memory-badges";
import { TruncatedCell } from "@/components/truncated-cell";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingRows } from "@/components/view-states";
import type { Schemas } from "@/lib/api/client";
import { useAudit } from "@/lib/api/queries";
import { formatTimestamp } from "@/lib/format";

// Only the filters GET /v1/audit accepts.
const AUDIT_FILTERS = [
  { name: "action", label: "Action", kind: "text", placeholder: "memory.forget" },
  { name: "session_id", label: "Session", kind: "text" },
  { name: "resource_id", label: "Resource", kind: "text" },
] as const satisfies readonly FilterField[];

function actorText(actor: Schemas["AuditActor"]): string {
  if (!actor.user_id) return actor.via;
  return `${actor.user_id} · ${actor.client ?? "unknown client"} via ${actor.via}`;
}

function resourceText(resource: Schemas["AuditResource"]): string {
  return resource.id ? `${resource.type} ${resource.id}` : resource.type;
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
          {/* Fixed layout: columns keep their share of the width and long values
              are cut off rather than pushing the table past the page. */}
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[6%]">Seq</TableHead>
                <TableHead className="w-[14%]">Time (UTC)</TableHead>
                <TableHead className="w-[14%]">Action</TableHead>
                <TableHead className="w-[20%]">Actor</TableHead>
                <TableHead className="w-[18%]">Resource</TableHead>
                <TableHead className="w-[12%]">Decision</TableHead>
                <TableHead className="w-[16%]">Policy</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((entry) => {
                const seq = (
                  <TableCell className="align-top font-mono text-xs">{entry.seq}</TableCell>
                );
                const time = (
                  <TruncatedCell fullText={formatTimestamp(entry.ts)}>{formatTimestamp(entry.ts)}</TruncatedCell>
                );
                if (entry.personal_placeholder) {
                  // Another user's personal-scope activity: the gateway sends no ids.
                  return (
                    <TableRow key={entry.seq}>
                      {seq}
                      {time}
                      <TableCell colSpan={5} className="text-muted-foreground align-top italic">
                        Personal activity
                      </TableCell>
                    </TableRow>
                  );
                }
                const memoryId = entry.resource.type === "memory" ? entry.resource.id : null;
                const policies = entry.decision.policy_ids.join(", ") || "None";
                return (
                  <TableRow key={entry.seq}>
                    {seq}
                    {time}
                    <TruncatedCell fullText={entry.action} className="font-mono text-xs">
                      {entry.action}
                    </TruncatedCell>
                    <TruncatedCell fullText={actorText(entry.actor)} className="text-xs">
                      {actorText(entry.actor)}
                    </TruncatedCell>
                    <TruncatedCell
                      fullText={resourceText(entry.resource)}
                      href={memoryId ? `/memories/${memoryId}` : undefined}
                      hrefLabel="Open memory"
                      className="font-mono text-xs"
                    >
                      {resourceText(entry.resource)}
                    </TruncatedCell>
                    <TableCell className="align-top">
                      <EffectBadge effect={entry.decision.effect} />
                    </TableCell>
                    <TruncatedCell fullText={policies} className="font-mono text-xs">
                      {policies}
                    </TruncatedCell>
                  </TableRow>
                );
              })}
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
