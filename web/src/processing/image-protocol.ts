import type { FlipbookOptions } from "../domain/types";

export interface ImageWorkerRequest {
  id: string;
  files: File[];
  options: FlipbookOptions;
}

export type ImageWorkerResponse =
  | { id: string; type: "progress"; percent: number }
  | { id: string; type: "success"; png: ArrayBuffer; framesWritten: number }
  | { id: string; type: "error"; message: string };
