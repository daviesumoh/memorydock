"use client";

import { CircleCheck, CircleX } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/view-states";
import { useMe, useVerifyAudit } from "@/lib/api/queries";

// Org admins only: the gateway refuses everyone else, so the button isn't shown to them.
export function VerifyChain() {
  const me = useMe();
  const verify = useVerifyAudit();

  if (!me.data?.roles.includes("admin")) return null;
  const result = verify.data;

  return (
    <div className="flex flex-col gap-3">
      <Button variant="outline" className="self-start" onClick={() => verify.mutate()} disabled={verify.isPending}>
        {verify.isPending ? "Verifying…" : "Verify chain"}
      </Button>
      {verify.isError ? <ErrorState title="Could not verify the chain" error={verify.error} /> : null}
      {result?.ok ? (
        <Alert>
          <CircleCheck aria-hidden />
          <AlertTitle>PASS: the chain verifies</AlertTitle>
          <AlertDescription>
            {result.checked} {result.checked === 1 ? "entry" : "entries"} recomputed; every hash matches.
          </AlertDescription>
        </Alert>
      ) : null}
      {result && !result.ok ? (
        <Alert variant="destructive">
          <CircleX aria-hidden />
          <AlertTitle>FAIL: broken at entry {result.first_bad_seq}</AlertTitle>
          <AlertDescription>
            {result.reason}. {result.checked} {result.checked === 1 ? "entry" : "entries"} verified before it.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
