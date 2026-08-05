# 圖片序列／影片轉 Flipbook（獨立版）

本工具從 SenPaiToolBox 的第 5 項功能獨立而來，不需要安裝 Blender。

## 安裝

雙擊 `安裝必要套件.bat` 後，安裝程式會先嘗試從 Python 官方網站安裝最新版 64 位元 Python，接著透過 pip 安裝最新版 Pillow 與 `imageio-ffmpeg`。若線上下載或安裝失敗，會自動改用 `installers` 資料夾內附的 Python 3.11.8、Pillow 12.3.0 與 imageio-ffmpeg 0.6.0，圖片序列及 MP4／MOV 影片功能皆可離線安裝使用。

## 視窗版使用方式（推薦）

1. 第一次使用時，雙擊 `安裝必要套件.bat`。
2. 安裝完成後，雙擊 `開啟Flipbook工具.vbs`。
3. 選擇「圖片序列」或「影片（MP4／MOV）」及存檔位置。
4. 設定欄數、列數、單格尺寸及通道模式。影片可另外設定起訖秒數與畫面適配方式。
5. 按下「執行生成 Flipbook 網格圖」。

容量處理：

- 設定格數少於來源圖片數：視窗會顯示白底驚嘆號警告；仍可生成，超出容量的尾端圖片會忽略。
- 設定格數多於來源圖片數：預設保留透明空格。勾選「用最後一格圖片補齊剩下的所有空格」後，所有空格都會重複使用最後一張來源圖片。

VBS 啟動器會在背景使用已安裝的 Python 3 開啟 GUI，不會出現 PowerShell 或命令提示字元視窗。

## 影片模式

- 支援單一 MP4 或 MOV 影片；音訊會忽略。
- 從指定的開始到結束時間平均抽取不重複影格，最多使用目前網格容量。
- 若影片影格少於網格容量，剩餘位置預設保留空格；可勾選用最後一格補齊。
- `置中裁切`：保持比例填滿正方形，超出部分從中央裁掉。
- `拉伸成正方形`：保留完整畫面範圍，但非正方形影片會變形。

## 命令列使用方式（選用）

```powershell
python flipbook_pillow.py "D:\Frames" "D:\Output\flipbook.png" --cols 12 --rows 10 --tile-size 256 --mode RGBA
```

影片範例：

```powershell
python flipbook_pillow.py "D:\Video\effect.mp4" "D:\Output\flipbook.png" --cols 8 --rows 8 --tile-size 256 --start 1.5 --end 5 --video-fit crop
```

圖片依檔名自然排序，例如 `frame2.png` 會排在 `frame10.png` 前面；排列方向為由左到右、再由上到下。格數不足時仍會生成，超出容量的尾端圖片會被忽略。

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
)
```
