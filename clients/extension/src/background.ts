import { handleMessage } from "./messages.ts";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Only this extension's own pages and content scripts may ask.
  if (sender.id !== chrome.runtime.id) return false;
  sendResponse(handleMessage(message));
  return false;
});
