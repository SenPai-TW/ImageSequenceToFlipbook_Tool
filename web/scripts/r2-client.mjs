import { createReadStream } from "node:fs";
import { join } from "node:path";

import { PutObjectCommand, S3Client } from "@aws-sdk/client-s3";

import { verifyManifest } from "./runtime-manifest.mjs";

function requiredEnv(env, name) {
  const value = env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

export function createR2ClientFromEnv(env = process.env) {
  const accountId = requiredEnv(env, "CLOUDFLARE_ACCOUNT_ID");
  return new S3Client({
    region: "auto",
    endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId: requiredEnv(env, "R2_ACCESS_KEY_ID"),
      secretAccessKey: requiredEnv(env, "R2_SECRET_ACCESS_KEY"),
    },
  });
}

export const createOnlyMiddleware = (next) => async (args) => {
  args.request.headers["if-none-match"] = "*";
  return next(args);
};

export async function publishManifest(client, bucket, root, manifest) {
  await verifyManifest(root, manifest);
  for (const entry of manifest.files) {
    const command = new PutObjectCommand({
      Bucket: bucket,
      Key: entry.key,
      Body: createReadStream(join(root, ...entry.path.split("/"))),
      ContentLength: entry.bytes,
      ContentType: entry.contentType,
      CacheControl: "public, max-age=31536000, immutable",
      Metadata: { sha256: entry.sha256 },
    });
    command.middlewareStack.add(createOnlyMiddleware, {
      name: "createOnlyRuntimeObject",
      step: "build",
      priority: "high",
    });
    process.stdout.write(`publishing ${entry.key}\n`);
    try {
      await client.send(command);
    } catch (error) {
      if (error?.$metadata?.httpStatusCode === 412 || error?.name === "PreconditionFailed") {
        throw new Error(`Immutable runtime object already exists: ${entry.key}`, { cause: error });
      }
      throw error;
    }
  }
}
