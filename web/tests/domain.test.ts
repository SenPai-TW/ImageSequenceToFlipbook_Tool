import { describe, expect, it } from "vitest";

import { evenIndices, naturalSortFiles } from "../src/domain/flipbook";
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
});
