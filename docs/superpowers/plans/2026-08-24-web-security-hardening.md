# WEB Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce an 8192 px browser-only image-processing budget, pause all video execution, reject every request body at the Cloudflare edge, and publish maintainer FFmpeg runtimes under verified immutable SHA-256 keys.

**Architecture:** A single domain resource-budget module validates geometry and files at the UI, public API, and image Worker boundaries. The React production graph becomes image-only while showing a disabled video option. The Worker runs before every static request, rejects non-`GET`/`HEAD` methods, and returns `410` for all runtime paths. Maintainer runtime publication uses a deterministic manifest plus an atomic R2 S3 `If-None-Match: *` upload.

**Tech Stack:** TypeScript 7, React 19, Vite 8, Vitest 4, Playwright, Cloudflare Workers Static Assets, Node.js 24, AWS SDK for JavaScript v3 (development-only R2 publisher).

## Global Constraints

- Maximum output width and height: 8192 px.
- Maximum output pixels and maximum decoded source pixels: 67,108,864.
- Maximum decoded source width and height: 8192 px.
- Maximum grid capacity and selected image count: 512.
- Maximum individual image size: 128 MiB; maximum combined image size: 1 GiB.
- User media must remain inside the browser tab. No Worker route may accept or read a request body.
- Only `GET` and `HEAD` may reach static assets; all `/runtime/ffmpeg/*` requests return `410` while video is paused.
- Production client output must not import or execute FFmpeg.
- Runtime keys use `ffmpeg/<version>/<sha256>/<variant>/<filename>` and may only be created atomically, never overwritten.
- Keep FFmpeg source modules and runtime packages for a later remediation; do not re-enable video in this plan.

---

### Task 1: Central Resource Budget

**Files:**
- Create: `WEB/src/domain/resource-budget.ts`
- Modify: `WEB/tests/domain.test.ts`

**Interfaces:**
- Produces: `RESOURCE_LIMITS`, `ResourceLimitError`, `validateOutputGeometry()`, `validateImageFiles()`, `validateDecodedImage()`.
- Consumes: `Pick<FlipbookOptions, "cols" | "rows" | "tileSize">`.

- [ ] **Step 1: Write failing boundary tests**

Add tests that use structural file metadata so large buffers are not allocated:

```ts
import {
  RESOURCE_LIMITS,
  validateDecodedImage,
  validateImageFiles,
  validateOutputGeometry,
} from "../src/domain/resource-budget";

it("accepts the exact 8192 square output boundary", () => {
  expect(validateOutputGeometry({ cols: 1, rows: 1, tileSize: 8192 })).toMatchObject({
    width: 8192,
    height: 8192,
    pixels: 8192 * 8192,
    capacity: 1,
  });
});

it.each([
  [{ cols: 1, rows: 1, tileSize: 8193 }, "8192"],
  [{ cols: 513, rows: 1, tileSize: 1 }, "512"],
  [{ cols: Number.MAX_SAFE_INTEGER, rows: 1, tileSize: 2 }, "安全範圍"],
])("rejects unsafe output geometry", (options, message) => {
  expect(() => validateOutputGeometry(options)).toThrow(message);
});

it("rejects excessive file count and byte budgets without allocating the files", () => {
  const files = Array.from({ length: 513 }, (_, index) => ({ name: `${index}.png`, size: 1 }));
  expect(() => validateImageFiles(files)).toThrow("512");
  expect(() => validateImageFiles([{ name: "huge.png", size: RESOURCE_LIMITS.maxFileBytes + 1 }]))
    .toThrow("128 MiB");
  expect(() => validateImageFiles([
    { name: "a.png", size: RESOURCE_LIMITS.maxTotalBytes },
    { name: "b.png", size: 1 },
  ])).toThrow("1 GiB");
});

it("rejects decoded source dimensions above the 8192 boundary", () => {
  expect(() => validateDecodedImage(8193, 1, "bomb.png")).toThrow("8192");
  expect(() => validateDecodedImage(8192, 8192, "edge.png")).not.toThrow();
});
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `cd WEB && npm test -- tests/domain.test.ts`

Expected: FAIL because `resource-budget.ts` does not exist.

- [ ] **Step 3: Implement checked resource validation**

Create the module with these exact exports and fail-closed multiplication:

```ts
import type { FlipbookOptions } from "./types";

