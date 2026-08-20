import { expect, test } from "@playwright/test";

test("opens as a private, local-processing Flipbook tool", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Flipbook Texture Sheet Generator" })).toBeVisible();
  await expect(page.getByText("素材只在這個瀏覽器分頁中處理，不會上傳")).toBeVisible();
  await expect(page.getByLabel("欄數")).toHaveValue("8");
  await expect(page.getByLabel("列數")).toHaveValue("8");
  await expect(
    page
      .getByRole("region", { name: "Flipbook 設定" })
      .getByText("2048 × 2048 px"),
  ).toBeVisible();
});

test("switches to video input and exposes the time range", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "影片" }).click();

  await expect(page.getByLabel("影片檔案")).toBeAttached();
  await expect(page.getByLabel("開始秒數")).toHaveValue("0");
  await expect(page.getByLabel("結束秒數")).toBeVisible();
});

test("generates and downloads a PNG without uploading the source", async ({ page }) => {
  const networkBodies: Array<string | null> = [];
  page.on("request", (request) => networkBodies.push(request.postData()));
  await page.goto("/");
  await page.getByLabel("欄數").fill("1");
  await page.getByLabel("列數").fill("1");
  await page.getByLabel("單格尺寸").fill("2");
  await page.getByLabel("圖片檔案").setInputFiles({
    name: "frame_001.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgQIAQnXUmwAAAABJRU5ErkJggg==", "base64"),
  });
  await page.getByRole("button", { name: "產生 Flipbook" }).click();

  await expect(page.getByRole("link", { name: "下載 flipbook.png" })).toBeVisible({ timeout: 30_000 });
  expect(networkBodies.every((body) => body === null)).toBe(true);
});

test("keeps unused RGB cells opaque black", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("欄數").fill("2");
  await page.getByLabel("列數").fill("1");
  await page.getByLabel("單格尺寸").fill("1");
  await page.getByRole("combobox").first().selectOption("RGB");
  await page.getByLabel("圖片檔案").setInputFiles({
    name: "frame_001.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgQIAQnXUmwAAAABJRU5ErkJggg==", "base64"),
  });
  await page.getByRole("button", { name: "產生 Flipbook" }).click();

  const download = page.getByRole("link", { name: "下載 flipbook.png" });
  await expect(download).toBeVisible();
  const pixels = await download.evaluate(async (link) => {
    const blob = await fetch((link as HTMLAnchorElement).href).then((response) => response.blob());
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("Canvas 2D is unavailable");
    context.drawImage(bitmap, 0, 0);
    return Array.from(context.getImageData(0, 0, bitmap.width, bitmap.height).data);
  });

  expect(pixels.slice(4, 8)).toEqual([0, 0, 0, 255]);
});
