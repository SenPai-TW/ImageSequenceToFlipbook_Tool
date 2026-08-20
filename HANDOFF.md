# ImageSequenceToFlipbook Tool — HANDOFF

更新時間：2026-08-20（Asia/Taipei）

## 目前狀態

- Git 分支：`master`
- HEAD：`a82069b`（修正自動安裝bat檔）
- 工作樹尚未提交，請勿用 reset、checkout 或清理指令覆蓋現有內容。
- 最新 Windows 成品位於 [`dist/FlipbookGenerator.exe`](./dist/FlipbookGenerator.exe)。
  - 建置時間：2026-08-20 20:00:21
  - 大小：50,532,866 bytes
  - SHA-256：`8119FD44F1EB742BD57B18EE02B10E0C171BF974B4B8AC2777C8B313C169F6B4`
  - 已實際啟動並確認主視窗可回應，驗證後已關閉測試程序。

## 尚未提交的工作

- [`flipbook_gui.pyw`](./flipbook_gui.pyw)
  - 顯示完整 Flipbook 尺寸與非 2 次方警告。
  - 小螢幕支援垂直捲動與滑鼠滾輪。
  - 垂直捲軸改為無上下箭頭的 10 px 簡約樣式。
  - 深色與淺色主題各有軌道、滑塊、hover、pressed 顏色。
- [`tests/test_gui_sources.py`](./tests/test_gui_sources.py)
  - 補上完整尺寸、視窗高度與深／淺色捲軸樣式相關測試。
- [`.gitignore`](./.gitignore) 與 [`README.md`](./README.md) 也有未提交修改。
- [`web/`](./web/) 目前整個目錄尚未被 Git 追蹤，屬既有工作內容；不要刪除或覆寫。
- 本 HANDOFF 檔案也是新增、尚未提交的交接紀錄。

修改細節以 `git diff` 為準，不在此重複貼入程式碼。

## 已完成驗證

- Python 編譯檢查通過。
- 19 項非 Tk GUI／核心測試通過。
- `git diff --check` 通過；僅出現 Git 的 LF／CRLF 提示。
- PyInstaller EXE 建置成功，且完成啟動 smoke test。

## 本次清理

已移除約 721.6 MB、可重新產生的項目：

- `__pycache__/`
- `tests/__pycache__/`
- `build/`
- `.build-venv/`
- `web/node_modules/`
- `web/dist/`
- `web/test-results/`
- `web/.wrangler/`
- `web/.runtime/`

保留項目：

- `dist/FlipbookGenerator.exe`：目前可交付成品。
- `.flipbook-python-path`：被 Git 忽略的本機狀態；供 [`開啟Flipbook工具.vbs`](./開啟Flipbook工具.vbs) 尋找 Python，不應提交 Git。
- `installers/`：離線安裝備援。

若要再次建置，執行 [`build_exe.ps1`](./build_exe.ps1)；它會重新建立 `.build-venv/` 與 `build/`。若要處理 Web 專案，先在 `web/` 依 [`web/README.md`](./web/README.md) 還原相依套件與 runtime。

## 建議下一步

1. 實機切換深色／淺色主題，確認右側捲軸在小尺寸螢幕的視覺與操作。
2. 決定 `web/` 是否要納入同一個 Git repository，再分開整理提交範圍。
3. 提交前檢查 `.gitignore`、`README.md` 是否都屬預期修改。
4. 若 GUI 再修改，重新跑測試、建置 EXE 與啟動 smoke test。

## Suggested skills

- `diagnosing-bugs`：GUI、拖放、VBS 啟動或影片解碼再次失敗時，先做根因診斷。
- `tdd`：新增轉檔或介面行為時，以回歸測試保護既有功能。
- `github:github`：使用者明確授權後，再整理 commit、push 或檢查 GitHub 狀態。
- `handoff`：下一次暫停工作前更新交接紀錄。
