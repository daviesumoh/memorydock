import { badgeText, type ExtensionMessage, type Reply } from "./messages.ts";

declare const CONSOLE_URL: string;

const ERROR_TEXT: Record<string, string> = {
  sign_in_cancelled: "Sign-in was cancelled.",
  state_mismatch: "Sign-in could not be verified. Try again.",
  issuer_mismatch: "Sign-in came from an unexpected server.",
  network_error: "Could not reach the sign-in service.",
  gateway_unreachable: "Signed in, but the gateway could not be reached to confirm the account.",
};

const element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

function send(message: ExtensionMessage): Promise<Reply> {
  return chrome.runtime.sendMessage(message) as Promise<Reply>;
}

function showError(code: string | null) {
  const box = element("error");
  box.hidden = code === null;
  box.textContent = code === null ? "" : (ERROR_TEXT[code] ?? `Something failed (${code}).`);
}

async function refresh() {
  const status = await send({ type: "get_status", page: null });
  if (!status.ok || !("signedIn" in status)) {
    showError(status.ok ? "internal_error" : status.error);
    return;
  }
  element("sign-in").hidden = status.signedIn;
  element("sign-out").hidden = !status.signedIn;
  element("capture").textContent = `Capture: ${badgeText(status.capture)}`;

  const accountLine = element("account");
  if (!status.signedIn) {
    accountLine.textContent = "Not signed in.";
    return;
  }
  const account = await send({ type: "get_account" });
  if (account.ok && "email" in account && account.email) {
    accountLine.textContent = `Signed in as ${account.email}`;
  } else {
    accountLine.textContent = "Signed in.";
    if (!account.ok) showError(account.error === "gateway_unreachable" ? account.error : `account_${account.error}`);
  }
}

async function run(message: ExtensionMessage, button: HTMLButtonElement) {
  button.disabled = true;
  showError(null);
  const reply = await send(message);
  button.disabled = false;
  if (!reply.ok) showError(reply.error);
  await refresh();
}

element<HTMLAnchorElement>("console-link").href = CONSOLE_URL;
element<HTMLButtonElement>("sign-in").addEventListener("click", (event) => {
  void run({ type: "sign_in" }, event.currentTarget as HTMLButtonElement);
});
element<HTMLButtonElement>("sign-out").addEventListener("click", (event) => {
  void run({ type: "sign_out" }, event.currentTarget as HTMLButtonElement);
});
void refresh();
