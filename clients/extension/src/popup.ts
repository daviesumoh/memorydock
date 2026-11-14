import { badgeText, type MessageReply } from "./messages.ts";

declare const CONSOLE_URL: string;

async function main() {
  const link = document.getElementById("console-link") as HTMLAnchorElement;
  link.href = CONSOLE_URL;

  const status = document.getElementById("status")!;
  const reply = (await chrome.runtime.sendMessage({ type: "get_status" })) as MessageReply;
  status.textContent = reply.ok ? `Capture: ${badgeText(reply.status)}` : "Could not reach the extension.";
}

void main();
