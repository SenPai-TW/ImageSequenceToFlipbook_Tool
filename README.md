# 圖片序列／影片轉 Flipbook（獨立版）

本工具從 SenPaiToolBox 的第 5 項功能獨立而來，不需要安裝 Blender。

目前版本：**v3.1**

## 版本維護

產品版本採 `v主版號.次版號`；Web 套件依 SemVer 補上修訂號，例如產品 `v3.1` 對應 Web `3.1.0`。

每次功能或修正準備發布時，必須同步更新：

1. [`flipbook_version.py`](flipbook_version.py)：桌面程式的版本來源與視窗標題。
2. [`web/package.json`](web/package.json) 與 [`web/package-lock.json`](web/package-lock.json)：Web 套件版本。
3. 本 README 的「目前版本」。
4. [`HANDOFF.md`](HANDOFF.md) 的目前產品版本與待辦狀態。
5. 完成驗證與建置後，才建立相同版本的 Git tag；commit、tag 與 push 仍需分別確認。

[`tests/test_version_metadata.py`](tests/test_version_metadata.py) 會檢查上述版本是否一致，避免後續更新漏改其中一處。

## 單一 EXE 版

已建置的 `FlipbookGenerator.exe` 可直接在 Windows 10／11 64 位元執行；取得後直接雙擊即可，不需要另外安裝 Python、Pillow 或 FFmpeg。EXE 同時包含圖片序列與 MP4／MOV 影片功能。

單檔版會在啟動時將必要元件解壓到 Windows 暫存目錄，因此冷啟動可能比原始碼版本慢。檔案預估約 45–70 MB；未經程式碼簽章的自行建置版本也可能觸發 Windows SmartScreen 提示。

### 建立 EXE

在專案根目錄執行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

建置腳本會：

1. 將內附的 Python 3.11.8 安裝到專案專用的 `.build-python311` 目錄，不修改系統 PATH。
2. 建立隔離的 `.build-venv`，並從 `installers` 安裝 Pillow、`imageio-ffmpeg` 與 `tkinterdnd2`。
3. 安裝固定版本的 PyInstaller，將 FFmpeg、Pillow 圖片格式支援與 Windows TkDnD runtime 一併封裝。
4. 清理舊的 `build`／`dist`，輸出 `dist\FlipbookGenerator.exe`。

PyInstaller 需從官方 PyPI 下載，因此第一次建置需要網路；其餘執行依賴均優先使用專案內附檔案。若內附 Python 無法驗證系統的 TLS 憑證鏈，腳本會限定對 `pypi.org` 與 `files.pythonhosted.org` 使用 pip 的 trusted-host 後備方式。重複建置會沿用專案專用的 Python 與虛擬環境。

## Python 視窗版（使用 .vbs）

使用 `.vbs` 啟動的原始碼版本需要先安裝 Python 與必要套件；單一 EXE 版不需要執行以下安裝。

### 安裝必要套件

雙擊 `安裝必要套件.bat` 後，安裝程式會先嘗試從 Python 官方網站安裝最新版 64 位元 Python，接著透過 pip 安裝 Pillow、`imageio-ffmpeg` 與 `tkinterdnd2`。若線上下載或安裝失敗，會自動改用 `installers` 資料夾內附的 Python 3.11.8、Pillow 12.3.0、imageio-ffmpeg 0.6.0 與 tkinterdnd2 0.6.2，圖片序列、拖放及 MP4／MOV 影片功能皆可離線安裝使用。

### 使用方式

1. 安裝完成後，雙擊 `開啟Flipbook工具.vbs`。
2. 選擇「序列圖片（選其中一張）」、「圖片資料夾」或「影片（MP4／MOV）」及存檔位置。也可以將單一來源直接拖入整個視窗。
3. 設定欄數、列數、單格尺寸、通道模式及畫面適配方式。影片可另外設定起訖秒數。
4. 按下「執行生成 Flipbook 網格圖」。

視窗右上角的滑動開關可即時切換深色與淺色主題；預設為深色。

處理期間會顯示實際的 `0%–100%` 進度；完成或失敗後，進度條會清空回到 `0%`。

容量處理：

- 設定格數少於來源圖片數：視窗會顯示白底驚嘆號警告；仍可生成，超出容量的尾端圖片會忽略。
- 設定格數多於來源圖片數：預設保留透明空格。勾選「用最後一格圖片補齊剩下的所有空格」後，所有空格都會重複使用最後一張來源圖片。

VBS 啟動器會在背景使用已安裝的 Python 3 開啟 GUI，不會出現 PowerShell 或命令提示字元視窗。

## 圖片來源與拖放

