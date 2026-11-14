import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { gateway } from "./client";
import { unwrap } from "./errors";
import type { operations } from "./schema";

export type MemoryFilters = NonNullable<operations["list_memories"]["parameters"]["query"]>;
export type AuditFilters = NonNullable<operations["list_audit"]["parameters"]["query"]>;
export type MemoryCreate = operations["create_memory"]["requestBody"]["content"]["application/json"];

const PAGE_SIZE = 25;

export function useMemories(filters: Omit<MemoryFilters, "limit" | "cursor">) {
  return useInfiniteQuery({
    queryKey: ["memories", filters],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) =>
      unwrap(
        await gateway.GET("/v1/memories", {
          params: { query: { ...filters, limit: PAGE_SIZE, cursor: pageParam } },
          signal,
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

export function useMemory(memoryId: string) {
  return useQuery({
    queryKey: ["memory", memoryId],
    queryFn: async ({ signal }) =>
      unwrap(await gateway.GET("/v1/memories/{memory_id}", { params: { path: { memory_id: memoryId } }, signal })),
  });
}

export function useMemoryVersions(memoryId: string) {
  return useInfiniteQuery({
    queryKey: ["memory-versions", memoryId],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) =>
      unwrap(
        await gateway.GET("/v1/memories/{memory_id}/versions", {
          params: { path: { memory_id: memoryId }, query: { limit: PAGE_SIZE, cursor: pageParam } },
          signal,
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

export function useAudit(filters: Omit<AuditFilters, "limit" | "cursor">) {
  return useInfiniteQuery({
    queryKey: ["audit", filters],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) =>
      unwrap(
        await gateway.GET("/v1/audit", {
          params: { query: { ...filters, limit: PAGE_SIZE, cursor: pageParam } },
          signal,
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

// A write changes the memory, its history, every list it appears in and the audit log.
function refreshAfterWrite(client: QueryClient, memoryId: string) {
  for (const key of [["memory", memoryId], ["memory-versions", memoryId], ["memories"], ["audit"]]) {
    void client.invalidateQueries({ queryKey: key });
  }
}

export function useCreateMemory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: MemoryCreate) => unwrap(await gateway.POST("/v1/memories", { body })),
    onSuccess: (memory) => refreshAfterWrite(client, memory.id),
  });
}

export function useForgetMemory(memoryId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (reason: string | null) =>
      unwrap(
        await gateway.POST("/v1/memories/{memory_id}/forget", {
          params: { path: { memory_id: memoryId } },
          body: { reason },
        }),
      ),
    onSuccess: () => refreshAfterWrite(client, memoryId),
  });
}
