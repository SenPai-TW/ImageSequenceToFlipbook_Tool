import { describe, expect, it } from "vitest";

import {
  dimensionsFromJpeg,
  dimensionsFromPng,
} from "../src/processing/image-dimensions";

function pngHeader(width: number, height: number): Uint8Array {
  const bytes = new Uint8Array(24);
  bytes.set([137, 80, 78, 71, 13, 10, 26, 10], 0);
  const view = new DataView(bytes.buffer);
  view.setUint32(8, 13, false);
  bytes.set([73, 72, 68, 82], 12);
  view.setUint32(16, width, false);
  view.setUint32(20, height, false);
  return bytes;
}

function jpegWithSof(width: number, height: number): Uint8Array {
  return new Uint8Array([
    0xff, 0xd8,
    0xff, 0xe0, 0x00, 0x04, 0x00, 0x00,
    0xff, 0xc0, 0x00, 0x11, 0x08,
    (height >>> 8) & 0xff, height & 0xff,
    (width >>> 8) & 0xff, width & 0xff,
    0x03, 0x01, 0x11, 0x00, 0x02, 0x11, 0x00, 0x03, 0x11, 0x00,
    0xff, 0xd9,
  ]);
}

describe("encoded image dimension parsing", () => {
  it("reads PNG IHDR dimensions", () => {
    expect(dimensionsFromPng(pngHeader(8192, 8192))).toEqual({ width: 8192, height: 8192 });
  });

  it("reads JPEG SOF dimensions after an APP segment", () => {
    expect(dimensionsFromJpeg(jpegWithSof(640, 480))).toEqual({ width: 640, height: 480 });
  });

  it("rejects truncated or dimensionless headers", () => {
    expect(() => dimensionsFromPng(new Uint8Array(8))).toThrow("PNG 標頭");
    expect(() => dimensionsFromJpeg(new Uint8Array([0xff, 0xd8, 0xff, 0xd9])))
      .toThrow("JPEG 尺寸");
  });
});
