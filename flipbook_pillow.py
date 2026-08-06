#!/usr/bin/env python3
"""Create a PNG flipbook from an image sequence or MP4/MOV video."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterator, Sequence

from PIL import Image, UnidentifiedImageError


VALID_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
CHANNEL_MODES = ("RGBA", "RGB", "RGB_BLACK")
VIDEO_FIT_MODES = ("crop", "stretch", "pad")


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


def collect_image_files(input_folder: Path) -> list[Path]:
    if not input_folder.is_dir():
        raise NotADirectoryError(f"Input folder does not exist: {input_folder}")
    files = [
        path for path in input_folder.iterdir()
        if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS
    ]
    return sorted(files, key=natural_sort_key)


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


def fit_video_frame(
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
        canvas.alpha_composite(resized, (left, top))
        return canvas
    if fit_mode != "crop":
        raise ValueError(f"video_fit must be one of: {', '.join(VIDEO_FIT_MODES)}")
    width, height = image.size
    scale = max(target_size / width, target_size / height)
    resized = image.resize(
        (max(target_size, round(width * scale)), max(target_size, round(height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - target_size) // 2
    top = (resized.height - target_size) // 2
    return resized.crop((left, top, left + target_size, top + target_size))


def _video_reader(path: Path, start: float, end: float) -> Iterator[object]:
    imageio_ffmpeg = _load_imageio_ffmpeg()
    return imageio_ffmpeg.read_frames(
        str(path),
        pix_fmt="rgb24",
        input_params=["-ss", f"{start:.6f}"],
        output_params=["-t", f"{end - start:.6f}", "-vsync", "0"],
    )


def _count_video_range(path: Path, start: float, end: float) -> tuple[int, tuple[int, int]]:
    reader = _video_reader(path, start, end)
    try:
        metadata = next(reader)
        size = tuple(metadata.get("size", (0, 0)))
        count = sum(1 for _frame in reader)
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
) -> tuple[Path, int]:
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

    try:
        frame_count, frame_size = _count_video_range(path, start, end)
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError(f"無法解碼指定的影片時間範圍：{exc}") from exc
    wanted = min(cols * rows, frame_count)
    selected_indices = _even_indices(frame_count, wanted)
    selected_lookup = set(selected_indices)
    canvas = Image.new("RGBA", (cols * target_size, rows * target_size), (0, 0, 0, 0))
    last_tile: Image.Image | None = None
    written = 0
    reader = _video_reader(path, start, end)
    try:
        next(reader)
        for source_index, frame_bytes in enumerate(reader):
            if source_index not in selected_lookup:
                continue
            tile = Image.frombytes("RGB", frame_size, frame_bytes).convert("RGBA")
            tile = fit_video_frame(tile, target_size, video_fit, channel_mode)
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

    output = Path(output_path).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise ValueError("Output filename must use the .png extension")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG")
    return output, written


def make_flipbook(
    input_folder: str | Path,
    output_path: str | Path,
    cols: int,
    rows: int,
    target_size: int,
    channel_mode: str = "RGBA",
    fill_empty_with_last: bool = False,
) -> tuple[Path, int]:
    """Build a flipbook and return ``(output_path, frames_written)``.

    Frames are placed left-to-right, then top-to-bottom. This produces the same
    visible PNG order as the Blender implementation after accounting for
    Blender's bottom-up pixel buffer and Pillow's top-left image origin.
    """
    if cols < 1 or rows < 1 or target_size < 1:
        raise ValueError("cols, rows, and target_size must all be at least 1")
    channel_mode = channel_mode.upper()
    if channel_mode not in CHANNEL_MODES:
        raise ValueError(f"channel_mode must be one of: {', '.join(CHANNEL_MODES)}")

    source = Path(input_folder).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    files = collect_image_files(source)
    if not files:
        raise ValueError(f"No supported images found in: {source}")

    capacity = cols * rows
    # A smaller grid intentionally keeps only the first frames. This mirrors a
    # fixed-capacity sprite sheet and makes the truncation behavior explicit.
    files_to_write = files[:capacity]

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

        if tile.size != (target_size, target_size):
            # The Blender add-on stretches each frame to an exact square too.
            tile = tile.resize((target_size, target_size), Image.Resampling.LANCZOS)
        tile = apply_channel_mode(tile, channel_mode)
        last_tile = tile.copy()
        x = (index % cols) * target_size
        y = (index // cols) * target_size
        canvas.paste(tile, (x, y))

    if fill_empty_with_last and last_tile is not None:
        for index in range(len(files_to_write), capacity):
            x = (index % cols) * target_size
            y = (index // cols) * target_size
            canvas.paste(last_tile, (x, y))

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() != ".png":
        raise ValueError("Output filename must use the .png extension")
    canvas.save(output, format="PNG")
    return output, len(files_to_write)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert an image sequence or MP4/MOV video into a PNG flipbook."
    )
    parser.add_argument("source", help="Image-sequence folder or MP4/MOV video")
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
        if source.is_dir():
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
            raise ValueError("Source must be an image folder or an MP4/MOV video file")
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Flipbook created: {output} ({count} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
