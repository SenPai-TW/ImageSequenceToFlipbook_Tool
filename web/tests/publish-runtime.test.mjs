import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { buildManifest, RUNTIME_FILES } from "../scripts/runtime-manifest.mjs";
import { createOnlyMiddleware, publishManifest } from "../scripts/r2-client.mjs";

async function stagedRuntime() {
  const root = await mkdtemp(join(tmpdir(), "flipbook-publish-"));
  for (const file of RUNTIME_FILES) {
    await mkdir(join(root, file.variant), { recursive: true });
    await writeFile(join(root, file.variant, file.filename), file.filename);
  }
  return { root, manifest: await buildManifest(root) };
}

describe("immutable runtime publisher", () => {
  it("adds the create-only HTTP precondition", async () => {
    const next = vi.fn(async (args) => args);
    const request = { headers: {} };
    await createOnlyMiddleware(next)({ request });
    expect(request.headers["if-none-match"]).toBe("*");
  });

  it("publishes verified content-addressed objects with immutable metadata", async () => {
    const { root, manifest } = await stagedRuntime();
    const sent = [];
    const client = { send: vi.fn(async (command) => sent.push(command)) };

    await publishManifest(client, "runtime-bucket", root, manifest);

    expect(sent).toHaveLength(5);
    expect(sent[0].input.Bucket).toBe("runtime-bucket");
    expect(sent[0].input.Key).toBe(manifest.files[0].key);
    expect(sent[0].input.CacheControl).toBe("public, max-age=31536000, immutable");
    expect(sent[0].input.Metadata.sha256).toBe(manifest.files[0].sha256);
  });

  it("fails hard when an immutable key already exists", async () => {
    const { root, manifest } = await stagedRuntime();
    const conflict = Object.assign(new Error("exists"), {
      name: "PreconditionFailed",
      $metadata: { httpStatusCode: 412 },
    });
    const client = { send: vi.fn(async () => { throw conflict; }) };

    await expect(publishManifest(client, "runtime-bucket", root, manifest))
      .rejects.toThrow("already exists");
    expect(client.send).toHaveBeenCalledTimes(1);
  });
});
