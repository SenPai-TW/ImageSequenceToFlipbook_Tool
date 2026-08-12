import { useEffect, useMemo, useRef, useState } from "react";

import {
  extensionOf,
  naturalSortFiles,
  supportedImageFiles,
  VIDEO_EXTENSIONS,
} from "./domain/flipbook";
import type {
  ChannelMode,
  FitMode,
  FlipbookOptions,
  ProcessingStage,
  ProgressUpdate,
  VideoMetadata,
} from "./domain/types";
import { collectResourceWarnings } from "./domain/warnings";
import {
  AlertIcon,
  CheckIcon,
  CloseIcon,
  DownloadIcon,
  FolderIcon,
  GridIcon,
  ImagesIcon,
  MoonIcon,
  ShieldIcon,
  SunIcon,
  UploadIcon,
  VideoIcon,
} from "./icons";
import { generateFlipbook, probeVideo } from "./processing";

type SourceMode = "images" | "video";
type Theme = "dark" | "light";

interface OutputResult {
  url: string;
  framesWritten: number;
  width: number;
  height: number;
  bytes: number;
}

const FIT_DETAILS: Record<FitMode, string> = {
  crop: "保持原始比例並填滿正方形，超出範圍從中央裁切。",
  stretch: "完整填滿正方形；非正方形來源會產生比例變形。",
  pad: "保持完整畫面與比例並置中；RGBA 使用透明延伸區域，其他模式使用黑底。",
};

const CHANNEL_DETAILS: Record<ChannelMode, string> = {
  RGBA: "完整保留 Alpha 透明通道，適合粒子、煙霧與去背特效。",
  RGB: "保留原始 RGB 資訊，並將所有像素設為完全不透明。",
  RGB_BLACK: "依 Alpha 合成到黑色背景，輸出不透明的 Premultiplied RGB。",
};

const STAGE_LABELS: Record<ProcessingStage, string> = {
  idle: "就緒",
  reading: "讀取素材",
  loading: "載入引擎",
  processing: "處理影格",
  encoding: "編碼 PNG",
  success: "完成",
  error: "處理失敗",
  cancelled: "已取消",
};

