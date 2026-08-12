import { spawn } from "node:child_process";
import http from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const playwright = join(projectRoot, "node_modules", "@playwright", "test", "cli.js");
const vite = join(projectRoot, "node_modules", "vite", "bin", "vite.js");
const env = { ...process.env };
const directAgent = new http.Agent({ proxyEnv: {} });

// Local browser tests must talk directly to Vite. Some managed environments
// inject a proxy that cannot reach 127.0.0.1.
for (const name of [
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "ALL_PROXY",
  "http_proxy",
  "https_proxy",
  "all_proxy",
]) {
  delete env[name];
}
env.NO_PROXY = "127.0.0.1,localhost";
env.no_proxy = env.NO_PROXY;
env.NODE_USE_ENV_PROXY = "0";
env.PLAYWRIGHT_EXTERNAL_SERVER = "1";

function waitForServer(url, attempts = 80) {
  return new Promise((resolve, reject) => {
    const check = (remaining) => {
      const request = http.get(url, { agent: directAgent }, (response) => {
        response.resume();
        if ((response.statusCode ?? 500) < 500) {
          resolve();
          return;
        }
        retry(remaining);
      });
      request.on("error", () => retry(remaining));
      request.setTimeout(1_000, () => request.destroy());
    };
    const retry = (remaining) => {
      if (remaining <= 0) {
        reject(new Error(`Vite did not become ready at ${url}`));
        return;
      }
      setTimeout(() => check(remaining - 1), 250);
    };
    check(attempts);
  });
}

const server = spawn(
  process.execPath,
  [vite, "--mode", "browser-test", "--host", "127.0.0.1"],
  { cwd: projectRoot, stdio: "inherit", env },
);

const stopServer = () => {
  if (!server.killed) server.kill();
};
process.once("SIGINT", stopServer);
process.once("SIGTERM", stopServer);

try {
  await waitForServer("http://127.0.0.1:5173");
  const runner = spawn(
    process.execPath,
    [playwright, ...process.argv.slice(2)],
    { cwd: projectRoot, stdio: "inherit", env },
  );
  const code = await new Promise((resolve, reject) => {
    runner.once("error", reject);
    runner.once("exit", (exitCode) => resolve(exitCode ?? 1));
  });
  stopServer();
  process.exitCode = code;
} catch (error) {
  stopServer();
  throw error;
}
