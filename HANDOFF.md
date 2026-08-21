# ImageSequenceToFlipbook Tool — HANDOFF

更新時間：2026-08-21（Asia/Taipei）

目前產品版本：**v3.2**

## 目前狀態

- 工作區：`D:\GitHub\ImageSequenceToFlipbook_Tool`
- Git 分支：`main`
- 目前 HEAD：`6a8511c`（`重新設計UI介面`）。
- 本機 `origin/main` 追蹤參照目前也指向 `6a8511c`；本次沒有重新連線查詢 GitHub，因此不把它當作即時遠端驗證。
- v3.2 介面、預覽、版本與建置程式碼已包含在 `6a8511c`；目前沒有 `v3.2` tag。
- `6a8511c` 建立時剛好遇到 HANDOFF 重寫中的暫時刪除狀態，因此該 commit 記錄了 `HANDOFF.md` 刪除；本文件已在工作樹恢復，但目前仍是未追蹤檔案。
- 修改細節以 `git show 6a8511c` 與目前 `git status` 為準；不要使用 reset、checkout 或清理指令覆蓋本文件。
- 最新 Windows 成品：[`dist/FlipbookGenerator.exe`](./dist/FlipbookGenerator.exe)
  - 建置時間：2026-08-21 21:03:39
  - 大小：50,918,229 bytes
  - SHA-256：`6452452AFFE86E06C695B15EA5CD18BB4A47645F59CDA36B4E0D74370BADA830`
  - smoke test 已確認標題為 `圖片序列／影片轉 Flipbook v3.2`、視窗正常回應，測試程序已關閉。

## v3.2 已完成內容

- [`flipbook_gui.pyw`](./flipbook_gui.pyw)
  - 將原本垂直長表單重構為寬版雙欄、窄版單欄的 Windows 工作台。
  - 左側整理來源模式、時間範圍、網格配置與影像處理；右側固定顯示預覽、摘要、進度與主要操作。
  - 來源類型改為三段式水平切換，保留圖片、資料夾、影片與拖放流程。
  - 區塊標題改為卡片內的內縮標題列與短色條；中文使用 `Microsoft JhengHei UI`，英文產品名使用 `Segoe UI Variable Display`。
  - 預覽使用 debounce、generation token、背景工作與主執行緒 PhotoImage 更新，舊結果不會覆蓋新設定。
- [`flipbook_pillow.py`](./flipbook_pillow.py)
  - 新增不寫入磁碟的圖片與影片低解析預覽介面，重用既有排序、fit、通道與補格規則。
  - 大型序列採代表影格取樣，影片採有限數量的均勻取樣；正式輸出 API 與結果維持不變。
- [`FlipbookGenerator.spec`](./FlipbookGenerator.spec) 與 [`pyi_rth_flipbook_tk.py`](./pyi_rth_flipbook_tk.py)
  - 明確封裝 Tcl/Tk 標準庫與 DLL，並在 frozen runtime 指向內附資源，繞過本機 Python 3.11 的 Tcl 偵測異常。
- 測試已涵蓋預覽、fit、取樣、進度、過期結果隔離、工作台配置與內縮標題結構。

## 版本同步

- 桌面版本來源：[`flipbook_version.py`](./flipbook_version.py) → `3.2`／`v3.2`。
- Web 版本：[`web/package.json`](./web/package.json) 與 [`web/package-lock.json`](./web/package-lock.json) → `3.2.0`。
- [`README.md`](./README.md) 與本 HANDOFF 已同步為 v3.2。
- [`tests/test_version_metadata.py`](./tests/test_version_metadata.py) 會檢查桌面、Web、README 與 HANDOFF 的版本一致性。

## 已完成驗證

- Python 編譯檢查通過：`flipbook_gui.pyw`、`flipbook_pillow.py`、`flipbook_version.py`。
- 完整 Python 測試共 50 項：24 項通過，26 項 Tk GUI 測試因來源 Python 3.11 的 Tcl 初始化異常而跳過；測試整體結果為 `OK (skipped=26)`。
- 版本同步測試通過：桌面 `v3.2`、Web `3.2.0`、README 與 HANDOFF 一致。
- `git diff --check` 通過；只有既有的 LF／CRLF 轉換提醒。
- v3.2 EXE 已使用 Python 3.11／PyInstaller 6.16.0 建置成功。
- frozen EXE smoke test 彌補來源 Tk 測試限制：視窗可建立、標題正確且正常回應。

## 已知限制

- 本機 Python 3.11 的 Tcl/Tk 安裝可找到 `init.tcl`，但初始化仍回報無法使用，因此來源 GUI 測試會跳過；目前不要把 skipped 測試誤報為 GUI 全數通過。
- PyInstaller 分析仍會顯示 `tkinter installation is broken`，但 spec 與 runtime hook 會手動封裝並指向 Tcl/Tk；成品 smoke test 已驗證可啟動。
- 本次沒有修改正式輸出排序、品質、CLI 或影片抽幀規則。

## 版本維護規則

後續每次發布更新必須同步：

1. `flipbook_version.py` 的桌面版本。
2. `web/package.json` 與 `web/package-lock.json` 的 SemVer。
3. `README.md` 與 `HANDOFF.md` 的目前版本及驗證結果。
4. 重新建置 EXE，記錄大小、SHA-256，並 smoke test 視窗標題。
5. 只有在使用者明確授權後才建立 commit、Git tag、push 或正式發布。

## 建議下一步

1. 人工操作圖片序列與影片各一次，確認預覽、生成、取消與輸出資料夾操作。
2. 在 760px、1000px、1180px 與 125%／150% DPI 下做最終版面驗收。
3. 由使用者決定是否把目前未追蹤的 `HANDOFF.md` 加回版本控制並建立後續 commit。
4. 只有在重新驗證 GitHub 狀態並取得明確授權後，才建立 `v3.2` tag 或進行其他發布操作。

## Suggested skills

- `code-review`：發布前檢查目前尚未提交的完整差異與回歸風險。
- `diagnosing-bugs`：來源 Tcl/Tk 或 frozen EXE 啟動再次異常時做根因診斷。
- `tdd`：新增預覽、生成或回應式介面行為時持續補回歸測試。
- `github:github`：僅在使用者明確授權後處理 commit、tag、push 或 GitHub 狀態。
- `handoff`：下一次暫停工作前更新本文件與暫存交接摘要。