- 「序列圖片（選其中一張）」使用 Windows 原生檔案選擇器。選擇序列中的任一張圖片後，程式以檔名最後一段數字作為影格編號，收集同資料夾內具有相同前綴、後綴及副檔名的圖片。例如 `smoke_v2_003.png` 會辨識 `smoke_v2_1.png` 與 `smoke_v2_12.png`；數字位數不必相同。檔名沒有數字時只使用選中的圖片。
- 「圖片資料夾」使用 Windows 原生資料夾選擇器，讀取該資料夾第一層的所有支援圖片，不會遞迴搜尋子資料夾。沒有支援圖片的資料夾不會套用。
- 「影片（MP4／MOV）」使用 Windows 原生檔案選擇器，只接受 MP4 與 MOV。
- 可拖入一個圖片資料夾、一張支援圖片，或一個 MP4／MOV 影片；程式會自動切換到對應的來源類型。有效來源會讓視窗漸暗，放開後套用來源；多個項目、不存在的路徑、空圖片資料夾或不支援格式會顯示禁止游標並讓視窗短暫震動，不會修改目前設定。
- 若原始碼環境沒有安裝 `tkinterdnd2`，程式仍可正常啟動及使用瀏覽功能，只會停用拖放。

## 畫面適配

圖片、圖片資料夾與影片都支援以下模式：

- `置中裁切`：保持比例填滿正方形，超出部分從中央裁掉。
- `拉伸成正方形`：保留完整畫面範圍，但非正方形來源會變形。
- `延伸空白畫布至正方形`（GUI 預設）：保持完整畫面與原始比例並置中，不裁切也不變形；RGBA 模式使用透明延伸區域，其他不透明通道模式使用純黑底。

未指定 `image_fit` 的既有 Python 圖片呼叫及命令列圖片模式仍維持原本的拉伸行為。

## 影片模式

- 支援單一 MP4 或 MOV 影片；音訊會忽略。
- 從指定的開始到結束時間平均抽取不重複影格，最多使用目前網格容量。
- 若影片影格少於網格容量，剩餘位置預設保留空格；可勾選用最後一格補齊。

## 命令列使用方式（選用）

```powershell
python flipbook_pillow.py "D:\Frames" "D:\Output\flipbook.png" --cols 12 --rows 10 --tile-size 256 --mode RGBA
```

影片範例：

```powershell
python flipbook_pillow.py "D:\Video\effect.mp4" "D:\Output\flipbook.png" --cols 8 --rows 8 --tile-size 256 --start 1.5 --end 5 --video-fit crop
```

若要保留完整影片畫面並將畫布延伸成正方形，可將 `--video-fit` 設為 `pad`。

圖片依檔名自然排序，例如 `frame2.png` 會排在 `frame10.png` 前面；排列方向為由左到右、再由上到下。格數不足時仍會生成，超出容量的尾端圖片會被忽略。

命令列的圖片來源也可以直接指定一張序列圖片，例如：

```powershell
python flipbook_pillow.py "D:\Frames\smoke_v2_003.png" "D:\Output\flipbook.png" --cols 12 --rows 10 --tile-size 256
```

命令列若要用最後一張圖片補滿空格，可加上 `--fill-empty-with-last`。

通道模式：

- `RGBA`：保留透明度。
- `RGB Straight`（命令列模式 `RGB`）：完整保留圖片RGB資訊，但將Alpha設為完全不透明。
- `RGB Premultiplied`（命令列模式 `RGB_BLACK`）：將圖片合成至黑色背景，會遺失原本透明部分的RGB資訊。

支援 PNG、JPEG、TIFF，以及目前 Pillow 安裝實際能解碼的其他列入格式。原 Blender 版本列有 EXR，但一般 Pillow 安裝不支援 EXR；請先將 EXR 轉成 PNG 或 TIFF。

程式也可當模組使用：

```python
from flipbook_pillow import make_flipbook

make_flipbook(
    input_folder=r"D:\Frames",
    output_path=r"D:\Output\flipbook.png",
    cols=12,
    rows=10,
    target_size=256,
    channel_mode="RGBA",
    image_fit="pad",  # crop、stretch 或 pad；省略時維持舊版 stretch 行為
)
```

## 網頁版（Cloudflare）

專案另包含 [`web`](web) 子專案：可部署至 Cloudflare Workers，讓使用者免安裝、免登入地在瀏覽器本機將圖片序列或 MP4／MOV 影片轉成 Flipbook PNG。素材不會上傳，Windows 桌面版仍獨立保留。

完整的本機開發、R2 runtime 初始化、Cloudflare 首次發布與 GitHub 自動部署步驟請見 [`web/README.md`](web/README.md)。
