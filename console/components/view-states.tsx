import { CircleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { GatewayError } from "@/lib/api/errors";

export function LoadingRows({ rows = 5, label }: { rows?: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-2">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-lg border border-dashed p-8 text-center">
      <p className="font-medium">{title}</p>
      {detail ? <p className="text-muted-foreground mt-1 text-sm">{detail}</p> : null}
    </div>
  );
}

export function ErrorState({ title, error }: { title: string; error: unknown }) {
  const gateway = error instanceof GatewayError ? error : null;
  return (
    <Alert variant="destructive">
      <CircleAlert aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <p>{gateway?.message ?? "The request did not complete."}</p>
        <p className="font-mono text-xs">
          Error code: {gateway?.code ?? "network_error"}
          {gateway?.requestId ? ` · Request id: ${gateway.requestId}` : null}
        </p>
      </AlertDescription>
    </Alert>
  );
}
