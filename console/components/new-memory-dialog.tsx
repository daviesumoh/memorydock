"use client";

import { useRouter } from "next/navigation";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ErrorState } from "@/components/view-states";
import { useCreateMemory, type MemoryCreate } from "@/lib/api/queries";

const TYPES = ["fact", "decision", "preference", "procedure", "finding", "open_question", "episode"] as const;

// The server picks the one scope of each level the user belongs to.
const SCOPES = [
  { value: "user", label: "Only me" },
  { value: "project", label: "My project" },
  { value: "team", label: "My team" },
  { value: "org", label: "Whole organization (needs approval)" },
] as const;

export function NewMemoryDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState("");
  const [type, setType] = useState<MemoryCreate["type"]>("decision");
  const [scope, setScope] = useState<NonNullable<MemoryCreate["scope"]>>("project");
  const create = useCreateMemory();
  const trimmed = content.trim();

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setContent("");
      create.reset();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button>New memory</Button>
      </DialogTrigger>
      <DialogContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate(
              { content: trimmed, type, scope },
              {
                onSuccess: (memory) => {
                  onOpenChange(false);
                  router.push(`/memories/${memory.id}`);
                },
              },
            );
          }}
        >
          <DialogHeader>
            <DialogTitle>New memory</DialogTitle>
            <DialogDescription>Saved as stated by you, so agents trust it above what they inferred.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="memory-content">Memory</Label>
            <Textarea
              id="memory-content"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              maxLength={4000}
              required
              placeholder="One fact, decision or preference"
            />
          </div>
          <div className="flex flex-wrap gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="memory-type">Type</Label>
              <Select value={type} onValueChange={(value) => setType(value as MemoryCreate["type"])}>
                <SelectTrigger id="memory-type" className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TYPES.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option.replace("_", " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="memory-scope">Who can see it</Label>
              <Select value={scope} onValueChange={(value) => setScope(value as typeof scope)}>
                <SelectTrigger id="memory-scope" className="w-64">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SCOPES.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {create.isError ? <ErrorState title="Could not save this memory" error={create.error} /> : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={create.isPending || !trimmed}>
              {create.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
