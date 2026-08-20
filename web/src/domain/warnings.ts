export interface ResourceWarningInput {
  cols: number;
  rows: number;
  tileSize: number;
  videoBytes?: number;
}

export interface ResourceWarning {
  code: "large-video" | "wide-output" | "high-memory";
  blocking: false;
  title: string;
  message: string;
}

const MIB = 1024 * 1024;

export function collectResourceWarnings(input: ResourceWarningInput): ResourceWarning[] {
  const width = input.cols * input.tileSize;
  const height = input.rows * input.tileSize;
  const rgbaBytes = width * height * 4;
  const warnings: ResourceWarning[] = [];

  if ((input.videoBytes ?? 0) >= 250 * MIB) {
    warnings.push({
      code: "large-video",
      blocking: false,
      title: "影片檔案很大",
      message: "瀏覽器需要較多時間與記憶體。若失敗，請縮短影片範圍後重試。",
    });
  }
  if (width > 8192 || height > 8192) {
    warnings.push({
      code: "wide-output",
      blocking: false,
      title: "輸出尺寸很大",
      message: `預計輸出 ${width} × ${height}px，部分瀏覽器可能無法建立這麼大的圖片。`,
    });
  }
  if (rgbaBytes >= 256 * MIB) {
    warnings.push({
      code: "high-memory",
      blocking: false,
      title: "預估記憶體用量偏高",
      message: `僅輸出像素即約 ${(rgbaBytes / MIB).toFixed(0)} MiB，實際處理還需要額外空間。`,
    });
  }
  return warnings;
}
