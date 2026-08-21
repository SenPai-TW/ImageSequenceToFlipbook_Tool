#!/usr/bin/env python3
"""Create a PNG flipbook from an image sequence or MP4/MOV video."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Sequence

from PIL import Image, ImageDraw, UnidentifiedImageError


VALID_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
CHANNEL_MODES = ("RGBA", "RGB", "RGB_BLACK")
FRAME_FIT_MODES = ("crop", "stretch", "pad")
# Backward-compatible public name used by the existing video CLI/API.
VIDEO_FIT_MODES = FRAME_FIT_MODES
ProgressCallback = Callable[[int], None]


@dataclass(frozen=True)
class PreviewResult:
    """Low-resolution, in-memory representation of a future flipbook."""

    image: Image.Image
    source_count: int
    frames_used: int
    sampled: bool


class _ProgressReporter:
    """Emit bounded integer percentages without flooding the GUI thread."""

    def __init__(self, callback: ProgressCallback | None) -> None:
        self.callback = callback
        self.last_value = -1

    def update(self, value: float) -> None:
        percent = max(0, min(100, round(value)))
        if self.callback is not None and percent != self.last_value:
            self.last_value = percent
            self.callback(percent)


def _load_imageio_ffmpeg():
    try:
        import imageio_ffmpeg
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "影片功能需要 imageio-ffmpeg。請連線網路後重新執行「安裝必要套件.bat」。"
        ) from exc
    return imageio_ffmpeg


def _read_video_metadata(path: Path) -> dict[str, object]:
    imageio_ffmpeg = _load_imageio_ffmpeg()
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    try:
        metadata = next(reader)
    finally:
        reader.close()
    width, height = metadata.get("size", (0, 0))
    duration = float(metadata.get("duration") or 0.0)
    if width < 1 or height < 1 or duration <= 0:
        raise RuntimeError("影片沒有可用的視訊影格。")
    return {
        "path": path,
        "width": int(width),
        "height": int(height),
        "fps": float(metadata.get("fps") or 0.0),
        "duration": duration,
    }


def probe_video(video_path: str | Path) -> dict[str, object]:
    """Return normalized video metadata used by the GUI and converter."""
    path = Path(video_path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("影片來源必須是存在的 MP4 或 MOV 檔案。")
    imageio_ffmpeg = _load_imageio_ffmpeg()
    try:
        metadata = _read_video_metadata(path)
        frame_count, duration = imageio_ffmpeg.count_frames_and_secs(str(path))
    except Exception as exc:
        raise RuntimeError(f"無法讀取影片資訊，檔案可能損壞、沒有視訊軌或編碼不受支援：{exc}") from exc

    duration = float(duration or metadata.get("duration") or 0.0)
    if duration <= 0 or frame_count < 1:
        raise RuntimeError("影片沒有可用的視訊影格。")
    metadata["duration"] = duration
    metadata["frame_count"] = int(frame_count)
    return metadata


def natural_sort_key(path: Path) -> list[object]:
    """Sort frame2 before frame10, matching the original add-on."""
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", path.name)]


def detect_image_sequence(selected_image: Path) -> list[Path]:
    """Return the numbered sequence represented by one selected image.

    The final numeric run in the filename stem is treated as the frame number.
    Matching files must have the same prefix, suffix, and extension. When the
    selected filename has no number, only that file is returned.
    """
    selected_image = Path(selected_image).expanduser().resolve()
    if not selected_image.is_file():
        raise FileNotFoundError(f"Image file does not exist: {selected_image}")
    if selected_image.suffix.lower() not in VALID_EXTENSIONS:
        raise ValueError(f"Unsupported image file: {selected_image}")

    matches = list(re.finditer(r"\d+", selected_image.stem))
    if not matches:
        return [selected_image]

    frame_number = matches[-1]
    prefix = selected_image.stem[:frame_number.start()]
    suffix = selected_image.stem[frame_number.end():]
    pattern = re.compile(
        rf"^{re.escape(prefix)}\d+{re.escape(suffix)}$",
        re.IGNORECASE,
    )
    extension = selected_image.suffix.casefold()
    files = [
        path.resolve()
        for path in selected_image.parent.iterdir()
        if path.is_file()
        and path.suffix.casefold() == extension
        and pattern.fullmatch(path.stem)
    ]
    return sorted(files, key=natural_sort_key)


def collect_image_files(source: Path) -> list[Path]:
    """Collect supported images from a folder or infer a selected image sequence."""
    source = Path(source).expanduser().resolve()
    if source.is_dir():
        files = [
            path for path in source.iterdir()
            if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS
        ]
        return sorted(files, key=natural_sort_key)
    if source.is_file():
        return detect_image_sequence(source)
    raise FileNotFoundError(f"Image source does not exist: {source}")


def apply_channel_mode(image: Image.Image, mode: str) -> Image.Image:
    rgba = image.convert("RGBA")
    if mode == "RGBA":
        return rgba
    if mode == "RGB":
        opaque = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        opaque.paste(rgba.convert("RGB"), (0, 0))
        return opaque
    if mode == "RGB_BLACK":
        # Alpha-composite over black: RGB is multiplied by alpha, then made opaque.
        black = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        return Image.alpha_composite(black, rgba)
    raise ValueError(f"Unknown channel mode: {mode}")


def fit_frame(
    image: Image.Image,
    target_size: int,
    fit_mode: str,
    channel_mode: str = "RGBA",
) -> Image.Image:
    fit_mode = fit_mode.lower()
    if fit_mode == "stretch":
        return image.resize((target_size, target_size), Image.Resampling.LANCZOS)
    if fit_mode == "pad":
        width, height = image.size
        scale = min(target_size / width, target_size / height)
        resized = image.convert("RGBA").resize(
            (
                min(target_size, max(1, round(width * scale))),
                min(target_size, max(1, round(height * scale))),
            ),
            Image.Resampling.LANCZOS,
        )
        background = (0, 0, 0, 0) if channel_mode.upper() == "RGBA" else (0, 0, 0, 255)
        canvas = Image.new("RGBA", (target_size, target_size), background)
        left = (target_size - resized.width) // 2
        top = (target_size - resized.height) // 2
        # Copy raw RGBA values so RGB Straight keeps the source RGB beneath
        # transparency; channel conversion happens after fitting.
        canvas.paste(resized, (left, top))
        return canvas
    if fit_mode != "crop":
        raise ValueError(f"fit_mode must be one of: {', '.join(FRAME_FIT_MODES)}")
    width, height = image.size
    scale = max(target_size / width, target_size / height)
    resized = image.resize(
        (max(target_size, round(width * scale)), max(target_size, round(height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - target_size) // 2
    top = (resized.height - target_size) // 2
    return resized.crop((left, top, left + target_size, top + target_size))


# Preserve the original helper name for callers that imported it directly.
fit_video_frame = fit_frame


def _preview_geometry(cols: int, rows: int, preview_edge: int) -> tuple[int, int, int]:
    if cols < 1 or rows < 1 or preview_edge < 32:
        raise ValueError("cols, rows, and preview_edge must all be positive")
    tile_size = max(1, preview_edge // max(cols, rows))
    return tile_size, cols * tile_size, rows * tile_size


def _preview_canvas(
    cols: int,
    rows: int,
    preview_edge: int,
    occupied: int,
) -> tuple[Image.Image, int]:
    tile_size, width, height = _preview_geometry(cols, rows, preview_edge)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    capacity = cols * rows
    occupied = max(0, min(capacity, occupied))
    placeholder = (92, 108, 120, 72)

    if capacity <= 4096:
        inset = 1 if tile_size >= 4 else 0
        for index in range(occupied):
            left = (index % cols) * tile_size + inset
            top = (index // cols) * tile_size + inset
            draw.rectangle(
                (
                    left,
                    top,
                    (index % cols + 1) * tile_size - 1,
                    (index // cols + 1) * tile_size - 1,
                ),
                fill=placeholder,
            )
    else:
        full_rows, remainder = divmod(occupied, cols)
        if full_rows:
            draw.rectangle((0, 0, width - 1, full_rows * tile_size - 1), fill=placeholder)
        if remainder:
            draw.rectangle(
                (0, full_rows * tile_size, remainder * tile_size - 1, (full_rows + 1) * tile_size - 1),
                fill=placeholder,
            )

    if tile_size >= 5 and capacity <= 4096:
        grid_color = (150, 166, 176, 58)
        for column in range(1, cols):
            x = column * tile_size
            draw.line((x, 0, x, height), fill=grid_color)
        for row in range(1, rows):
            y = row * tile_size
            draw.line((0, y, width, y), fill=grid_color)
    return canvas, tile_size


def _place_preview_tile(
    canvas: Image.Image,
    tile: Image.Image,
    index: int,
    cols: int,
    tile_size: int,
) -> None:
    x = (index % cols) * tile_size
    y = (index // cols) * tile_size
    ImageDraw.Draw(canvas).rectangle(
        (x, y, x + tile_size - 1, y + tile_size - 1), fill=(0, 0, 0, 0)
    )
    canvas.alpha_composite(tile, (x, y))


def make_image_preview(
    source: str | Path,
    cols: int,
    rows: int,
    channel_mode: str = "RGBA",
    fill_empty_with_last: bool = False,
    image_fit: str = "pad",
    preview_edge: int = 360,
    max_thumbnails: int = 64,
) -> PreviewResult:
    """Build a bounded, in-memory preview without changing generation behavior."""
    channel_mode = channel_mode.upper()
    image_fit = image_fit.lower()
    if channel_mode not in CHANNEL_MODES:
        raise ValueError(f"channel_mode must be one of: {', '.join(CHANNEL_MODES)}")
    if image_fit not in FRAME_FIT_MODES:
        raise ValueError(f"image_fit must be one of: {', '.join(FRAME_FIT_MODES)}")
    if max_thumbnails < 1:
        raise ValueError("max_thumbnails must be at least 1")

    files = collect_image_files(Path(source))
    if not files:
        raise ValueError(f"No supported images found in: {source}")
    capacity = cols * rows
    frames_used = min(len(files), capacity)
    occupied = capacity if fill_empty_with_last and frames_used else frames_used
    canvas, tile_size = _preview_canvas(cols, rows, preview_edge, occupied)
    sampled = frames_used > max_thumbnails
    indices = (
        _even_indices(frames_used, max_thumbnails)
        if sampled else list(range(frames_used))
    )
    last_tile: Image.Image | None = None
    for index in indices:
        path = files[index]
        try:
            with Image.open(path) as source_image:
                source_image.load()
                tile = source_image.convert("RGBA")
        except (UnidentifiedImageError, OSError) as exc:
            raise RuntimeError(f"無法建立預覽：Pillow 無法讀取 '{path}'：{exc}") from exc
        tile = fit_frame(tile, tile_size, image_fit, channel_mode)
        tile = apply_channel_mode(tile, channel_mode)
        _place_preview_tile(canvas, tile, index, cols, tile_size)
        if index == frames_used - 1:
            last_tile = tile.copy()

    if fill_empty_with_last and frames_used and last_tile is None:
        with Image.open(files[frames_used - 1]) as source_image:
            tile = fit_frame(source_image.convert("RGBA"), tile_size, image_fit, channel_mode)
            last_tile = apply_channel_mode(tile, channel_mode)
    if fill_empty_with_last and last_tile is not None:
        fill_indices = range(frames_used, capacity)
        if capacity - frames_used > max_thumbnails:
            fill_indices = _even_indices(capacity - frames_used, max_thumbnails)
            fill_indices = (frames_used + index for index in fill_indices)
            sampled = True
        for index in fill_indices:
            _place_preview_tile(canvas, last_tile, index, cols, tile_size)
    return PreviewResult(canvas, len(files), frames_used, sampled)


def _read_video_frame_at(path: Path, timestamp: float) -> Image.Image:
    imageio_ffmpeg = _load_imageio_ffmpeg()
    reader = imageio_ffmpeg.read_frames(
        str(path),
        pix_fmt="rgb24",
        input_params=["-ss", f"{max(0.0, timestamp):.6f}"],
        output_params=["-frames:v", "1"],
    )
    try:
        metadata = next(reader)
        width, height = metadata.get("size", (0, 0))
        frame_bytes = next(reader)
    finally:
        reader.close()
    if width < 1 or height < 1:
        raise RuntimeError("影片預覽沒有取得有效影格尺寸。")
    return Image.frombytes("RGB", (int(width), int(height)), frame_bytes).convert("RGBA")


def make_video_preview(
    video_path: str | Path,
    cols: int,
    rows: int,
    channel_mode: str = "RGBA",
    fill_empty_with_last: bool = False,
    start: float = 0.0,
    end: float | None = None,
    video_fit: str = "pad",
    preview_edge: int = 360,
    max_thumbnails: int = 12,
) -> PreviewResult:
    """Create a representative video preview using bounded random-access seeks."""
    path = Path(video_path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("影片來源必須是存在的 MP4 或 MOV 檔案。")
    metadata = _read_video_metadata(path)
    duration = float(metadata["duration"])
    fps = max(0.001, float(metadata.get("fps") or 0.0))
    start = float(start)
    end = duration if end is None else float(end)
    if start < 0 or start >= end or end > duration + 0.001:
        raise ValueError("影片預覽時間範圍無效。")
    if max_thumbnails < 1:
        raise ValueError("max_thumbnails must be at least 1")

    source_count = max(1, round((end - start) * fps))
    capacity = cols * rows
    frames_used = min(source_count, capacity)
    occupied = capacity if fill_empty_with_last and frames_used else frames_used
    canvas, tile_size = _preview_canvas(cols, rows, preview_edge, occupied)
    wanted = min(frames_used, max_thumbnails)
    indices = _even_indices(frames_used, wanted)
    sampled = frames_used > wanted
    last_tile: Image.Image | None = None
    span = max(0.0, end - start - min(0.001, (end - start) / 1000))
    for index in indices:
        fraction = 0.0 if frames_used <= 1 else index / (frames_used - 1)
        frame = _read_video_frame_at(path, start + span * fraction)
        tile = fit_frame(frame, tile_size, video_fit, channel_mode)
        tile = apply_channel_mode(tile, channel_mode)
        _place_preview_tile(canvas, tile, index, cols, tile_size)
        if index == frames_used - 1:
            last_tile = tile.copy()
    if fill_empty_with_last and last_tile is not None:
        fill_count = capacity - frames_used
        fill_offsets = range(fill_count)
        if fill_count > max_thumbnails:
            fill_offsets = _even_indices(fill_count, max_thumbnails)
            sampled = True
        for offset in fill_offsets:
            index = frames_used + offset
            _place_preview_tile(canvas, last_tile, index, cols, tile_size)
    return PreviewResult(canvas, source_count, frames_used, sampled)


def _video_reader(path: Path, start: float, end: float) -> Iterator[object]:
    imageio_ffmpeg = _load_imageio_ffmpeg()
    return imageio_ffmpeg.read_frames(
        str(path),
        pix_fmt="rgb24",
        input_params=["-ss", f"{start:.6f}"],
        output_params=["-t", f"{end - start:.6f}", "-vsync", "0"],
    )


def _count_video_range(
    path: Path,
    start: float,
    end: float,
    progress: _ProgressReporter | None = None,
    estimated_frames: int = 1,
) -> tuple[int, tuple[int, int]]:
    reader = _video_reader(path, start, end)
    try:
        metadata = next(reader)
        size = tuple(metadata.get("size", (0, 0)))
        count = 0
        for count, _frame in enumerate(reader, start=1):
            if progress is not None:
                progress.update(5 + min(29, 29 * count / max(1, estimated_frames)))
    finally:
        reader.close()
    if count < 1 or len(size) != 2 or min(size) < 1:
        raise ValueError("指定的時間範圍內沒有可用影格。")
    return count, (int(size[0]), int(size[1]))


def _even_indices(frame_count: int, wanted: int) -> list[int]:
    if wanted >= frame_count:
        return list(range(frame_count))
    if wanted == 1:
        return [0]
    return [(index * (frame_count - 1)) // (wanted - 1) for index in range(wanted)]


def make_video_flipbook(
    video_path: str | Path,
    output_path: str | Path,
    cols: int,
    rows: int,
    target_size: int,
    channel_mode: str = "RGBA",
    fill_empty_with_last: bool = False,
    start: float = 0.0,
    end: float | None = None,
    video_fit: str = "crop",
    progress_callback: ProgressCallback | None = None,
) -> tuple[Path, int]:
    progress = _ProgressReporter(progress_callback)
    progress.update(0)
    if cols < 1 or rows < 1 or target_size < 1:
        raise ValueError("cols, rows, and target_size must all be at least 1")
    channel_mode = channel_mode.upper()
    if channel_mode not in CHANNEL_MODES:
        raise ValueError(f"channel_mode must be one of: {', '.join(CHANNEL_MODES)}")
    video_fit = video_fit.lower()
    if video_fit not in VIDEO_FIT_MODES:
        raise ValueError(f"video_fit must be one of: {', '.join(VIDEO_FIT_MODES)}")

    path = Path(video_path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("影片來源必須是存在的 MP4 或 MOV 檔案。")
    try:
        metadata = _read_video_metadata(path)
    except Exception as exc:
        raise RuntimeError(f"無法讀取影片資訊，檔案可能損壞、沒有視訊軌或編碼不受支援：{exc}") from exc
    duration = float(metadata["duration"])
    end = duration if end is None else float(end)
    start = float(start)
    if start < 0:
        raise ValueError("開始時間不可小於 0 秒。")
    if end > duration + 0.001:
        raise ValueError(f"結束時間不可超過影片長度 {duration:.3f} 秒。")
    if start >= end:
        raise ValueError("開始時間必須小於結束時間。")
    progress.update(5)

    try:
        estimated_frames = max(
            1, round((end - start) * max(0.0, float(metadata.get("fps") or 0.0)))
        )
        frame_count, frame_size = _count_video_range(
            path, start, end, progress, estimated_frames
        )
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError(f"無法解碼指定的影片時間範圍：{exc}") from exc
    wanted = min(cols * rows, frame_count)
    progress.update(35)
    selected_indices = _even_indices(frame_count, wanted)
    selected_lookup = set(selected_indices)
    canvas = Image.new("RGBA", (cols * target_size, rows * target_size), (0, 0, 0, 0))
    last_tile: Image.Image | None = None
    written = 0
    reader = _video_reader(path, start, end)
    try:
        next(reader)
        for source_index, frame_bytes in enumerate(reader):
            progress.update(35 + 55 * (source_index + 1) / frame_count)
            if source_index not in selected_lookup:
                continue
            tile = Image.frombytes("RGB", frame_size, frame_bytes).convert("RGBA")
            tile = fit_frame(tile, target_size, video_fit, channel_mode)
            tile = apply_channel_mode(tile, channel_mode)
            x = (written % cols) * target_size
            y = (written // cols) * target_size
            canvas.paste(tile, (x, y))
            last_tile = tile.copy()
            written += 1
            if written == wanted:
                break
    except Exception as exc:
        raise RuntimeError(f"影片解碼失敗：{exc}") from exc
    finally:
        reader.close()

    if written < 1:
        raise RuntimeError("影片沒有成功解碼出任何影格。")
    if fill_empty_with_last and last_tile is not None:
        for index in range(written, cols * rows):
            canvas.paste(last_tile, ((index % cols) * target_size, (index // cols) * target_size))
    progress.update(95)

    output = Path(output_path).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise ValueError("Output filename must use the .png extension")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG")
    progress.update(100)
    return output, written


def make_flipbook(
    input_folder: str | Path,
    output_path: str | Path,
    cols: int,
    rows: int,
    target_size: int,
    channel_mode: str = "RGBA",
    fill_empty_with_last: bool = False,
    progress_callback: ProgressCallback | None = None,
    image_fit: str = "stretch",
) -> tuple[Path, int]:
    """Build a flipbook and return ``(output_path, frames_written)``.

    Frames are placed left-to-right, then top-to-bottom. This produces the same
    visible PNG order as the Blender implementation after accounting for
    Blender's bottom-up pixel buffer and Pillow's top-left image origin.
    """
    progress = _ProgressReporter(progress_callback)
    progress.update(0)
    if cols < 1 or rows < 1 or target_size < 1:
        raise ValueError("cols, rows, and target_size must all be at least 1")
    channel_mode = channel_mode.upper()
    if channel_mode not in CHANNEL_MODES:
        raise ValueError(f"channel_mode must be one of: {', '.join(CHANNEL_MODES)}")
    image_fit = image_fit.lower()
    if image_fit not in FRAME_FIT_MODES:
        raise ValueError(f"image_fit must be one of: {', '.join(FRAME_FIT_MODES)}")

    source = Path(input_folder).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    files = collect_image_files(source)
    if not files:
        raise ValueError(f"No supported images found in: {source}")

    capacity = cols * rows
    # A smaller grid intentionally keeps only the first frames. This mirrors a
    # fixed-capacity sprite sheet and makes the truncation behavior explicit.
    files_to_write = files[:capacity]
    fill_count = capacity - len(files_to_write) if fill_empty_with_last else 0
    work_items = max(1, len(files_to_write) + fill_count)
    completed_items = 0
    progress.update(5)

    canvas = Image.new("RGBA", (cols * target_size, rows * target_size),
                       (0, 0, 0, 0))
    last_tile: Image.Image | None = None
    for index, path in enumerate(files_to_write):
        try:
            with Image.open(path) as source_image:
                source_image.load()
                tile = source_image.convert("RGBA")
        except (UnidentifiedImageError, OSError) as exc:
            raise RuntimeError(
                f"Pillow could not read '{path}'. EXR is not supported by most "
                "Pillow builds; convert it to PNG/TIFF first. Details: {exc}"
            ) from exc

        tile = fit_frame(tile, target_size, image_fit, channel_mode)
        tile = apply_channel_mode(tile, channel_mode)
        last_tile = tile.copy()
        x = (index % cols) * target_size
        y = (index // cols) * target_size
        canvas.paste(tile, (x, y))
        completed_items += 1
        progress.update(5 + 85 * completed_items / work_items)

    if fill_empty_with_last and last_tile is not None:
        for index in range(len(files_to_write), capacity):
            x = (index % cols) * target_size
            y = (index // cols) * target_size
            canvas.paste(last_tile, (x, y))
            completed_items += 1
            progress.update(5 + 85 * completed_items / work_items)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() != ".png":
        raise ValueError("Output filename must use the .png extension")
    progress.update(95)
    canvas.save(output, format="PNG")
    progress.update(100)
    return output, len(files_to_write)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert an image sequence or MP4/MOV video into a PNG flipbook."
    )
    parser.add_argument("source", help="Image-sequence folder, one sequence image, or MP4/MOV video")
    parser.add_argument("output", help="Output PNG path")
    parser.add_argument("--cols", type=int, default=12, help="Grid columns (default: 12)")
    parser.add_argument("--rows", type=int, default=10, help="Grid rows (default: 10)")
    parser.add_argument("--tile-size", type=int, default=256,
                        help="Width and height of each frame (default: 256)")
    parser.add_argument("--mode", choices=CHANNEL_MODES, default="RGBA",
                        help="RGBA, RGB (opaque), or RGB_BLACK (over black)")
    parser.add_argument(
        "--fill-empty-with-last", action="store_true",
        help="Fill unused grid slots by repeating the final source image",
    )
    parser.add_argument("--start", type=float, default=0.0,
                        help="Video start time in seconds (default: 0)")
    parser.add_argument("--end", type=float, default=None,
                        help="Video end time in seconds (default: video end)")
    parser.add_argument("--video-fit", choices=VIDEO_FIT_MODES, default="crop",
                        help="Video frame fitting: crop, stretch, or pad (default: crop)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = Path(args.source).expanduser()
        if source.is_dir() or source.suffix.lower() in VALID_EXTENSIONS:
            output, count = make_flipbook(
                source, args.output, args.cols, args.rows,
                args.tile_size, args.mode, args.fill_empty_with_last,
            )
        elif source.suffix.lower() in VIDEO_EXTENSIONS:
            output, count = make_video_flipbook(
                source, args.output, args.cols, args.rows, args.tile_size,
                args.mode, args.fill_empty_with_last, args.start, args.end,
                args.video_fit,
            )
        else:
            raise ValueError(
                "Source must be an image folder, a supported image, or an MP4/MOV video file"
            )
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Flipbook created: {output} ({count} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
