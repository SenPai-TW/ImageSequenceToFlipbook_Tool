import { cloudflare } from "@cloudflare/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(({ mode }) => ({
  // Browser tests exercise only the client. The runtime route has its own
  // Worker-level tests, so this mode does not need to start Miniflare.
  plugins: [react(), ...(mode === "browser-test" ? [] : [cloudflare()])],
  optimizeDeps: {
    exclude: ["@jsquash/jpeg", "@jsquash/png", "@jsquash/resize"],
    include: ["utif"],
  },
  server: {
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
      "Cross-Origin-Resource-Policy": "same-origin",
    },
  },
  worker: {
    format: "es",
  },
}));
