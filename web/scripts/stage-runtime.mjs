import { cp, mkdir, rm, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = join(projectRoot, ".runtime", "ffmpeg", "0.12.10");
const files = [
  ["@ffmpeg/core", "st/ffmpeg-core.js"],
  ["@ffmpeg/core/wasm", "st/ffmpeg-core.wasm"],
  ["@ffmpeg/core-mt", "mt/ffmpeg-core.js"],
  ["@ffmpeg/core-mt/wasm", "mt/ffmpeg-core.wasm"],
  ["@ffmpeg/core-mt/worker", "mt/ffmpeg-core.worker.js"],
];

await rm(outputRoot, { recursive: true, force: true });
for (const [packagePath, destination] of files) {
  const source = fileURLToPath(import.meta.resolve(packagePath));
  const output = join(outputRoot, destination);
  await mkdir(dirname(output), { recursive: true });
  await cp(source, output);
  const details = await stat(output);
  process.stdout.write(`staged ${destination} (${(details.size / 1024 / 1024).toFixed(1)} MiB)\n`);
}
