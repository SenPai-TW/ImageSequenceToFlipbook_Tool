export type ChannelMode = "RGBA" | "RGB" | "RGB_BLACK";
export type FitMode = "crop" | "stretch" | "pad";

export interface FlipbookOptions {
  cols: number;
  rows: number;
  tileSize: number;
  channelMode: ChannelMode;
  fitMode: FitMode;
  fillEmptyWithLast: boolean;
}

export interface ImagesSource {
  kind: "images";
  files: File[];
}

export interface VideoMetadata {
  duration: number;
  fps: number;
  frameCount: number;
  width: number;
  height: number;
  codec?: string;
}

export interface VideoSource {
  kind: "video";
  file: File;
  start: number;
  end: number;
  metadata?: VideoMetadata;
}

export type SourceInput = ImagesSource | VideoSource;

export type ProcessingStage =
  | "idle"
  | "reading"
  | "loading"
  | "processing"
  | "encoding"
  | "success"
  | "error"
  | "cancelled";

export interface ProgressUpdate {
  stage: Exclude<ProcessingStage, "idle" | "success" | "error" | "cancelled">;
  percent: number;
  message: string;
}

export interface GenerateFlipbookRequest {
  source: SourceInput;
  options: FlipbookOptions;
  signal?: AbortSignal;
  onProgress?: (update: ProgressUpdate) => void;
}

export interface GenerateFlipbookResult {
  blob: Blob;
  framesWritten: number;
  width: number;
  height: number;
}
