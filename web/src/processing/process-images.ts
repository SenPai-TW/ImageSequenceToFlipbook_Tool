import type { FlipbookOptions, ProgressUpdate } from "../domain/types";
import type { ImageWorkerRequest, ImageWorkerResponse } from "./image-protocol";

export interface ProcessImagesOptions {
  files: File[];
  options: FlipbookOptions;
  signal?: AbortSignal;
  onProgress?: (update: ProgressUpdate) => void;
}

export interface ProcessImagesResult {
  blob: Blob;
  framesWritten: number;
}

export async function processImages(input: ProcessImagesOptions): Promise<ProcessImagesResult> {
  if (input.signal?.aborted) throw new DOMException("處理已取消。", "AbortError");
  const request: ImageWorkerRequest = {
    id: crypto.randomUUID(),
    files: input.files,
    options: input.options,
  };
  const worker = new Worker(new URL("./image.worker.ts", import.meta.url), { type: "module" });

  return new Promise<ProcessImagesResult>((resolve, reject) => {
    const cleanup = (): void => {
      input.signal?.removeEventListener("abort", abort);
      worker.terminate();
    };
    const abort = (): void => {
      cleanup();
      reject(new DOMException("處理已取消。", "AbortError"));
    };

    input.signal?.addEventListener("abort", abort, { once: true });
    worker.addEventListener("message", (event: MessageEvent<ImageWorkerResponse>) => {
      if (event.data.id !== request.id) return;
      if (event.data.type === "progress") {
        input.onProgress?.({
          stage: event.data.percent >= 90 ? "encoding" : "processing",
          percent: event.data.percent,
          message: event.data.percent >= 90 ? "正在編碼 PNG…" : "正在排列圖片影格…",
        });
        return;
      }
      cleanup();
      if (event.data.type === "error") {
        reject(new Error(event.data.message));
        return;
      }
      resolve({
        blob: new Blob([event.data.png], { type: "image/png" }),
        framesWritten: event.data.framesWritten,
      });
    });
    worker.addEventListener("error", (event) => {
      cleanup();
      reject(new Error(event.message || "圖片處理 Worker 無法啟動。"));
    });
    worker.postMessage(request);
  });
}
