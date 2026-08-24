import { describe, expect, it, vi } from "vitest";

import { handleRequest } from "../worker/index";

function testEnv(response = new Response("spa")): {
  env: Parameters<typeof handleRequest>[1];
  assetsFetch: ReturnType<typeof vi.fn>;
} {
  const assetsFetch = vi.fn(async () => response.clone());
  return {
    env: { ASSETS: { fetch: assetsFetch } } as unknown as Parameters<typeof handleRequest>[1],
    assetsFetch,
  };
}

describe("public Worker request boundary", () => {
  it.each(["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])(
    "rejects %s before static assets",
    async (method) => {
      const { env, assetsFetch } = testEnv();
      const response = await handleRequest(new Request("https://example.com/", { method }), env);

      expect(response.status).toBe(405);
      expect(response.headers.get("allow")).toBe("GET, HEAD");
      expect(response.headers.get("cache-control")).toBe("no-store");
      expect(assetsFetch).not.toHaveBeenCalled();
    },
  );

  it("does not inspect the URL or body of a rejected upload attempt", async () => {
    const { env, assetsFetch } = testEnv();
    const request = {
      method: "POST",
      get url(): string {
        throw new Error("URL must not be inspected");
      },
      get body(): never {
        throw new Error("Body must not be read");
      },
    } as unknown as Request;

    expect((await handleRequest(request, env)).status).toBe(405);
    expect(assetsFetch).not.toHaveBeenCalled();
  });

  it.each(["GET", "HEAD"])("returns 410 for every %s runtime request without R2 or assets", async (method) => {
    const { env, assetsFetch } = testEnv();
    const response = await handleRequest(
      new Request("https://example.com/runtime/ffmpeg/anything", { method }),
      env,
    );

    expect(response.status).toBe(410);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(assetsFetch).not.toHaveBeenCalled();
  });

  it.each(["GET", "HEAD"])("forwards ordinary %s requests to static assets", async (method) => {
    const { env, assetsFetch } = testEnv();
    const request = new Request("https://example.com/tool/settings", { method });
    const response = await handleRequest(request, env);

    expect(response.status).toBe(200);
    expect(assetsFetch).toHaveBeenCalledOnce();
    expect(assetsFetch).toHaveBeenCalledWith(request);
  });
});
