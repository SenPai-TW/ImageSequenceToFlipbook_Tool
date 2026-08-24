import { describe, expect, it } from "vitest";

import { evenIndices, naturalSortFiles } from "../src/domain/flipbook";
import {
  RESOURCE_LIMITS,
  validateDecodedImage,
  validateImageFiles,
  validateOutputGeometry,
} from "../src/domain/resource-budget";
import { collectResourceWarnings } from "../src/domain/warnings";

describe("Flipbook domain behavior", () => {
  it("sorts numbered frame names naturally and case-insensitively", () => {
    const files = [
      new File([], "Smoke10.PNG"),
      new File([], "smoke2.png"),
      new File([], "smoke001.png"),
    ];

    expect(naturalSortFiles(files).map((file) => file.name)).toEqual([
      "smoke001.png",
      "smoke2.png",
      "Smoke10.PNG",
    ]);
  });

  it("samples both ends of a video range without duplicate indices", () => {
    expect(evenIndices(10, 4)).toEqual([0, 3, 6, 9]);
    expect(evenIndices(3, 8)).toEqual([0, 1, 2]);
    expect(evenIndices(10, 1)).toEqual([0]);
  });

  it("warns without blocking when the requested work is unusually large", () => {
    const warnings = collectResourceWarnings({
      cols: 40,
      rows: 40,
      tileSize: 256,
      videoBytes: 251 * 1024 * 1024,
    });

    expect(warnings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "large-video", blocking: false }),
        expect.objectContaining({ code: "wide-output", blocking: false }),
        expect.objectContaining({ code: "high-memory", blocking: false }),
      ]),
    );
  });

  it("accepts the exact 8192 square output boundary", () => {
    expect(validateOutputGeometry({ cols: 1, rows: 1, tileSize: 8192 })).toMatchObject({
      width: 8192,
      height: 8192,
      pixels: 8192 * 8192,
      capacity: 1,
    });
  });

  it.each([
    [{ cols: 1, rows: 1, tileSize: 8193 }, "8192"],
    [{ cols: 513, rows: 1, tileSize: 1 }, "512"],
    [{ cols: 2, rows: 1, tileSize: Number.MAX_SAFE_INTEGER }, "安全範圍"],
  ])("rejects unsafe output geometry", (options, message) => {
    expect(() => validateOutputGeometry(options)).toThrow(message);
  });

  it("rejects excessive file count and byte budgets without allocating large files", () => {
    const files = Array.from({ length: 513 }, (_, index) => ({
      name: `${index}.png`,
      size: 1,
    }));
    expect(() => validateImageFiles(files)).toThrow("512");
    expect(() => validateImageFiles([
      { name: "huge.png", size: RESOURCE_LIMITS.maxFileBytes + 1 },
    ])).toThrow("128 MiB");
    const totalOverflow = Array.from({ length: 9 }, (_, index) => ({
      name: `${index}.png`,
      size: RESOURCE_LIMITS.maxFileBytes,
    }));
    expect(() => validateImageFiles(totalOverflow)).toThrow("1 GiB");
  });

  it("rejects decoded source dimensions above the 8192 boundary", () => {
    expect(() => validateDecodedImage(8193, 1, "bomb.png")).toThrow("8192");
    expect(() => validateDecodedImage(8192, 8192, "edge.png")).not.toThrow();
  });
});
