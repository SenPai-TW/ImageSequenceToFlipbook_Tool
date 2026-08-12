import { describe, expect, it } from "vitest";

import { handleRequest, type RuntimeEnv } from "../worker/index";

function runtimeEnv(body: string | null = "runtime-binary"): RuntimeEnv {
  const object = body === null
    ? null
    : {
        body: new Blob([body]).stream(),
      httpEtag: '"runtime-etag"',
      httpMetadata: { contentType: "application/wasm" },
      writeHttpMetadata: (headers: Headers) => {
        headers.set("Content-Type", "application/wasm");
      },
      };

  return {
    FFMPEG_RUNTIME: {
      get: async () => object,
      head: async () => object,
    },
    ASSETS: {
      fetch: async () => new Response("spa"),
    },
  } satisfies RuntimeEnv;
}

describe("FFmpeg runtime endpoint", () => {
  it("streams a versioned object with immutable cache metadata", async () => {
    const response = await handleRequest(
      new Request("https://example.com/runtime/ffmpeg/0.12.10/st/ffmpeg-core.wasm"),
      runtimeEnv(),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/wasm");
    expect(response.headers.get("etag")).toBe('"runtime-etag"');
    expect(response.headers.get("cache-control")).toContain("immutable");
    expect(await response.text()).toBe("runtime-binary");
  });

  it("supports HEAD without returning the object body", async () => {
    const response = await handleRequest(
      new Request(
        "https://example.com/runtime/ffmpeg/0.12.10/mt/ffmpeg-core.worker.js",
        { method: "HEAD" },
      ),
      runtimeEnv(),
    );

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("");
  });

  it("returns 404 for missing objects and 405 for writes", async () => {
    const missing = await handleRequest(
      new Request("https://example.com/runtime/ffmpeg/0.12.10/st/missing.wasm"),
      runtimeEnv(null),
    );
    const write = await handleRequest(
      new Request("https://example.com/runtime/ffmpeg/0.12.10/st/ffmpeg-core.wasm", {
        method: "POST",
      }),
      runtimeEnv(),
    );

    expect(missing.status).toBe(404);
    expect(write.status).toBe(405);
    expect(write.headers.get("allow")).toBe("GET, HEAD");
  });

  it("never sends non-runtime requests to R2", async () => {
    const response = await handleRequest(
      new Request("https://example.com/tool/settings"),
      runtimeEnv(),
    );

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("spa");
  });
});
