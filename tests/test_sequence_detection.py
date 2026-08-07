from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import flipbook_pillow as flipbook
from flipbook_pillow import collect_image_files, detect_image_sequence, make_flipbook


class SequenceDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def create(self, *names: str) -> None:
        for name in names:
            (self.folder / name).touch()

    def names(self, paths: list[Path]) -> list[str]:
        return [path.name for path in paths]

    def test_uses_last_numeric_run_and_natural_sort(self) -> None:
        self.create(
            "smoke_v2_1.png", "smoke_v2_003.png", "smoke_v2_12.png",
            "smoke_v3_4.png", "smoke_v2_alt_4.png",
        )
        result = detect_image_sequence(self.folder / "smoke_v2_003.png")
        self.assertEqual(
            self.names(result),
            ["smoke_v2_1.png", "smoke_v2_003.png", "smoke_v2_12.png"],
        )

    def test_preserves_suffix_and_extension(self) -> None:
        self.create(
            "fire_1_left.png", "fire_02_left.png", "fire_3_right.png",
            "fire_4_left.jpg",
        )
        result = detect_image_sequence(self.folder / "fire_02_left.png")
        self.assertEqual(self.names(result), ["fire_1_left.png", "fire_02_left.png"])

    def test_file_without_number_is_a_single_image(self) -> None:
        self.create("still.png", "still-copy.png")
        result = collect_image_files(self.folder / "still.png")
        self.assertEqual(self.names(result), ["still.png"])

    def test_folder_collects_all_supported_images_only(self) -> None:
        self.create("frame10.png", "frame2.jpg", "notes.txt", "clip.mp4")
        (self.folder / "nested").mkdir()
        (self.folder / "nested" / "frame1.png").touch()
        result = collect_image_files(self.folder)
        self.assertEqual(self.names(result), ["frame2.jpg", "frame10.png"])

    def test_make_flipbook_accepts_one_sequence_image(self) -> None:
        first = self.folder / "spark_1.png"
        second = self.folder / "spark_02.png"
        unrelated = self.folder / "other_3.png"
        Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(first)
        Image.new("RGBA", (2, 2), (0, 255, 0, 255)).save(second)
        Image.new("RGBA", (2, 2), (0, 0, 255, 255)).save(unrelated)
        output = self.folder / "result.png"

        saved, count = make_flipbook(first, output, 2, 1, 2)

        self.assertEqual(saved, output.resolve())
        self.assertEqual(count, 2)
        with Image.open(output) as result:
            self.assertEqual(result.size, (4, 2))
            self.assertEqual(result.getpixel((0, 0)), (255, 0, 0, 255))
            self.assertEqual(result.getpixel((2, 0)), (0, 255, 0, 255))

    def test_shared_frame_fit_preserves_video_helper_compatibility(self) -> None:
        self.assertIs(flipbook.fit_video_frame, flipbook.fit_frame)

        source = Image.new("RGBA", (4, 2), (255, 0, 0, 255))
        stretched = flipbook.fit_frame(source, 4, "stretch")
        cropped = flipbook.fit_frame(source, 4, "crop")
        padded = flipbook.fit_frame(source, 4, "pad", "RGBA")

        self.assertEqual(stretched.size, (4, 4))
        self.assertEqual(cropped.size, (4, 4))
        self.assertEqual(cropped.getpixel((2, 2)), (255, 0, 0, 255))
        self.assertEqual(padded.getpixel((2, 0)), (0, 0, 0, 0))
        self.assertEqual(padded.getpixel((2, 1)), (255, 0, 0, 255))

    def test_pad_uses_transparency_only_for_rgba_output(self) -> None:
        source = Image.new("RGBA", (4, 2), (255, 0, 0, 128))

        rgba = flipbook.fit_frame(source, 4, "pad", "RGBA")
        rgb = flipbook.fit_frame(source, 4, "pad", "RGB")
        premultiplied = flipbook.fit_frame(source, 4, "pad", "RGB_BLACK")

        self.assertEqual(rgba.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(rgb.getpixel((0, 0)), (0, 0, 0, 255))
        self.assertEqual(premultiplied.getpixel((0, 0)), (0, 0, 0, 255))
        self.assertEqual(
            flipbook.apply_channel_mode(rgb, "RGB").getpixel((0, 1)),
            (255, 0, 0, 255),
        )
        self.assertEqual(
            flipbook.apply_channel_mode(premultiplied, "RGB_BLACK").getpixel((0, 1)),
            (128, 0, 0, 255),
        )

    def test_image_generation_supports_all_fit_modes_and_keeps_legacy_default(self) -> None:
        source = self.folder / "wide.png"
        Image.new("RGBA", (4, 2), (255, 0, 0, 255)).save(source)

        for fit_mode in flipbook.FRAME_FIT_MODES:
            output = self.folder / f"{fit_mode}.png"
            make_flipbook(source, output, 1, 1, 4, image_fit=fit_mode)
            with Image.open(output) as result:
                self.assertEqual(result.size, (4, 4))

        with Image.open(self.folder / "pad.png") as padded:
            self.assertEqual(padded.getpixel((2, 0)), (0, 0, 0, 0))
        with Image.open(self.folder / "stretch.png") as stretched:
            self.assertEqual(stretched.getpixel((2, 0)), (255, 0, 0, 255))

        legacy_output = self.folder / "legacy.png"
        make_flipbook(source, legacy_output, 1, 1, 4)
        with Image.open(legacy_output) as legacy:
            self.assertEqual(legacy.getpixel((2, 0)), (255, 0, 0, 255))

    def test_rejects_missing_or_unsupported_file(self) -> None:
        self.create("notes.txt")
        with self.assertRaises(ValueError):
            collect_image_files(self.folder / "notes.txt")
        with self.assertRaises(FileNotFoundError):
            collect_image_files(self.folder / "missing.png")

    def test_image_generation_reports_monotonic_progress(self) -> None:
        first = self.folder / "frame_1.png"
        second = self.folder / "frame_2.png"
        Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(first)
        Image.new("RGBA", (2, 2), (0, 255, 0, 255)).save(second)
        progress: list[int] = []

        make_flipbook(
            self.folder, self.folder / "progress.png", 2, 1, 2,
            progress_callback=progress.append,
        )

        self.assertEqual(progress[0], 0)
        self.assertEqual(progress[-1], 100)
        self.assertEqual(progress, sorted(set(progress)))
        self.assertIn(95, progress)

    def test_video_generation_reports_both_decode_passes(self) -> None:
        video = self.folder / "clip.mp4"
        video.touch()
        frame_bytes = bytes((255, 0, 0)) * 4

        def reader():
            yield {"size": (2, 2)}
            yield frame_bytes
            yield frame_bytes
            yield frame_bytes

        progress: list[int] = []
        with (
            mock.patch.object(
                flipbook, "_read_video_metadata",
                return_value={"duration": 1.0, "fps": 3.0},
            ),
            mock.patch.object(
                flipbook, "_video_reader", side_effect=[reader(), reader()]
            ),
        ):
            flipbook.make_video_flipbook(
                video, self.folder / "video-progress.png", 3, 1, 2,
                video_fit="pad", progress_callback=progress.append,
            )

        self.assertEqual(progress[0], 0)
        self.assertEqual(progress[-1], 100)
        self.assertEqual(progress, sorted(set(progress)))
        self.assertIn(35, progress)
        self.assertIn(95, progress)


if __name__ == "__main__":
    unittest.main()
