# Flipbook 網頁版

公開、免登入、完全在瀏覽器本機處理的圖片序列／影片轉 Flipbook 工具。React SPA 由 Cloudflare Workers Static Assets 提供；大型 FFmpeg WebAssembly runtime 儲存在 R2。使用者選擇的圖片、影片與輸出不會送到 Worker 或 R2。

## 本機開發

需要 Node.js 22 以上，建議使用 `.nvmrc` 指定的 Node.js 24。

```powershell
npm install
npm run types
npm run runtime:seed
npm run dev
```

`runtime:seed` 會把固定版本的單執行緒／多執行緒 FFmpeg 核心放入 Wrangler 本機 R2 狀態。圖片模式不依賴 R2；影片探測與解碼才會載入這些 runtime。

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

## 第一次 Cloudflare 發布

### 暫時不啟用 R2

目前 `wrangler.jsonc` 已暫時註解 `FFMPEG_RUNTIME` 的 R2 binding，讓尚未啟用 R2 的帳號也能先部署網站。圖片序列功能可以正常使用；影片介面與處理程式仍保留，但 runtime 請求會回傳 `503`，因此 MP4／MOV 暫時無法執行。

未來啟用 R2 時，依 `wrangler.jsonc` 內的註解恢復 `r2_buckets` 設定，建立並填入 `flipbook-ffmpeg-runtime` bucket，再重新部署即可，不需要復原影片程式碼。

### 啟用完整影片功能

先登入並建立專用 bucket：

```powershell
npx wrangler login
npx wrangler r2 bucket create flipbook-ffmpeg-runtime
npm run runtime:publish
npm run deploy
```

發布順序必須是 runtime 先、網站後。`runtime:publish` 只在升級 FFmpeg core 時重跑；物件 key 已包含 `0.12.10` 版本並使用 immutable cache。

## GitHub 自動部署

1. 在 Cloudflare Dashboard 開啟 **Workers & Pages → Create application → Import a repository**。
2. 選擇 `SenPai-TW/ImageSequenceToFlipbook_Tool`。
3. Root directory 設為 `/web`，Production branch 設為 `master`。
4. Build command 設為 `npm run types && npm run check`，Deploy command 使用 `npm run deploy`。
5. Worker 名稱必須與 `wrangler.jsonc` 的 `image-sequence-to-flipbook` 相同。
6. 非 `master` 分支由 Workers Builds 建立版本預覽；R2 runtime 共用同一批唯讀、版本化物件。

Cloudflare Git 整合不會替新帳號建立或填入 FFmpeg R2 內容，所以必須先完成上一節的第一次發布。

## 架構與隱私邊界

- `generateFlipbook(request)` 是圖片與影片共用的公開轉換入口。
- 圖片解碼、縮放、通道運算與 PNG 編碼都在 dedicated Web Worker 執行。
- 影片以 ffmpeg.wasm 的 WORKERFS 掛載本機 `File`，避免先複製成另一份完整輸入 buffer。
- Worker 只有靜態網站與 `GET/HEAD /runtime/ffmpeg/0.12.10/{st|mt}/...`；沒有素材上傳 API。
- R2 binding 只讀取部署者預先發布的 FFmpeg runtime，不保存使用者資料。
- COOP／COEP 開啟時使用多執行緒核心；不支援時自動降級為單執行緒。

## 支援範圍

- 圖片：PNG、JPEG、TIFF；EXR 會提示先轉 PNG/TIFF。
- 影片容器：MP4、MOV；H.264、H.265、ProRes 列入正式驗收，其餘由固定 FFmpeg core 能力決定。
- 正式支援最新版 Chrome、Edge、Firefox、Safari 桌面版。手機可嘗試，但大型素材不保證。
- 沒有登入、資料庫、同步、分享、通知、雲端歷史或伺服器端媒體處理。
