/// <reference lib="webworker" />

import { decode as decodeJpeg } from "@jsquash/jpeg";
import { decode as decodePng, encode as encodePng } from "@jsquash/png";
import resize from "@jsquash/resize";
import * as UTIF from "utif";

import { extensionOf } from "../domain/flipbook";
import type { ChannelMode, FitMode, FlipbookOptions } from "../domain/types";
import type { ImageWorkerRequest, ImageWorkerResponse } from "./image-protocol";

declare const self: DedicatedWorkerGlobalScope;

function post(message: ImageWorkerResponse, transfer: Transferable[] = []): void {
  self.postMessage(message, transfer);
}

async function decodeImage(file: File): Promise<ImageData> {
  const extension = extensionOf(file.name);
  const buffer = await file.arrayBuffer();
  if (extension === ".png") {
    const decoded = await decodePng(buffer, { bitDepth: 8 });
    if (decoded.data instanceof Uint16Array) {
      throw new Error(`${file.name} 無法轉換為 8-bit RGBA。`);
    }
    return decoded;
  }
  if (extension === ".jpg" || extension === ".jpeg") {
    return decodeJpeg(buffer);
  }
  if (extension === ".tif" || extension === ".tiff") {
    const directories = UTIF.decode(buffer);
    const first = directories[0];
    if (first === undefined) throw new Error(`${file.name} 沒有可讀取的 TIFF 畫面。`);
    UTIF.decodeImage(buffer, first);
    return new ImageData(new Uint8ClampedArray(UTIF.toRGBA8(first)), first.width, first.height);
  }
  throw new Error(`${file.name} 不是支援的 PNG、JPEG 或 TIFF 圖片。`);
}

async function resizeRgba(source: ImageData, width: number, height: number): Promise<ImageData> {
  return resize(source, {
    width,
    height,
    method: "lanczos3",
    fitMethod: "stretch",
    premultiply: false,
    linearRGB: false,
  });
}

function copyRect(
  source: ImageData,
  destination: Uint8ClampedArray,
  destinationWidth: number,
  destinationX: number,
  destinationY: number,
  cropX = 0,
  cropY = 0,
  cropWidth = source.width,
  cropHeight = source.height,
): void {
  for (let y = 0; y < cropHeight; y += 1) {
    const sourceStart = ((y + cropY) * source.width + cropX) * 4;
    const destinationStart = ((y + destinationY) * destinationWidth + destinationX) * 4;
    destination.set(
      source.data.subarray(sourceStart, sourceStart + cropWidth * 4),
      destinationStart,
    );
  }
}

async function fitFrame(
  source: ImageData,
  tileSize: number,
  fitMode: FitMode,
  channelMode: ChannelMode,
): Promise<ImageData> {
  if (fitMode === "stretch") return resizeRgba(source, tileSize, tileSize);

  const sourceScale = fitMode === "pad"
    ? Math.min(tileSize / source.width, tileSize / source.height)
    : Math.max(tileSize / source.width, tileSize / source.height);
  const width = Math.max(1, Math.round(source.width * sourceScale));
  const height = Math.max(1, Math.round(source.height * sourceScale));
  const resized = await resizeRgba(source, width, height);
  const output = new Uint8ClampedArray(tileSize * tileSize * 4);

  if (fitMode === "pad") {
    if (channelMode !== "RGBA") {
      for (let offset = 3; offset < output.length; offset += 4) output[offset] = 255;
    }
    copyRect(
      resized,
      output,
      tileSize,
      Math.floor((tileSize - width) / 2),
      Math.floor((tileSize - height) / 2),
    );
  } else {
    copyRect(
      resized,
      output,
      tileSize,
      0,
      0,
      Math.floor((width - tileSize) / 2),
      Math.floor((height - tileSize) / 2),
      tileSize,
      tileSize,
    );
  }
  return new ImageData(output, tileSize, tileSize);
}

function applyChannelMode(image: ImageData, mode: ChannelMode): ImageData {
  if (mode === "RGBA") return image;
  const data = new Uint8ClampedArray(image.data);
  for (let offset = 0; offset < data.length; offset += 4) {
    const alpha = data[offset + 3];
    if (mode === "RGB_BLACK") {
      data[offset] = Math.round((data[offset] * alpha) / 255);
      data[offset + 1] = Math.round((data[offset + 1] * alpha) / 255);
      data[offset + 2] = Math.round((data[offset + 2] * alpha) / 255);
    }
    data[offset + 3] = 255;
  }
  return new ImageData(data, image.width, image.height);
}

function pasteTile(
  tile: ImageData,
  canvas: Uint8ClampedArray,
  canvasWidth: number,
  index: number,
  options: FlipbookOptions,
): void {
  const left = (index % options.cols) * options.tileSize;
  const top = Math.floor(index / options.cols) * options.tileSize;
  copyRect(tile, canvas, canvasWidth, left, top);
}

async function generate(request: ImageWorkerRequest): Promise<void> {
  const { id, files, options } = request;
  const capacity = options.cols * options.rows;
  const selected = files.slice(0, capacity);
  if (selected.length === 0) throw new Error("沒有可處理的圖片。");

  const width = options.cols * options.tileSize;
  const height = options.rows * options.tileSize;
  const canvas = new Uint8ClampedArray(width * height * 4);
  if (options.channelMode !== "RGBA") {
    for (let offset = 3; offset < canvas.length; offset += 4) canvas[offset] = 255;
  }
  let lastTile: ImageData | null = null;

  for (let index = 0; index < selected.length; index += 1) {
    const source = await decodeImage(selected[index]);
    const fitted = await fitFrame(source, options.tileSize, options.fitMode, options.channelMode);
    const tile = applyChannelMode(fitted, options.channelMode);
    pasteTile(tile, canvas, width, index, options);
    lastTile = tile;
    post({ id, type: "progress", percent: Math.round(((index + 1) / selected.length) * 88) });
  }

  if (options.fillEmptyWithLast && lastTile !== null) {
    for (let index = selected.length; index < capacity; index += 1) {
      pasteTile(lastTile, canvas, width, index, options);
    }
  }

  post({ id, type: "progress", percent: 94 });
  const png = await encodePng(new ImageData(canvas, width, height));
  post({ id, type: "success", png, framesWritten: selected.length }, [png]);
}

self.addEventListener("message", (event: MessageEvent<ImageWorkerRequest>) => {
  void generate(event.data).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : "圖片處理失敗。";
    post({ id: event.data.id, type: "error", message });
  });
});
