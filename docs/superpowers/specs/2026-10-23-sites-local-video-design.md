# Sites local video design

The user approved a ChatGPT Sites edition retaining FFmpeg, with no R2 and no media uploads. Keep the existing desktop and Cloudflare editions intact in their current directories; create the independently deployable Sites project in `sites/flipbook-local`.

Reuse the React interface and image Web Worker. Restore MP4/MOV selection and time-range controls. Use single-thread FFmpeg 0.12.10 in a dedicated browser worker to avoid requiring cross-origin isolation in Sites previews. At build time, split the engine into <= 8 MiB static assets and generate a pinned digest manifest bundled with the client. Download only same-origin manifest-listed assets using GET; validate sizes and SHA-256 before executing engine JavaScript or WASM. No runtime CDN, R2, API key, database, media upload, telemetry, or persistent media storage.

Limit video input to 256 MiB, decoded dimensions to 4096 per edge and 8,847,360 pixels, selected duration to 60 seconds, and sampling to 128 frames. Extract one representative frame per target timestamp, resize before PNG encoding, and delete each virtual output after reading. Enforce a 180-second overall video deadline, terminate workers on cancellation, and clean up blob URLs. Existing image limits remain in effect. Unsupported codecs produce a local error. Timing is uniform time sampling, not a guarantee of frame-index identity for variable-frame-rate sources.

Generated PNGs and source files remain in browser memory. Downloads use blob URLs. The application has no API accepting media; static server requests are read-only and filenames/settings never enter request URLs. Sites infrastructure may independently log ordinary page/asset request metadata.

Validate runtime tampering rejection, resource limits, image regression tests, real MP4/MOV conversions, cancellation/retry, range validation, and network requests (same origin GET/HEAD only, no media filenames/bodies). Build and package for Sites, starting owner-private. If the Sites service is unavailable, preserve the tested local project and explicitly report publication as blocked.