function initialTheme(): Theme {
  const stored = localStorage.getItem("flipbook-theme");
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(2).padStart(5, "0")}`;
}

function App(): React.ReactElement {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [sourceMode, setSourceMode] = useState<SourceMode>("images");
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [ignoredCount, setIgnoredCount] = useState(0);
  const [hasExr, setHasExr] = useState(false);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoMetadata, setVideoMetadata] = useState<VideoMetadata | null>(null);
  const [videoStart, setVideoStart] = useState("0");
  const [videoEnd, setVideoEnd] = useState("");
  const [cols, setCols] = useState(8);
  const [rows, setRows] = useState(8);
  const [tileSize, setTileSize] = useState(256);
  const [channelMode, setChannelMode] = useState<ChannelMode>("RGBA");
  const [fitMode, setFitMode] = useState<FitMode>("pad");
  const [fillEmpty, setFillEmpty] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [probing, setProbing] = useState(false);
  const [stage, setStage] = useState<ProcessingStage>("idle");
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("選擇本機圖片或影片後即可開始。");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OutputResult | null>(null);
  const generationController = useRef<AbortController | null>(null);
  const probeController = useRef<AbortController | null>(null);

  const options: FlipbookOptions = useMemo(() => ({
    cols,
    rows,
    tileSize,
    channelMode,
    fitMode,
    fillEmptyWithLast: fillEmpty,
  }), [channelMode, cols, fillEmpty, fitMode, rows, tileSize]);
  const capacity = cols * rows;
  const outputWidth = cols * tileSize;
  const outputHeight = rows * tileSize;
  const sourceCount = sourceMode === "images"
    ? imageFiles.length
    : videoMetadata
      ? Math.max(1, Math.round((Number(videoEnd || videoMetadata.duration) - Number(videoStart)) * videoMetadata.fps))
      : 0;
  const warnings = useMemo(() => collectResourceWarnings({
    cols,
    rows,
    tileSize,
    videoBytes: videoFile?.size,
  }), [cols, rows, tileSize, videoFile]);
  const isBusy = ["reading", "loading", "processing", "encoding"].includes(stage);
  const ready = sourceMode === "images" ? imageFiles.length > 0 : videoFile !== null && videoMetadata !== null;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("flipbook-theme", theme);
  }, [theme]);

  useEffect(() => () => {
    generationController.current?.abort();
    probeController.current?.abort();
  }, []);

  useEffect(() => () => {
    if (result) URL.revokeObjectURL(result.url);
  }, [result]);

  function clearResult(): void {
    if (result) URL.revokeObjectURL(result.url);
    setResult(null);
  }

  function applyImages(files: File[]): void {
    const exr = files.some((file) => extensionOf(file.name) === ".exr");
    const supported = supportedImageFiles(files);
    setHasExr(exr);
    setIgnoredCount(files.length - supported.length);
    setImageFiles(supported);
    setError(supported.length === 0 ? "沒有找到可處理的 PNG、JPEG 或 TIFF 圖片。" : null);
    setStatusMessage(supported.length > 0 ? `已載入 ${supported.length} 張圖片，並依檔名自然排序。` : "請重新選擇圖片。");
    setStage("idle");
    clearResult();
  }

  async function applyVideo(file: File): Promise<void> {
    if (!VIDEO_EXTENSIONS.has(extensionOf(file.name))) {
      setError("請選擇 MP4 或 MOV 影片。");
      return;
    }
    probeController.current?.abort();
    const controller = new AbortController();
    probeController.current = controller;
    setVideoFile(file);
    setVideoMetadata(null);
    setVideoStart("0");
    setVideoEnd("");
    setProbing(true);
    setError(null);
    clearResult();
    try {
      const metadata = await probeVideo(file, {
        signal: controller.signal,
        onProgress: (update) => setStatusMessage(update.message),
      });
      setVideoMetadata(metadata);
      setVideoEnd(metadata.duration.toFixed(3));
      setStatusMessage("影片分析完成，可以設定時間範圍。");
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(caught instanceof Error ? caught.message : "影片分析失敗。");
      setStatusMessage("無法讀取影片。");
    } finally {
      if (probeController.current === controller) probeController.current = null;
      setProbing(false);
    }
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragging(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length === 0) return;
    const first = files[0];
    if (files.length === 1 && VIDEO_EXTENSIONS.has(extensionOf(first.name))) {
      setSourceMode("video");
      void applyVideo(first);
    } else {
      setSourceMode("images");
      applyImages(files);
    }
  }

  function handleProgress(update: ProgressUpdate): void {
    setStage(update.stage);
    setProgress(update.percent);
    setStatusMessage(update.message);
  }

  async function runGeneration(): Promise<void> {
    if (!ready || isBusy) return;
    clearResult();
    setError(null);
    const controller = new AbortController();
    generationController.current = controller;
    try {
      const generated = await generateFlipbook({
        source: sourceMode === "images"
          ? { kind: "images", files: imageFiles }
          : {
              kind: "video",
              file: videoFile!,
              start: Number(videoStart),
              end: Number(videoEnd),
              metadata: videoMetadata!,
            },
        options,
        signal: controller.signal,
        onProgress: handleProgress,
      });
      const url = URL.createObjectURL(generated.blob);
      setResult({
        url,
        framesWritten: generated.framesWritten,
        width: generated.width,
        height: generated.height,
        bytes: generated.blob.size,
      });
      setStage("success");
      setProgress(100);
      setStatusMessage(`已完成 ${generated.framesWritten} 格影格，可預覽並下載 PNG。`);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setStage("cancelled");
        setProgress(0);
        setStatusMessage("已取消處理，可以調整設定後重新執行。");
      } else {
        setStage("error");
        setProgress(0);
        setError(caught instanceof Error ? caught.message : "Flipbook 產生失敗。");
        setStatusMessage("請縮小網格、單格尺寸或影片時間範圍後重試。");
      }
    } finally {
      if (generationController.current === controller) generationController.current = null;
    }
  }

  function changeSourceMode(mode: SourceMode): void {
    if (isBusy) return;
    setSourceMode(mode);
    setError(null);
    setStage("idle");
    setProgress(0);
    setStatusMessage(mode === "images" ? "選擇多張圖片或整個資料夾。" : "選擇一個 MP4 或 MOV 影片。");
    clearResult();
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Flipbook 工具首頁">
          <span className="brand-mark"><GridIcon /></span>
          <span><strong>Flipbook</strong><small>Texture Sheet Generator</small></span>
        </a>
        <button
          className="theme-toggle"
          type="button"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={theme === "dark" ? "切換淺色主題" : "切換深色主題"}
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
          <span>{theme === "dark" ? "淺色" : "深色"}</span>
        </button>
      </header>

      <main id="top" className="workspace">
        <section className="hero">
          <div>
            <p className="eyebrow">LOCAL-FIRST · NO UPLOAD</p>
            <h1>Flipbook Texture Sheet Generator</h1>
            <p className="hero-copy">將圖片序列或影片，快速整理成固定網格的 PNG 貼圖。</p>
          </div>
          <div className="privacy-pill"><ShieldIcon /><span><strong>素材只在這個瀏覽器分頁中處理，不會上傳</strong><small>關閉分頁後不保留任何素材或結果</small></span></div>
        </section>

        <div className="content-grid">
          <div className="main-column">
            <section className="panel source-panel" aria-labelledby="source-title">
              <div className="panel-heading">
                <div><span className="step-number">01</span><div><h2 id="source-title">選擇來源</h2><p>圖片序列或影片擇一</p></div></div>
                <div className="source-tabs" role="tablist" aria-label="來源類型">
                  <button role="tab" aria-selected={sourceMode === "images"} onClick={() => changeSourceMode("images")}><ImagesIcon />圖片序列</button>
                  <button role="tab" aria-selected={sourceMode === "video"} onClick={() => changeSourceMode("video")}><VideoIcon />影片</button>
                </div>
              </div>

              <div
                className={`dropzone ${dragging ? "is-dragging" : ""}`}
                onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
                onDrop={handleDrop}
              >
                <span className="drop-icon"><UploadIcon /></span>
                {sourceMode === "images" ? (
                  <>
                    <h3>{imageFiles.length > 0 ? `已載入 ${imageFiles.length} 張圖片` : "將圖片拖放到這裡"}</h3>
                    <p>支援 PNG、JPEG、TIFF；自動依檔名自然排序</p>
                    <div className="file-actions">
                      <label className="button secondary"><ImagesIcon />選擇多張圖片<input aria-label="圖片檔案" type="file" accept=".png,.jpg,.jpeg,.tif,.tiff,.exr" multiple hidden onChange={(event) => applyImages(Array.from(event.target.files ?? []))} /></label>
                      <label className="button ghost"><FolderIcon />選擇資料夾<input aria-label="圖片資料夾" ref={(element) => element?.setAttribute("webkitdirectory", "")} type="file" multiple hidden onChange={(event) => applyImages(Array.from(event.target.files ?? []))} /></label>
                    </div>
                  </>
                ) : (
                  <>
                    <h3>{videoFile ? videoFile.name : "將 MP4 或 MOV 影片拖放到這裡"}</h3>
                    <p>{videoFile ? `${formatBytes(videoFile.size)} · ${probing ? "正在分析影片…" : "影片留在本機"}` : "音訊會自動忽略；常見 H.264、H.265、ProRes 編碼"}</p>
                    <label className="button secondary"><VideoIcon />選擇影片<input aria-label="影片檔案" type="file" accept=".mp4,.mov,video/mp4,video/quicktime" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void applyVideo(file); }} /></label>
                  </>
                )}
              </div>

              {imageFiles.length > 0 && sourceMode === "images" && (
                <div className="file-summary">
                  <div><CheckIcon /><span><strong>{imageFiles[0].name}</strong><small>第一格</small></span></div>
                  <span>～</span>
                  <div><span><strong>{imageFiles.at(-1)?.name}</strong><small>最後一格</small></span></div>
                  <button type="button" aria-label="清除圖片" onClick={() => applyImages([])}><CloseIcon /></button>
                </div>
              )}
              {videoMetadata && sourceMode === "video" && (
                <div className="metadata-grid">
                  <div><small>長度</small><strong>{formatDuration(videoMetadata.duration)}</strong></div>
                  <div><small>解析度</small><strong>{videoMetadata.width} × {videoMetadata.height}</strong></div>
                  <div><small>影格率</small><strong>{videoMetadata.fps.toFixed(3)} FPS</strong></div>
                  <div><small>影格／編碼</small><strong>{videoMetadata.frameCount} · {videoMetadata.codec ?? "未知"}</strong></div>
                </div>
              )}
              {(hasExr || ignoredCount > 0) && <div className="inline-warning"><AlertIcon /><span>{hasExr ? "EXR 無法在網頁版解碼，請先轉成 PNG 或 TIFF。" : ""}{ignoredCount > 0 ? ` 已略過 ${ignoredCount} 個不支援的檔案。` : ""}</span></div>}
            </section>

            {sourceMode === "video" && (
              <section className="panel" aria-labelledby="range-title">
                <div className="panel-heading compact"><div><span className="step-number">02</span><div><h2 id="range-title">時間範圍</h2><p>從選取範圍平均抽格</p></div></div></div>
                <div className="field-grid two">
                  <label><span>開始秒數</span><input type="number" min="0" step="0.1" value={videoStart} onChange={(event) => setVideoStart(event.target.value)} disabled={!videoMetadata || isBusy} /></label>
                  <label><span>結束秒數</span><input type="number" min="0" step="0.1" max={videoMetadata?.duration} value={videoEnd} onChange={(event) => setVideoEnd(event.target.value)} disabled={!videoMetadata || isBusy} /></label>
                </div>
              </section>
            )}

            <section className="panel" aria-labelledby="settings-title">
              <div className="panel-heading compact"><div><span className="step-number">{sourceMode === "video" ? "03" : "02"}</span><div><h2 id="settings-title">Flipbook 設定</h2><p>決定網格與每格輸出方式</p></div></div></div>
              <div className="settings-sections">
                <div className="setting-group">
                  <h3>網格尺寸</h3>
                  <div className="field-grid three">
                    <label><span>欄數</span><input aria-label="欄數" type="number" min="1" step="1" value={cols} onChange={(event) => setCols(Math.max(1, Number(event.target.value)))} disabled={isBusy} /></label>
                    <label><span>列數</span><input aria-label="列數" type="number" min="1" step="1" value={rows} onChange={(event) => setRows(Math.max(1, Number(event.target.value)))} disabled={isBusy} /></label>
                    <label><span>單格尺寸</span><div className="input-suffix"><input aria-label="單格尺寸" type="number" min="1" step="1" value={tileSize} onChange={(event) => setTileSize(Math.max(1, Number(event.target.value)))} disabled={isBusy} /><span>px</span></div></label>
                  </div>
                  <div className="dimension-card"><GridIcon /><span><small>最終輸出</small><strong>{outputWidth} × {outputHeight} px</strong></span><span><small>網格容量</small><strong>{cols} × {rows} = {capacity} 格</strong></span></div>
                </div>

                <div className="setting-group split">
                  <div>
                    <h3>通道模式</h3>
                    <label className="select-field"><select value={channelMode} onChange={(event) => setChannelMode(event.target.value as ChannelMode)} disabled={isBusy}><option value="RGBA">RGBA（透明）</option><option value="RGB">RGB Straight</option><option value="RGB_BLACK">RGB Premultiplied</option></select></label>
                    <p className="field-help">{CHANNEL_DETAILS[channelMode]}</p>
                  </div>
                  <div>
                    <h3>畫面適配</h3>
                    <label className="select-field"><select value={fitMode} onChange={(event) => setFitMode(event.target.value as FitMode)} disabled={isBusy}><option value="pad">延伸空白畫布</option><option value="crop">置中裁切</option><option value="stretch">拉伸成正方形</option></select></label>
                    <p className="field-help">{FIT_DETAILS[fitMode]}</p>
                  </div>
                </div>

                <label className="check-row"><input type="checkbox" checked={fillEmpty} onChange={(event) => setFillEmpty(event.target.checked)} disabled={isBusy} /><span><strong>用最後一格補滿剩餘空格</strong><small>關閉時，未使用的位置會保持{channelMode === "RGBA" ? "透明" : "不透明黑色"}。</small></span></label>
              </div>

              {sourceCount > capacity && <div className="inline-warning"><AlertIcon /><span>來源多於 {capacity} 格。{sourceMode === "video" ? "會平均抽取整段範圍。" : `尾端 ${sourceCount - capacity} 張圖片不會寫入。`}</span></div>}
              {warnings.map((warning) => <div className="inline-warning resource" key={warning.code}><AlertIcon /><span><strong>{warning.title}</strong>{warning.message} 你仍可繼續執行。</span></div>)}
            </section>
          </div>

          <aside className="side-column">
            <section className="panel sticky-panel" aria-labelledby="output-title">
              <div className="panel-heading compact"><div><span className="step-number">{sourceMode === "video" ? "04" : "03"}</span><div><h2 id="output-title">產生與下載</h2><p>輸出為 PNG 貼圖</p></div></div></div>

              <div className={`preview ${result ? "has-result" : ""}`}>
                {result ? <img src={result.url} alt="完成的 Flipbook PNG 預覽" /> : <><GridIcon /><strong>輸出預覽</strong><span>{outputWidth} × {outputHeight} px</span></>}
              </div>

              <div className="status-block" aria-live="polite">
                <div className="status-line"><span className={`status-dot ${stage}`}></span><strong>{STAGE_LABELS[stage]}</strong><span>{Math.round(progress)}%</span></div>
                <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
                <p>{statusMessage}</p>
              </div>

              {error && <div className="error-box" role="alert"><AlertIcon /><span><strong>無法完成</strong>{error}</span></div>}
              {result && <div className="result-stats"><span><small>影格</small><strong>{result.framesWritten}</strong></span><span><small>尺寸</small><strong>{result.width} × {result.height}</strong></span><span><small>檔案</small><strong>{formatBytes(result.bytes)}</strong></span></div>}

              {isBusy ? (
                <button className="button danger full" type="button" onClick={() => generationController.current?.abort()}><CloseIcon />取消處理</button>
              ) : result ? (
                <a className="button primary full" href={result.url} download="flipbook.png"><DownloadIcon />下載 flipbook.png</a>
              ) : (
                <button className="button primary full" type="button" disabled={!ready || probing} onClick={() => void runGeneration()}><GridIcon />產生 Flipbook</button>
              )}
              <p className="local-note"><ShieldIcon />不需登入、不會上傳、不會保存</p>
            </section>
          </aside>
        </div>

        <section className="mobile-note"><AlertIcon /><span><strong>建議使用桌面瀏覽器</strong>手機可嘗試使用，但大型影片或高解析度輸出可能因記憶體不足而失敗。</span></section>
      </main>

      <footer><span>Image Sequence to Flipbook · Browser Edition</span><a href="/THIRD_PARTY_NOTICES.txt" target="_blank" rel="noreferrer">第三方授權</a></footer>
    </div>
  );
}

export default App;
