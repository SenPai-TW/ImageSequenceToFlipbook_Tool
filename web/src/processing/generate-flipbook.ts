import { naturalSortFiles, supportedImageFiles } from "../domain/flipbook";
import type {
  GenerateFlipbookRequest,
  GenerateFlipbookResult,
  ProgressUpdate,
} from "../domain/types";
import { validateImageFiles, validateOutputGeometry } from "../domain/resource-budget";
import { processImages } from "./process-images";

function validateRequest(request: GenerateFlipbookRequest): void {
  validateOutputGeometry(request.options);
}

function forwardProgress(
  request: GenerateFlipbookRequest,
  start: number,
  span: number,
): (update: ProgressUpdate) => void {
  return (update) => request.onProgress?.({
    ...update,
    percent: Math.min(99, start + Math.round((update.percent / 100) * span)),
  });
}

export async function generateFlipbook(
  request: GenerateFlipbookRequest,
): Promise<GenerateFlipbookResult> {
  validateRequest(request);
  const geometry = validateOutputGeometry(request.options);
  request.onProgress?.({ stage: "reading", percent: 0, message: "正在讀取本機素材…" });
  const frames = supportedImageFiles(request.source.files);
  if (frames.length === 0) throw new Error("請選擇 PNG、JPEG 或 TIFF 圖片。");

  validateImageFiles(frames);

  const result = await processImages({
    files: naturalSortFiles(frames),
    options: request.options,
    signal: request.signal,
    onProgress: forwardProgress(request, 2, 97),
  });
  request.onProgress?.({ stage: "encoding", percent: 100, message: "PNG 已完成。" });
  return {
    ...result,
    width: geometry.width,
    height: geometry.height,
  };
}
