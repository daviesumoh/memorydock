// Always UTC: the server and the browser may sit in different time zones, and
// local formatting would make the server-rendered text differ from the client's.
const timestamp = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

export function formatTimestamp(iso: string): string {
  return `${timestamp.format(new Date(iso))} UTC`;
}
