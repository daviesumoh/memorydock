import { badgeText, type MessageReply } from "./messages.ts";

const HOST_ID = "memorydock-badge";

function renderBadge(text: string): HTMLElement {
  const host = document.createElement("div");
  host.id = HOST_ID;
  // A closed shadow root keeps chatgpt.com's styles and scripts out of the badge.
  const shadow = host.attachShadow({ mode: "closed" });
  const badge = document.createElement("div");
  badge.textContent = text;
  badge.setAttribute("role", "status");
  badge.style.cssText =
    "position:fixed;bottom:12px;right:12px;z-index:2147483647;padding:4px 8px;" +
    "border-radius:6px;font:12px system-ui,sans-serif;background:#222;color:#eee;opacity:.85;";
  shadow.append(badge);
  document.documentElement.append(host);
  return host;
}

async function main() {
  const reply = (await chrome.runtime.sendMessage({ type: "get_status" })) as MessageReply;
  if (!reply.ok) return;
  const host = renderBadge(badgeText(reply.status));

  // After the extension reloads, this script is orphaned: chrome.runtime.id is
  // gone and messaging throws. Remove the badge instead of showing stale state.
  const orphanCheck = setInterval(() => {
    if (!chrome.runtime?.id) {
      clearInterval(orphanCheck);
      host.remove();
    }
  }, 2_000);
}

if (!document.getElementById(HOST_ID)) void main();
