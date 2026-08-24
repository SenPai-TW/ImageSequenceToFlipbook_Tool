import { cp, mkdir, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  RUNTIME_FILES,
  buildManifest,
  serializeManifest,
  verifyManifest,
} from "./runtime-manifest.mjs";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = join(projectRoot, ".runtime", "ffmpeg", "0.12.10");

await rm(outputRoot, { recursive: true, force: true });
for (const { packagePath, variant, filename } of RUNTIME_FILES) {
  const destination = `${variant}/${filename}`;
  const source = fileURLToPath(import.meta.resolve(packagePath));
  const output = join(outputRoot, destination);
  await mkdir(dirname(output), { recursive: true });
  await cp(source, output);
  const details = await stat(output);
  process.stdout.write(`staged ${destination} (${(details.size / 1024 / 1024).toFixed(1)} MiB)\n`);
}

const manifest = await buildManifest(outputRoot);
await verifyManifest(outputRoot, manifest);
await writeFile(join(projectRoot, ".runtime", "manifest.json"), serializeManifest(manifest));
process.stdout.write("verified .runtime/manifest.json\n");
