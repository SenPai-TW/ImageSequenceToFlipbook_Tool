#!/usr/bin/env python3
"""Create a PNG flipbook (sprite sheet) from an image sequence using Pillow.

Designed for Python 3.11 and Pillow 12.3.0. This is the standalone version of
the "image sequence to flipbook" feature from SenPaiToolBox; Blender is not
required.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

from PIL import Image, UnidentifiedImageError


VALID_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr"}
CHANNEL_MODES = ("RGBA", "RGB", "RGB_BLACK")


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
        description="Convert an image sequence into a PNG flipbook using Pillow."
    )
    parser.add_argument("input_folder", help="Folder containing sequence frames")
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output, count = make_flipbook(
            args.input_folder, args.output, args.cols, args.rows,
            args.tile_size, args.mode, args.fill_empty_with_last,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Flipbook created: {output} ({count} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
