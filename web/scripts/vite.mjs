import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const logPath = join(projectRoot, ".wrangler", "logs", "vite-wrangler.log");
const vite = join(projectRoot, "node_modules", "vite", "bin", "vite.js");
mkdirSync(dirname(logPath), { recursive: true });
const env = {
  ...process.env,
  CLOUDFLARE_CF_FETCH_ENABLED: "false",
  WRANGLER_LOG_PATH: logPath,
  XDG_CONFIG_HOME: join(projectRoot, ".wrangler", "xdg.config"),
};
for (const name of ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]) {
  delete env[name];
}
delete env.NODE_USE_ENV_PROXY;
const result = spawnSync(process.execPath, [vite, ...process.argv.slice(2)], {
  cwd: projectRoot,
  stdio: "inherit",
  env,
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
