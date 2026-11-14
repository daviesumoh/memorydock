"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, ErrorState, LoadingRows } from "@/components/view-states";
import type { Schemas } from "@/lib/api/client";
import { useSessions, useSetSessionStatus } from "@/lib/api/queries";
import { formatTimestamp } from "@/lib/format";

type Session = Schemas["SessionOut"];

const STATUS_VARIANT: Record<Session["status"], "default" | "secondary" | "destructive" | "outline"> = {
  active: "default",
  paused: "secondary",
  revoked: "destructive",
  ended: "outline",
};

function RevokeDialog({ session }: { session: Session }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const revoke = useSetSessionStatus();

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setReason("");
      revoke.reset();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" variant="destructive">
          Revoke
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            revoke.mutate(
              { id: session.id, action: "revoke", reason: reason.trim() || null },
              { onSuccess: () => onOpenChange(false) },
            );
          }}
        >
          <DialogHeader>
            <DialogTitle>Revoke this {session.client} session?</DialogTitle>
            <DialogDescription>
              Its next call is denied, and it can&apos;t be resumed. The agent has to sign in again to get a new
              session.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="revoke-reason">Reason (optional)</Label>
            <Textarea
              id="revoke-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={500}
            />
          </div>
          {revoke.isError ? <ErrorState title="Could not revoke this session" error={revoke.error} /> : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" variant="destructive" disabled={revoke.isPending}>
              {revoke.isPending ? "Revoking…" : "Revoke"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Actions({ session, current }: { session: Session; current: boolean }) {
  const change = useSetSessionStatus();
  // The gateway refuses changes to the session the console itself is using.
  if (current) return <span className="text-muted-foreground text-xs">This console</span>;
  if (session.status === "revoked" || session.status === "ended") return null;

  const pauseOrResume = session.status === "active" ? "pause" : "resume";
  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={change.isPending}
          onClick={() => change.mutate({ id: session.id, action: pauseOrResume })}
        >
          {pauseOrResume === "pause" ? "Pause" : "Resume"}
        </Button>
        <RevokeDialog session={session} />
      </div>
      {change.isError ? <ErrorState title={`Could not ${pauseOrResume} this session`} error={change.error} /> : null}
    </div>
  );
}

export function SessionList() {
  const query = useSessions();

  if (query.isPending) return <LoadingRows label="Loading sessions" />;
  if (query.isError) return <ErrorState title="Could not load sessions" error={query.error} />;
  const { items, current_session_id: currentId } = query.data;
  if (items.length === 0) return <EmptyState title="No sessions yet" detail="Sessions appear once an agent signs in." />;

  return (
    <Table className="table-fixed">
      <TableHeader>
        <TableRow>
          <TableHead className="w-[14%]">Client</TableHead>
          <TableHead className="w-[22%]">User</TableHead>
          <TableHead className="w-[12%]">Status</TableHead>
          <TableHead className="w-[16%]">Started (UTC)</TableHead>
          <TableHead className="w-[16%]">Last seen (UTC)</TableHead>
          <TableHead className="w-[20%]">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((session) => (
          <TableRow key={session.id}>
            <TableCell className="align-top">{session.client}</TableCell>
            <TableCell className="truncate align-top font-mono text-xs" title={session.user_id}>
              {session.user_id}
            </TableCell>
            <TableCell className="align-top">
              <Badge variant={STATUS_VARIANT[session.status]}>{session.status}</Badge>
            </TableCell>
            <TableCell className="align-top text-xs">{formatTimestamp(session.started_at)}</TableCell>
            <TableCell className="align-top text-xs">{formatTimestamp(session.last_seen_at)}</TableCell>
            <TableCell className="align-top">
              <Actions session={session} current={session.id === currentId} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
