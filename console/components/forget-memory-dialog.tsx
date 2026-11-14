"use client";

import { useState } from "react";

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
import { Textarea } from "@/components/ui/textarea";
import { ErrorState } from "@/components/view-states";
import type { Schemas } from "@/lib/api/client";
import { useForgetMemory } from "@/lib/api/queries";

// Policy requires a reason to forget anything outside the user's own scope.
export function reasonRequired(memory: Pick<Schemas["MemoryOut"], "scope_level">) {
  return memory.scope_level !== "user";
}

export function ForgetMemoryDialog({ memory }: { memory: Schemas["MemoryOut"] }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const forget = useForgetMemory(memory.id);
  const required = reasonRequired(memory);
  const trimmed = reason.trim();

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setReason("");
      forget.reset();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="destructive">Forget</Button>
      </DialogTrigger>
      <DialogContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            forget.mutate(trimmed || null, { onSuccess: () => onOpenChange(false) });
          }}
        >
          <DialogHeader>
            <DialogTitle>Forget this memory?</DialogTitle>
            <DialogDescription>
              Its text is erased from the memory and every version, and the same text can&apos;t be saved again. The
              audit log keeps a record that it was forgotten and by whom. Backups keep data until their retention period
              ends.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="forget-reason">Reason{required ? "" : " (optional)"}</Label>
            <Textarea
              id="forget-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={500}
              required={required}
              placeholder={required ? "Required for memories shared beyond you" : undefined}
            />
          </div>
          {forget.isError ? <ErrorState title="Could not forget this memory" error={forget.error} /> : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" variant="destructive" disabled={forget.isPending || (required && !trimmed)}>
              {forget.isPending ? "Forgetting…" : "Forget"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
