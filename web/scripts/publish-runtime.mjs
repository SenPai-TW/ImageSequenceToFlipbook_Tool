import { mkdir, readdir } from "node:fs/promises";
import { dirname, join, relative, sep } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const mode = process.argv[2];
if (mode !== "--local" && mode !== "--remote") {
  throw new Error("Usage: node scripts/publish-runtime.mjs --local|--remote");
}

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const runtimeRoot = join(projectRoot, ".runtime");
const bucket = "flipbook-ffmpeg-runtime";
const wranglerLog = join(projectRoot, ".wrangler", "logs", "wrangler.log");
const wrangler = join(projectRoot, "node_modules", "wrangler", "bin", "wrangler.js");
await mkdir(dirname(wranglerLog), { recursive: true });

async function filesUnder(folder) {
  const entries = await readdir(folder, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const path = join(folder, entry.name);
    return entry.isDirectory() ? filesUnder(path) : [path];
  }));
  return nested.flat();
}

for (const path of await filesUnder(runtimeRoot)) {
  const key = relative(runtimeRoot, path).split(sep).join("/");
  const contentType = path.endsWith(".wasm") ? "application/wasm" : "text/javascript; charset=utf-8";
  process.stdout.write(`publishing ${key} (${mode.slice(2)})\n`);
  const result = spawnSync(process.execPath, [
    wrangler, "r2", "object", "put", `${bucket}/${key}`,
    "--file", path,
    "--content-type", contentType,
    "--cache-control", "public, max-age=31536000, immutable",
    mode,
  ], {
    cwd: projectRoot,
    stdio: "inherit",
    env: { ...process.env, WRANGLER_LOG_PATH: wranglerLog },
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
