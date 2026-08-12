const RUNTIME_ROUTE = /^\/runtime\/ffmpeg\/(0\.12\.10)\/(st|mt)\/(ffmpeg-core\.(?:js|wasm|worker\.js))$/;
const IMMUTABLE_CACHE = "public, max-age=31536000, immutable";

interface RuntimeObject {
  body?: ReadableStream;
  httpEtag: string;
  writeHttpMetadata(headers: Headers): void;
}

export interface RuntimeEnv {
  ASSETS: { fetch(request: Request): Promise<Response> };
  FFMPEG_RUNTIME: {
    get(key: string): Promise<RuntimeObject | null>;
    head(key: string): Promise<RuntimeObject | null>;
  };
}

function securityHeaders(): HeadersInit {
  return {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  };
}

function contentTypeFor(filename: string): string {
  if (filename.endsWith(".wasm")) return "application/wasm";
  return "text/javascript; charset=utf-8";
}

async function runtimeResponse(
  request: Request,
  env: RuntimeEnv,
  match: RegExpMatchArray,
): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method Not Allowed", {
      status: 405,
      headers: { ...securityHeaders(), Allow: "GET, HEAD" },
    });
  }

  const [, version, variant, filename] = match;
  const key = `ffmpeg/${version}/${variant}/${filename}`;
  const object = request.method === "HEAD"
    ? await env.FFMPEG_RUNTIME.head(key)
    : await env.FFMPEG_RUNTIME.get(key);

  if (object === null) {
    return new Response("Runtime object not found", {
      status: 404,
      headers: securityHeaders(),
    });
  }

  const headers = new Headers(securityHeaders());
  object.writeHttpMetadata(headers);
  headers.set("Content-Type", headers.get("Content-Type") ?? contentTypeFor(filename));
  headers.set("Cache-Control", IMMUTABLE_CACHE);
  headers.set("ETag", object.httpEtag);

  const body = request.method === "HEAD" ? null : (object.body ?? null);
  return new Response(body, { status: 200, headers });
}

export async function handleRequest(request: Request, env: RuntimeEnv): Promise<Response> {
  const path = new URL(request.url).pathname;
  const match = path.match(RUNTIME_ROUTE);
  if (match !== null) return runtimeResponse(request, env, match);

  if (path.startsWith("/runtime/ffmpeg/")) {
    return new Response("Runtime object not found", {
      status: 404,
      headers: securityHeaders(),
    });
  }
  return env.ASSETS.fetch(request);
}

export default {
  fetch(request, env) {
    return handleRequest(request, env);
  },
} satisfies ExportedHandler<Env>;
