#!/usr/bin/env pythonw
"""Windowed front-end for image-sequence and video flipbook conversion."""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from flipbook_pillow import (
        collect_image_files,
        make_flipbook,
        make_video_flipbook,
        probe_video,
    )
except ModuleNotFoundError as exc:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "缺少必要套件",
        "無法載入圖片處理套件。請先執行「安裝必要套件.bat」。\n\n"
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

SOURCE_TYPES = ("圖片序列", "影片（MP4／MOV）")
VIDEO_FIT_LABELS = {
    "置中裁切": "crop",
    "拉伸成正方形": "stretch",
    "延伸畫布成正方形": "pad",
}


class FlipbookApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("圖片序列／影片轉 Flipbook")
        self.geometry("960x760")
        self.minsize(900, 640)
        self.configure(bg="#1f2328")

        self.source_var = tk.StringVar()
        self.source_type_var = tk.StringVar(value=SOURCE_TYPES[0])
        self.output_var = tk.StringVar()
        self.cols_var = tk.IntVar(value=12)
        self.rows_var = tk.IntVar(value=10)
        self.size_var = tk.IntVar(value=256)
        self.mode_var = tk.StringVar(value="RGBA（透明）")
        self.fill_empty_var = tk.BooleanVar(value=False)
        self.video_start_var = tk.StringVar(value="0")
        self.video_end_var = tk.StringVar()
        self.video_fit_var = tk.StringVar(value="置中裁切")
        self.count_var = tk.StringVar(value="請選擇包含序列圖檔的來源路徑")
        self.capacity_var = tk.StringVar(value="目前設定總網格數：12 × 10 = 120 格")
        self.detail_var = tk.StringVar(value="完整保留 Alpha 透明去背通道背景輸出。")
        self.status_var = tk.StringVar(value="就緒")
        self.detail_canvas: tk.Canvas | None = None
        self.detail_text_id: int | None = None
        self.output_folder_button: ttk.Button | None = None
        self._last_output_path: Path | None = None
        self._busy = False
        self._source_count = 0
        self._video_metadata: dict[str, object] | None = None
        self._probe_id = 0

        self._configure_style()
        self._build_ui()
        self.after_idle(self._fit_initial_window)
        for variable in (
            self.cols_var, self.rows_var,
            self.video_start_var, self.video_end_var,
        ):
            variable.trace_add("write", self._settings_changed)
        self.mode_var.trace_add("write", self._mode_changed)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        bg, panel, field = "#1f2328", "#1f2328", "#171b20"
        text, muted, border, accent = "#e4e9ed", "#98a2aa", "#46515a", "#5f96c7"
        family = "Microsoft JhengHei UI"
        title = (family, 22, "bold")
        base = (family, 10)
        section_title = (family, 16, "bold")

        # Large stretched images made live window resizing expensive. Sections
        # now use a lightweight borderless layout; rounded images are limited to
        # the small input controls where their redraw cost is negligible.
        style.layout("Section.TLabelframe", [
            ("Labelframe.padding", {"sticky": "nsew"}),
        ])

        # Extra transparent space on the right keeps the arrow away from the edge.
        arrow_image = tk.PhotoImage(master=self, width=23, height=11)
        arrow_color = "#b8c1c8"
        for y, half_width in enumerate((5, 4, 3, 2, 1)):
            left = 8 - half_width
            right = 9 + half_width
            arrow_image.put(arrow_color, to=(left, y + 3, right, y + 4))

        self._combo_arrow_image = arrow_image
        style.element_create("FlatCombo.arrow", "image", arrow_image, sticky="e")

        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("PanelFlat.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground=text, font=base)
        style.configure("Title.TLabel", background=bg, foreground="#f2f5f7", font=title)
        style.configure("Muted.TLabel", background=bg, foreground=muted, font=base)
        style.configure("Panel.TLabel", background=panel, foreground=text, font=base)
        style.configure("Hint.Panel.TLabel", background=panel, foreground=muted, font=(family, 9))
        style.configure("Section.TLabelframe", background=bg, foreground=text, borderwidth=0)
        style.configure("Section.TLabelframe.Label", background=bg, foreground="#f1f5f8", font=section_title)
        style.configure("InfoTitle.Panel.TLabel", background=panel, foreground="#cfe8f7", font=(family, 10, "bold"))
        style.configure("WarningIcon.TLabel", background="#c07d38", foreground="#fff5ea", padding=(6, 1), font=(family, 9, "bold"))
        style.configure("WarningText.TLabel", background=panel, foreground="#e0b783", font=(family, 9))
        style.configure("TButton", background="#363e45", foreground=text, bordercolor=border,
                        lightcolor=border, darkcolor=border, padding=(12, 7), font=base)
        style.map("TButton", background=[("active", "#4a545e"), ("disabled", "#30363b")],
                  foreground=[("disabled", "#747d85")])
        style.configure("Browse.TButton", background="#363e45", foreground=text,
                        bordercolor="#363e45", lightcolor="#363e45", darkcolor="#363e45",
                        relief="flat", borderwidth=0, padding=(12, 7), font=base)
        style.map("Browse.TButton", background=[("active", "#4a545e"), ("disabled", "#30363b")],
                  foreground=[("disabled", "#747d85")])
        style.configure("Primary.TButton", background=accent, foreground="#f5fbff",
                        bordercolor=accent, lightcolor=accent, darkcolor=accent,
                        relief="flat", borderwidth=0, padding=(14, 12),
                        font=("Microsoft JhengHei UI", 11, "bold"))
        style.map("Primary.TButton", background=[("active", "#72acd9"), ("disabled", "#405565")])
        style.configure("SecondaryAction.TButton", background="#363e45", foreground=text,
                        bordercolor="#363e45", lightcolor="#363e45", darkcolor="#363e45",
                        relief="flat", borderwidth=0, padding=(12, 13), font=(family, 10))
        style.map("SecondaryAction.TButton",
                  background=[("active", "#4a545e"), ("disabled", "#30363b")],
                  foreground=[("disabled", "#747d85")])
        style.configure("TEntry", fieldbackground=field, foreground=text, insertcolor=text,
                        background=field, bordercolor=field, lightcolor=field, darkcolor=field,
                        relief="flat", borderwidth=0, padding=(10, 7), font=base)
        style.map("TEntry",
                  fieldbackground=[("disabled", field), ("focus", field), ("!focus", field)],
                  background=[("disabled", field), ("focus", field), ("!focus", field)],
                  foreground=[("disabled", muted), ("!disabled", text)])
        style.layout("TEntry", [
            ("Entry.padding", {"sticky": "nsew", "children": [
                ("Entry.textarea", {"sticky": "nsew"}),
            ]}),
        ])
        style.configure("TSpinbox", fieldbackground=field, foreground=text, insertcolor=text,
                        background=field, bordercolor=field, lightcolor=field, darkcolor=field,
                        relief="flat", borderwidth=0, padding=(10, 7), font=base)
        style.map("TSpinbox",
                  fieldbackground=[("disabled", field), ("focus", field), ("!focus", field)],
                  background=[("disabled", field), ("focus", field), ("!focus", field)],
                  foreground=[("disabled", muted), ("!disabled", text)])
        style.layout("TSpinbox", [
            ("Spinbox.padding", {"sticky": "nsew", "children": [
                ("Spinbox.textarea", {"sticky": "nsew"}),
            ]}),
        ])
        style.configure("TCombobox", fieldbackground=field, foreground=text,
                        background=field, bordercolor=field, lightcolor=field, darkcolor=field,
                        relief="flat", borderwidth=0, padding=(10, 7), font=base)
        style.layout("TCombobox", [
            ("FlatCombo.arrow", {"side": "right", "sticky": "e"}),
            ("Combobox.padding", {"sticky": "nsew", "children": [
                ("Combobox.textarea", {"sticky": "nsew"}),
            ]}),
        ])
        style.map("TCombobox",
                  fieldbackground=[("disabled", field), ("readonly", field), ("focus", field), ("!focus", field)],
                  background=[("disabled", field), ("readonly", field), ("focus", field), ("!focus", field)],
                  foreground=[("disabled", muted), ("readonly", text), ("!disabled", text)])
        self.option_add("*TCombobox*Listbox.background", field)
        self.option_add("*TCombobox*Listbox.foreground", text)
        self.option_add("*TCombobox*Listbox.selectBackground", accent)
        self.option_add("*TCombobox*Listbox.selectForeground", "#f5fbff")
        self.option_add("*TCombobox*Listbox.font", base)
        style.configure("Horizontal.TProgressbar", background=accent, troughcolor=field,
                        bordercolor=field, lightcolor=accent, darkcolor=accent,
                        relief="flat", borderwidth=0, thickness=13)
        style.configure("TCheckbutton", background=panel, foreground=text, font=(family, 9))
        style.map("TCheckbutton", background=[("active", panel)], foreground=[("disabled", "#777f85")])

    def _section(self, parent: ttk.Frame, title: str, row: int) -> ttk.Labelframe:
        section = ttk.Labelframe(parent, text=title, style="Section.TLabelframe", padding=(0, 14, 0, 14))
        section.grid(row=row, column=0, sticky="ew", pady=(0, 16))
        section.columnconfigure(1, weight=1)
        return section

    def _fit_initial_window(self) -> None:
        """Size for the taller video layout, even when image mode starts selected."""
        self.update_idletasks()
        video_was_visible = self.video_options.winfo_ismapped()
        if not video_was_visible:
            self.video_options.grid()
            self.update_idletasks()
        requested = self.winfo_reqheight() + 16
        if not video_was_visible:
            self.video_options.grid_remove()
            self.update_idletasks()
        available = max(640, self.winfo_screenheight() - 96)
        height = min(requested, available)
        width = max(960, self.winfo_reqwidth())
        self.geometry(f"{width}x{height}")

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=(20, 14, 20, 12))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        ttk.Label(main, text="Flipbook Texture Sheet Generator", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(main, text="將圖片序列或影片轉成固定網格貼圖", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 30))

        source_section = self._section(main, "來源與輸出", 2)
        source_section.columnconfigure(1, weight=0)
        source_section.columnconfigure(2, weight=1)
        ttk.Label(source_section, text="來源：", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        source_type = ttk.Combobox(
            source_section, textvariable=self.source_type_var,
            values=SOURCE_TYPES, state="readonly", width=18,
        )
        source_type.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=5)
        source_type.bind("<<ComboboxSelected>>", self._source_type_changed)
        ttk.Entry(source_section, textvariable=self.source_var).grid(row=0, column=2, sticky="ew", pady=5)
        ttk.Button(source_section, text="瀏覽…", command=self._choose_source, width=11, style="Browse.TButton").grid(row=0, column=3, padx=(10, 0), pady=5)

        ttk.Label(source_section, text="儲存位置：", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(source_section, textvariable=self.output_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Button(source_section, text="瀏覽…", command=self._choose_output, width=11, style="Browse.TButton").grid(row=1, column=3, padx=(10, 0), pady=5)
        ttk.Label(source_section, textvariable=self.count_var, style="Hint.Panel.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", pady=(9, 0))

        self.video_options = self._section(main, "時間範圍與畫面適配", 3)
        for column in (1, 3, 5):
            self.video_options.columnconfigure(column, weight=1)
        ttk.Label(self.video_options, text="開始秒數", style="Panel.TLabel").grid(row=0, column=0, padx=(0, 9), pady=2)
        ttk.Spinbox(self.video_options, from_=0, to=999999, increment=0.1, textvariable=self.video_start_var).grid(row=0, column=1, sticky="ew", padx=(0, 20), pady=2)
        ttk.Label(self.video_options, text="結束秒數", style="Panel.TLabel").grid(row=0, column=2, padx=(0, 9), pady=2)
        ttk.Spinbox(self.video_options, from_=0, to=999999, increment=0.1, textvariable=self.video_end_var).grid(row=0, column=3, sticky="ew", padx=(0, 20), pady=2)
        ttk.Label(self.video_options, text="畫面適配", style="Panel.TLabel").grid(row=0, column=4, padx=(0, 9), pady=2)
        ttk.Combobox(self.video_options, textvariable=self.video_fit_var, values=tuple(VIDEO_FIT_LABELS), state="readonly", width=15).grid(row=0, column=5, sticky="ew", pady=2)
        self.video_options.grid_remove()

        settings = self._section(main, "Flipbook 設定", 4)
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)
        ttk.Label(settings, text="欄數 (Cols)", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Spinbox(settings, from_=1, to=999, textvariable=self.cols_var).grid(row=0, column=1, sticky="ew", padx=(0, 24), pady=5)
        ttk.Label(settings, text="列數 (Rows)", style="Panel.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 12), pady=5)
        ttk.Spinbox(settings, from_=1, to=999, textvariable=self.rows_var).grid(row=0, column=3, sticky="ew", pady=5)
        ttk.Label(settings, text="單格尺寸", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Spinbox(settings, from_=1, to=8192, textvariable=self.size_var).grid(row=1, column=1, sticky="ew", padx=(0, 24), pady=5)
        ttk.Label(settings, text="px²", style="Hint.Panel.TLabel").grid(row=1, column=2, sticky="w", pady=5)
        ttk.Label(settings, text="通道模式", style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=5)
        mode_combo = ttk.Combobox(
            settings, textvariable=self.mode_var, values=tuple(MODE_LABELS),
            state="readonly", width=22,
        )
        mode_combo.grid(row=2, column=1, columnspan=3, sticky="w", pady=5)

        capacity_line = ttk.Frame(settings, style="PanelFlat.TFrame")
        capacity_line.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(12, 6))
        ttk.Label(capacity_line, textvariable=self.capacity_var, style="Hint.Panel.TLabel").pack(side="left")
        self.warning_icon = ttk.Label(capacity_line, text="!", style="WarningIcon.TLabel")
        self.warning_text = ttk.Label(capacity_line, text="需求的圖片總格數不足，多的格數會被刪掉", style="WarningText.TLabel")
        self.fill_check = ttk.Checkbutton(settings, text="用最後一格補齊剩餘空格", variable=self.fill_empty_var)
        self.fill_check.grid(row=4, column=0, columnspan=4, sticky="w", pady=(0, 9))
        self.fill_check.grid_remove()

        self.detail_canvas = tk.Canvas(
            settings, width=860, height=70, bg="#1f2328",
            highlightthickness=0, bd=0,
        )
        self.detail_canvas.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.detail_canvas.create_text(
            12, 14, text="ⓘ  模式說明", anchor="nw", fill="#d8edf9",
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.detail_text_id = self.detail_canvas.create_text(
            12, 40, text=self.detail_var.get(), anchor="nw", fill="#9aa3aa",
            font=("Microsoft JhengHei UI", 9), width=820,
        )

        action = self._section(main, "執行與處理狀態", 5)
        action.columnconfigure(0, weight=1)
        action.columnconfigure(1, weight=0)
        self.progress = ttk.Progressbar(action, mode="indeterminate")
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(action, textvariable=self.status_var, style="Hint.Panel.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.run_button = ttk.Button(action, text="▦  執行生成 Flipbook 網格圖", style="Primary.TButton", command=self._start)
        self.run_button.grid(row=2, column=0, sticky="ew", padx=(0, 10))
        self.output_folder_button = ttk.Button(
            action, text="開啟輸出資料夾", command=self._open_last_output_folder,
            state="disabled", style="SecondaryAction.TButton", width=12,
        )
        self.output_folder_button.grid(row=2, column=1, sticky="ew")

    def _choose_source(self) -> None:
        if self.source_type_var.get() == SOURCE_TYPES[0]:
            selected = filedialog.askdirectory(title="選擇序列圖檔來源目錄")
        else:
            selected = filedialog.askopenfilename(
                title="選擇 MP4 或 MOV 影片",
                filetypes=[("支援的影片", "*.mp4 *.mov"), ("MP4", "*.mp4"), ("MOV", "*.mov")],
            )
        if selected:
            self.source_var.set(selected)
            if not self.output_var.get():
                source_path = Path(selected)
                output_folder = source_path if source_path.is_dir() else source_path.parent
                self.output_var.set(str(output_folder / "flipbook.png"))
            self._refresh_count()

    def _source_type_changed(self, _event: object | None = None) -> None:
        self._probe_id += 1
        self.source_var.set("")
        self._source_count = 0
        self._video_metadata = None
        self.video_start_var.set("0")
        self.video_end_var.set("")
        if self.source_type_var.get() == SOURCE_TYPES[0]:
            self.video_options.grid_remove()
            self.count_var.set("請選擇包含序列圖檔的來源路徑")
        else:
            self.video_options.grid()
            self.count_var.set("請選擇 MP4 或 MOV 影片")
        self._update_capacity()

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
        if self.source_type_var.get() != SOURCE_TYPES[0]:
            self._probe_id += 1
            probe_id = self._probe_id
            self._video_metadata = None
            self._source_count = 0
            self.count_var.set("正在讀取影片資訊……")
            self.status_var.set("正在分析影片……")
            threading.Thread(
                target=self._probe_video_worker,
                args=(self.source_var.get(), probe_id),
                daemon=True,
            ).start()
            return
        try:
            count = len(collect_image_files(Path(self.source_var.get())))
            self._source_count = count
            self.count_var.set(f"來源目錄內共有 {count} 張支援的圖片")
        except (OSError, ValueError):
            self._source_count = 0
            self.count_var.set("來源目錄無法讀取")
        self._update_capacity()

    def _probe_video_worker(self, path: str, probe_id: int) -> None:
        try:
            metadata = probe_video(path)
        except Exception as exc:
            self.after(0, self._probe_video_error, probe_id, str(exc))
        else:
            self.after(0, self._probe_video_ok, probe_id, metadata)

    def _probe_video_error(self, probe_id: int, error: str) -> None:
        if probe_id != self._probe_id:
            return
        self._video_metadata = None
        self._source_count = 0
        self.count_var.set(f"影片無法讀取：{error}")
        self.status_var.set("影片分析失敗")
        self._update_capacity()

    def _probe_video_ok(self, probe_id: int, metadata: dict[str, object]) -> None:
        if probe_id != self._probe_id:
            return
        self._video_metadata = metadata
        duration = float(metadata["duration"])
        self.video_end_var.set(f"{duration:.3f}")
        self.count_var.set(
            f"影片：{metadata['width']} × {metadata['height']}，"
            f"{float(metadata['fps']):.3f} FPS，{metadata['frame_count']} 格，"
            f"長度 {duration:.3f} 秒"
        )
        self.status_var.set("就緒")
        self._update_video_range_count()

    def _update_video_range_count(self) -> None:
        if not self._video_metadata:
            return
        try:
            start = float(self.video_start_var.get())
            end_text = self.video_end_var.get().strip()
            end = float(end_text) if end_text else float(self._video_metadata["duration"])
            duration = float(self._video_metadata["duration"])
            total = int(self._video_metadata["frame_count"])
            if start < 0 or end <= start or end > duration + 0.001:
                self._source_count = 0
            else:
                self._source_count = max(1, min(total, round(total * (end - start) / duration)))
        except ValueError:
            self._source_count = 0
        self._update_capacity()

    def _settings_changed(self, *_args: object) -> None:
        self.after_idle(self._update_capacity)
        if self.source_type_var.get() != SOURCE_TYPES[0]:
            self.after_idle(self._update_video_range_count)

    def _mode_changed(self, *_args: object) -> None:
        descriptions = {
            "RGBA（透明）": "完整保留 Alpha 透明去背通道背景輸出。適合透明粒子、網格特效圖。",
            "RGB Straight": "完整保留圖片RGB資訊，但將Alpha設為完全不透明。",
            "RGB Premultiplied": "將圖片合成至黑色背景，會遺失原本透明部分的RGB資訊。",
        }
        self._set_detail_text(descriptions.get(self.mode_var.get(), ""))

    def _set_detail_text(self, text: str) -> None:
        self.detail_var.set(text)
        if self.detail_canvas is not None and self.detail_text_id is not None:
            self.detail_canvas.itemconfigure(self.detail_text_id, text=text)

    def _update_capacity(self) -> None:
        try:
            cols, rows = self.cols_var.get(), self.rows_var.get()
            capacity = cols * rows
            self.capacity_var.set(f"目前設定總網格數：{cols} × {rows} = {capacity} 格（左到右、上到下）")
            if self._source_count > capacity:
                if self.source_type_var.get() == SOURCE_TYPES[0]:
                    self.warning_text.configure(text="需求的圖片總格數不足，多的格數會被刪掉")
                else:
                    self.warning_text.configure(text="影片影格多於網格容量，將平均抽取整段範圍")
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
            messagebox.showerror("缺少路徑", "請選擇來源與存檔位置。")
            return

        is_video = self.source_type_var.get() != SOURCE_TYPES[0]
        start, end = 0.0, None
        if is_video:
            if not self._video_metadata:
                messagebox.showerror("影片尚未就緒", "請先選擇並成功讀取 MP4 或 MOV 影片。")
                return
            try:
                start = float(self.video_start_var.get())
                end_text = self.video_end_var.get().strip()
                end = float(end_text) if end_text else None
            except ValueError:
                messagebox.showerror("設定錯誤", "影片開始與結束時間必須是數字。")
                return

        self._busy = True
        self.run_button.configure(state="disabled")
        self.progress.start(12)
        self.status_var.set("正在產生 Flipbook，請稍候……")
        self._last_output_path = None
        if self.output_folder_button is not None:
            self.output_folder_button.configure(state="disabled")
        mode = MODE_LABELS[self.mode_var.get()]
        fill_empty = self.fill_empty_var.get()
        threading.Thread(
            target=self._generate,
            args=(source, output, cols, rows, size, mode, fill_empty,
                  is_video, start, end, VIDEO_FIT_LABELS[self.video_fit_var.get()]),
            daemon=True,
        ).start()

    def _generate(self, source: str, output: str, cols: int, rows: int,
                  size: int, mode: str, fill_empty: bool, is_video: bool,
                  start: float, end: float | None, video_fit: str) -> None:
        try:
            if is_video:
                saved_path, count = make_video_flipbook(
                    source, output, cols, rows, size, mode, fill_empty,
                    start, end, video_fit,
                )
            else:
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
        self.status_var.set(f"完成：已輸出 {count} 格影格")
        self._last_output_path = Path(path)
        if self.output_folder_button is not None:
            self.output_folder_button.configure(state="normal")
        messagebox.showinfo("完成", f"Flipbook 已成功產生：\n{path}")

    def _open_last_output_folder(self) -> None:
        if self._last_output_path is None:
            return
        os.startfile(str(self._last_output_path.parent))


if __name__ == "__main__":
    FlipbookApp().mainloop()
