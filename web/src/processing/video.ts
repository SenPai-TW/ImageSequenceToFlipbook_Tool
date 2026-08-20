import { FFmpeg } from "@ffmpeg/ffmpeg";
import { FFFSType } from "@ffmpeg/ffmpeg";

import { evenIndices, naturalCompare } from "../domain/flipbook";
import type { ProgressUpdate, VideoMetadata } from "../domain/types";

const CORE_VERSION = "0.12.10";

interface ProbeJson {
  streams?: Array<{
    width?: number;
    height?: number;
    avg_frame_rate?: string;
    r_frame_rate?: string;
    nb_read_frames?: string;
    nb_frames?: string;
    duration?: string;
    codec_name?: string;
  }>;
  format?: { duration?: string };
}

interface VideoOperation {
  signal?: AbortSignal;
  onProgress?: (update: ProgressUpdate) => void;
}

function parseRate(value: string | undefined): number {
  if (!value) return 0;
  const parts = value.split("/");
  const numerator = Number(parts[0]);
  const denominator = Number(parts[1] ?? 1);
  return denominator === 0 ? 0 : numerator / denominator;
}

function decodeText(data: Uint8Array | string): string {
  return typeof data === "string" ? data : new TextDecoder().decode(data);
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("處理已取消。", "AbortError");
}

function runtimeVariants(): Array<"st" | "mt"> {
  return self.crossOriginIsolated && typeof SharedArrayBuffer !== "undefined"
    ? ["mt", "st"]
    : ["st"];
}

function runtimeUrls(variant: "st" | "mt"): { coreURL: string; wasmURL: string; workerURL?: string; variant: "st" | "mt" } {
  const base = `/runtime/ffmpeg/${CORE_VERSION}/${variant}`;
  return {
    variant,
    coreURL: `${base}/ffmpeg-core.js`,
    wasmURL: `${base}/ffmpeg-core.wasm`,
    ...(variant === "mt" ? { workerURL: `${base}/ffmpeg-core.worker.js` } : {}),
  };
}

async function withFfmpeg<T>(
  file: File,
  operation: VideoOperation,
  run: (ffmpeg: FFmpeg, inputPath: string) => Promise<T>,
): Promise<T> {
  throwIfAborted(operation.signal);
  let lastError: unknown = new Error("影片引擎無法啟動。");

  for (const variant of runtimeVariants()) {
    const ffmpeg = new FFmpeg();
    const urls = runtimeUrls(variant);
    const abort = (): void => ffmpeg.terminate();
    operation.signal?.addEventListener("abort", abort, { once: true });

    try {
      operation.onProgress?.({
        stage: "loading",
        percent: 4,
        message: `正在載入 ${urls.variant === "mt" ? "多執行緒" : "相容模式"}影片引擎…`,
      });
      await ffmpeg.load(urls);
      throwIfAborted(operation.signal);
      await ffmpeg.createDir("/input");
      await ffmpeg.mount(FFFSType.WORKERFS, { files: [file] }, "/input");
      const mountedFiles = await ffmpeg.listDir("/input");
      if (!mountedFiles.some((entry) => !entry.isDir && entry.name === file.name)) {
        throw new Error("瀏覽器無法掛載這個本機影片檔案。");
      }
      return await run(ffmpeg, `/input/${file.name}`);
    } catch (error) {
      throwIfAborted(operation.signal);
      lastError = error;
    } finally {
      operation.signal?.removeEventListener("abort", abort);
      ffmpeg.terminate();
    }
  }

  throw lastError;
}

