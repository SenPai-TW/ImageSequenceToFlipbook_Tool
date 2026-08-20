# ImageSequenceToFlipbook Tool — HANDOFF

更新時間：2026-08-20（Asia/Taipei）

目前產品版本：**v3.1**

## 目前狀態

- 新工作區：`D:\GitHub\ImageSequenceToFlipbook_Tool`
- Git 分支：`main`
- 版本更新前 HEAD：`540a063`（feat: 優化小螢幕介面、捲軸樣式與 Flipbook 尺寸提示）
- GitHub 預設分支為 `main`；遠端 `master` 已刪除。
- 舊版 `main` 保存在 `archive/old-main-20260820`（`db46633`）。
- 工作樹包含尚未提交的 v3.1 版本資訊更新，請勿用 reset、checkout 或清理指令覆蓋。
- 最新 Windows 成品位於 [`dist/FlipbookGenerator.exe`](./dist/FlipbookGenerator.exe)。
  - 建置時間：2026-08-20 20:51:55
  - 大小：50,536,086 bytes
  - SHA-256：`69805FD39CD84C8AE93F8CD3457ABCEC0C485D7A482667585B46104BF6B56313`
  - 已確認主視窗標題為 `圖片序列／影片轉 Flipbook v3.1` 且正常回應，驗證後已關閉測試程序。

## 尚未提交的工作

- 新增 [`flipbook_version.py`](./flipbook_version.py)，桌面版版本為 `3.1`，顯示為 `v3.1`。
- [`flipbook_gui.pyw`](./flipbook_gui.pyw) 的視窗標題會顯示版本。
- Web package 與 lockfile 版本同步為 `3.1.0`。
- 新增 [`tests/test_version_metadata.py`](./tests/test_version_metadata.py)，強制檢查版本資訊一致。
- [`README.md`](./README.md) 與本 HANDOFF 已加入版本維護規則。

修改細節以 `git diff` 為準，不在此重複貼入程式碼。

## 已完成驗證

- v3.1 的 Python 編譯檢查通過。
- 完整單元測試共 43 項：21 項通過；22 項 Tk GUI 測試因本機 Python 3.14 缺少 Tcl/Tk 而跳過。
- 版本同步測試通過：桌面 `v3.1`、Web `3.1.0`、README 與 HANDOFF 一致。
- `git diff --check` 通過。
- v3.1 EXE 已使用 Python 3.11／PyInstaller 6.16.0 成功建置，啟動 smoke test 通過。

## 版本維護規則

後續每次發布更新，必須同步修改：

- `flipbook_version.py` 的桌面產品版本。
- `web/package.json` 與 `web/package-lock.json` 的 SemVer。
- `README.md` 與本 HANDOFF 的目前版本。
- 重新建置 EXE，驗證視窗標題，最後才建立相同版本的 Git tag。

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

1. 檢查 v3.1 變更後再決定 commit、tag 與 push。
2. 後續功能或修正發布時持續遞增版本，並遵循版本維護規則。

## Suggested skills

- `diagnosing-bugs`：GUI、拖放、VBS 啟動或影片解碼再次失敗時，先做根因診斷。
- `tdd`：新增轉檔或介面行為時，以回歸測試保護既有功能。
- `github:github`：使用者明確授權後，再整理 commit、push 或檢查 GitHub 狀態。
- `handoff`：下一次暫停工作前更新交接紀錄。