const MIB = 1024 * 1024;

export const RESOURCE_LIMITS = Object.freeze({
  maxOutputEdge: 8192,
  maxOutputPixels: 8192 * 8192,
  maxDecodedEdge: 8192,
  maxDecodedPixels: 8192 * 8192,
  maxFrameCount: 512,
  maxFileBytes: 128 * MIB,
  maxTotalBytes: 1024 * MIB,
});

export class ResourceLimitError extends Error {
  override name = "ResourceLimitError";
}

export interface ValidatedOutputGeometry {
  width: number;
  height: number;
  pixels: number;
  rgbaBytes: number;
  capacity: number;
}

type ImageFileMetadata = Pick<File, "name" | "size">;

function checkedMultiply(left: number, right: number, label: string): number {
  const result = left * right;
  if (!Number.isSafeInteger(result)) {
    throw new ResourceLimitError(`${label}超出安全範圍。`);
  }
  return result;
}

export function validateOutputGeometry(
  options: Pick<FlipbookOptions, "cols" | "rows" | "tileSize">,
): ValidatedOutputGeometry {
  const { cols, rows, tileSize } = options;
  if (![cols, rows, tileSize].every((value) => Number.isSafeInteger(value) && value >= 1)) {
    throw new ResourceLimitError("欄數、列數與單格尺寸都必須是大於 0 的整數。");
  }
  const capacity = checkedMultiply(cols, rows, "網格容量");
  if (capacity > RESOURCE_LIMITS.maxFrameCount) {
    throw new ResourceLimitError("網格容量不得超過 512 格。");
  }
  const width = checkedMultiply(cols, tileSize, "輸出寬度");
  const height = checkedMultiply(rows, tileSize, "輸出高度");
  if (width > RESOURCE_LIMITS.maxOutputEdge || height > RESOURCE_LIMITS.maxOutputEdge) {
    throw new ResourceLimitError("輸出寬度與高度不得超過 8192 px。");
  }
  const pixels = checkedMultiply(width, height, "輸出像素");
  if (pixels > RESOURCE_LIMITS.maxOutputPixels) {
    throw new ResourceLimitError("輸出總像素不得超過 8192 × 8192。");
  }
  return { width, height, pixels, rgbaBytes: checkedMultiply(pixels, 4, "RGBA 記憶體"), capacity };
}

export function validateImageFiles(files: readonly ImageFileMetadata[]): void {
  if (files.length > RESOURCE_LIMITS.maxFrameCount) {
    throw new ResourceLimitError("一次最多處理 512 張圖片。");
  }
  let total = 0;
  for (const file of files) {
    if (!Number.isSafeInteger(file.size) || file.size < 0) throw new ResourceLimitError("圖片檔案大小無效。");
    if (file.size > RESOURCE_LIMITS.maxFileBytes) throw new ResourceLimitError(`${file.name} 超過 128 MiB。`);
    total += file.size;
    if (!Number.isSafeInteger(total) || total > RESOURCE_LIMITS.maxTotalBytes) {
      throw new ResourceLimitError("圖片總大小不得超過 1 GiB。");
    }
  }
}

