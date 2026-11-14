import { createPublicKey } from "node:crypto";
import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

import { parseConfig } from "../src/config.ts";
import { buildManifest, extensionIdFromPublicKey } from "../src/manifest.ts";

const root = fileURLToPath(new URL("..", import.meta.url));
const dist = `${root}dist`;

// CI passes the settings as environment variables; locally they live in .env.local.
if (existsSync(`${root}.env.local`)) process.loadEnvFile(`${root}.env.local`);
const config = parseConfig(process.env);

const pem = await readFile(`${root}extension-key.pub`, "utf8");
const spkiDer = createPublicKey(pem).export({ type: "spki", format: "der" });
const { version } = JSON.parse(await readFile(`${root}package.json`, "utf8")) as { version: string };

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

await build({
  entryPoints: ["background", "content", "popup"].map((name) => `${root}src/${name}.ts`),
  outdir: dist,
  bundle: true,
  // Content scripts cannot be ES modules, so every entry is a plain script.
  format: "iife",
  target: "chrome120",
  define: { CONSOLE_URL: JSON.stringify(config.consoleUrl.href) },
  logLevel: "warning",
});

await copyFile(`${root}src/popup.html`, `${dist}/popup.html`);
await writeFile(
  `${dist}/manifest.json`,
  `${JSON.stringify(buildManifest(config, spkiDer, version), null, 2)}\n`,
);

console.log(`Built dist/ for extension id ${extensionIdFromPublicKey(spkiDer)}`);
