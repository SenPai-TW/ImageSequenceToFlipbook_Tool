# Flipbook 網頁版

公開、免登入、在瀏覽器分頁內處理的圖片序列轉 Flipbook 工具。使用者選擇的圖片與輸出不會送到 Worker、R2 或任何第三方服務；網站沒有接收檔案的 API。影片功能因安全性更新暫停。

## 本機開發

需要 Node.js 22 以上，建議使用 `.nvmrc` 指定的 Node.js 24。

```powershell
npm install
npm run types
npm run dev
```

圖片功能不依賴 FFmpeg 或 R2。開發伺服器與正式 Worker 都不接收上傳內容。

驗證：

```powershell
npm test
npm run test:e2e
npm run check
npm run deploy:dry-run
```

Playwright 首次使用前需安裝瀏覽器：`npx playwright install`。若受管制網路無法下載測試瀏覽器，可先用已安裝的 Chrome 驗證 Chromium 專案：

```powershell
$env:PLAYWRIGHT_USE_SYSTEM_CHROME='1'
npm run test:e2e -- --project=chromium
```

## Cloudflare 發布

```powershell
npx wrangler login
npm run deploy
```

Worker 只允許 `GET`／`HEAD` 靜態資源請求。其他方法會在讀取 URL 或 body 前回覆 `405`；所有 `/runtime/ffmpeg/` 路徑回覆 `410`，不會觸碰 R2 或接收內容。

### 維護者 runtime 封存流程

影片程式仍保留供日後安全審查，但不在正式 client bundle 執行。只有維護者需要封存固定 FFmpeg runtime 時，才建立專用 R2 bucket 並設定 `CLOUDFLARE_ACCOUNT_ID`、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY` 後執行 `npm run runtime:publish`。這不處理使用者檔案。

發布器會先驗證五個固定檔案的 SHA-256，使用 `ffmpeg/0.12.10/{sha256}/{variant}/{filename}` 內容位址鍵，並以 `If-None-Match: *` 建立。物件已存在時會以 `412` 失敗，不覆寫既有內容。

## GitHub 自動部署

1. 在 Cloudflare Dashboard 開啟 **Workers & Pages → Create application → Import a repository**。
2. 選擇 `SenPai-TW/ImageSequenceToFlipbook_Tool`。
3. Root directory 設為 `/web`，Production branch 設為 `master`。
4. Build command 設為 `npm run types && npm run check`，Deploy command 使用 `npm run deploy`。
5. Worker 名稱必須與 `wrangler.jsonc` 的 `image-sequence-to-flipbook` 相同。
6. 非 `master` 分支由 Workers Builds 建立版本預覽。

## 架構與隱私邊界

- `generateFlipbook(request)` 只接受使用者在分頁內選擇的圖片。
- 圖片解碼、縮放、通道運算與 PNG 編碼都在 dedicated Web Worker 執行。
- 輸出長寬各上限 `8192` 像素、總像素上限 `8192 × 8192`；格數與選取檔案上限 `512`。
- 單張圖片上限 `128 MiB`，本次選取總量上限 `1 GiB`；PNG/JPEG/TIFF 解碼前後都會再次檢查尺寸。
- Worker 沒有檔案上傳、素材接收、登入、資料庫或 R2 runtime 讀取介面。
- Cloudflare 可能依設定抽樣請求中繼資料供維運與錯誤診斷；不包含圖片內容。

## 支援範圍

- 圖片：PNG、JPEG、TIFF；EXR 會提示先轉 PNG/TIFF。
- 影片：安全性更新中，暫停使用；介面不可選取影片，runtime 路由固定回覆 `410`。
- 正式支援最新版 Chrome、Edge、Firefox、Safari 桌面版。手機可嘗試，但大型圖片不保證。
- 沒有登入、資料庫、同步、分享、通知、雲端歷史或伺服器端媒體處理。
