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

  return {
    width,
    height,
    pixels,
    rgbaBytes: checkedMultiply(pixels, 4, "RGBA 記憶體"),
    capacity,
  };
}

export function validateImageFiles(files: readonly ImageFileMetadata[]): void {
  if (files.length > RESOURCE_LIMITS.maxFrameCount) {
    throw new ResourceLimitError("一次最多處理 512 張圖片。");
  }

  let total = 0;
  for (const file of files) {
    if (!Number.isSafeInteger(file.size) || file.size < 0) {
      throw new ResourceLimitError("圖片檔案大小無效。");
    }
    if (file.size > RESOURCE_LIMITS.maxFileBytes) {
      throw new ResourceLimitError(`${file.name} 超過 128 MiB。`);
    }
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
