# WEB Security Hardening Design

## Goal

Harden the browser edition against hostile local media and runtime supply-chain replacement while preserving 8192 px professional image output. Temporarily disable all video processing. The deployed application must never accept, read, upload, transmit, or store user-selected media on the server, Worker, or R2.

## Security Boundary

- User images remain `File` objects inside the active browser tab and are processed only by a dedicated browser Web Worker.
- The Cloudflare Worker exposes no upload endpoint and never reads an HTTP request body.
- Only `GET` and `HEAD` requests may reach static-asset handling. `POST`, `PUT`, `PATCH`, `DELETE`, and other methods return `405 Method Not Allowed` before any body access.
- While video is paused, every `/runtime/ffmpeg/*` request returns `410 Gone`, uses `Cache-Control: no-store`, and does not access R2.
- No analytics, beacon, external API, or telemetry code may receive filenames, media bytes, generated output, or processing settings.
- Cloudflare invocation logs may retain sampled request metadata, but application URLs must not contain filenames or media-derived data. The UI and README must distinguish this metadata from media content.

HTTP infrastructure necessarily receives the request line and headers needed to serve the site. “Do not receive files” means the application provides no route that accepts file bodies and never reads or stores request bodies or user media.

## Resource Budget

Create one domain module that owns all hard limits and checked calculations. UI attributes and warnings are supplementary; the public generation entry point and image Worker must independently enforce the same budget.

Hard limits:

- Maximum output width: 8192 px.
- Maximum output height: 8192 px.
- Maximum output pixels: 67,108,864 (`8192 * 8192`).
- Maximum decoded width or height per source image: 8192 px.
- Maximum decoded pixels per source image: 67,108,864.
- Maximum selected image count: 512.
- Maximum individual image file size: 128 MiB.
- Maximum combined image file size: 1 GiB.
- Every dimension and byte calculation must use safe-integer checks before multiplication or allocation.

The validator returns a validated geometry/resource-budget value or throws a user-facing error. It must run:

1. When files or output settings change, so the UI can explain why work is blocked.
2. At the start of `generateFlipbook`, so callers cannot bypass the UI.
3. Inside the image Worker before allocating the output canvas.
4. After each image is decoded and before resizing, copying, or allocating derived buffers.

Compressed image dimensions must be checked as early as the decoder allows. Post-decode checks are mandatory because file size and extension do not establish decoded size. Exceeding a hard limit stops processing; there is no “continue anyway” path.

## Paused Video Experience

- Keep the image/video mode selector so the planned capability remains visible.
- Render the video option disabled with the message “安全性更新中，暫停使用”.
- Remove video file inputs, drag-and-drop activation, probing, metadata, range controls, and generation calls from reachable UI behavior.
- The production client entry graph must not import `src/processing/video.ts` or `@ffmpeg/ffmpeg`; therefore FFmpeg code is absent from the emitted client JavaScript.
- Keep the video source files and dependencies temporarily for the future remediation work, but no production code path may load or execute them.
- README support and privacy sections must clearly say that only image processing is currently available.

## Runtime Staging and Publication

Runtime publication remains available for maintainers but is disconnected from public request handling while video is paused.

Staging must:

1. Copy the exact pinned runtime files into `.runtime`.
2. Calculate SHA-256 and byte size for every staged file.
3. Produce a deterministic JSON manifest containing runtime version, variant, logical filename, content type, size, digest, and content-addressed R2 key.
4. Use keys shaped like `ffmpeg/<runtime-version>/<sha256>/<variant>/<filename>`.
5. Re-read staged files and verify size/digest before publication.

Publication must:

- Reject files absent from the manifest or whose size/digest differs.
- Never publish the old mutable keys.
- Treat an existing content-addressed object as immutable. A remote publish must fail closed instead of overwriting it; an explicitly separate verification operation may confirm an identical existing object.
- Stop at the first verification or publication failure and return a non-zero exit code.
- Never place Cloudflare credentials, account identifiers, or secrets in the manifest or source tree.

When video support is restored in a future change, its loader must fetch the manifest-selected runtime, verify SHA-256 in the browser before execution, and only then create the Blob URL passed to FFmpeg. That future re-enable is outside this implementation.

## Worker Behavior

Request handling order:

1. Reject any method other than `GET` or `HEAD` with `405`, `Allow: GET, HEAD`, `Cache-Control: no-store`, and the standard security headers.
2. Return `410 Gone` for every `/runtime/ffmpeg/*` path without reading R2 or forwarding to static assets.
3. Forward remaining `GET` and `HEAD` requests to the generated `ASSETS` binding.

Use Wrangler-generated `Env` types for the production handler. Test doubles may define a focused structural type, but production bindings must not be duplicated manually.

## Error Handling and User Copy

- Resource-limit errors state the exceeded limit and suggest reducing grid size, tile size, file count, or source dimensions.
- Errors must not expose local filesystem paths, media contents, stack traces, R2 identifiers, or Cloudflare credentials.
- The UI privacy statement becomes precise: image content stays in the browser and is never uploaded or stored; sampled request metadata may exist for short-term operations.
- The disabled video control must not imply that selecting a video is possible.

## Verification

Automated tests must cover:

- 8192 × 8192 output is accepted when all other limits pass.
- Width or height 8193 is rejected.
- Unsafe multiplication, excessive total pixels, 513 files, a 128 MiB-plus file, and more than 1 GiB combined input are rejected.
- A decoded image exceeding dimension or pixel limits is rejected before resize/output allocation.
- Video controls are disabled and no video file chooser is rendered.
- The production client manifest contains no FFmpeg client module or core asset.
- Every non-`GET`/`HEAD` Worker request returns `405` without reading its body.
- Every runtime path returns `410` and an R2 spy records zero `get`/`head` calls.
- Runtime manifests are deterministic; modified, missing, oversized, or digest-mismatched files fail publication validation.
- Existing content-addressed keys are never overwritten.
- Existing unit tests, TypeScript build, production build, dependency audit, and Wrangler dry-run pass.

## Out of Scope

- Re-enabling video processing.
- Building a patched FFmpeg core.
- Browser-side runtime digest verification and Blob loading.
- Cloudflare R2 object-lock or retention-policy configuration.
- Removing FFmpeg source modules and package dependencies permanently.
