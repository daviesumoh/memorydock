# memorydock Chrome extension

Manifest V3 extension for capturing opted-in ChatGPT Project conversations into memorydock. This is the skeleton: it builds, loads in Chrome under a fixed id, and shows that capture is off. Sign-in, opt-in and capture are not built yet.

## What is here

- **Background service worker** (`src/background.ts`): answers a fixed set of messages, and only from this extension's own pages and scripts. It is the only context that will hold tokens or call the gateway. Today it answers `get_status`, always with capture off.
- **Content script on chatgpt.com** (`src/content.ts`): shows a read-only badge in a closed shadow root with the capture state from the background script. When the extension reloads, the orphaned script removes its badge.
- **Popup** (`src/popup.html`, `src/popup.ts`): shows the capture state and links to the console.

The manifest asks only for `storage` and `identity`, with host access to `https://chatgpt.com/*`, the gateway origin and the AuthKit origin.

## Extension id

`extension-key.pub` is put in the manifest's `key`, which fixes the id at `ohlflggckmdbbaooockgncafhecpjboc` for every build and every machine. Its sign-in redirect will be `https://ohlflggckmdbbaooockgncafhecpjboc.chromiumapp.org/`.

The private key is needed only to pack the extension for the Chrome Web Store. It is not in the repository.

## Build

```
cp clients/extension/.env.example clients/extension/.env.local   # fill in AUTHKIT_DOMAIN
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
