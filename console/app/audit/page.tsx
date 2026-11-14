import { Suspense } from "react";

import { VerifyChain } from "@/components/verify-chain";
import { LoadingRows } from "@/components/view-states";

import { AuditList } from "./audit-list";

export default function AuditPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold">Audit log</h1>
      <VerifyChain />
      <Suspense fallback={<LoadingRows label="Loading audit entries" />}>
        <AuditList />
      </Suspense>
    </>
  );
}
