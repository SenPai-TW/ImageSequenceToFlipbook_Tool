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

from flipbook_version import APP_VERSION, APP_VERSION_TAG

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
        make_image_preview,
        make_flipbook,
        make_video_preview,
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

from PIL import Image, ImageDraw, ImageTk


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
WORKSPACE_BREAKPOINT = 1000
PREVIEW_DEBOUNCE_MS = 180
PREVIEW_EDGE = 360
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


def calculate_window_height(
    requested_height: int, screen_height: int, reserved_height: int = 96
) -> int:
    """Clamp the initial window height to the usable vertical screen space."""
    available_height = max(1, screen_height - reserved_height)
    return min(requested_height, available_height)


def client_animations_enabled() -> bool:
    """Respect the Windows preference for non-essential interface animation."""
    if sys.platform != "win32":
        return True
    enabled = wintypes.BOOL()
    try:
        success = ctypes.windll.user32.SystemParametersInfoW(
            0x1042, 0, ctypes.byref(enabled), 0
        )
    except (AttributeError, OSError):
        return True
    return bool(enabled.value) if success else True


THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_PALETTES = {
    THEME_DARK: {
        "window_bg": "#1F2328",
        "section_bg": "#252A30",
        "panel_alt": "#20252A",
        "panel_border": "#343B43",
        "preview_bg": "#15191D",
        "success_text": "#82C7A5",
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
        "scrollbar_track": "#1F2328",
        "scrollbar_thumb": "#3A424A",
        "scrollbar_thumb_hover": "#53606B",
        "scrollbar_thumb_pressed": "#667582",
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
        "section_bg": "#FFFFFF",
        "panel_alt": "#F7F6F3",
        "panel_border": "#D9D7D2",
        "preview_bg": "#E8E7E3",
        "success_text": "#3D8563",
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
        "scrollbar_track": "#F1F0ED",
        "scrollbar_thumb": "#C8C6C1",
        "scrollbar_thumb_hover": "#ABA9A4",
        "scrollbar_thumb_pressed": "#8E8C87",
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
        self.title(f"圖片序列／影片轉 Flipbook {APP_VERSION_TAG}")
        initial_width = min(1180, max(760, self.winfo_screenwidth() - 64))
        initial_height = calculate_window_height(760, self.winfo_screenheight())
        self.geometry(f"{initial_width}x{initial_height}")
        self.minsize(760, 560)

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
        self.preview_title_var = tk.StringVar(value="等待來源")
        self.preview_detail_var = tk.StringVar(value="選擇圖片或影片後會顯示低解析網格預覽")
        self.preview_source_var = tk.StringVar(value="來源  —")
        self.preview_capacity_var = tk.StringVar(value="容量  8 × 8 = 64")
        self.preview_size_var = tk.StringVar(value="輸出  2048 × 2048 px")
        self.preview_mode_var = tk.StringVar(value="RGBA · 延伸空白畫布")
        self.preview_output_var = tk.StringVar(value="尚未選擇輸出位置")
        self.detail_canvas: tk.Canvas | None = None
        self.detail_text_id: int | None = None
        self.fit_detail_canvas: tk.Canvas | None = None
        self.fit_detail_text_id: int | None = None
        self.theme_toggle_canvas: tk.Canvas | None = None
        self.viewport_canvas: tk.Canvas | None = None
        self.viewport_scrollbar: ttk.Scrollbar | None = None
        self.main_frame: ttk.Frame | None = None
        self.workspace_frame: ttk.Frame | None = None
        self.right_panel: ttk.Frame | None = None
        self.preview_canvas: tk.Canvas | None = None
        self.preview_image_id: int | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self._preview_source_image: Image.Image | None = None
        self._preview_after_id: str | None = None
        self._preview_request_id = 0
        self._preview_animation_id: str | None = None
        self._workspace_layout = ""
        self._source_buttons: dict[str, ttk.Button] = {}
        self._animations_enabled = client_animations_enabled()
        self._viewport_window_id: int | None = None
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
            self.video_start_var, self.video_end_var, self.fill_empty_var,
        ):
            variable.trace_add("write", self._settings_changed)
        self.mode_var.trace_add("write", self._mode_changed)
        self.fit_var.trace_add("write", self._fit_changed)
        self.output_var.trace_add("write", self._output_changed)
        self.preview_title_var.trace_add("write", self._preview_text_changed)
        self.preview_detail_var.trace_add("write", self._preview_text_changed)

    def _configure_style(self) -> None:
        self._style = ttk.Style(self)
        self._style.theme_use("clam")
        # Keep Chinese labels on one deliberate Windows UI face instead of
        # relying on per-widget fallback from Segoe UI Variable. The display
        # face is reserved for the English product title.
        self._font_family = "Microsoft JhengHei UI"
        self._display_font_family = "Segoe UI Variable Display"

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
        self._style.layout("Minimal.Vertical.TScrollbar", [
            ("Vertical.Scrollbar.trough", {
                "sticky": "ns",
                "children": [
                    ("Vertical.Scrollbar.thumb", {
                        "expand": "1", "sticky": "nswe",
                    }),
                ],
            }),
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
        style.configure("PanelAlt.TFrame", background=palette["panel_alt"])
        style.configure(
            "SectionAccent.TFrame", background=palette["primary_button"]
        )
        style.configure("Workspace.TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=text, font=base)
        style.configure(
            "Title.TLabel", background=bg, foreground=palette["heading_text"],
            font=(self._display_font_family, 22, "bold"),
        )
        style.configure(
            "Muted.TLabel", background=bg, foreground=palette["secondary_text"],
            font=base,
        )
        style.configure("Panel.TLabel", background=panel, foreground=text, font=base)
        style.configure(
            "PanelStrong.TLabel", background=panel,
            foreground=palette["heading_text"], font=(family, 11, "bold"),
        )
        style.configure(
            "PanelMeta.TLabel", background=panel,
            foreground=palette["secondary_text"], font=(family, 9),
        )
        style.configure(
            "Success.Panel.TLabel", background=panel,
            foreground=palette["success_text"], font=(family, 9, "bold"),
        )
        style.configure(
            "Hint.Panel.TLabel", background=panel,
            foreground=palette["helper_text"], font=(family, 9),
        )
        style.configure(
            "SectionTitle.Panel.TLabel", background=panel,
            foreground=palette["heading_text"], font=(family, 13, "bold"),
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
        style.configure(
            "Minimal.Vertical.TScrollbar",
            background=palette["scrollbar_thumb"],
            troughcolor=palette["scrollbar_track"],
            bordercolor=palette["scrollbar_track"],
            lightcolor=palette["scrollbar_thumb"],
            darkcolor=palette["scrollbar_thumb"],
            relief="flat", borderwidth=0, width=10,
        )
        style.map(
            "Minimal.Vertical.TScrollbar",
            background=[
                ("pressed", palette["scrollbar_thumb_pressed"]),
                ("active", palette["scrollbar_thumb_hover"]),
                ("!active", palette["scrollbar_thumb"]),
            ],
            lightcolor=[
                ("pressed", palette["scrollbar_thumb_pressed"]),
                ("active", palette["scrollbar_thumb_hover"]),
                ("!active", palette["scrollbar_thumb"]),
            ],
            darkcolor=[
                ("pressed", palette["scrollbar_thumb_pressed"]),
                ("active", palette["scrollbar_thumb_hover"]),
                ("!active", palette["scrollbar_thumb"]),
            ],
        )
        if self.viewport_canvas is not None:
            self.viewport_canvas.configure(bg=bg)
        if self.preview_canvas is not None:
            self.preview_canvas.configure(
                bg=palette["preview_bg"],
                highlightbackground=palette["panel_border"],
            )
            self.preview_canvas.itemconfigure(
                getattr(self, "preview_title_id", 0), fill=palette["heading_text"]
            )
            self.preview_canvas.itemconfigure(
                getattr(self, "preview_detail_id", 0), fill=palette["helper_text"]
            )
            if self._preview_source_image is not None:
                self.after_idle(
                    self._animate_preview_image, self._preview_source_image.copy()
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
        for source_style, selected in (
            ("SourceTab.TButton", False), ("SourceTabSelected.TButton", True),
        ):
            tab_bg = palette["primary_button"] if selected else palette["panel_alt"]
            tab_fg = palette["button_text"] if selected else palette["secondary_text"]
            style.configure(
                source_style, background=tab_bg, foreground=tab_fg,
                bordercolor=tab_bg, lightcolor=tab_bg, darkcolor=tab_bg,
                relief="flat", borderwidth=0, padding=(12, 9),
                font=(family, 9, "bold"),
            )
            style.map(
                source_style,
                background=[
                    ("pressed", palette["primary_button_pressed"] if selected else palette["input_hover"]),
                    ("active", palette["primary_button_hover"] if selected else palette["input_hover"]),
                ],
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
        if not hasattr(self, "mode_combo"):
            return
        palette = self._palette
        for combo in (self.mode_combo, self.fit_combo):
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
        if not animate or not self._animations_enabled or self.theme_toggle_canvas is None:
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
    def _section(self, parent: ttk.Frame, title: str, row: int) -> ttk.Frame:
        section = ttk.Frame(
            parent, style="Panel.TFrame", padding=(18, 14, 18, 16)
        )
        section.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        section.columnconfigure(1, weight=1)

        header = ttk.Frame(section, style="Panel.TFrame")
        header.grid(
            row=0, column=0, columnspan=4, sticky="ew", pady=(0, 14)
        )
        accent = ttk.Frame(
            header, style="SectionAccent.TFrame", width=3, height=18
        )
        accent.grid(row=0, column=0, sticky="w", padx=(0, 10))
        accent.grid_propagate(False)
        title_label = ttk.Label(
            header, text=title, style="SectionTitle.Panel.TLabel"
        )
        title_label.grid(row=0, column=1, sticky="w")
        section._section_title_label = title_label
        section._section_header = header
        return section

    def _fit_initial_window(self) -> None:
        """Open as a wide workbench while respecting the usable screen area."""
        self.update_idletasks()
        height = calculate_window_height(760, self.winfo_screenheight())
        available_width = max(760, self.winfo_screenwidth() - 64)
        width = min(1180, available_width)
        self.geometry(f"{width}x{height}")
        self._apply_workspace_layout(width)
        if self._overlay is not None and self._overlay_prime_after_id is None:
            # Let Windows map the final root geometry before creating the
            # always-mapped alpha-zero overlay. This still happens long before
            # a user can begin a drag, but avoids priming at Tk's temporary 1x1.
            self._overlay_prime_after_id = self.after(
                OVERLAY_PRIME_DELAY_MS, self._prime_overlay
            )

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, style="Workspace.TFrame", padding=(24, 14, 24, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, text="Flipbook Texture Sheet Generator", style="Title.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header, text="本機影像序列與影片工作台", style="Muted.TLabel"
        ).grid(row=1, column=0, sticky="w", pady=(1, 0))
        theme_slot = ttk.Frame(header, style="Workspace.TFrame")
        theme_slot.grid(row=0, column=1, rowspan=2, sticky="e")
        self._build_theme_toggle(theme_slot)

        self.viewport_canvas = tk.Canvas(
            self, bg=self._palette["window_bg"], highlightthickness=0, bd=0,
        )
        self.viewport_scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.viewport_canvas.yview,
            style="Minimal.Vertical.TScrollbar",
        )
        self.viewport_canvas.configure(yscrollcommand=self.viewport_scrollbar.set)
        self.viewport_canvas.grid(row=1, column=0, sticky="nsew")
        self.viewport_scrollbar.grid(row=1, column=1, sticky="ns")

        main = ttk.Frame(
            self.viewport_canvas, style="Workspace.TFrame", padding=(24, 8, 24, 24)
        )
        self.main_frame = main
        self._viewport_window_id = self.viewport_canvas.create_window(
            (0, 0), window=main, anchor="nw"
        )
        main.bind("<Configure>", self._update_viewport_scroll_region)
        self.viewport_canvas.bind("<Configure>", self._resize_viewport_content)
        self.bind("<MouseWheel>", self._scroll_viewport, add="+")
        main.columnconfigure(0, weight=7)
        main.columnconfigure(1, weight=5)

        left = ttk.Frame(main, style="Workspace.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        left.columnconfigure(0, weight=1)
        self.workspace_frame = left

        source_section = self._section(left, "選擇來源", 0)
        self.source_section = source_section
        source_section.columnconfigure(1, weight=0)
        source_section.columnconfigure(2, weight=1)
        tabs = ttk.Frame(source_section, style="Panel.TFrame")
        tabs.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 12))
        tab_labels = {
            SOURCE_IMAGE_FILE: "序列圖片",
            SOURCE_IMAGE_FOLDER: "圖片資料夾",
            SOURCE_VIDEO: "影片 MP4 / MOV",
        }
        for column, source_kind in enumerate(
            (SOURCE_IMAGE_FILE, SOURCE_IMAGE_FOLDER, SOURCE_VIDEO)
        ):
            tabs.columnconfigure(column, weight=1)
            button = ttk.Button(
                tabs, text=tab_labels[source_kind],
                command=lambda kind=source_kind: self._select_source_type(kind),
                style="SourceTab.TButton",
            )
            button.grid(
                row=0, column=column, sticky="ew",
                padx=(0, 5) if column < 2 else 0,
            )
            self._source_buttons[source_kind] = button
        self._update_source_tabs()

        ttk.Label(source_section, text="來源路徑", style="Panel.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 12), pady=5
        )
        ttk.Entry(source_section, textvariable=self.source_var).grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=5
        )
        ttk.Button(
            source_section, text="瀏覽…", command=self._choose_source,
            width=11, style="Browse.TButton",
        ).grid(row=2, column=3, padx=(10, 0), pady=5)
        ttk.Label(
            source_section, textvariable=self.count_var, style="Hint.Panel.TLabel",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(9, 0))

        self.video_options = self._section(left, "時間範圍", 1)
        for column in (1, 3):
            self.video_options.columnconfigure(column, weight=1)
        ttk.Label(self.video_options, text="開始秒數", style="Panel.TLabel").grid(row=1, column=0, padx=(0, 9), pady=2)
        ttk.Spinbox(self.video_options, from_=0, to=999999, increment=0.1, textvariable=self.video_start_var).grid(row=1, column=1, sticky="ew", padx=(0, 20), pady=2)
        ttk.Label(self.video_options, text="結束秒數", style="Panel.TLabel").grid(row=1, column=2, padx=(0, 9), pady=2)
        ttk.Spinbox(self.video_options, from_=0, to=999999, increment=0.1, textvariable=self.video_end_var).grid(row=1, column=3, sticky="ew", pady=2)
        self.video_options.grid_remove()

        settings = self._section(left, "Flipbook 設定", 2)
        self.settings_section = settings
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)
        ttk.Label(settings, text="網格配置", style="InfoTitle.Panel.TLabel").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(0, 8)
        )
        ttk.Label(settings, text="欄數 (Cols)", style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Spinbox(settings, from_=1, to=999, textvariable=self.cols_var).grid(row=2, column=1, sticky="ew", padx=(0, 24), pady=5)
        ttk.Label(settings, text="列數 (Rows)", style="Panel.TLabel").grid(row=2, column=2, sticky="w", padx=(0, 12), pady=5)
        ttk.Spinbox(settings, from_=1, to=999, textvariable=self.rows_var).grid(row=2, column=3, sticky="ew", pady=5)
        ttk.Label(settings, text="單格尺寸", style="Panel.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Spinbox(settings, from_=1, to=8192, textvariable=self.size_var).grid(row=3, column=1, sticky="ew", padx=(0, 24), pady=5)
        ttk.Label(settings, text="px", style="Hint.Panel.TLabel").grid(row=3, column=2, sticky="w", pady=5)

        self.capacity_label = ttk.Label(settings, textvariable=self.capacity_var, style="Hint.Panel.TLabel")
        self.capacity_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self.full_size_label = ttk.Label(settings, textvariable=self.full_size_var, style="Hint.Panel.TLabel")
        self.full_size_label.grid(row=4, column=2, columnspan=2, sticky="w", pady=(10, 4))
        self.power_of_two_warning = ttk.Label(
            settings, text="! 建議圖片寬 × 高尺寸皆為 2 的次方",
            style="PowerOfTwoWarning.TLabel",
        )

        ttk.Separator(settings, orient="horizontal").grid(
            row=6, column=0, columnspan=4, sticky="ew", pady=(14, 14)
        )
        ttk.Label(settings, text="影像處理", style="InfoTitle.Panel.TLabel").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(0, 8)
        )
        ttk.Label(settings, text="通道模式", style="Panel.TLabel").grid(row=8, column=0, sticky="w", padx=(0, 12), pady=5)
        self.mode_combo = ttk.Combobox(
            settings, textvariable=self.mode_var, values=tuple(MODE_LABELS),
            state="readonly", width=22,
        )
        self.mode_combo.grid(row=8, column=1, sticky="ew", padx=(0, 24), pady=5)
        self.fit_label = ttk.Label(settings, text="畫面適配", style="Panel.TLabel")
        self.fit_label.grid(row=8, column=2, sticky="w", padx=(0, 12), pady=5)
        self.fit_combo = ttk.Combobox(
            settings, textvariable=self.fit_var, values=tuple(FIT_LABELS),
            state="readonly", width=22,
        )
        self.fit_combo.grid(row=8, column=3, sticky="ew", pady=5)
        self.capacity_warning_line = ttk.Frame(
            settings, style="PanelFlat.TFrame"
        )
        self.capacity_warning_line.grid(
            row=10, column=0, columnspan=4, sticky="ew", pady=(8, 0)
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
        self.fill_check.grid(row=11, column=0, columnspan=4, sticky="w", pady=(4, 9))
        self.fill_check.grid_remove()

        self.detail_canvas = tk.Canvas(
            settings, width=420, height=90, bg=self._palette["section_bg"],
            highlightthickness=0, bd=0,
        )
        self.detail_canvas.grid(row=9, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=(8, 0))
        self.detail_title_id = self.detail_canvas.create_text(
            0, 14, text="ⓘ  通道模式說明", anchor="nw",
            fill=self._palette["heading_text"],
            font=(self._font_family, 10, "bold"),
        )
        self.detail_text_id = self.detail_canvas.create_text(
            0, 40, text=self.detail_var.get(), anchor="nw",
            fill=self._palette["helper_text"],
            font=(self._font_family, 9), width=416,
        )
        self.fit_detail_canvas = tk.Canvas(
            settings, width=420, height=90, bg=self._palette["section_bg"],
            highlightthickness=0, bd=0,
        )
        self.fit_detail_canvas.grid(row=9, column=2, columnspan=2, sticky="ew", pady=(8, 0))
        self.fit_detail_title_id = self.fit_detail_canvas.create_text(
            0, 14, text="ⓘ  畫面適配說明", anchor="nw",
            fill=self._palette["heading_text"],
            font=(self._font_family, 10, "bold"),
        )
        self.fit_detail_text_id = self.fit_detail_canvas.create_text(
            0, 40, text=self.fit_detail_var.get(), anchor="nw",
            fill=self._palette["helper_text"],
            font=(self._font_family, 9), width=416,
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

        action = ttk.Frame(main, style="Panel.TFrame", padding=(18, 16))
        self.right_panel = action
        action.grid(row=0, column=1, sticky="nsew")
        action.columnconfigure(0, weight=1)
        ttk.Label(action, text="輸出預覽", style="PanelStrong.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(action, text="低解析工作預覽，不會寫入磁碟", style="PanelMeta.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 12)
        )
        self.preview_canvas = tk.Canvas(
            action, width=360, height=260, bg=self._palette["preview_bg"],
            highlightthickness=1, highlightbackground=self._palette["panel_border"], bd=0,
        )
        self.preview_canvas.grid(row=2, column=0, sticky="ew")
        self.preview_image_id = self.preview_canvas.create_image(180, 130, anchor="center")
        self.preview_title_id = self.preview_canvas.create_text(
            180, 118, text=self.preview_title_var.get(), anchor="s",
            fill=self._palette["heading_text"], font=(self._font_family, 12, "bold"),
        )
        self.preview_detail_id = self.preview_canvas.create_text(
            180, 133, text=self.preview_detail_var.get(), anchor="n", width=290,
            justify="center", fill=self._palette["helper_text"], font=(self._font_family, 9),
        )
        self.preview_canvas.bind("<Configure>", self._resize_preview_canvas)

        summary = ttk.Frame(action, style="Panel.TFrame")
        summary.grid(row=3, column=0, sticky="ew", pady=(14, 12))
        summary.columnconfigure((0, 1), weight=1)
        for row, (left_var, right_var) in enumerate((
            (self.preview_source_var, self.preview_capacity_var),
            (self.preview_size_var, self.preview_mode_var),
        )):
            ttk.Label(summary, textvariable=left_var, style="PanelMeta.TLabel").grid(
                row=row, column=0, sticky="w", pady=2
            )
            ttk.Label(summary, textvariable=right_var, style="PanelMeta.TLabel").grid(
                row=row, column=1, sticky="e", pady=2
            )

        ttk.Label(action, text="輸出位置", style="PanelStrong.TLabel").grid(
            row=4, column=0, sticky="w", pady=(2, 6)
        )
        output_line = ttk.Frame(action, style="Panel.TFrame")
        output_line.grid(row=5, column=0, sticky="ew")
        output_line.columnconfigure(0, weight=1)
        ttk.Entry(output_line, textvariable=self.output_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            output_line, text="瀏覽…", command=self._choose_output,
            style="Browse.TButton", width=9,
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(action, textvariable=self.preview_output_var, style="PanelMeta.TLabel").grid(
            row=6, column=0, sticky="w", pady=(6, 12)
        )

        progress_line = ttk.Frame(action, style="PanelFlat.TFrame")
        progress_line.grid(row=7, column=0, sticky="ew", pady=(0, 8))
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
        ttk.Label(action, textvariable=self.status_var, style="Hint.Panel.TLabel").grid(row=8, column=0, sticky="w", pady=(0, 10))
        self.run_button = ttk.Button(action, text="產生 Flipbook 網格圖", style="Primary.TButton", command=self._start)
        self.run_button.grid(row=9, column=0, sticky="ew")
        self.output_folder_button = ttk.Button(
            action, text="開啟輸出資料夾", command=self._open_last_output_folder,
            state="disabled", style="SecondaryAction.TButton", width=12,
        )
        self.output_folder_button.grid(row=10, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            action, text="素材只在本機處理，不會上傳",
            style="Success.Panel.TLabel",
        ).grid(row=11, column=0, sticky="w", pady=(12, 0))
        main.bind("<Configure>", self._workspace_resized, add="+")
        self._apply_workspace_layout(1180)

    def _select_source_type(self, source_kind: str) -> None:
        target = SOURCE_TYPE_LABELS[source_kind]
        if self.source_type_var.get() == target:
            return
        self.source_type_var.set(target)
        self._source_type_changed()

    def _update_source_tabs(self) -> None:
        current = self._current_source_kind()
        for source_kind, button in self._source_buttons.items():
            button.configure(
                style=(
                    "SourceTabSelected.TButton"
                    if source_kind == current else "SourceTab.TButton"
                )
            )

    def _workspace_resized(self, event: object) -> None:
        self._apply_workspace_layout(int(getattr(event, "width", 1)))

    def _apply_workspace_layout(self, width: int) -> None:
        if self.main_frame is None or self.workspace_frame is None or self.right_panel is None:
            return
        layout = "wide" if width >= WORKSPACE_BREAKPOINT else "narrow"
        if layout == self._workspace_layout:
            return
        self._workspace_layout = layout
        self.workspace_frame.grid_forget()
        self.right_panel.grid_forget()
        if layout == "wide":
            self.main_frame.columnconfigure(0, weight=7)
            self.main_frame.columnconfigure(1, weight=5)
            self.workspace_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
            self.right_panel.grid(row=0, column=1, sticky="nsew")
        else:
            self.main_frame.columnconfigure(0, weight=1)
            self.main_frame.columnconfigure(1, weight=0)
            self.workspace_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
            self.right_panel.grid(
                row=1, column=0, columnspan=2, sticky="nsew", pady=(4, 0)
            )
        self.after_idle(self._update_viewport_scroll_region)

    def _output_changed(self, *_args: object) -> None:
        output = self.output_var.get().strip()
        self.preview_output_var.set(
            f"將儲存為 {Path(output).name}" if output else "尚未選擇輸出位置"
        )

    def _preview_text_changed(self, *_args: object) -> None:
        if self.preview_canvas is None:
            return
        self.preview_canvas.itemconfigure(
            self.preview_title_id, text=self.preview_title_var.get()
        )
        self.preview_canvas.itemconfigure(
            self.preview_detail_id, text=self.preview_detail_var.get()
        )

    def _schedule_preview(self) -> None:
        if self._closing or self.preview_canvas is None:
            return
        self._preview_request_id += 1
        request_id = self._preview_request_id
        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except tk.TclError:
                pass
        self._preview_after_id = self.after(
            PREVIEW_DEBOUNCE_MS, self._start_preview_request, request_id
        )

    def _start_preview_request(self, request_id: int) -> None:
        self._preview_after_id = None
        if request_id != self._preview_request_id or self._closing:
            return
        source = self.source_var.get().strip()
        if not source or self._source_count < 1:
            self._clear_preview()
            return
        try:
            cols, rows = self.cols_var.get(), self.rows_var.get()
            mode = MODE_LABELS[self.mode_var.get()]
            frame_fit = FIT_LABELS[self.fit_var.get()]
            fill_empty = self.fill_empty_var.get()
            source_kind = self._current_source_kind()
            start = float(self.video_start_var.get() or 0)
            end_text = self.video_end_var.get().strip()
            end = float(end_text) if end_text else None
        except (tk.TclError, ValueError, KeyError):
            self._preview_error(request_id, "目前設定無法建立預覽。")
            return
        self.preview_title_var.set("正在更新預覽")
        self.preview_detail_var.set("正式輸出仍可照常執行")
        threading.Thread(
            target=self._preview_worker,
            args=(
                request_id, source, source_kind, cols, rows, mode,
                fill_empty, start, end, frame_fit,
            ),
            daemon=True,
        ).start()

    def _preview_worker(
        self,
        request_id: int,
        source: str,
        source_kind: str,
        cols: int,
        rows: int,
        mode: str,
        fill_empty: bool,
        start: float,
        end: float | None,
        frame_fit: str,
    ) -> None:
        try:
            if source_kind == SOURCE_VIDEO:
                result = make_video_preview(
                    source, cols, rows, mode, fill_empty, start, end,
                    frame_fit, PREVIEW_EDGE,
                )
            else:
                result = make_image_preview(
                    source, cols, rows, mode, fill_empty, frame_fit,
                    PREVIEW_EDGE,
                )
        except Exception as exc:
            if not self._closing:
                try:
                    self.after(0, self._preview_error, request_id, str(exc))
                except (RuntimeError, tk.TclError):
                    pass
        else:
            if not self._closing:
                try:
                    self.after(0, self._preview_ready, request_id, result)
                except (RuntimeError, tk.TclError):
                    pass

    def _preview_ready(self, request_id: int, result: object) -> None:
        if request_id != self._preview_request_id or self._closing:
            return
        self._preview_source_image = result.image.copy()
        self.preview_title_var.set("")
        self.preview_detail_var.set("")
        suffix = " · 代表影格" if result.sampled else " · 完整縮圖"
        self.preview_source_var.set(f"來源  {result.source_count} 格{suffix}")
        self._animate_preview_image(self._preview_source_image)

    def _preview_error(self, request_id: int, error: str) -> None:
        if request_id != self._preview_request_id or self._closing:
            return
        self._preview_source_image = None
        if self.preview_canvas is not None and self.preview_image_id is not None:
            self.preview_canvas.itemconfigure(self.preview_image_id, image="")
        self.preview_title_var.set("預覽暫時不可用")
        self.preview_detail_var.set(error[:120])

    def _clear_preview(self) -> None:
        self._preview_source_image = None
        self.preview_photo = None
        if self.preview_canvas is not None and self.preview_image_id is not None:
            self.preview_canvas.itemconfigure(self.preview_image_id, image="")
        self.preview_title_var.set("等待來源")
        self.preview_detail_var.set("選擇圖片或影片後會顯示低解析網格預覽")
        self.preview_source_var.set("來源  —")

    def _compose_preview_display(
        self, source: Image.Image, width: int, height: int
    ) -> Image.Image:
        width = max(80, width)
        height = max(80, height)
        light = self.theme_var.get() == THEME_LIGHT
        colors = ((232, 231, 227, 255), (214, 213, 209, 255)) if light else (
            (22, 26, 30, 255), (32, 37, 42, 255)
        )
        display = Image.new("RGBA", (width, height), colors[0])
        draw = ImageDraw.Draw(display)
        checker = 14
        for y in range(0, height, checker):
            for x in range(0, width, checker):
                if (x // checker + y // checker) % 2:
                    draw.rectangle((x, y, x + checker - 1, y + checker - 1), fill=colors[1])
        content = source.copy()
        content.thumbnail((max(1, width - 28), max(1, height - 28)), Image.Resampling.LANCZOS)
        display.alpha_composite(
            content, ((width - content.width) // 2, (height - content.height) // 2)
        )
        return display

    def _animate_preview_image(self, source: Image.Image) -> None:
        if self.preview_canvas is None or self.preview_image_id is None:
            return
        if self._preview_animation_id is not None:
            try:
                self.after_cancel(self._preview_animation_id)
            except tk.TclError:
                pass
        width = max(80, self.preview_canvas.winfo_width())
        height = max(80, self.preview_canvas.winfo_height())
        final = self._compose_preview_display(source, width, height)
        if not self._animations_enabled:
            self.preview_photo = ImageTk.PhotoImage(final, master=self)
            self.preview_canvas.itemconfigure(
                self.preview_image_id, image=self.preview_photo
            )
            return
        background = Image.new("RGBA", final.size, self._palette["preview_bg"])
        started = time.perf_counter()

        def step() -> None:
            if self._closing or self.preview_canvas is None:
                self._preview_animation_id = None
                return
            progress = min(1.0, (time.perf_counter() - started) / 0.14)
            eased = 1 - (1 - progress) ** 3
            scale = 0.94 + 0.06 * eased
            scaled = final.resize(
                (max(1, round(final.width * scale)), max(1, round(final.height * scale))),
                Image.Resampling.BILINEAR,
            )
            frame = background.copy()
            frame.alpha_composite(
                scaled, ((frame.width - scaled.width) // 2, (frame.height - scaled.height) // 2)
            )
            frame = Image.blend(background, frame, 0.35 + 0.65 * eased)
            self.preview_photo = ImageTk.PhotoImage(frame, master=self)
            self.preview_canvas.itemconfigure(self.preview_image_id, image=self.preview_photo)
            self.preview_canvas.tag_raise(self.preview_title_id)
            self.preview_canvas.tag_raise(self.preview_detail_id)
            if progress < 1:
                self._preview_animation_id = self.after(16, step)
            else:
                self._preview_animation_id = None

        step()

    def _resize_preview_canvas(self, event: object) -> None:
        if self.preview_canvas is None:
            return
        width = max(80, int(getattr(event, "width", 360)))
        height = max(80, int(getattr(event, "height", 300)))
        self.preview_canvas.coords(self.preview_image_id, width / 2, height / 2)
        self.preview_canvas.coords(self.preview_title_id, width / 2, height / 2 - 8)
        self.preview_canvas.coords(self.preview_detail_id, width / 2, height / 2 + 8)
        self.preview_canvas.itemconfigure(self.preview_detail_id, width=max(120, width - 70))
        if self._preview_source_image is not None:
            final = self._compose_preview_display(self._preview_source_image, width, height)
            self.preview_photo = ImageTk.PhotoImage(final, master=self)
            self.preview_canvas.itemconfigure(self.preview_image_id, image=self.preview_photo)

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
        self._update_source_tabs()
        self._clear_preview()
        self._update_capacity()

    def _update_viewport_scroll_region(self, _event: object | None = None) -> None:
        if self.viewport_canvas is not None:
            bounds = self.viewport_canvas.bbox("all")
            if bounds is not None:
                self.viewport_canvas.configure(scrollregion=bounds)

    def _resize_viewport_content(self, event: object) -> None:
        if self.viewport_canvas is None or self._viewport_window_id is None:
            return
        width = max(1, int(getattr(event, "width", 1)))
        self.viewport_canvas.itemconfigure(self._viewport_window_id, width=width)
        self._apply_workspace_layout(width)

    def _scroll_viewport(self, event: object) -> str | None:
        if self.viewport_canvas is None:
            return None
        widget = getattr(event, "widget", None)
        if widget is not None and widget.winfo_class() in {"TSpinbox", "TCombobox"}:
            return None
        bounds = self.viewport_canvas.bbox("all")
        if bounds is None or bounds[3] - bounds[1] <= self.viewport_canvas.winfo_height():
            return None
        delta = int(getattr(event, "delta", 0))
        if delta:
            self.viewport_canvas.yview_scroll(-1 if delta > 0 else 1, "units")
            return "break"
        return None

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
        self._update_source_tabs()

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
            self._preview_after_id, self._preview_animation_id,
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
        self._schedule_preview()

    def _mode_changed(self, *_args: object) -> None:
        descriptions = {
            "RGBA（透明）": "完整保留 Alpha 透明去背通道背景輸出。適合透明粒子、網格特效圖。",
            "RGB Straight": "完整保留圖片RGB資訊，但將Alpha設為完全不透明。",
            "RGB Premultiplied": "將圖片合成至黑色背景，會遺失原本透明部分的RGB資訊。",
        }
        self._set_detail_text(descriptions.get(self.mode_var.get(), ""))
        self._schedule_preview()

    def _set_detail_text(self, text: str) -> None:
        self.detail_var.set(text)
        if self.detail_canvas is not None and self.detail_text_id is not None:
            self.detail_canvas.itemconfigure(self.detail_text_id, text=text)

    def _fit_changed(self, *_args: object) -> None:
        text = FIT_DESCRIPTIONS.get(self.fit_var.get(), "")
        self.fit_detail_var.set(text)
        if self.fit_detail_canvas is not None and self.fit_detail_text_id is not None:
            self.fit_detail_canvas.itemconfigure(self.fit_detail_text_id, text=text)
        self._schedule_preview()

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
            self.preview_capacity_var.set(f"容量  {cols} × {rows} = {capacity}")
            self.preview_size_var.set(f"輸出  {full_width} × {full_height} px")
            mode_short = self.mode_var.get().split("（", 1)[0]
            fit_short = self.fit_var.get().replace("至正方形", "")
            self.preview_mode_var.set(f"{mode_short} · {fit_short}")
            if uses_power_of_two_dimensions:
                self.power_of_two_warning.grid_remove()
            elif not self.power_of_two_warning.winfo_manager():
                self.power_of_two_warning.grid(
                    row=5, column=0, columnspan=4, sticky="w", pady=(4, 0)
                )
            if self._source_count > capacity:
                if self._current_source_kind() != SOURCE_VIDEO:
                    self.warning_text.configure(text="需求的圖片總格數不足，多的格數會被刪掉")
                else:
                    self.warning_text.configure(text="影片影格多於網格容量，將平均抽取整段範圍")
                if not self.capacity_warning_line.winfo_manager():
                    self.capacity_warning_line.grid()
                self.fill_check.grid_remove()
                if self.fill_empty_var.get():
                    self.fill_empty_var.set(False)
            else:
                self.capacity_warning_line.grid_remove()
                if self._source_count > 0 and capacity > self._source_count:
                    self.fill_check.grid()
                else:
                    self.fill_check.grid_remove()
                    if self.fill_empty_var.get():
                        self.fill_empty_var.set(False)
        except tk.TclError:
            self.capacity_var.set("欄數與列數必須是整數")
            self.full_size_var.set("完整尺寸：—")
            self.power_of_two_warning.grid_remove()
        self._schedule_preview()

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