async function readProbe(ffmpeg: FFmpeg, inputPath: string): Promise<VideoMetadata> {
  const outputPath = "/probe.json";
  const logs: string[] = [];
  const collectLog = ({ message }: { message: string }): void => {
    logs.push(message);
    if (logs.length > 8) logs.shift();
  };
  ffmpeg.on("log", collectLog);
  const exitCode = await ffmpeg.ffprobe([
    "-v", "error",
    "-select_streams", "v:0",
    "-show_entries",
    "stream=width,height,avg_frame_rate,r_frame_rate,nb_read_frames,nb_frames,duration,codec_name:format=duration",
    "-of", "json",
    inputPath,
    "-o", outputPath,
  ]).finally(() => ffmpeg.off("log", collectLog));
  let probeOutput: Uint8Array | string | undefined;
  try {
    probeOutput = await ffmpeg.readFile(outputPath);
  } catch {
    probeOutput = undefined;
  }
  if (exitCode !== 0 && probeOutput === undefined) {
    const detail = logs.at(-1)?.replaceAll(inputPath, "本機影片");
    throw new Error(`無法讀取影片資訊；檔案可能損壞或編碼不受支援。${detail ? `（${detail}）` : ""}`);
  }
  if (probeOutput === undefined) throw new Error("影片探測沒有產生可讀取的結果。");
  const parsed = JSON.parse(decodeText(probeOutput)) as ProbeJson;
  const stream = parsed.streams?.[0];
  if (!stream?.width || !stream.height) throw new Error("影片沒有可用的視訊軌。");
  const fps = parseRate(stream.avg_frame_rate) || parseRate(stream.r_frame_rate);
  const duration = Number(stream.duration ?? parsed.format?.duration ?? 0);
  const frameCount = Number(stream.nb_read_frames ?? stream.nb_frames ?? Math.round(duration * fps));
  if (!(duration > 0) || !(frameCount > 0)) throw new Error("影片沒有可用的視訊影格。");
  return {
    duration,
    fps,
    frameCount,
    width: stream.width,
    height: stream.height,
    codec: stream.codec_name,
  };
}

export async function probeVideo(
  file: File,
  operation: VideoOperation = {},
): Promise<VideoMetadata> {
  return withFfmpeg(file, operation, async (ffmpeg, inputPath) => {
    operation.onProgress?.({ stage: "reading", percent: 35, message: "正在分析影片資訊…" });
    return readProbe(ffmpeg, inputPath);
  });
}

export async function extractVideoFrames(
  file: File,
  metadata: VideoMetadata | undefined,
  start: number,
  end: number,
  capacity: number,
  operation: VideoOperation = {},
): Promise<File[]> {
  return withFfmpeg(file, operation, async (ffmpeg, inputPath) => {
    const info = metadata ?? await readProbe(ffmpeg, inputPath);
    if (start < 0 || end <= start || end > info.duration + 0.001) {
      throw new Error(`時間範圍必須介於 0 與 ${info.duration.toFixed(3)} 秒之間。`);
    }

    const rangeFrames = Math.max(1, Math.round((end - start) * info.fps));
    const indices = evenIndices(rangeFrames, capacity);
    const select = indices.map((index) => `eq(n\\,${index})`).join("+");
    await ffmpeg.createDir("/frames");
    ffmpeg.on("progress", ({ progress }) => {
      const bounded = Math.max(0, Math.min(1, progress));
      operation.onProgress?.({
        stage: "processing",
        percent: 12 + Math.round(bounded * 58),
        message: "正在從影片平均抽取影格…",
      });
    });
    const exitCode = await ffmpeg.exec([
      "-threads", "2",
      "-filter_threads", "1",
      "-ss", start.toFixed(6),
      "-t", (end - start).toFixed(6),
      "-i", inputPath,
      "-an",
      "-vf", `select=${select}`,
      "-fps_mode", "vfr",
      "-threads", "2",
      "/frames/frame-%05d.png",
    ]);
    if (exitCode !== 0) throw new Error("影片解碼失敗；請確認編碼受支援，或縮短時間範圍後重試。");
    throwIfAborted(operation.signal);

    const entries = (await ffmpeg.listDir("/frames"))
      .filter((entry) => !entry.isDir && entry.name.endsWith(".png"))
      .sort((left, right) => naturalCompare(left.name, right.name));
    if (entries.length === 0) throw new Error("指定的時間範圍沒有成功解碼出影格。");
    const frames: File[] = [];
    for (const entry of entries) {
      const data = await ffmpeg.readFile(`/frames/${entry.name}`);
      if (typeof data === "string") throw new Error("影片影格輸出格式錯誤。");
      frames.push(new File([Uint8Array.from(data).buffer], entry.name, { type: "image/png" }));
    }
    return frames;
  });
}
