import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const logPath = join(projectRoot, ".wrangler", "logs", "wrangler.log");
mkdirSync(dirname(logPath), { recursive: true });
const wrangler = join(projectRoot, "node_modules", "wrangler", "bin", "wrangler.js");
const result = spawnSync(process.execPath, [wrangler, ...process.argv.slice(2)], {
  cwd: projectRoot,
  stdio: "inherit",
  env: { ...process.env, WRANGLER_LOG_PATH: logPath },
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
