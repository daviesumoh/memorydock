import { Suspense } from "react";

import { NewMemoryDialog } from "@/components/new-memory-dialog";
import { LoadingRows } from "@/components/view-states";

import { MemoryList } from "./memory-list";

export default function MemoriesPage() {
  return (
    <>
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Memories</h1>
        <NewMemoryDialog />
      </div>
      <Suspense fallback={<LoadingRows label="Loading memories" />}>
        <MemoryList />
      </Suspense>
    </>
  );
}
