import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createR2ClientFromEnv, publishManifest } from "./r2-client.mjs";

if (process.argv[2] !== "--remote") {
  throw new Error("Usage: node scripts/publish-runtime.mjs --remote");
}

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const runtimeRoot = join(projectRoot, ".runtime", "ffmpeg", "0.12.10");
const manifest = JSON.parse(await readFile(join(projectRoot, ".runtime", "manifest.json"), "utf8"));
const client = createR2ClientFromEnv();
try {
  await publishManifest(client, "flipbook-ffmpeg-runtime", runtimeRoot, manifest);
} finally {
  client.destroy();
}
