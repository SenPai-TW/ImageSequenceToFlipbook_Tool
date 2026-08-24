function securityHeaders(): HeadersInit {
  return {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  };
}

export async function handleRequest(
  request: Request,
  env: Pick<Env, "ASSETS">,
): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method Not Allowed", {
      status: 405,
      headers: {
        ...securityHeaders(),
        Allow: "GET, HEAD",
        "Cache-Control": "no-store",
      },
    });
  }

  const path = new URL(request.url).pathname;
  if (path.startsWith("/runtime/ffmpeg/")) {
    return new Response("Video runtime is temporarily disabled", {
      status: 410,
      headers: {
        ...securityHeaders(),
        "Cache-Control": "no-store",
      },
    });
  }

  return env.ASSETS.fetch(request);
}

export default {
  fetch(request, env) {
    return handleRequest(request, env);
  },
} satisfies ExportedHandler<Env>;
