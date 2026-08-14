#!/usr/bin/env pythonw
"""Windowed front-end for image-sequence and video flipbook conversion."""

from __future__ import annotations

import os
import sys
import ctypes
import tempfile
import threading
import time
import traceback
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import COPY, DND_FILES, REFUSE_DROP, TkinterDnD
except ModuleNotFoundError:
    COPY = "copy"
    DND_FILES = "DND_Files"
    REFUSE_DROP = "refuse_drop"
    TkinterDnD = None

try:
    from flipbook_pillow import (
        VALID_EXTENSIONS,
        VIDEO_EXTENSIONS,
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

SOURCE_IMAGE_FILE = "image_file"
SOURCE_IMAGE_FOLDER = "image_folder"
SOURCE_VIDEO = "video"
SOURCE_TYPE_LABELS = {
    SOURCE_IMAGE_FILE: "序列圖片（選其中一張）",
    SOURCE_IMAGE_FOLDER: "圖片資料夾",
    SOURCE_VIDEO: "影片（MP4／MOV）",
}
SOURCE_TYPE_BY_LABEL = {label: kind for kind, label in SOURCE_TYPE_LABELS.items()}
SOURCE_TYPES = tuple(SOURCE_TYPE_LABELS.values())
OVERLAY_ALPHA = 0.65
OVERLAY_FADE_IN_MS = 160
OVERLAY_FADE_OUT_MS = 100
OVERLAY_REJECT_FADE_MS = 80
OVERLAY_FRAME_MS = 20
OVERLAY_PRIME_DELAY_MS = 50
FIT_LABELS = {
    "置中裁切": "crop",
    "拉伸成正方形": "stretch",
    "延伸空白畫布至正方形": "pad",
}
VIDEO_FIT_LABELS = FIT_LABELS
FIT_DESCRIPTIONS = {
    "置中裁切": "保持原始比例並填滿正方形，超出範圍的部分會從中央裁切。",
    "拉伸成正方形": "完整填滿正方形，但非正方形來源會被拉伸而產生比例變形。",
    "延伸空白畫布至正方形": (
        "保持完整畫面與原始比例並置中；空白區域在 RGBA 模式為透明，其他模式為黑色。"
    ),
}


def is_power_of_two(value: int) -> bool:
    """Return whether a positive integer is an exact power of two."""
    return value > 0 and value & (value - 1) == 0


def calculate_full_size(
    cols: int, rows: int, tile_size: int
) -> tuple[int, int, bool]:
    """Return the full texture dimensions and whether both are powers of two."""
    width = cols * tile_size
    height = rows * tile_size
    return width, height, is_power_of_two(width) and is_power_of_two(height)


THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_PALETTES = {
    THEME_DARK: {
        "window_bg": "#1F2328",
        "section_bg": "#1F2328",
        "input_bg": "#171B20",
        "input_hover": "#20262C",
        "input_focus": "#252C33",
        "secondary_button": "#363E45",
        "secondary_button_hover": "#4A545E",
        "secondary_button_pressed": "#2D343A",
        "primary_button": "#5F96C7",
        "primary_button_hover": "#72ACD9",
        "primary_button_pressed": "#4F83B1",
        "disabled_bg": "#30363B",
        "progress_track": "#171B20",
        "progress_fill": "#5F96C7",
        "heading_text": "#F2F5F7",
        "normal_text": "#E4E9ED",
        "input_text": "#E4E9ED",
        "secondary_text": "#98A2AA",
        "helper_text": "#9AA3AA",
        "disabled_text": "#747D85",
        "error_text": "#E0B783",
        "button_text": "#F5FBFF",
        "warning_bg": "#C07D38",
        "arrow": "#B8C1C8",
    },
    THEME_LIGHT: {
        "window_bg": "#F1F0ED",
        "section_bg": "#F1F0ED",
        "input_bg": "#E5E3DF",
        "input_hover": "#DEDBD6",
        "input_focus": "#D9D6D1",
        "secondary_button": "#DEDCD7",
        "secondary_button_hover": "#D4D1CB",
        "secondary_button_pressed": "#CAC7C1",
        "primary_button": "#687F94",
        "primary_button_hover": "#748CA2",
        "primary_button_pressed": "#586F84",
        "disabled_bg": "#DFDDD9",
        "progress_track": "#D9D7D2",
        "progress_fill": "#74899C",
        "heading_text": "#34383B",
        "normal_text": "#484C4F",
        "input_text": "#3F4346",
        "secondary_text": "#777A7C",
        "helper_text": "#878A8C",
        "disabled_text": "#A3A29F",
        "error_text": "#B76561",
        "button_text": "#F7F7F5",
        "warning_bg": "#B76561",
        "arrow": "#555A5D",
    },
}


def classify_source_path(path: str | Path) -> str | None:
    """Classify one existing item as an image file, image folder, or video."""
    source = Path(path).expanduser()
    try:
        source = source.resolve()
        if source.is_dir():
            with os.scandir(source) as entries:
                return SOURCE_IMAGE_FOLDER if any(
                    entry.is_file() and Path(entry.name).suffix.lower() in VALID_EXTENSIONS
                    for entry in entries
                ) else None
        if not source.is_file():
            return None
        if source.suffix.lower() in VALID_EXTENSIONS:
            return SOURCE_IMAGE_FILE
        if source.suffix.lower() in VIDEO_EXTENSIONS:
            return SOURCE_VIDEO
    except (OSError, ValueError):
        return None
    return None


def source_dialog_initial_directory(current_source: str) -> str | None:
    """Return a useful native-dialog start folder without overriding system defaults."""
    current = Path(current_source).expanduser() if current_source.strip() else None
    if current is not None:
        try:
            current = current.resolve()
            if current.is_file():
                return str(current.parent)
            if current.is_dir():
                return str(current)
        except OSError:
            pass
    return None


if sys.platform == "win32":
    _OverlayWndProc = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    )

    class _OverlayWindowClass(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", _OverlayWndProc),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        ]

    class _OverlayPaintStruct(ctypes.Structure):
        _fields_ = [
            ("hdc", wintypes.HDC),
            ("fErase", wintypes.BOOL),
            ("rcPaint", wintypes.RECT),
            ("fRestore", wintypes.BOOL),
            ("fIncUpdate", wintypes.BOOL),
            ("rgbReserved", ctypes.c_byte * 32),
        ]


class Win32DropOverlay:
    """Alpha-blended child HWND that never becomes a second OLE toplevel."""

    WM_PAINT = 0x000F
    WM_ERASEBKGND = 0x0014
    WM_NCHITTEST = 0x0084
    HTTRANSPARENT = -1
    WS_CHILD = 0x40000000
    WS_VISIBLE = 0x10000000
    WS_CLIPSIBLINGS = 0x04000000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_LAYERED = 0x00080000
    WS_EX_NOACTIVATE = 0x08000000
    LWA_ALPHA = 0x00000002
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    DT_CENTER = 0x00000001
    DT_VCENTER = 0x00000004
    DT_SINGLELINE = 0x00000020
    TRANSPARENT = 1

    def __init__(self, parent: tk.Misc) -> None:
        if sys.platform != "win32":
            raise RuntimeError("The layered drop overlay requires Windows.")
        self._parent = parent
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._kernel32 = ctypes.windll.kernel32
        self._configure_api()
        self._hwnd = 0
        self._class_atom = 0
        self._class_name = f"FlipbookDropOverlay_{os.getpid()}_{id(self):x}"
        self._text = "放開以套用來源"
        self._brush = self._gdi32.CreateSolidBrush(self._rgb(0x11, 0x16, 0x1A))
        self._font = self._gdi32.CreateFontW(
            -24, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 5, 0,
            "Microsoft JhengHei UI",
        )
        self._window_proc_callback = _OverlayWndProc(self._window_proc)
        self._hinstance = self._kernel32.GetModuleHandleW(None)
        window_class = _OverlayWindowClass()
        window_class.cbSize = ctypes.sizeof(_OverlayWindowClass)
        window_class.lpfnWndProc = self._window_proc_callback
        window_class.hInstance = self._hinstance
        window_class.lpszClassName = self._class_name
        self._class_atom = self._user32.RegisterClassExW(ctypes.byref(window_class))
        if not self._class_atom:
            self.destroy()
            raise ctypes.WinError()

        self._hwnd = int(self._user32.CreateWindowExW(
            self.WS_EX_LAYERED | self.WS_EX_TRANSPARENT | self.WS_EX_NOACTIVATE,
            self._class_name,
            "",
            self.WS_CHILD | self.WS_VISIBLE | self.WS_CLIPSIBLINGS,
            0, 0, 1, 1,
            int(parent.winfo_id()),
            None, self._hinstance, None,
        ) or 0)
        if not self._hwnd:
            self.destroy()
            raise ctypes.WinError()
        self.set_alpha(0.0)

    def _configure_api(self) -> None:
        """Preserve 64-bit handles when calling Win32 through ctypes."""
        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        self._user32.RegisterClassExW.argtypes = [
            ctypes.POINTER(_OverlayWindowClass)
        ]
        self._user32.RegisterClassExW.restype = wintypes.ATOM
        self._user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]
        self._user32.CreateWindowExW.restype = wintypes.HWND
        self._user32.DefWindowProcW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        self._user32.DefWindowProcW.restype = ctypes.c_ssize_t
        self._user32.BeginPaint.argtypes = [
            wintypes.HWND, ctypes.POINTER(_OverlayPaintStruct)
        ]
        self._user32.BeginPaint.restype = wintypes.HDC
        self._user32.EndPaint.argtypes = [
            wintypes.HWND, ctypes.POINTER(_OverlayPaintStruct)
        ]
        self._user32.GetClientRect.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.RECT)
        ]
        self._user32.FillRect.argtypes = [
            wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH
        ]
        self._user32.DrawTextW.argtypes = [
            wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
            ctypes.POINTER(wintypes.RECT), wintypes.UINT,
        ]
        self._user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        self._user32.SetWindowPos.restype = wintypes.BOOL
        self._user32.SetLayeredWindowAttributes.argtypes = [
            wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD
        ]
        self._user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
        self._user32.DestroyWindow.argtypes = [wintypes.HWND]
        self._user32.UnregisterClassW.argtypes = [
            wintypes.LPCWSTR, wintypes.HINSTANCE
        ]
        self._gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        self._gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
        self._gdi32.CreateFontW.restype = wintypes.HFONT
        self._gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        self._gdi32.SelectObject.restype = wintypes.HANDLE
        self._gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
        self._gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
        self._gdi32.DeleteObject.argtypes = [wintypes.HANDLE]

    @staticmethod
    def _rgb(red: int, green: int, blue: int) -> int:
        return red | (green << 8) | (blue << 16)

    def _window_proc(
        self, hwnd: int, message: int, wparam: int, lparam: int
    ) -> int:
        if message == self.WM_NCHITTEST:
            return self.HTTRANSPARENT
        if message == self.WM_ERASEBKGND:
            return 1
        if message == self.WM_PAINT:
            paint = _OverlayPaintStruct()
            dc = self._user32.BeginPaint(hwnd, ctypes.byref(paint))
            rect = wintypes.RECT()
            self._user32.GetClientRect(hwnd, ctypes.byref(rect))
            self._user32.FillRect(dc, ctypes.byref(rect), self._brush)
            old_font = self._gdi32.SelectObject(dc, self._font)
            self._gdi32.SetBkMode(dc, self.TRANSPARENT)
            self._gdi32.SetTextColor(dc, self._rgb(0xEE, 0xF6, 0xFB))
            self._user32.DrawTextW(
                dc, self._text, -1, ctypes.byref(rect),
                self.DT_CENTER | self.DT_VCENTER | self.DT_SINGLELINE,
            )
            self._gdi32.SelectObject(dc, old_font)
            self._user32.EndPaint(hwnd, ctypes.byref(paint))
            return 0
        return int(self._user32.DefWindowProcW(hwnd, message, wparam, lparam))

    def resize(self, width: int, height: int) -> None:
        if self._hwnd:
            self._user32.SetWindowPos(
                self._hwnd, 0, 0, 0, max(1, width), max(1, height),
                self.SWP_NOACTIVATE | self.SWP_SHOWWINDOW,
            )

    def set_alpha(self, alpha: float) -> None:
        if self._hwnd:
            value = max(0, min(255, round(alpha * 255)))
            self._user32.SetLayeredWindowAttributes(
                self._hwnd, 0, value, self.LWA_ALPHA
            )

    def destroy(self) -> None:
        if getattr(self, "_hwnd", 0):
            self._user32.DestroyWindow(self._hwnd)
            self._hwnd = 0
        if getattr(self, "_font", 0):
            self._gdi32.DeleteObject(self._font)
            self._font = 0
        if getattr(self, "_brush", 0):
            self._gdi32.DeleteObject(self._brush)
            self._brush = 0
        if getattr(self, "_class_atom", 0):
            self._user32.UnregisterClassW(self._class_name, self._hinstance)
            self._class_atom = 0