export function validateDecodedImage(width: number, height: number, filename: string): void {
  if (![width, height].every((value) => Number.isSafeInteger(value) && value >= 1)) {
    throw new ResourceLimitError(`${filename} 的圖片尺寸無效。`);
  }
  if (width > RESOURCE_LIMITS.maxDecodedEdge || height > RESOURCE_LIMITS.maxDecodedEdge) {
    throw new ResourceLimitError(`${filename} 的寬度或高度超過 8192 px。`);
  }
  if (checkedMultiply(width, height, `${filename} 的像素數`) > RESOURCE_LIMITS.maxDecodedPixels) {
    throw new ResourceLimitError(`${filename} 的總像素超過安全上限。`);
  }
}
```

- [ ] **Step 4: Run focused tests**

Run: `cd WEB && npm test -- tests/domain.test.ts`

Expected: all domain tests pass after replacing the old “warnings never block” expectation with boundary assertions.

- [ ] **Step 5: Commit**

```bash
git add WEB/src/domain/resource-budget.ts WEB/tests/domain.test.ts
git commit -m "feat(web): enforce image resource budgets"
```

---

### Task 2: Decode Guards and Worker Enforcement

**Files:**
- Create: `WEB/src/processing/image-dimensions.ts`
- Create: `WEB/tests/image-dimensions.test.ts`
- Modify: `WEB/src/processing/image.worker.ts`
- Modify: `WEB/src/processing/generate-flipbook.ts`
- Modify: `WEB/src/processing/process-images.ts`

**Interfaces:**
- Consumes: Task 1 validators.
- Produces: `dimensionsFromPng()`, `dimensionsFromJpeg()`, guarded `decodeImage()`, and layered validation at public API/Worker boundaries.

- [ ] **Step 1: Write failing PNG/JPEG header tests**

Construct minimal byte arrays with dimensions at the real format offsets. Include 8192 accepted, 8193 rejected through `validateDecodedImage`, truncated input rejected, and a JPEG SOF marker found after an APP segment.

```ts
expect(dimensionsFromPng(pngHeader(8192, 8192))).toEqual({ width: 8192, height: 8192 });
expect(dimensionsFromJpeg(jpegWithSof(640, 480))).toEqual({ width: 640, height: 480 });
expect(() => dimensionsFromPng(new Uint8Array(8))).toThrow("PNG 標頭");
expect(() => dimensionsFromJpeg(new Uint8Array([0xff, 0xd8, 0xff, 0xd9]))).toThrow("JPEG 尺寸");
```

- [ ] **Step 2: Run the new test and verify failure**

Run: `cd WEB && npm test -- tests/image-dimensions.test.ts`

Expected: FAIL because the parser module does not exist.

- [ ] **Step 3: Implement fail-closed header parsers**

Implement PNG signature/IHDR parsing with `DataView.getUint32(..., false)`. Implement JPEG marker walking with bounds-checked segment lengths and accept SOF markers `C0-C3`, `C5-C7`, `C9-CB`, `CD-CF`; reject malformed/truncated data without decoding.

```ts
export interface ImageDimensions { width: number; height: number }
export function dimensionsFromPng(bytes: Uint8Array): ImageDimensions;
export function dimensionsFromJpeg(bytes: Uint8Array): ImageDimensions;
```

- [ ] **Step 4: Add layered checks around decode and allocation**

In `generateFlipbook()` call `validateOutputGeometry(request.options)` and `validateImageFiles(frames)` before spawning the Worker. In `processImages()` repeat both checks before `postMessage`.

In `image.worker.ts`:

```ts
validateOutputGeometry(options);
validateImageFiles(files);
```

Before PNG/JPEG decode, parse dimensions from the already size-bounded `ArrayBuffer` and call `validateDecodedImage`. For TIFF, call `UTIF.decode(buffer)`, validate `first.width/first.height`, and only then call `UTIF.decodeImage`. After every decoder returns, repeat `validateDecodedImage(decoded.width, decoded.height, file.name)` before resize. Re-run `validateOutputGeometry` immediately before allocating `new Uint8ClampedArray(width * height * 4)`.

- [ ] **Step 5: Run domain, parser, and processing tests**

Run: `cd WEB && npm test`

Expected: all tests pass; malformed headers fail with user-safe messages.

- [ ] **Step 6: Commit**

```bash
git add WEB/src/processing/image-dimensions.ts WEB/tests/image-dimensions.test.ts WEB/src/processing/image.worker.ts WEB/src/processing/generate-flipbook.ts WEB/src/processing/process-images.ts
git commit -m "fix(web): reject oversized decoded images"
```

---

### Task 3: Pause Video and Remove FFmpeg from the Client Graph

**Files:**
- Modify: `WEB/src/domain/types.ts`
- Modify: `WEB/src/processing/generate-flipbook.ts`
- Modify: `WEB/src/processing/index.ts`
- Modify: `WEB/src/App.tsx`
- Modify: `WEB/tests/e2e/app.spec.ts`

**Interfaces:**
- Produces: image-only `GenerateFlipbookRequest` and a disabled video UI control.
- Leaves untouched: `WEB/src/processing/video.ts` and FFmpeg package declarations.

- [ ] **Step 1: Write failing browser assertions**

```ts
await expect(page.getByRole("button", { name: /影片.*安全性更新中/ })).toBeDisabled();
await expect(page.getByLabel("影片檔案")).toHaveCount(0);
await expect(page.getByText("安全性更新中，暫停使用")).toBeVisible();
```

Keep the existing network listener and strengthen it so every request with `postData()` fails the test and every external origin fails the test.

- [ ] **Step 2: Run the Chromium E2E test and verify failure**

Run: `cd WEB && $env:PLAYWRIGHT_USE_SYSTEM_CHROME='1'; npm run test:e2e -- --project=chromium`

Expected: FAIL because video input is still active.

- [ ] **Step 3: Make the public processing API image-only**

Change `GenerateFlipbookRequest.source` to `ImagesSource`. Delete `VideoSource` and `SourceInput` from `domain/types.ts`, but retain `VideoMetadata` because the parked `video.ts` source still type-checks. Delete the `extractVideoFrames` import and video branch from `generate-flipbook.ts`. Stop exporting `probeVideo`, `SourceInput`, `VideoSource`, and `VideoMetadata` from `src/processing/index.ts`.

- [ ] **Step 4: Render a disabled video option without video state or handlers**

Remove `videoFile`, `videoMetadata`, range state, probe/generation controllers, `applyVideo`, and video drag-drop behavior from `App.tsx`. Keep an image mode button and add:

```tsx
<button type="button" className="mode-tab" disabled aria-label="影片功能：安全性更新中，暫停使用">
  <VideoIcon />
  <span><strong>影片</strong><small>安全性更新中，暫停使用</small></span>
