// Always UTC, written as "2026-11-11 09:12": the server and the browser may sit
// in different time zones, and local formatting would make the server-rendered
// text differ from the client's. Labels and column headers say "UTC" once.
export function formatTimestamp(iso: string): string {
  return new Date(iso).toISOString().slice(0, 16).replace("T", " ");
}
