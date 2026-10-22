# Sites Local Video Implementation Plan

**Goal:** Ship the approved browser-local FFmpeg tool on Sites without R2 or uploads.

**Architecture:** An independent React/Vite static project in `sites/flipbook-local` reuses image processing. Build-time engine splitting supplies digest-pinned browser-only FFmpeg; bounded local extraction feeds the existing image worker.

**Tech Stack:** React, TypeScript, Vite, FFmpeg WASM, Vitest, Playwright.

## Global constraints

- No media or filenames in HTTP requests; no R2, database, telemetry, external CDN, or API keys.
- Preserve the original desktop and Cloudflare applications.
- Static engine chunks <= 8 MiB; verify every loaded runtime file against bundled SHA-256.
- Video <= 256 MiB, <= 4096 px per edge, <= 8,847,360 pixels, selected range <= 60 seconds, <= 128 frames, 180-second video deadline.
- Keep new Sites owner-private. Never report publication without a successful service result.

## Tasks

- [x] Create static project configuration, headers, split-runtime script, and manifest loader. Test reconstructed hashes and tamper rejection with `npm test`.
- [x] Implement file/metadata/range checks and bounded cancellable FFmpeg extraction in `src/processing/video-local.ts`; test invalid inputs and time sampling in `tests/video.test.ts`.
- [x] Wire source union, generation pipeline, video controls and local-only copy. Preserve fit modes, channel modes, natural sorting, fill-last and download.
- [x] Use real synthetic MP4/MOV fixtures for browser generation, cancellation/retry and image regression checks. Assert GET/HEAD only, same-origin assets and no filenames in request URLs.
- [ ] Run tests and production build, inspect desktop/mobile UI, document exact results. Register, package and deploy with Sites when service becomes available; otherwise record service blocker and retain build.

Implementation is inline in this chat. User authorization for the selected design was given immediately before implementation; no repeated design approval or unrelated GitHub push is needed.

Local checks/build and UI inspection complete (18 unit tests, 8 Chrome browser tests). Publication remains blocked by unavailable Sites service tools; see `sites/flipbook-local/VALIDATION.md`. No GitHub commit or push performed.
