import { naturalSortFiles, supportedImageFiles } from "../domain/flipbook";
import type {
  GenerateFlipbookRequest,
  GenerateFlipbookResult,
  ProgressUpdate,
} from "../domain/types";
import { processImages } from "./process-images";
import { extractVideoFrames } from "./video";

function validateRequest(request: GenerateFlipbookRequest): void {
  const { cols, rows, tileSize } = request.options;
  if (![cols, rows, tileSize].every((value) => Number.isSafeInteger(value) && value >= 1)) {
    throw new Error("欄數、列數與單格尺寸都必須是大於 0 的整數。");
  }
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
  request.onProgress?.({ stage: "reading", percent: 0, message: "正在讀取本機素材…" });
  const capacity = request.options.cols * request.options.rows;

  let frames: File[];
  if (request.source.kind === "images") {
    frames = supportedImageFiles(request.source.files);
    if (frames.length === 0) throw new Error("請選擇 PNG、JPEG 或 TIFF 圖片。");
  } else {
    frames = await extractVideoFrames(
      request.source.file,
      request.source.metadata,
      request.source.start,
      request.source.end,
      capacity,
      {
        signal: request.signal,
        onProgress: forwardProgress(request, 0, 72),
      },
    );
  }

  const result = await processImages({
    files: naturalSortFiles(frames),
    options: request.options,
    signal: request.signal,
    onProgress: forwardProgress(request, request.source.kind === "video" ? 72 : 2, request.source.kind === "video" ? 27 : 97),
  });
  request.onProgress?.({ stage: "encoding", percent: 100, message: "PNG 已完成。" });
  return {
    ...result,
    width: request.options.cols * request.options.tileSize,
    height: request.options.rows * request.options.tileSize,
  };
}
