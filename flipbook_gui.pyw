#!/usr/bin/env pythonw
"""Windowed front-end for flipbook_pillow.py (Python 3.11 + Pillow 12.3.0)."""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from flipbook_pillow import collect_image_files, make_flipbook
except ModuleNotFoundError as exc:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "缺少必要套件",
        "無法載入 Pillow。請先安裝 Python 3.11 與 Pillow 12.3.0。\n\n"
        "若使用完整安裝包，請執行一次「安裝必要套件.bat」。\n\n"
        f"詳細訊息：{exc}",
    )
    root.destroy()
    raise SystemExit(1)


MODE_LABELS = {
    "RGBA（透明）": "RGBA",
    "RGB Straight": "RGB",
    "RGB Premultiplied": "RGB_BLACK",
}


class FlipbookApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("序列圖檔轉 Flipbook")
        self.geometry("690x470")
        self.minsize(620, 440)
        self.configure(bg="#292929")

        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.cols_var = tk.IntVar(value=12)
        self.rows_var = tk.IntVar(value=10)
        self.size_var = tk.IntVar(value=256)
        self.mode_var = tk.StringVar(value="RGBA（透明）")
        self.fill_empty_var = tk.BooleanVar(value=False)
        self.count_var = tk.StringVar(value="請選擇包含序列圖檔的來源路徑")
        self.capacity_var = tk.StringVar(value="目前設定總網格數：12 × 10 = 120 格")
        self.detail_var = tk.StringVar(value="完整保留 Alpha 透明去背通道背景輸出。")
        self.status_var = tk.StringVar(value="就緒")
        self._busy = False
        self._source_count = 0

        self._configure_style()
        self._build_ui()
        for variable in (self.cols_var, self.rows_var, self.mode_var):
            variable.trace_add("write", self._settings_changed)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#292929")
        style.configure("Panel.TFrame", background="#242424", relief="solid", borderwidth=1)
        style.configure("TLabel", background="#292929", foreground="#ededed", font=("Microsoft JhengHei UI", 10))
        style.configure("Muted.TLabel", foreground="#c4c4c4")
        style.configure("WarningIcon.TLabel", background="#ffffff", foreground="#111111", padding=(5, 1), font=("Arial", 10, "bold"))
        style.configure("WarningText.TLabel", foreground="#ffffff", font=("Microsoft JhengHei UI", 9))
        style.configure("Panel.TLabel", background="#242424", foreground="#ededed")
        style.configure("TButton", background="#5a5a5a", foreground="#ffffff", padding=(8, 6), font=("Microsoft JhengHei UI", 10))
        style.map("TButton", background=[("active", "#707070"), ("disabled", "#414141")])
        style.configure("Primary.TButton", background="#686868", font=("Microsoft JhengHei UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#858585")])
        style.configure("TEntry", fieldbackground="#202020", foreground="#ffffff", insertcolor="#ffffff")
        style.configure("TSpinbox", fieldbackground="#363636", foreground="#ffffff", arrowsize=14)
        style.configure("TCombobox", fieldbackground="#363636", background="#363636", foreground="#ffffff")
        style.map("TCombobox", fieldbackground=[("readonly", "#363636")], foreground=[("readonly", "#ffffff")])
        style.configure("Horizontal.TProgressbar", background="#6a9fd4", troughcolor="#202020")
        style.configure("TCheckbutton", background="#292929", foreground="#ededed", font=("Microsoft JhengHei UI", 10))
        style.map("TCheckbutton", background=[("active", "#292929")], foreground=[("disabled", "#777777")])

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=14)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="來源目錄：").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(main, textvariable=self.source_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(main, text="瀏覽…", command=self._choose_source).grid(row=0, column=2)

        ttk.Label(main, text="存檔位置：").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(main, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(main, text="瀏覽…", command=self._choose_output).grid(row=1, column=2)

        ttk.Label(main, textvariable=self.count_var, style="Muted.TLabel").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(6, 12)
        )

        settings = ttk.Frame(main)
        settings.grid(row=3, column=0, columnspan=3, sticky="ew")
        for col in (1, 3):
            settings.columnconfigure(col, weight=1)

        ttk.Label(settings, text="欄數 (Cols)").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Spinbox(settings, from_=1, to=999, textvariable=self.cols_var, width=10).grid(row=0, column=1, sticky="ew", padx=(0, 18))
        ttk.Label(settings, text="列數 (Rows)").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Spinbox(settings, from_=1, to=999, textvariable=self.rows_var, width=10).grid(row=0, column=3, sticky="ew")

        capacity_line = ttk.Frame(main)
        capacity_line.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(9, 5))
        ttk.Label(capacity_line, textvariable=self.capacity_var, style="Muted.TLabel").pack(side="left")
        self.warning_icon = ttk.Label(capacity_line, text="!", style="WarningIcon.TLabel")
        self.warning_text = ttk.Label(
            capacity_line,
            text="需求的圖片總格數不足，多的格數會被刪掉",
            style="WarningText.TLabel",
        )

        self.fill_check = ttk.Checkbutton(
            main,
            text="用最後一格圖片補齊剩下的所有空格",
            variable=self.fill_empty_var,
        )
        self.fill_check.grid(row=5, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.fill_check.grid_remove()

        lower = ttk.Frame(main)
        lower.grid(row=6, column=0, columnspan=3, sticky="ew")
        lower.columnconfigure(1, weight=1)
        lower.columnconfigure(3, weight=1)
        ttk.Label(lower, text="單格尺寸(pixel²)").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Spinbox(lower, from_=1, to=8192, textvariable=self.size_var, width=10).grid(row=0, column=1, sticky="ew", padx=(0, 18))
        ttk.Label(lower, text="通道模式").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Combobox(lower, textvariable=self.mode_var, values=tuple(MODE_LABELS), state="readonly").grid(row=0, column=3, sticky="ew")

        info = ttk.Frame(main, style="Panel.TFrame", padding=12)
        info.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=14)
        ttk.Label(info, text="ⓘ　模式說明", style="Panel.TLabel", font=("Microsoft JhengHei UI", 10, "bold")).pack(anchor="w")
        ttk.Label(info, textvariable=self.detail_var, style="Panel.TLabel", wraplength=610).pack(anchor="w", pady=(10, 0))

        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        ttk.Label(main, textvariable=self.status_var, style="Muted.TLabel").grid(row=9, column=0, columnspan=3, sticky="w")
        self.run_button = ttk.Button(main, text="🎞　執行生成 Flipbook 網格圖", style="Primary.TButton", command=self._start)
        self.run_button.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        main.rowconfigure(7, weight=1)

    def _choose_source(self) -> None:
        folder = filedialog.askdirectory(title="選擇序列圖檔來源目錄")
        if folder:
            self.source_var.set(folder)
            if not self.output_var.get():
                self.output_var.set(str(Path(folder) / "flipbook.png"))
            self._refresh_count()

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="選擇 Flipbook 存檔位置",
            defaultextension=".png",
            filetypes=[("PNG 圖片", "*.png")],
            initialfile="flipbook.png",
        )
        if path:
            self.output_var.set(path)

    def _refresh_count(self) -> None:
        try:
            count = len(collect_image_files(Path(self.source_var.get())))
            self._source_count = count
            self.count_var.set(f"來源目錄內共有 {count} 張支援的圖片")
        except (OSError, ValueError):
            self._source_count = 0
            self.count_var.set("來源目錄無法讀取")
        self._update_capacity()

    def _settings_changed(self, *_args: object) -> None:
        self.after_idle(self._update_capacity)
        descriptions = {
            "RGBA（透明）": "完整保留 Alpha 透明去背通道背景輸出。適合透明粒子、網格特效圖。",
            "RGB Straight": "完整保留圖片RGB資訊，但將Alpha設為完全不透明。",
            "RGB Premultiplied": "將圖片合成至黑色背景，會遺失原本透明部分的RGB資訊。",
        }
        self.detail_var.set(descriptions.get(self.mode_var.get(), ""))

    def _update_capacity(self) -> None:
        try:
            cols, rows = self.cols_var.get(), self.rows_var.get()
            capacity = cols * rows
            self.capacity_var.set(f"目前設定總網格數：{cols} × {rows} = {capacity} 格（左到右、上到下）")
            if self._source_count > capacity:
                if not self.warning_icon.winfo_ismapped():
                    self.warning_icon.pack(side="left", padx=(10, 5))
                    self.warning_text.pack(side="left")
                self.fill_check.grid_remove()
                self.fill_empty_var.set(False)
            else:
                self.warning_icon.pack_forget()
                self.warning_text.pack_forget()
                if self._source_count > 0 and capacity > self._source_count:
                    self.fill_check.grid()
                else:
                    self.fill_check.grid_remove()
                    self.fill_empty_var.set(False)
        except tk.TclError:
            self.capacity_var.set("欄數與列數必須是整數")

    def _start(self) -> None:
        if self._busy:
            return
        try:
            source = self.source_var.get().strip()
            output = self.output_var.get().strip()
            cols, rows, size = self.cols_var.get(), self.rows_var.get(), self.size_var.get()
        except tk.TclError:
            messagebox.showerror("設定錯誤", "欄數、列數與單格尺寸必須是整數。")
            return
        if not source or not output:
            messagebox.showerror("缺少路徑", "請選擇來源目錄與存檔位置。")
            return

        self._busy = True
        self.run_button.configure(state="disabled")
        self.progress.start(12)
        self.status_var.set("正在產生 Flipbook，請稍候……")
        mode = MODE_LABELS[self.mode_var.get()]
        fill_empty = self.fill_empty_var.get()
        threading.Thread(
            target=self._generate,
            args=(source, output, cols, rows, size, mode, fill_empty),
            daemon=True,
        ).start()

    def _generate(self, source: str, output: str, cols: int, rows: int,
                  size: int, mode: str, fill_empty: bool) -> None:
        try:
            saved_path, count = make_flipbook(
                source, output, cols, rows, size, mode, fill_empty
            )
        except Exception as exc:
            self.after(0, self._finished_error, str(exc))
        else:
            self.after(0, self._finished_ok, str(saved_path), count)

    def _finish_common(self) -> None:
        self._busy = False
        self.progress.stop()
        self.run_button.configure(state="normal")

    def _finished_error(self, error: str) -> None:
        self._finish_common()
        self.status_var.set("產生失敗")
        messagebox.showerror("Flipbook 產生失敗", error)

    def _finished_ok(self, path: str, count: int) -> None:
        self._finish_common()
        self.status_var.set(f"完成：已輸出 {count} 張圖片")
        if messagebox.askyesno("完成", f"Flipbook 已成功產生：\n{path}\n\n是否開啟輸出資料夾？"):
            os.startfile(str(Path(path).parent))


if __name__ == "__main__":
    FlipbookApp().mainloop()