</button>
```

Set file drop and generation logic to images only. Add `max={8192}` to dimension fields and compute the blocking error without throwing during render:

```ts
const budgetError = useMemo(() => {
  try {
    validateOutputGeometry(options);
    validateImageFiles(imageFiles);
    return null;
  } catch (caught) {
    return caught instanceof Error ? caught.message : "目前設定超出安全處理範圍。";
  }
}, [imageFiles, options]);
const ready = imageFiles.length > 0 && budgetError === null;
```

Render `budgetError` as a blocking error next to the existing warnings; disable Generate when it is non-null.

- [ ] **Step 5: Run E2E, build, and inspect emitted client assets**

Run:

```powershell
cd WEB
$env:PLAYWRIGHT_USE_SYSTEM_CHROME='1'
npm run test:e2e -- --project=chromium
npm run build
rg -n "ffmpeg-core|@ffmpeg/ffmpeg|new FFmpeg" dist/client
```

Expected: E2E and build pass; `rg` returns no matches.

- [ ] **Step 6: Commit**

```bash
git add WEB/src/domain/types.ts WEB/src/processing/generate-flipbook.ts WEB/src/processing/index.ts WEB/src/App.tsx WEB/tests/e2e/app.spec.ts
git commit -m "feat(web): pause browser video processing"
```

---

### Task 4: Reject Request Bodies and Disable Runtime Delivery

**Files:**
- Modify: `WEB/wrangler.jsonc`
- Modify: `WEB/worker/index.ts`
- Modify: `WEB/tests/runtime-handler.test.ts`
- Regenerate: `WEB/worker-configuration.d.ts`

**Interfaces:**
- Consumes: generated global `Env` with `ASSETS: Fetcher`.
- Produces: `handleRequest(request, env: Pick<Env, "ASSETS">): Promise<Response>`.

- [ ] **Step 1: Replace runtime tests with failing method/runtime isolation tests**

Add an `ASSETS.fetch` spy. Assert:

```ts
expect((await handleRequest(new Request("https://example.com/", { method: "POST", body: "x" }), env)).status).toBe(405);
expect(assetsFetch).not.toHaveBeenCalled();

