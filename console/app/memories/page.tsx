import { Suspense } from "react";

import { LoadingRows } from "@/components/view-states";

import { MemoryList } from "./memory-list";

export default function MemoriesPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold">Memories</h1>
      <Suspense fallback={<LoadingRows label="Loading memories" />}>
        <MemoryList />
      </Suspense>
    </>
  );
}
