// Cursor paging with the gateway's rules: limit 1–100 (default 50), an opaque
// base64url cursor of {k: <last id>, v: 1}, and 422 invalid_cursor for anything
// that does not decode to a key on the list.

export const MAX_LIMIT = 100;

export type PageResult<T> = { items: T[]; next_cursor: string | null } | { error: "invalid_limit" | "invalid_cursor" };

// btoa/atob rather than Buffer: these handlers also run in the browser.
export function encodeCursor(key: string): string {
  return btoa(JSON.stringify({ k: key, v: 1 })).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function decodeCursor(cursor: string): string | null {
  if (!/^[A-Za-z0-9_-]+$/.test(cursor)) return null;
  try {
    const parsed: unknown = JSON.parse(atob(cursor.replaceAll("-", "+").replaceAll("_", "/")));
    if (typeof parsed !== "object" || parsed === null) return null;
    const { k, v } = parsed as { k?: unknown; v?: unknown };
    return v === 1 && typeof k === "string" ? k : null;
  } catch {
    return null;
  }
}

export function paginate<T>(items: T[], keyOf: (item: T) => string, params: URLSearchParams): PageResult<T> {
  const rawLimit = params.get("limit");
  const limit = rawLimit === null ? 50 : Number(rawLimit);
  if (!Number.isInteger(limit) || limit < 1 || limit > MAX_LIMIT) return { error: "invalid_limit" };

  let start = 0;
  const cursor = params.get("cursor");
  if (cursor !== null) {
    const key = decodeCursor(cursor);
    const index = key === null ? -1 : items.findIndex((item) => keyOf(item) === key);
    if (index === -1) return { error: "invalid_cursor" };
    start = index + 1;
  }

  const page = items.slice(start, start + limit);
  const hasMore = start + limit < items.length;
  return { items: page, next_cursor: hasMore ? encodeCursor(keyOf(page[page.length - 1])) : null };
}
