"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { StatusBadge, TypeBadge } from "@/components/memory-badges";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingRows } from "@/components/view-states";
import { GatewayError } from "@/lib/api/errors";
import { useMemory, useMemoryVersions } from "@/lib/api/queries";
import { formatTimestamp } from "@/lib/format";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-muted-foreground text-xs font-medium uppercase">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

function MemoryLink({ id }: { id: string }) {
  return (
    <Link href={`/memories/${id}`} className="font-mono text-xs underline underline-offset-4">
      {id}
    </Link>
  );
}

function VersionHistory({ memoryId }: { memoryId: string }) {
  const query = useMemoryVersions(memoryId);
  const versions = query.data?.pages.flatMap((page) => page.items) ?? [];

  if (query.isPending) return <LoadingRows rows={2} label="Loading versions" />;
  if (query.isError) return <ErrorState title="Could not load versions" error={query.error} />;
  if (versions.length === 0) return <EmptyState title="No versions recorded" />;

  return (
    <>
      <ol className="flex flex-col gap-3">
        {versions.map((version) => (
          <li key={version.version} className="rounded-md border p-3">
            <div className="mb-1 flex items-center gap-2 text-sm">
              <span className="font-medium">Version {version.version}</span>
              <StatusBadge status={version.status} />
              <span className="text-muted-foreground">{formatTimestamp(version.created_at)}</span>
            </div>
            <p className="text-sm whitespace-pre-wrap">
              {version.content ?? <span className="text-muted-foreground italic">Content forgotten</span>}
            </p>
          </li>
        ))}
      </ol>
      {query.hasNextPage ? (
        <Button variant="outline" className="self-start" onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}>
          {query.isFetchingNextPage ? "Loading…" : "Older versions"}
        </Button>
      ) : null}
    </>
  );
}

export function MemoryDetail({ memoryId }: { memoryId: string }) {
  const query = useMemory(memoryId);

  if (query.isPending) return <LoadingRows rows={3} label="Loading memory" />;
  if (query.isError) {
    const notFound = query.error instanceof GatewayError && query.error.status === 404;
    return notFound ? (
      <EmptyState title="Memory not found" detail="It does not exist, or you cannot read its scope." />
    ) : (
      <ErrorState title="Could not load this memory" error={query.error} />
    );
  }

  const memory = query.data;
  return (
    <article className="flex flex-col gap-6">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <TypeBadge type={memory.type} />
          <StatusBadge status={memory.status} />
          <span className="text-muted-foreground font-mono text-xs">{memory.id}</span>
        </div>
        {memory.forgotten ? (
          <Alert>
            <AlertTitle>Forgotten {formatTimestamp(memory.forgotten.at)}</AlertTitle>
            <AlertDescription>
              Content and search data were purged; only this record remains.
              {memory.forgotten.reason ? ` Reason: ${memory.forgotten.reason}` : null}
            </AlertDescription>
          </Alert>
        ) : (
          // Agent-written text: rendered as text, never as HTML.
          <p className="text-lg whitespace-pre-wrap">{memory.content}</p>
        )}
        {memory.instruction_like ? (
          <Alert variant="destructive">
            <AlertTitle>Reads like an instruction</AlertTitle>
            <AlertDescription>
              The gate flagged this memory as instruction-like. Agents receive it as quoted data, never as a command.
            </AlertDescription>
          </Alert>
        ) : null}
      </header>

      <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Field label="Scope">
          <span className="font-mono text-xs">{memory.scope_key}</span>
        </Field>
        <Field label="Category">{memory.category ?? "None"}</Field>
        <Field label="Version">{memory.version}</Field>
        <Field label="Updated">{formatTimestamp(memory.updated_at)}</Field>
        <Field label="Asserted by">{memory.trust.asserted_by.replace("_", " ")}</Field>
        <Field label="Confidence">{Math.round(memory.trust.confidence * 100)}%</Field>
        <Field label="Flags">{memory.trust.flags}</Field>
        <Field label="Expires">{memory.expires_at ? formatTimestamp(memory.expires_at) : "Never"}</Field>
        <Field label="Source client">{memory.provenance.source_client}</Field>
        <Field label="Captured by">{memory.provenance.captured_by}</Field>
        <Field label="Actor">
          <span className="font-mono text-xs">{memory.provenance.actor_user}</span>
        </Field>
        <Field label="Session">
          <span className="font-mono text-xs">{memory.provenance.session_id ?? "None"}</span>
        </Field>
      </dl>

      {memory.supersedes || memory.superseded_by || memory.conflicts_with.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className="font-semibold">Related memories</h2>
          <ul className="flex flex-col gap-1 text-sm">
            {memory.supersedes ? (
              <li>
                Replaces <MemoryLink id={memory.supersedes} />
              </li>
            ) : null}
            {memory.superseded_by ? (
              <li>
                Replaced by <MemoryLink id={memory.superseded_by} />
              </li>
            ) : null}
            {memory.conflicts_with.map((id) => (
              <li key={id}>
                Conflicts with <MemoryLink id={id} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="flex flex-col gap-3">
        <h2 className="font-semibold">Version history</h2>
        <VersionHistory memoryId={memory.id} />
      </section>
    </article>
  );
}
