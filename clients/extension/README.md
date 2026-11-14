# memorydock Chrome extension

Manifest V3 extension for capturing opted-in ChatGPT Project conversations into memorydock. Sign-in works. Capture does not exist yet and is always off: page facts need the verified DOM contract, and enabling a project needs the mappings route.

## What is here

- **Background service worker** (`src/background.ts`): the only context that holds tokens or calls the gateway. It answers four messages, and only from this extension: `get_status` (content script and popup), and `get_account`, `sign_in` and `sign_out` (popup only).
- **Content script on chatgpt.com** (`src/content.ts`): shows a read-only badge in a closed shadow root with the capture state from the background script. When the extension reloads, the orphaned script removes its badge.
- **Popup** (`src/popup.html`, `src/popup.ts`): sign in and out, the account from `/v1/me`, the capture state, and a link to the console.

## Sign-in

AuthKit authorization code with PKCE (S256) through `chrome.identity.launchWebAuthFlow`, as a public client with no secret. The token is bound to the gateway's MCP resource (`<GATEWAY_URL>/mcp`). Before using the code, the extension checks the redirect address, `state`, and AuthKit's `iss` (RFC 9207).

- The access token is kept in `storage.session` and the refresh token in `storage.local`, restricted to extension pages. If Chrome will not restrict it, the refresh token stays in `storage.session` and sign-in ends when the browser closes.
- Tokens are refreshed a minute before they expire, once for all callers. AuthKit refusing a refresh signs out; a network failure does not. Signing out while a refresh is running wins.

`CLIENT_ID` is the extension's client, registered once with AuthKit's dynamic client registration for the redirect `https://ohlflggckmdbbaooockgncafhecpjboc.chromiumapp.org/`.

## When capture is allowed

`src/capture-state.ts` decides, in this order, and reports the first thing in the way: layout drift, temporary chat, signed out, no conversation, chat outside a ChatGPT Project, project not ticked or not mapped. Chats outside a Project are never captured.

The manifest asks only for `storage` and `identity`, with host access to `https://chatgpt.com/*`, the gateway origin and the AuthKit origin.

## Extension id

`extension-key.pub` is put in the manifest's `key`, which fixes the id at `ohlflggckmdbbaooockgncafhecpjboc` for every build and every machine. Its sign-in redirect will be `https://ohlflggckmdbbaooockgncafhecpjboc.chromiumapp.org/`.

The private key is needed only to pack the extension for the Chrome Web Store. It is not in the repository.

## Build

```
cp clients/extension/.env.example clients/extension/.env.local   # fill in AUTHKIT_DOMAIN and CLIENT_ID
pnpm --filter memorydock-extension build
```

`dist/` is the unpacked extension. Settings are compiled in at build time; the build fails naming any missing or non-https URL (plain http is allowed only for localhost).

Load it in Chrome: `chrome://extensions`, turn on Developer mode, Load unpacked, choose `clients/extension/dist`. The id shown should be the one above.

## Checks

```
pnpm typecheck
pnpm test          # unit tests (Vitest)
pnpm build
pnpm test:e2e      # loads dist/ in Chromium; run pnpm build first
```

The e2e tests need Chromium (`pnpm exec playwright install chromium`). They check that Chrome assigns the pinned id, that the popup gets its status from the background script, and that the content script adds its badge on a stand-in chatgpt.com page; nothing reaches the real site.
