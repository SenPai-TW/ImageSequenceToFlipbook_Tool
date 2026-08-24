import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  RUNTIME_FILES,
  buildManifest,
  serializeManifest,
  verifyManifest,
} from "../scripts/runtime-manifest.mjs";

async function stagedRuntime() {
  const root = await mkdtemp(join(tmpdir(), "flipbook-runtime-"));
  for (const file of RUNTIME_FILES) {
    const path = join(root, file.variant, file.filename);
    await mkdir(join(root, file.variant), { recursive: true });
    await writeFile(path, `${file.variant}/${file.filename}`);
  }
  return root;
}

describe("runtime manifest", () => {
  it("is deterministic and content-addressed", async () => {
    const root = await stagedRuntime();
    const first = await buildManifest(root);
    const second = await buildManifest(root);

    expect(serializeManifest(first)).toBe(serializeManifest(second));
    expect(first.files).toHaveLength(5);
    for (const file of first.files) {
      expect(file.sha256).toMatch(/^[a-f0-9]{64}$/);
      expect(file.key).toBe(
        `ffmpeg/0.12.10/${file.sha256}/${file.variant}/${file.filename}`,
      );
      expect(file.bytes).toBeGreaterThan(0);
    }
    await expect(verifyManifest(root, first)).resolves.toBeUndefined();
  });

  it("rejects a staged file changed after manifest creation", async () => {
    const root = await stagedRuntime();
    const manifest = await buildManifest(root);
    const target = manifest.files[0];
    await writeFile(join(root, target.path), "tampered");

    await expect(verifyManifest(root, manifest)).rejects.toThrow("SHA-256");
  });

  it("serializes with a final newline and can be parsed again", async () => {
    const root = await stagedRuntime();
    const manifest = await buildManifest(root);
    const path = join(root, "manifest.json");
    await writeFile(path, serializeManifest(manifest));

    expect((await readFile(path, "utf8")).endsWith("\n")).toBe(true);
    await expect(verifyManifest(root, JSON.parse(await readFile(path, "utf8"))))
      .resolves.toBeUndefined();
  });
});