const runtime = await handleRequest(
  new Request("https://example.com/runtime/ffmpeg/0.12.10/st/ffmpeg-core.wasm"), env,
);
expect(runtime.status).toBe(410);
expect(runtime.headers.get("cache-control")).toBe("no-store");
expect(assetsFetch).not.toHaveBeenCalled();
```

Cover `PUT`, `PATCH`, `DELETE`, `OPTIONS`, and a POST whose `body` getter/stream throws if consumed.

- [ ] **Step 2: Run focused Worker tests and verify failure**

Run: `cd WEB && npm test -- tests/runtime-handler.test.ts`

Expected: existing handler forwards non-runtime POST and serves configured runtime objects.

- [ ] **Step 3: Implement method-first routing**

Remove `RuntimeObject`, `FFMPEG_RUNTIME`, filename matching, and R2 reads. Use this order:

```ts
export async function handleRequest(request: Request, env: Pick<Env, "ASSETS">): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method Not Allowed", {
      status: 405,
      headers: { ...securityHeaders(), Allow: "GET, HEAD", "Cache-Control": "no-store" },
    });
  }
  const path = new URL(request.url).pathname;
  if (path.startsWith("/runtime/ffmpeg/")) {
    return new Response("Video runtime is temporarily disabled", {
      status: 410,
      headers: { ...securityHeaders(), "Cache-Control": "no-store" },
    });
  }
  return env.ASSETS.fetch(request);
}
```

Keep `satisfies ExportedHandler<Env>` on the default export.

- [ ] **Step 4: Route every request through the Worker and regenerate types**

Set `assets.run_worker_first` to `true` in `wrangler.jsonc`; the installed Wrangler schema confirms Boolean `true` routes every request through the User Worker. Run `cd WEB && npm run types` and verify `npm run types:check` succeeds.

- [ ] **Step 5: Run Worker tests and deploy dry-run**

Run: `cd WEB && npm test -- tests/runtime-handler.test.ts && npm run deploy:dry-run`

Expected: tests pass, generated types are current, and only `ASSETS` is listed as a binding.

- [ ] **Step 6: Commit**

```bash
git add WEB/wrangler.jsonc WEB/worker/index.ts WEB/tests/runtime-handler.test.ts WEB/worker-configuration.d.ts
git commit -m "fix(web): reject uploads and disable runtime routes"
```

---

### Task 5: Deterministic Runtime Manifest

**Files:**
- Create: `WEB/scripts/runtime-manifest.mjs`
- Create: `WEB/tests/runtime-manifest.test.mjs`
- Modify: `WEB/scripts/stage-runtime.mjs`
- Modify: `WEB/vitest.config.ts`

**Interfaces:**
- Produces: `RUNTIME_VERSION`, `runtimeSources`, `sha256File()`, `buildManifest()`, `verifyManifest()`.
- Manifest path: `WEB/.runtime/manifest.json`.

- [ ] **Step 1: Write failing manifest tests using a temporary directory**

Test deterministic sort/order, lowercase 64-character SHA-256, byte size, key shape, and rejection after one staged byte is modified.

```ts
expect(manifest.files[0].key).toMatch(/^ffmpeg\/0\.12\.10\/[a-f0-9]{64}\/(st|mt)\/ffmpeg-core/);
await expect(verifyManifest(root, manifest)).resolves.toBeUndefined();
await writeFile(join(root, manifest.files[0].path), "tampered");
await expect(verifyManifest(root, manifest)).rejects.toThrow("SHA-256");
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `cd WEB && npm test -- tests/runtime-manifest.test.mjs`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement streaming SHA-256 and canonical manifest generation**

