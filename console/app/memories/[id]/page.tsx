import Link from "next/link";
import { Suspense } from "react";

import { LoadingRows } from "@/components/view-states";

import { MemoryDetail } from "./memory-detail";

async function Detail({ params }: { params: PageProps<"/memories/[id]">["params"] }) {
  const { id } = await params;
  return <MemoryDetail memoryId={id} />;
}

export default function MemoryPage({ params }: PageProps<"/memories/[id]">) {
  return (
    <>
      <Link href="/memories" className="text-muted-foreground self-start text-sm underline-offset-4 hover:underline">
        ← All memories
      </Link>
      <Suspense fallback={<LoadingRows rows={3} label="Loading memory" />}>
        <Detail params={params} />
      </Suspense>
    </>
  );
}