if TkinterDnD is not None:
    DndRootMixin = TkinterDnD.DnDWrapper
else:
    class DndRootMixin:
        pass


class FlipbookApp(tk.Tk, DndRootMixin):
    def __init__(self) -> None:
        super().__init__()
        dnd_enabled = False
        if TkinterDnD is not None:
            try:
                TkinterDnD.require(self)
                dnd_enabled = True
            except (RuntimeError, tk.TclError):
                # Browsing and generation remain available when TkDnD's native
                # runtime is absent or cannot be loaded in an older install.
                pass
        self.title("圖片序列／影片轉 Flipbook")
        self.geometry("960x760")
        self.minsize(900, 640)

        self.theme_var = tk.StringVar(value=THEME_DARK)
        self.source_var = tk.StringVar()
        self.source_type_var = tk.StringVar(value=SOURCE_TYPE_LABELS[SOURCE_IMAGE_FILE])
        self.output_var = tk.StringVar()
        self.cols_var = tk.IntVar(value=8)
        self.rows_var = tk.IntVar(value=8)
        self.size_var = tk.IntVar(value=256)
        self.mode_var = tk.StringVar(value="RGBA（透明）")
        self.fill_empty_var = tk.BooleanVar(value=False)
        self.video_start_var = tk.StringVar(value="0")
        self.video_end_var = tk.StringVar()
        self.fit_var = tk.StringVar(value="延伸空白畫布至正方形")
        self.video_fit_var = self.fit_var
        self.count_var = tk.StringVar(value="請選擇序列中的一張圖片")
        self.capacity_var = tk.StringVar(value="目前設定總網格數：8 × 8 = 64 格")
        self.full_size_var = tk.StringVar(value="完整尺寸：2048 × 2048 pixel")
        self.detail_var = tk.StringVar(value="完整保留 Alpha 透明去背通道背景輸出。")
        self.fit_detail_var = tk.StringVar(
            value=FIT_DESCRIPTIONS["延伸空白畫布至正方形"]
        )
        self.status_var = tk.StringVar(value="就緒")
        self.progress_var = tk.IntVar(value=0)
        self.progress_text_var = tk.StringVar(value="0%")
        self.detail_canvas: tk.Canvas | None = None
        self.detail_text_id: int | None = None
        self.fit_detail_canvas: tk.Canvas | None = None
        self.fit_detail_text_id: int | None = None
        self.theme_toggle_canvas: tk.Canvas | None = None
        self._theme_after_id: str | None = None
        self._theme_knob_x = 9.0
        self.output_folder_button: ttk.Button | None = None
        self._last_output_path: Path | None = None
        self._busy = False
        self._source_count = 0
        self._video_metadata: dict[str, object] | None = None
        self._probe_id = 0
        self._dnd_enabled = dnd_enabled
        self._drag_valid = False
        self._drag_rejected = False
        self._drop_cache_data: tuple[str, ...] = ()
        self._drop_cache_result: tuple[Path, str] | None = None
        self._overlay: Win32DropOverlay | None = None
        self._overlay_alpha = 0.0
        self._overlay_target = 0.0
        self._overlay_ready = False
        self._overlay_after_id: str | None = None
        self._overlay_prime_after_id: str | None = None
        self._overlay_sync_after_id: str | None = None
        self._overlay_config_bind_id: str | None = None
        self._leave_after_id: str | None = None
        self._shake_after_id: str | None = None
        self._shake_queue_id: str | None = None
        self._shake_origin: tuple[int, int] | None = None
        self._closing = False

        self._configure_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        if self._dnd_enabled:
            try:
                # Keep one stable OLE target (the root). The visual overlay is
                # an input-transparent child HWND, never a second Tk toplevel.
                self._overlay = self._create_overlay()
                self._setup_drag_and_drop()
            except Exception as exc:
                self._record_dnd_error("setup", exc)
                self._dnd_enabled = False
                if self._overlay is not None:
                    self._overlay.destroy()
                    self._overlay = None
        self.after_idle(self._fit_initial_window)
        for variable in (
            self.cols_var, self.rows_var, self.size_var,
            self.video_start_var, self.video_end_var,
        ):
            variable.trace_add("write", self._settings_changed)
        self.mode_var.trace_add("write", self._mode_changed)
        self.fit_var.trace_add("write", self._fit_changed)

    def _configure_style(self) -> None:
        self._style = ttk.Style(self)
        self._style.theme_use("clam")
        self._font_family = "Microsoft JhengHei UI"

        # Large stretched images made live window resizing expensive. Sections
        # now use a lightweight borderless layout; rounded images are limited to
        # the small input controls where their redraw cost is negligible.
        self._style.layout("Section.TLabelframe", [
            ("Labelframe.padding", {"sticky": "nsew"}),
        ])

        # Extra transparent space on the right keeps the arrow away from the edge.
        self._combo_arrow_image = tk.PhotoImage(master=self, width=23, height=11)
        self._style.element_create(
            "FlatCombo.arrow", "image", self._combo_arrow_image, sticky="e"
        )
        self._style.layout("TEntry", [
            ("Entry.padding", {"sticky": "nsew", "children": [
                ("Entry.textarea", {"sticky": "nsew"}),
            ]}),
        ])
        self._style.layout("TSpinbox", [
            ("Spinbox.padding", {"sticky": "nsew", "children": [
                ("Spinbox.textarea", {"sticky": "nsew"}),
            ]}),
        ])
        self._style.layout("TCombobox", [
            ("FlatCombo.arrow", {"side": "right", "sticky": "e"}),
            ("Combobox.padding", {"sticky": "nsew", "children": [
                ("Combobox.textarea", {"sticky": "nsew"}),
            ]}),
        ])
        self._apply_theme_styles(THEME_PALETTES[self.theme_var.get()])

    def _apply_theme_styles(self, palette: dict[str, str]) -> None:
        self._palette = palette
        style = self._style
        family = self._font_family
        base = (family, 10)
        field = palette["input_bg"]
        text = palette["normal_text"]
        input_text = palette["input_text"]
        panel = palette["section_bg"]
        bg = palette["window_bg"]

        self.configure(bg=bg)
        self._combo_arrow_image.blank()
        for y, half_width in enumerate((5, 4, 3, 2, 1)):
            left = 8 - half_width
            right = 9 + half_width
            self._combo_arrow_image.put(
                palette["arrow"], to=(left, y + 3, right, y + 4)
            )

        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("PanelFlat.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground=text, font=base)
        style.configure(
            "Title.TLabel", background=bg, foreground=palette["heading_text"],
            font=(family, 22, "bold"),
        )
        style.configure(
            "Muted.TLabel", background=bg, foreground=palette["secondary_text"],
            font=base,
        )
        style.configure("Panel.TLabel", background=panel, foreground=text, font=base)
        style.configure(
            "Hint.Panel.TLabel", background=panel,
            foreground=palette["helper_text"], font=(family, 9),
        )
        style.configure(
            "Section.TLabelframe", background=bg, foreground=text, borderwidth=0
        )
        style.configure(
            "Section.TLabelframe.Label", background=bg,
            foreground=palette["heading_text"], font=(family, 16, "bold"),
        )
        style.configure(
            "InfoTitle.Panel.TLabel", background=panel,
            foreground=palette["heading_text"], font=(family, 10, "bold"),
        )
        style.configure(
            "WarningIcon.TLabel", background=palette["warning_bg"],
            foreground=palette["button_text"], padding=(6, 1),
            font=(family, 9, "bold"),
        )
        style.configure(
            "WarningText.TLabel", background=panel,
            foreground=palette["error_text"], font=(family, 9),
        )
        style.configure(
            "PowerOfTwoWarning.TLabel", background=panel,
            foreground=palette["error_text"], font=(family, 9, "bold"),
        )

        for button_style, vertical_padding in (
            ("TButton", 7), ("Browse.TButton", 7),
            ("SecondaryAction.TButton", 13),
        ):
            style.configure(
                button_style,
                background=palette["secondary_button"], foreground=text,
                bordercolor=palette["secondary_button"],
                lightcolor=palette["secondary_button"],
                darkcolor=palette["secondary_button"], relief="flat",
                borderwidth=0, padding=(12, vertical_padding), font=base,
            )
            style.map(
                button_style,
                background=[
                    ("disabled", palette["disabled_bg"]),
                    ("pressed", palette["secondary_button_pressed"]),
                    ("active", palette["secondary_button_hover"]),
                ],
                foreground=[("disabled", palette["disabled_text"])],
            )
        style.configure(
            "Primary.TButton", background=palette["primary_button"],
            foreground=palette["button_text"],
            bordercolor=palette["primary_button"],
            lightcolor=palette["primary_button"],
            darkcolor=palette["primary_button"], relief="flat", borderwidth=0,
            padding=(14, 12), font=(family, 11, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("disabled", palette["disabled_bg"]),
                ("pressed", palette["primary_button_pressed"]),
                ("active", palette["primary_button_hover"]),
            ],
            foreground=[("disabled", palette["disabled_text"])],
        )

        for field_style in ("TEntry", "TSpinbox", "TCombobox"):
            style.configure(
                field_style, fieldbackground=field, foreground=input_text,
                insertcolor=input_text, background=field, bordercolor=field,
                lightcolor=field, darkcolor=field, relief="flat", borderwidth=0,
                padding=(10, 7), font=base,
            )
            style.map(
                field_style,
                fieldbackground=[
                    ("disabled", palette["disabled_bg"]),
                    ("focus", palette["input_focus"]),
                    ("active", palette["input_hover"]),
                    ("!focus", field),
                ],
                background=[
                    ("disabled", palette["disabled_bg"]),
                    ("focus", palette["input_focus"]),
                    ("active", palette["input_hover"]),
                    ("!focus", field),
                ],
                foreground=[
                    ("disabled", palette["disabled_text"]),
                    ("!disabled", input_text),
                ],
            )

        self.option_add("*TCombobox*Listbox.background", field)
        self.option_add("*TCombobox*Listbox.foreground", input_text)
        self.option_add(
            "*TCombobox*Listbox.selectBackground", palette["primary_button"]
        )
        self.option_add(
            "*TCombobox*Listbox.selectForeground", palette["button_text"]
        )
        self.option_add("*TCombobox*Listbox.font", base)
        style.configure(
            "Horizontal.TProgressbar", background=palette["progress_fill"],
            troughcolor=palette["progress_track"],
            bordercolor=palette["progress_track"],
            lightcolor=palette["progress_fill"],
            darkcolor=palette["progress_fill"], relief="flat",
            borderwidth=0, thickness=13,
        )
        style.configure(
            "TCheckbutton", background=panel, foreground=text, font=(family, 9),
            indicatorbackground=field, indicatorforeground=palette["primary_button"],
            bordercolor=field, lightcolor=field, darkcolor=field,
        )
        style.map(
            "TCheckbutton", background=[("active", panel)],
            foreground=[("disabled", palette["disabled_text"])],
            indicatorbackground=[
                ("disabled", palette["disabled_bg"]),
                ("active", palette["input_hover"]),
            ],
        )

        for canvas, title_id, text_id in (
            (
                self.detail_canvas,
                getattr(self, "detail_title_id", None),
                self.detail_text_id,
            ),
            (
                self.fit_detail_canvas,
                getattr(self, "fit_detail_title_id", None),
                self.fit_detail_text_id,
            ),
        ):
            if canvas is not None:
                canvas.configure(bg=panel)
                if title_id is not None:
                    canvas.itemconfigure(title_id, fill=palette["heading_text"])
                if text_id is not None:
                    canvas.itemconfigure(text_id, fill=palette["helper_text"])
        self._refresh_combobox_popdown_colors()
        self._update_theme_toggle_colors()

    def _refresh_combobox_popdown_colors(self) -> None:
        if not hasattr(self, "source_type_combo"):
            return
        palette = self._palette
        for combo in (self.source_type_combo, self.mode_combo, self.fit_combo):
            try:
                popdown = self.tk.call(
                    "ttk::combobox::PopdownWindow", str(combo)
                )
                listbox = f"{popdown}.f.l"
                self.tk.call(
                    listbox, "configure",
                    "-background", palette["input_bg"],
                    "-foreground", palette["input_text"],
                    "-selectbackground", palette["primary_button"],
                    "-selectforeground", palette["button_text"],
                )
            except tk.TclError:
                pass

    def _build_theme_toggle(self, parent: ttk.Frame) -> None:
        palette = self._palette
        self.theme_toggle_canvas = tk.Canvas(
            parent, width=34, height=20, bg=palette["window_bg"],
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self.theme_toggle_canvas.grid(
            row=0, column=0, rowspan=2, sticky="ne", pady=(1, 0)
        )
        track = palette["primary_button"]
        self._theme_track_ids = (
            self.theme_toggle_canvas.create_oval(
                2, 3, 16, 17, fill=track, outline=track
            ),
            self.theme_toggle_canvas.create_rectangle(
                9, 3, 25, 17, fill=track, outline=track
            ),
            self.theme_toggle_canvas.create_oval(
                18, 3, 32, 17, fill=track, outline=track
            ),
        )
        self._theme_knob_id = self.theme_toggle_canvas.create_oval(
            4, 5, 14, 15, fill=palette["button_text"],
            outline=palette["button_text"],
        )
        self.theme_toggle_canvas.bind("<Button-1>", self._toggle_theme)
        self.theme_toggle_canvas.bind("<Return>", self._toggle_theme)

    def _update_theme_toggle_colors(self) -> None:
        if self.theme_toggle_canvas is None:
            return
        palette = self._palette
        self.theme_toggle_canvas.configure(bg=palette["window_bg"])
        for item_id in self._theme_track_ids:
            self.theme_toggle_canvas.itemconfigure(
                item_id, fill=palette["primary_button"],
                outline=palette["primary_button"],
            )
        self.theme_toggle_canvas.itemconfigure(
            self._theme_knob_id, fill=palette["button_text"],
            outline=palette["button_text"],
        )

    def _set_theme_knob_position(self, center_x: float) -> None:
        self._theme_knob_x = center_x
        if self.theme_toggle_canvas is not None:
            self.theme_toggle_canvas.coords(
                self._theme_knob_id,
                center_x - 5, 5, center_x + 5, 15,
            )

    def _set_theme(self, theme: str, animate: bool = True) -> None:
        if theme not in THEME_PALETTES:
            raise ValueError(f"Unknown theme: {theme}")
        if self._theme_after_id is not None:
            self.after_cancel(self._theme_after_id)
            self._theme_after_id = None
        self.theme_var.set(theme)
        self._apply_theme_styles(THEME_PALETTES[theme])
        target_x = 25.0 if theme == THEME_LIGHT else 9.0
        if not animate or self.theme_toggle_canvas is None:
            self._set_theme_knob_position(target_x)
            return

        start_x = self._theme_knob_x
        started = time.perf_counter()
        duration_ms = 140

        def step() -> None:
            if self._closing or self.theme_toggle_canvas is None:
                self._theme_after_id = None
                return
            elapsed = (time.perf_counter() - started) * 1000
            progress = min(1.0, elapsed / duration_ms)
            eased = 1 - (1 - progress) ** 3
            self._set_theme_knob_position(
                start_x + (target_x - start_x) * eased
            )
            if progress < 1:
                self._theme_after_id = self.after(16, step)
            else:
                self._theme_after_id = None

        step()

    def _toggle_theme(self, _event: object | None = None) -> str:
        target = THEME_LIGHT if self.theme_var.get() == THEME_DARK else THEME_DARK
        self._set_theme(target, animate=True)
        return "break"
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
        if self._overlay is not None and self._overlay_prime_after_id is None:
            # Let Windows map the final root geometry before creating the
            # always-mapped alpha-zero overlay. This still happens long before
            # a user can begin a drag, but avoids priming at Tk's temporary 1x1.
            self._overlay_prime_after_id = self.after(
                OVERLAY_PRIME_DELAY_MS, self._prime_overlay
            )

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=(20, 14, 20, 12))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        ttk.Label(main, text="Flipbook Texture Sheet Generator", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(main, text="將圖片序列或影片轉成固定網格貼圖", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 30))
        self._build_theme_toggle(main)

        source_section = self._section(main, "來源與輸出", 2)
        source_section.columnconfigure(1, weight=0)
        source_section.columnconfigure(2, weight=1)
        ttk.Label(source_section, text="來源：", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        self.source_type_combo = ttk.Combobox(
            source_section, textvariable=self.source_type_var,
            values=SOURCE_TYPES, state="readonly", width=24,
        )
        self.source_type_combo.grid(
            row=0, column=1, sticky="ew", padx=(0, 10), pady=5
        )
        self.source_type_combo.bind(
            "<<ComboboxSelected>>", self._source_type_changed
        )
        ttk.Entry(source_section, textvariable=self.source_var).grid(row=0, column=2, sticky="ew", pady=5)
        ttk.Button(source_section, text="瀏覽…", command=self._choose_source, width=11, style="Browse.TButton").grid(row=0, column=3, padx=(10, 0), pady=5)

        ttk.Label(source_section, text="儲存位置：", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(source_section, textvariable=self.output_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Button(source_section, text="瀏覽…", command=self._choose_output, width=11, style="Browse.TButton").grid(row=1, column=3, padx=(10, 0), pady=5)
        ttk.Label(source_section, textvariable=self.count_var, style="Hint.Panel.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", pady=(9, 0))

        self.video_options = self._section(main, "時間範圍", 3)
        for column in (1, 3):
            self.video_options.columnconfigure(column, weight=1)
        ttk.Label(self.video_options, text="開始秒數", style="Panel.TLabel").grid(row=0, column=0, padx=(0, 9), pady=2)
        ttk.Spinbox(self.video_options, from_=0, to=999999, increment=0.1, textvariable=self.video_start_var).grid(row=0, column=1, sticky="ew", padx=(0, 20), pady=2)
        ttk.Label(self.video_options, text="結束秒數", style="Panel.TLabel").grid(row=0, column=2, padx=(0, 9), pady=2)
        ttk.Spinbox(self.video_options, from_=0, to=999999, increment=0.1, textvariable=self.video_end_var).grid(row=0, column=3, sticky="ew", pady=2)
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
        self.mode_combo = ttk.Combobox(
            settings, textvariable=self.mode_var, values=tuple(MODE_LABELS),
            state="readonly", width=22,
        )
        self.mode_combo.grid(row=2, column=1, sticky="ew", padx=(0, 24), pady=5)
        self.fit_label = ttk.Label(settings, text="畫面適配", style="Panel.TLabel")
        self.fit_label.grid(row=2, column=2, sticky="w", padx=(0, 12), pady=5)
        self.fit_combo = ttk.Combobox(
            settings, textvariable=self.fit_var, values=tuple(FIT_LABELS),
            state="readonly", width=22,
        )
        self.fit_combo.grid(row=2, column=3, sticky="ew", pady=5)

        self.capacity_label = ttk.Label(
            settings, textvariable=self.capacity_var,
            style="Hint.Panel.TLabel",
        )
        self.capacity_label.grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(12, 6)
        )
        self.full_size_label = ttk.Label(
            settings, textvariable=self.full_size_var,
            style="Hint.Panel.TLabel",
        )
        self.full_size_label.grid(
            row=3, column=2, sticky="w", pady=(12, 6)
        )
        self.power_of_two_warning = ttk.Label(
            settings,
            text="! 建議圖片寬 × 高尺寸皆為 2 的次方",
            style="PowerOfTwoWarning.TLabel",
        )
        self.capacity_warning_line = ttk.Frame(
            settings, style="PanelFlat.TFrame"
        )
        self.capacity_warning_line.grid(
            row=4, column=0, columnspan=4, sticky="ew", pady=(4, 0)
        )
        self.capacity_warning_line.grid_remove()
        self.warning_icon = ttk.Label(
            self.capacity_warning_line, text="!", style="WarningIcon.TLabel"
        )
        self.warning_icon.pack(side="left", padx=(0, 5))
        self.warning_text = ttk.Label(
            self.capacity_warning_line,
            text="需求的圖片總格數不足，多的格數會被刪掉",
            style="WarningText.TLabel",
        )
        self.warning_text.pack(side="left")
        self.fill_check = ttk.Checkbutton(settings, text="用最後一格補齊剩餘空格", variable=self.fill_empty_var)
        self.fill_check.grid(row=5, column=0, columnspan=4, sticky="w", pady=(0, 9))
        self.fill_check.grid_remove()

        self.detail_canvas = tk.Canvas(
            settings, width=420, height=90, bg=self._palette["section_bg"],
            highlightthickness=0, bd=0,
        )
        self.detail_canvas.grid(row=6, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=(8, 0))
        self.detail_title_id = self.detail_canvas.create_text(
            0, 14, text="ⓘ  通道模式說明", anchor="nw",
            fill=self._palette["heading_text"],
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.detail_text_id = self.detail_canvas.create_text(
            0, 40, text=self.detail_var.get(), anchor="nw",
            fill=self._palette["helper_text"],
            font=("Microsoft JhengHei UI", 9), width=416,
        )
        self.fit_detail_canvas = tk.Canvas(
            settings, width=420, height=90, bg=self._palette["section_bg"],
            highlightthickness=0, bd=0,
        )
        self.fit_detail_canvas.grid(
            row=6, column=2, columnspan=2, sticky="ew", pady=(8, 0)
        )
        self.fit_detail_title_id = self.fit_detail_canvas.create_text(
            0, 14, text="ⓘ  畫面適配說明", anchor="nw",
            fill=self._palette["heading_text"],
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.fit_detail_text_id = self.fit_detail_canvas.create_text(
            0, 40, text=self.fit_detail_var.get(), anchor="nw",
            fill=self._palette["helper_text"],
            font=("Microsoft JhengHei UI", 9), width=416,
        )
        self.detail_canvas.bind(
            "<Configure>",
            lambda event: self._resize_detail_text(
                self.detail_canvas, self.detail_text_id, event.width
            ),
        )
        self.fit_detail_canvas.bind(
            "<Configure>",
            lambda event: self._resize_detail_text(
                self.fit_detail_canvas, self.fit_detail_text_id, event.width
            ),
        )

        action = self._section(main, "執行與處理狀態", 5)
        action.columnconfigure(0, weight=1)
        action.columnconfigure(1, weight=0)
        progress_line = ttk.Frame(action, style="PanelFlat.TFrame")
        progress_line.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        progress_line.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(
            progress_line, mode="determinate", maximum=100,
            variable=self.progress_var,
        )
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            progress_line, textvariable=self.progress_text_var,
            style="Hint.Panel.TLabel", width=5, anchor="e",
        ).grid(row=0, column=1, padx=(10, 0))
        ttk.Label(action, textvariable=self.status_var, style="Hint.Panel.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.run_button = ttk.Button(action, text="▦  執行生成 Flipbook 網格圖", style="Primary.TButton", command=self._start)
        self.run_button.grid(row=2, column=0, sticky="ew", padx=(0, 10))
        self.output_folder_button = ttk.Button(
            action, text="開啟輸出資料夾", command=self._open_last_output_folder,
            state="disabled", style="SecondaryAction.TButton", width=12,
        )
        self.output_folder_button.grid(row=2, column=1, sticky="ew")

    def _choose_source(self) -> None:
        source_kind = self._current_source_kind()
        options: dict[str, object] = {"parent": self}
        initial_directory = source_dialog_initial_directory(self.source_var.get())
        if initial_directory is not None:
            options["initialdir"] = initial_directory

        if source_kind == SOURCE_IMAGE_FILE:
            patterns = " ".join(f"*{extension}" for extension in sorted(VALID_EXTENSIONS))
            selected = filedialog.askopenfilename(
                title="選擇序列中的一張圖片",
                filetypes=[
                    ("支援的圖片", patterns),
                    ("PNG", "*.png"),
                    ("JPEG", "*.jpg *.jpeg"),
                    ("TIFF", "*.tif *.tiff"),
                    ("EXR", "*.exr"),
                ],
                **options,
            )
        elif source_kind == SOURCE_IMAGE_FOLDER:
            selected = filedialog.askdirectory(
                title="選擇圖片資料夾", mustexist=True, **options
            )
        else:
            selected = filedialog.askopenfilename(
                title="選擇 MP4 或 MOV 影片",
                filetypes=[("支援的影片", "*.mp4 *.mov"), ("MP4", "*.mp4"), ("MOV", "*.mov")],
                **options,
            )
        if not selected:
            return

        selected_path = Path(selected)
        actual_kind = classify_source_path(selected_path)
        if actual_kind != source_kind:
            messages = {
                SOURCE_IMAGE_FILE: "請選擇一張支援的圖片檔。",
                SOURCE_IMAGE_FOLDER: "這個資料夾第一層沒有支援的圖片，請選擇其他資料夾。",
                SOURCE_VIDEO: "請選擇存在的 MP4 或 MOV 影片。",
            }
            messagebox.showwarning("不支援的來源", messages[source_kind], parent=self)
            return
        self._apply_source(selected_path, source_kind, reset_output=False)

    def _current_source_kind(self) -> str:
        return SOURCE_TYPE_BY_LABEL.get(self.source_type_var.get(), SOURCE_IMAGE_FILE)

    def _source_type_changed(self, _event: object | None = None) -> None:
        self._probe_id += 1
        self.source_var.set("")
        self._source_count = 0
        self._video_metadata = None
        self.video_start_var.set("0")
        self.video_end_var.set("")
        if self._current_source_kind() != SOURCE_VIDEO:
            self.video_options.grid_remove()
            if self._current_source_kind() == SOURCE_IMAGE_FILE:
                self.count_var.set("請選擇序列中的一張圖片")
            else:
                self.count_var.set("請選擇包含序列圖片的資料夾")
        else:
            self.video_options.grid()
            self.count_var.set("請選擇 MP4 或 MOV 影片")
        self._update_capacity()

    def _set_source_type(self, source_kind: str) -> None:
        target = SOURCE_TYPE_LABELS[source_kind]
        if self.source_type_var.get() != target:
            self.source_type_var.set(target)
        self._probe_id += 1
        self._source_count = 0
        self._video_metadata = None
        self.video_start_var.set("0")
        self.video_end_var.set("")
        if source_kind != SOURCE_VIDEO:
            self.video_options.grid_remove()
        else:
            self.video_options.grid()

    def _apply_source(self, source: Path, source_kind: str, reset_output: bool = True) -> None:
        source = source.expanduser().resolve()
        self._set_source_type(source_kind)
        self.source_var.set(str(source))
        if reset_output or not self.output_var.get().strip():
            output_folder = source if source.is_dir() else source.parent
            self.output_var.set(str(output_folder / "flipbook.png"))
        self._refresh_count()

    def _setup_drag_and_drop(self) -> None:
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<DropEnter>>", self._guard_dnd("enter", self._on_drop_enter))
        self.dnd_bind("<<DropPosition>>", self._guard_dnd("position", self._on_drop_position))
        self.dnd_bind("<<DropLeave>>", self._guard_dnd("leave", self._on_drop_leave))
        self.dnd_bind("<<Drop>>", self._guard_dnd("drop", self._on_drop))

    def _guard_dnd(self, name: str, handler: object) -> object:
        def guarded(event: object) -> str:
            try:
                return handler(event)
            except Exception as exc:
                self._record_dnd_error(name, exc)
                self._drag_valid = False
                self._drag_rejected = True
                self._hide_overlay(animated=True, duration_ms=OVERLAY_REJECT_FADE_MS)
                self._queue_shake()
                return REFUSE_DROP
        return guarded

    def _record_dnd_error(self, phase: str, error: Exception) -> None:
        try:
            log_path = Path(tempfile.gettempdir()) / "FlipbookGenerator-dnd.log"
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {phase}: {error!r}\n")
                log.write(traceback.format_exc())
        except OSError:
            pass
        if hasattr(self, "status_var"):
            self.status_var.set("拖放處理失敗；請使用瀏覽按鈕，或回報暫存目錄內的拖放記錄")

    def _drop_item(self, data: object) -> tuple[Path, str] | None:
        try:
            if isinstance(data, (tuple, list)):
                items = tuple(str(item) for item in data)
            elif data:
                items = tuple(str(item) for item in self.tk.splitlist(str(data)))
            else:
                items = ()
        except (TypeError, ValueError, tk.TclError):
            return None
        if items == self._drop_cache_data:
            return self._drop_cache_result
        if len(items) != 1:
            result = None
        else:
            path = Path(items[0])
            source_kind = classify_source_path(path)
            result = (path.resolve(), source_kind) if source_kind else None
        self._drop_cache_data = items
        self._drop_cache_result = result
        return result

    def _on_drop_enter(self, event: object) -> str:
        if self._leave_after_id is not None:
            self.after_cancel(self._leave_after_id)
            self._leave_after_id = None
        data = getattr(event, "data", "")
        accepted = self._drop_item(data) if data else None
        # This window is registered only for DND_FILES. TkDnD on Windows does
        # not expose CF_HDROP paths until Drop, so an enter event with no data
        # is itself sufficient to show the provisional file-drag preview.
        provisional_file_drag = not data
        if provisional_file_drag:
            self._drag_valid = True
            self._drag_rejected = False
            self._show_overlay()
            return COPY
        self._drag_valid = accepted is not None
        if accepted:
            self._drag_rejected = False
            self._show_overlay()
            return COPY
        self._hide_overlay(animated=False)
        if not self._drag_rejected:
            self._drag_rejected = True
            self._queue_shake()
        return REFUSE_DROP

    def _on_drop_position(self, event: object) -> str:
        data = getattr(event, "data", "")
        accepted = self._drop_item(data) if data else None
        if not data:
            self._drag_valid = True
            self._drag_rejected = False
            self._show_overlay()
            return COPY
        if accepted:
            self._drag_valid = True
            self._drag_rejected = False
            self._show_overlay()
            return COPY
        self._drag_valid = False
        self._hide_overlay(animated=False)
        if not self._drag_rejected:
            self._drag_rejected = True
            self._queue_shake()
        return REFUSE_DROP

    def _on_drop_leave(self, _event: object | None = None) -> str:
        if self._leave_after_id is not None:
            self.after_cancel(self._leave_after_id)
        self._leave_after_id = self.after(60, self._finish_drag_leave)
        return REFUSE_DROP

    def _finish_drag_leave(self) -> None:
        self._leave_after_id = None
        self._drag_valid = False
        self._drag_rejected = False
        self._drop_cache_data = ()
        self._drop_cache_result = None
        self._hide_overlay(animated=True)

    def _on_drop(self, event: object) -> str:
        if self._leave_after_id is not None:
            self.after_cancel(self._leave_after_id)
            self._leave_after_id = None
        accepted = self._drop_item(getattr(event, "data", ""))
        self._drag_valid = False
        self._drag_rejected = False
        self._drop_cache_data = ()
        self._drop_cache_result = None
        if accepted is None:
            self._hide_overlay(animated=True, duration_ms=OVERLAY_REJECT_FADE_MS)
            self._queue_shake()
            return REFUSE_DROP
        source, source_kind = accepted
        self._apply_source(source, source_kind, reset_output=True)
        self._hide_overlay(animated=True)
        return COPY

    def _create_overlay(self) -> Win32DropOverlay:
        return Win32DropOverlay(self)

    def _sync_overlay(self, _event: object | None = None) -> None:
        if self._overlay is None:
            return
        self._overlay.resize(
            max(1, self.winfo_width()), max(1, self.winfo_height())
        )

    def _schedule_overlay_sync(self, _event: object | None = None) -> None:
        if self._closing or self._overlay is None:
            return
        if self._overlay_sync_after_id is not None:
            self.after_cancel(self._overlay_sync_after_id)
        self._overlay_sync_after_id = self.after(32, self._finish_overlay_sync)

    def _finish_overlay_sync(self) -> None:
        self._overlay_sync_after_id = None
        if not self._closing:
            self._sync_overlay()

    def _prime_overlay(self) -> None:
        """Map one alpha-zero overlay before any Windows OLE drag callback."""
        self._overlay_prime_after_id = None
        if self._closing or self._overlay is None or self._overlay_ready:
            return
        self._sync_overlay()
        self._overlay.set_alpha(0.0)
        self._overlay_ready = True
        if self._overlay_config_bind_id is None:
            self._overlay_config_bind_id = self.bind(
                "<Configure>", self._schedule_overlay_sync, add="+"
            )

    def _show_overlay(self) -> None:
        if self._overlay is None or not self._overlay_ready:
            return
        if self._overlay_target != OVERLAY_ALPHA:
            self._animate_overlay(OVERLAY_ALPHA, OVERLAY_FADE_IN_MS)

    def _hide_overlay(
        self, animated: bool, duration_ms: int = OVERLAY_FADE_OUT_MS
    ) -> None:
        if self._overlay is None:
            return
        if animated and self._overlay_ready and self._overlay_alpha > 0:
            self._animate_overlay(0.0, duration_ms)
        else:
            self._finish_overlay_hide()

    def _animate_overlay(self, target: float, duration_ms: int) -> None:
        if self._overlay is None:
            return
        if self._overlay_after_id is not None:
            self.after_cancel(self._overlay_after_id)
            self._overlay_after_id = None
        self._overlay_target = target
        start_alpha = self._overlay_alpha
        started = time.perf_counter()

        def step() -> None:
            if self._closing or self._overlay is None:
                return
            elapsed = (time.perf_counter() - started) * 1000
            progress = min(1.0, elapsed / max(1, duration_ms))
            eased = 1 - (1 - progress) ** 3 if target > start_alpha else progress
            self._overlay_alpha = start_alpha + (target - start_alpha) * eased
            self._overlay.set_alpha(self._overlay_alpha)
            if progress < 1:
                self._overlay_after_id = self.after(OVERLAY_FRAME_MS, step)
            else:
                self._overlay_after_id = None
                if target <= 0:
                    self._finish_overlay_hide()

        step()

    def _finish_overlay_hide(self) -> None:
        if self._overlay_after_id is not None:
            self.after_cancel(self._overlay_after_id)
            self._overlay_after_id = None
        self._overlay_alpha = 0.0
        self._overlay_target = 0.0
        if self._overlay is not None:
            self._overlay.set_alpha(0.0)

    def _start_shake(self) -> None:
        self._shake_queue_id = None
        if self._shake_after_id is not None or self.state() != "normal":
            return
        origin_x, origin_y = self.winfo_x(), self.winfo_y()
        self._shake_origin = (origin_x, origin_y)
        offsets = (-8, 8, -8, 8, -6, 6, -3, 3, 0)

        def step(index: int = 0) -> None:
            if self._closing or self._shake_origin is None:
                return
            x, y = self._shake_origin
            self.geometry(f"+{x + offsets[index]}+{y}")
            if index + 1 < len(offsets):
                self._shake_after_id = self.after(30, step, index + 1)
            else:
                self.geometry(f"+{x}+{y}")
                self._shake_after_id = None
                self._shake_origin = None

        step()

    def _queue_shake(self) -> None:
        if self._shake_queue_id is None and self._shake_after_id is None:
            self._shake_queue_id = self.after_idle(self._start_shake)

    def _close(self) -> None:
        self._closing = True
        for callback_id in (
            self._theme_after_id,
            self._overlay_after_id, self._overlay_prime_after_id,
            self._overlay_sync_after_id, self._leave_after_id,
            self._shake_after_id, self._shake_queue_id,
        ):
            if callback_id is not None:
                try:
                    self.after_cancel(callback_id)
                except tk.TclError:
                    pass
        if self._shake_origin is not None:
            x, y = self._shake_origin
            self.geometry(f"+{x}+{y}")
        if self._overlay is not None:
            self._overlay.destroy()
        self.destroy()

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
        if self._current_source_kind() == SOURCE_VIDEO:
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
            source = Path(self.source_var.get())
            if source.is_file():
                self.count_var.set(f"已由選定圖片辨識出 {count} 張序列圖片")
            else:
                self.count_var.set(f"來源目錄內共有 {count} 張支援的圖片")
        except (OSError, ValueError):
            self._source_count = 0
            self.count_var.set("圖片來源無法讀取")
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
        if self._current_source_kind() == SOURCE_VIDEO:
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

    def _fit_changed(self, *_args: object) -> None:
        text = FIT_DESCRIPTIONS.get(self.fit_var.get(), "")
        self.fit_detail_var.set(text)
        if self.fit_detail_canvas is not None and self.fit_detail_text_id is not None:
            self.fit_detail_canvas.itemconfigure(self.fit_detail_text_id, text=text)

    @staticmethod
    def _resize_detail_text(
        canvas: tk.Canvas | None, text_id: int | None, width: int
    ) -> None:
        if canvas is not None and text_id is not None:
            canvas.itemconfigure(text_id, width=max(80, width - 4))

    def _update_capacity(self) -> None:
        try:
            cols, rows, size = (
                self.cols_var.get(), self.rows_var.get(), self.size_var.get()
            )
            capacity = cols * rows
            full_width, full_height, uses_power_of_two_dimensions = (
                calculate_full_size(cols, rows, size)
            )
            self.capacity_var.set(f"目前設定總網格數：{cols} × {rows} = {capacity} 格（左到右、上到下）")
            self.full_size_var.set(
                f"完整尺寸：{full_width} × {full_height} pixel"
            )
            if uses_power_of_two_dimensions:
                self.power_of_two_warning.grid_remove()
            elif not self.power_of_two_warning.winfo_manager():
                self.power_of_two_warning.grid(
                    row=3, column=3, sticky="e", padx=(16, 0), pady=(12, 6)
                )
            if self._source_count > capacity:
                if self._current_source_kind() != SOURCE_VIDEO:
                    self.warning_text.configure(text="需求的圖片總格數不足，多的格數會被刪掉")
                else:
                    self.warning_text.configure(text="影片影格多於網格容量，將平均抽取整段範圍")
                if not self.capacity_warning_line.winfo_manager():
                    self.capacity_warning_line.grid()
                self.fill_check.grid_remove()
                self.fill_empty_var.set(False)
            else:
                self.capacity_warning_line.grid_remove()
                if self._source_count > 0 and capacity > self._source_count:
                    self.fill_check.grid()
                else:
                    self.fill_check.grid_remove()
                    self.fill_empty_var.set(False)
        except tk.TclError:
            self.capacity_var.set("欄數與列數必須是整數")
            self.full_size_var.set("完整尺寸：—")
            self.power_of_two_warning.grid_remove()

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

        is_video = self._current_source_kind() == SOURCE_VIDEO
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
        self._set_progress(0)
        self.status_var.set("正在產生 Flipbook，請稍候……")
        self._last_output_path = None
        if self.output_folder_button is not None:
            self.output_folder_button.configure(state="disabled")
        mode = MODE_LABELS[self.mode_var.get()]
        fill_empty = self.fill_empty_var.get()
        threading.Thread(
            target=self._generate,
            args=(source, output, cols, rows, size, mode, fill_empty,
                  is_video, start, end, FIT_LABELS[self.fit_var.get()]),
            daemon=True,
        ).start()

    def _generate(self, source: str, output: str, cols: int, rows: int,
                  size: int, mode: str, fill_empty: bool, is_video: bool,
                  start: float, end: float | None, frame_fit: str) -> None:
        try:
            if is_video:
                saved_path, count = make_video_flipbook(
                    source, output, cols, rows, size, mode, fill_empty,
                    start, end, frame_fit,
                    progress_callback=self._queue_progress,
                )
            else:
                saved_path, count = make_flipbook(
                    source, output, cols, rows, size, mode, fill_empty,
                    progress_callback=self._queue_progress,
                    image_fit=frame_fit,
                )
        except Exception as exc:
            self.after(0, self._finished_error, str(exc))
        else:
            self.after(0, self._finished_ok, str(saved_path), count)

    def _finish_common(self) -> None:
        self._busy = False
        self._set_progress(0)
        self.run_button.configure(state="normal")

    def _queue_progress(self, percent: int) -> None:
        self.after(0, self._set_progress, percent)

    def _set_progress(self, percent: int | float) -> None:
        value = max(0, min(100, round(float(percent))))
        self.progress_var.set(value)
        self.progress_text_var.set(f"{value}%")

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