Use `createReadStream()` piped into `createHash("sha256")`; never load FFmpeg WASM fully into Node memory. Manifest entries have:

```ts
{
  variant: "st" | "mt",
  filename: string,
  path: string,
  contentType: string,
  bytes: number,
  sha256: string,
  key: `ffmpeg/${RUNTIME_VERSION}/${sha256}/${variant}/${filename}`,
}
```

Sort by `variant`, then `filename`, and serialize with `JSON.stringify(manifest, null, 2) + "\n"`.

Update `vitest.config.ts` to `include: ["tests/**/*.test.{ts,mjs}"]` so Node script tests remain outside TypeScript compilation while still running under Vitest.

- [ ] **Step 4: Update staging to create and re-verify the manifest**

After copying the five pinned files, call `buildManifest(outputRoot)`, write `.runtime/manifest.json`, read it back, and call `verifyManifest()` before reporting success.

- [ ] **Step 5: Run manifest tests and stage the real runtime**

Run: `cd WEB && npm test -- tests/runtime-manifest.test.mjs && npm run runtime:stage`

Expected: tests pass; `.runtime/manifest.json` contains five content-addressed entries and verification succeeds.

- [ ] **Step 6: Commit**

```bash
git add WEB/scripts/runtime-manifest.mjs WEB/scripts/stage-runtime.mjs WEB/tests/runtime-manifest.test.mjs WEB/vitest.config.ts
git commit -m "feat(web): create hashed runtime manifests"
```

---

### Task 6: Atomic No-Overwrite R2 Publisher

**Files:**
- Modify: `WEB/package.json`
- Modify: `WEB/package-lock.json`
- Create: `WEB/scripts/r2-client.mjs`
- Modify: `WEB/scripts/publish-runtime.mjs`
- Create: `WEB/tests/publish-runtime.test.mjs`

**Interfaces:**
- Consumes: Task 5 manifest and `verifyManifest()`.
- Produces: `createR2ClientFromEnv()`, `createOnlyMiddleware()`, and `publishManifest(client, bucket, runtimeRoot, manifest)`.

- [ ] **Step 1: Add the development-only S3 client**

Run: `cd WEB && npm install --save-dev @aws-sdk/client-s3`

Use exact lockfile resolution generated by npm; do not add runtime credentials to files.

- [ ] **Step 2: Write failing publisher tests with a fake S3 client**

Assert each command carries `If-None-Match: *`, content type/cache metadata match the manifest, `412 PreconditionFailed` fails closed without retry/overwrite, and every other error stops publication. Test the exported middleware directly with a minimal request object, while the fake client records command inputs:

```ts
await publishManifest(client, "bucket", root, manifest);
expect(sent[0].input.Key).toBe(manifest.files[0].key);
const request = { headers: {} };
await createOnlyMiddleware(async (args) => args)({ request });
expect(request.headers["if-none-match"]).toBe("*");
```

- [ ] **Step 3: Run the focused publisher test and verify failure**

Run: `cd WEB && npm test -- tests/publish-runtime.test.mjs`

Expected: FAIL because `r2-client.mjs` and the new publisher interface do not exist.

- [ ] **Step 4: Implement atomic conditional PutObject**

Create `S3Client` with region `auto` and endpoint `https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com`. Require `CLOUDFLARE_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY` from the environment with explicit missing-variable errors.

Export and attach this middleware at the command build step:

```js
export const createOnlyMiddleware = (next) => async (args) => {
  args.request.headers["if-none-match"] = "*";
  return next(args);
};
```

Cloudflare R2 documents `If-None-Match` support for `PutObject`; a pre-existing key returns HTTP 412. Treat 412 as a hard, non-zero “immutable object already exists” failure—do not silently skip and do not retry without the condition. Set `ContentType`, immutable `CacheControl`, and custom metadata containing the already verified SHA-256 string. Do not send an R2 checksum header unless the current R2 compatibility table explicitly supports that SDK field.

