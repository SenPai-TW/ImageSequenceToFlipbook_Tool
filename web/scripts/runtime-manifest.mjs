import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { join } from "node:path";

export const RUNTIME_VERSION = "0.12.10";

export const RUNTIME_FILES = Object.freeze([
  { packagePath: "@ffmpeg/core", variant: "st", filename: "ffmpeg-core.js", contentType: "text/javascript; charset=utf-8" },
  { packagePath: "@ffmpeg/core/wasm", variant: "st", filename: "ffmpeg-core.wasm", contentType: "application/wasm" },
  { packagePath: "@ffmpeg/core-mt", variant: "mt", filename: "ffmpeg-core.js", contentType: "text/javascript; charset=utf-8" },
  { packagePath: "@ffmpeg/core-mt/wasm", variant: "mt", filename: "ffmpeg-core.wasm", contentType: "application/wasm" },
  { packagePath: "@ffmpeg/core-mt/worker", variant: "mt", filename: "ffmpeg-core.worker.js", contentType: "text/javascript; charset=utf-8" },
]);

async function sha256File(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

function stagedPath(root, relativePath) {
  return join(root, ...relativePath.split("/"));
}

function expectedFiles() {
  return [...RUNTIME_FILES].sort((left, right) =>
    `${left.variant}/${left.filename}`.localeCompare(`${right.variant}/${right.filename}`),
  );
}

export async function buildManifest(root) {
  const files = [];
  for (const descriptor of expectedFiles()) {
    const path = `${descriptor.variant}/${descriptor.filename}`;
    const source = stagedPath(root, path);
    const [details, sha256] = await Promise.all([stat(source), sha256File(source)]);
    files.push({
      variant: descriptor.variant,
      filename: descriptor.filename,
      path,
      contentType: descriptor.contentType,
      bytes: details.size,
      sha256,
      key: `ffmpeg/${RUNTIME_VERSION}/${sha256}/${path}`,
    });
  }
  return { schemaVersion: 1, runtimeVersion: RUNTIME_VERSION, files };
}

export function serializeManifest(manifest) {
  return `${JSON.stringify(manifest, null, 2)}\n`;
}

export async function verifyManifest(root, manifest) {
  if (manifest?.schemaVersion !== 1 || manifest?.runtimeVersion !== RUNTIME_VERSION) {
    throw new Error("Unsupported runtime manifest schema or version");
  }
  const descriptors = expectedFiles();
  if (!Array.isArray(manifest.files) || manifest.files.length !== descriptors.length) {
    throw new Error("Runtime manifest does not contain the expected files");
  }
  for (let index = 0; index < descriptors.length; index += 1) {
    const descriptor = descriptors[index];
    const entry = manifest.files[index];
    const path = `${descriptor.variant}/${descriptor.filename}`;
    if (
      entry?.path !== path || entry.variant !== descriptor.variant ||
      entry.filename !== descriptor.filename || entry.contentType !== descriptor.contentType
    ) {
      throw new Error(`Unexpected runtime manifest entry at index ${index}`);
    }
    if (!/^[a-f0-9]{64}$/.test(entry.sha256)) {
      throw new Error(`Invalid SHA-256 for ${path}`);
    }
    const expectedKey = `ffmpeg/${RUNTIME_VERSION}/${entry.sha256}/${path}`;
    if (entry.key !== expectedKey) throw new Error(`Invalid content-addressed key for ${path}`);
    const source = stagedPath(root, path);
    const [details, actualSha256] = await Promise.all([stat(source), sha256File(source)]);
    if (entry.sha256 !== actualSha256) throw new Error(`SHA-256 mismatch for ${path}`);
    if (entry.bytes !== details.size) throw new Error(`Size mismatch for ${path}`);
  }
}