- [ ] **Step 5: Replace Wrangler object put with the verified publisher**

`publish-runtime.mjs` must accept only `--remote`, load/validate `.runtime/manifest.json`, call `verifyManifest()`, and then invoke the atomic S3 publisher. Remove the `--local` mode and the mutable Wrangler `r2 object put` loop. Update package scripts so `runtime:publish` is remote-only and remove `runtime:seed`, because the public runtime route is disabled.

- [ ] **Step 6: Run publisher and manifest tests without credentials**

Run: `cd WEB && npm test -- tests/runtime-manifest.test.mjs tests/publish-runtime.test.mjs`

Expected: all fake-client tests pass; no network or R2 credentials are used.

- [ ] **Step 7: Commit**

```bash
git add WEB/package.json WEB/package-lock.json WEB/scripts/r2-client.mjs WEB/scripts/publish-runtime.mjs WEB/tests/publish-runtime.test.mjs
git commit -m "feat(web): publish immutable runtime objects"
```

---

### Task 7: Documentation, Privacy Copy, and Full Verification

**Files:**
- Modify: `WEB/README.md`
- Modify: `WEB/src/App.tsx`
- Modify: `WEB/tests/e2e/app.spec.ts`

**Interfaces:**
- Documents the implemented security boundary and maintainer-only runtime workflow.

- [ ] **Step 1: Update user-facing privacy copy**

Use precise copy:

```text
圖片內容只在這個瀏覽器分頁處理，不會上傳或儲存。服務可能短期保留抽樣的請求中繼資料，用於維運與錯誤診斷；其中不包含圖片內容。
```

Do not claim that absolutely no request metadata exists.

- [ ] **Step 2: Rewrite README deployment/support sections**

State that image processing is available, video is paused for a security update, the public Worker accepts only `GET/HEAD`, no route reads bodies, all runtime URLs return `410`, and R2 runtime publication is maintainer-only. Document the three S3 credential environment variable names without values and explain that they must be scoped only to the runtime bucket.

- [ ] **Step 3: Strengthen privacy E2E assertions**

Assert the new copy, disabled video option, absent video input, and zero request bodies/external origins during image generation. Keep the generated PNG verification.

- [ ] **Step 4: Run the complete verification matrix**

Run:

```powershell
cd WEB
npm audit
npm run types:check
npm test
$env:PLAYWRIGHT_USE_SYSTEM_CHROME='1'
npm run test:e2e -- --project=chromium
npm run build
rg -n "ffmpeg-core|@ffmpeg/ffmpeg|new FFmpeg" dist/client
npm run deploy:dry-run
```

Expected: audit reports zero known npm vulnerabilities; types, unit tests, E2E, build, and dry-run pass; the FFmpeg search returns no matches.

- [ ] **Step 5: Review the final diff for secrets and accidental uploads**

Run:

```powershell
git diff --check
rg -n -i "(R2_SECRET_ACCESS_KEY\s*=|R2_ACCESS_KEY_ID\s*=|api[_-]?key\s*=|password\s*=)" WEB docs
git status --short
```

Expected: no whitespace errors, no credential values, and only intended tracked files changed.

- [ ] **Step 6: Commit**

```bash
git add WEB/README.md WEB/src/App.tsx WEB/tests/e2e/app.spec.ts
git commit -m "docs(web): explain image-only privacy boundary"
```

---

## Final Acceptance

- An image-only production build works at the 8192 × 8192 boundary.
- Inputs above any hard resource limit fail before unsafe allocation or decode work.
- Video is visible only as a disabled maintenance option, and FFmpeg is absent from the client bundle.
- No application route accepts or reads request bodies.
- Runtime URLs return `410` without touching R2.
- Maintainer runtime artifacts are deterministic, SHA-256 addressed, checksum verified, and atomically non-overwriting.
- All automated checks and Cloudflare dry-run pass.
