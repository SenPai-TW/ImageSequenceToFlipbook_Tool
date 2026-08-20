from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


GUI_PATH = Path(__file__).resolve().parents[1] / "flipbook_gui.pyw"
SPEC = importlib.util.spec_from_file_location("flipbook_gui_for_tests", GUI_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load GUI module from {GUI_PATH}")
GUI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUI)


class GridSummaryTests(unittest.TestCase):
    def test_both_themes_define_minimal_scrollbar_colors(self) -> None:
        required = {
            "scrollbar_track",
            "scrollbar_thumb",
            "scrollbar_thumb_hover",
            "scrollbar_thumb_pressed",
        }
        for palette in GUI.THEME_PALETTES.values():
            self.assertTrue(required.issubset(palette))

    def test_small_screen_window_height_never_exceeds_available_space(self) -> None:
        self.assertEqual(
            GUI.calculate_window_height(
                requested_height=760,
                screen_height=600,
                reserved_height=96,
            ),
            504,
        )

    def test_calculates_power_of_two_texture_dimensions(self) -> None:
        self.assertEqual(
            GUI.calculate_full_size(8, 8, 256), (2048, 2048, True)
        )
        self.assertEqual(
            GUI.calculate_full_size(4, 8, 256), (1024, 2048, True)
        )

    def test_flags_when_either_texture_dimension_is_not_a_power_of_two(self) -> None:
        self.assertEqual(
            GUI.calculate_full_size(3, 8, 256), (768, 2048, False)
        )
        self.assertEqual(
            GUI.calculate_full_size(4, 8, 300), (1200, 2400, False)
        )

    def test_zero_and_negative_dimensions_are_not_powers_of_two(self) -> None:
        self.assertFalse(GUI.is_power_of_two(0))
        self.assertFalse(GUI.is_power_of_two(-2))


class SourceClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary_directory.name) / "中文 source folder"
        self.folder.mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_distinguishes_image_file_folder_and_video(self) -> None:
        image = self.folder / "smoke_001.png"
        video = self.folder / "smoke.mov"
        image.touch()
        video.touch()

        self.assertEqual(GUI.classify_source_path(image), GUI.SOURCE_IMAGE_FILE)
        self.assertEqual(GUI.classify_source_path(self.folder), GUI.SOURCE_IMAGE_FOLDER)
        self.assertEqual(GUI.classify_source_path(video), GUI.SOURCE_VIDEO)

    def test_rejects_empty_folder_and_unsupported_file(self) -> None:
        unsupported = self.folder / "notes.txt"
        unsupported.touch()

        self.assertIsNone(GUI.classify_source_path(self.folder))
        self.assertIsNone(GUI.classify_source_path(unsupported))
        self.assertIsNone(GUI.classify_source_path(self.folder / "missing.png"))

    def test_native_dialog_start_folder_uses_current_source_only(self) -> None:
        image = self.folder / "frame.png"
        image.touch()

        self.assertEqual(GUI.source_dialog_initial_directory(str(image)), str(self.folder.resolve()))
        self.assertEqual(GUI.source_dialog_initial_directory(str(self.folder)), str(self.folder.resolve()))
        self.assertIsNone(GUI.source_dialog_initial_directory(""))
        self.assertIsNone(GUI.source_dialog_initial_directory(str(self.folder / "missing.png")))


class NativeSourceDialogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary_directory.name) / "中文 source folder"
        self.folder.mkdir()
        self.app = None
        with mock.patch.object(GUI, "TkinterDnD", None):
            try:
                self.app = GUI.FlipbookApp()
            except GUI.tk.TclError as exc:
                self.skipTest(f"Tk runtime is unavailable: {exc}")
        self.app.withdraw()
        self.app.update_idletasks()

    def tearDown(self) -> None:
        if self.app is not None:
            self.app.update_idletasks()
            self.app._close()
        self.temporary_directory.cleanup()

    def _select_type(self, source_kind: str) -> None:
        self.app.source_type_var.set(GUI.SOURCE_TYPE_LABELS[source_kind])

    def test_each_source_type_uses_the_matching_native_dialog(self) -> None:
        image = self.folder / "frame_001.png"
        video = self.folder / "clip.mp4"
        image.touch()
        video.touch()

        cases = (
            (GUI.SOURCE_IMAGE_FILE, "askopenfilename", image),
            (GUI.SOURCE_IMAGE_FOLDER, "askdirectory", self.folder),
            (GUI.SOURCE_VIDEO, "askopenfilename", video),
        )
        for source_kind, dialog_name, selected in cases:
            with self.subTest(source_kind=source_kind):
                self._select_type(source_kind)
                apply_source = mock.Mock()
                self.app._apply_source = apply_source
                with mock.patch.object(
                    GUI.filedialog, dialog_name, return_value=str(selected)
                ) as dialog:
                    self.app._choose_source()

                apply_source.assert_called_once_with(
                    selected, source_kind, reset_output=False
                )
                options = dialog.call_args.kwargs
                self.assertIs(options["parent"], self.app)
                if source_kind == GUI.SOURCE_IMAGE_FOLDER:
                    self.assertTrue(options["mustexist"])
                else:
                    self.assertIn("filetypes", options)

    def test_cancel_keeps_current_source(self) -> None:
        self.app.source_var.set("keep-this-source")
        self._select_type(GUI.SOURCE_IMAGE_FILE)
        self.app._apply_source = mock.Mock()

        with mock.patch.object(GUI.filedialog, "askopenfilename", return_value=""):
            self.app._choose_source()

        self.assertEqual(self.app.source_var.get(), "keep-this-source")
        self.app._apply_source.assert_not_called()

    def test_empty_folder_warns_and_keeps_current_source(self) -> None:
        self.app.source_var.set("keep-this-source")
        self._select_type(GUI.SOURCE_IMAGE_FOLDER)
        self.app._apply_source = mock.Mock()

        with (
            mock.patch.object(GUI.filedialog, "askdirectory", return_value=str(self.folder)),
            mock.patch.object(GUI.messagebox, "showwarning") as warning,
        ):
            self.app._choose_source()

        self.assertEqual(self.app.source_var.get(), "keep-this-source")
        self.app._apply_source.assert_not_called()
        warning.assert_called_once()

    def test_source_type_change_clears_incompatible_state(self) -> None:
        self.app.source_var.set(str(self.folder / "old.png"))
        self.app._source_count = 9
        self.app._video_metadata = {"duration": 1.0}
        self._select_type(GUI.SOURCE_VIDEO)

        self.app._source_type_changed()

        self.assertEqual(self.app.source_var.get(), "")
        self.assertEqual(self.app._source_count, 0)
        self.assertIsNone(self.app._video_metadata)
        self.assertEqual(self.app.count_var.get(), "請選擇 MP4 或 MOV 影片")

        self._select_type(GUI.SOURCE_IMAGE_FOLDER)
        self.app._source_type_changed()
        self.assertEqual(self.app.count_var.get(), "請選擇包含序列圖片的資料夾")

    def test_video_fit_defaults_to_blank_canvas_padding(self) -> None:
        label = "延伸空白畫布至正方形"

        self.assertEqual(self.app.fit_var.get(), label)
        self.assertEqual(GUI.FIT_LABELS[label], "pad")

    def test_frame_fit_is_permanent_and_only_time_range_toggles(self) -> None:
        self.assertEqual(self.app.video_options.cget("text"), "時間範圍")
        self.assertTrue(self.app.fit_label.grid_info())
        self.assertTrue(self.app.fit_combo.grid_info())
        self.assertFalse(self.app.video_options.grid_info())

        self._select_type(GUI.SOURCE_VIDEO)
        self.app._source_type_changed()
        self.assertTrue(self.app.video_options.grid_info())
        self.assertTrue(self.app.fit_combo.grid_info())

        self._select_type(GUI.SOURCE_IMAGE_FOLDER)
        self.app._source_type_changed()
        self.assertFalse(self.app.video_options.grid_info())
        self.assertTrue(self.app.fit_combo.grid_info())

    def test_fit_controls_and_descriptions_use_aligned_two_column_layout(self) -> None:
        mode_grid = self.app.mode_combo.grid_info()
        fit_label_grid = self.app.fit_label.grid_info()
        fit_grid = self.app.fit_combo.grid_info()
        left_detail_grid = self.app.detail_canvas.grid_info()
        right_detail_grid = self.app.fit_detail_canvas.grid_info()

        self.assertEqual((int(mode_grid["row"]), int(mode_grid["column"])), (2, 1))
        self.assertEqual(
            (int(fit_label_grid["row"]), int(fit_label_grid["column"])), (2, 2)
        )
        self.assertEqual((int(fit_grid["row"]), int(fit_grid["column"])), (2, 3))
        self.assertEqual(int(left_detail_grid["row"]), int(right_detail_grid["row"]))
        self.assertEqual(int(left_detail_grid["column"]), 0)
        self.assertEqual(int(right_detail_grid["column"]), 2)
        self.assertEqual(right_detail_grid["padx"], 0)
        self.assertEqual(
            self.app.detail_canvas.coords(self.app.detail_title_id)[0], 0.0
        )
        self.assertEqual(
            self.app.detail_canvas.coords(self.app.detail_text_id)[0], 0.0
        )
        self.assertEqual(
            self.app.fit_detail_canvas.coords(self.app.fit_detail_title_id)[0], 0.0
        )
        self.assertEqual(
            self.app.fit_detail_canvas.coords(self.app.fit_detail_text_id)[0], 0.0
        )
        self.assertEqual(
            int(self.app.detail_canvas.cget("height")),
            int(self.app.fit_detail_canvas.cget("height")),
        )
        self.assertEqual(
            self.app.detail_canvas.itemcget(self.app.detail_text_id, "fill"),
            self.app.fit_detail_canvas.itemcget(self.app.fit_detail_text_id, "fill"),
        )
        self.assertEqual(
            self.app.detail_canvas.itemcget(self.app.detail_text_id, "font"),
            self.app.fit_detail_canvas.itemcget(self.app.fit_detail_text_id, "font"),
        )

    def test_fit_description_updates_for_each_option(self) -> None:
        for label, description in GUI.FIT_DESCRIPTIONS.items():
            with self.subTest(label=label):
                self.app.fit_var.set(label)
                self.assertEqual(self.app.fit_detail_var.get(), description)
                self.assertEqual(
                    self.app.fit_detail_canvas.itemcget(
                        self.app.fit_detail_text_id, "text"
                    ),
                    description,
                )

    def test_generation_forwards_frame_fit_to_images_and_video(self) -> None:
        callbacks: list[tuple[object, ...]] = []

        def record_after(*args: object) -> str:
            callbacks.append(args)
            return "callback"

        with (
            mock.patch.object(self.app, "after", side_effect=record_after),
            mock.patch.object(
                GUI, "make_flipbook", return_value=(self.folder / "image.png", 1)
            ) as make_images,
        ):
            self.app._generate(
                "source", "output.png", 1, 1, 4, "RGBA", False,
                False, 0.0, None, "pad",
            )
        self.assertEqual(make_images.call_args.kwargs["image_fit"], "pad")

        with (
            mock.patch.object(self.app, "after", side_effect=record_after),
            mock.patch.object(
                GUI, "make_video_flipbook", return_value=(self.folder / "video.png", 1)
            ) as make_video,
        ):
            self.app._generate(
                "source", "output.png", 1, 1, 4, "RGBA", False,
                True, 0.0, 1.0, "crop",
            )
        self.assertEqual(make_video.call_args.args[9], "crop")

    def test_grid_defaults_to_eight_by_eight(self) -> None:
        self.assertEqual(self.app.cols_var.get(), 8)
        self.assertEqual(self.app.rows_var.get(), 8)
        self.assertIn("8 × 8 = 64", self.app.capacity_var.get())
        self.assertEqual(
            self.app.full_size_var.get(), "完整尺寸：2048 × 2048 pixel"
        )
        self.assertEqual(self.app.power_of_two_warning.winfo_manager(), "")

    def test_main_content_uses_a_vertical_scroll_viewport(self) -> None:
        self.assertIs(self.app.main_frame.master, self.app.viewport_canvas)
        self.assertIsNotNone(self.app._viewport_window_id)
        self.assertEqual(
            self.app.viewport_scrollbar.cget("style"),
            "Minimal.Vertical.TScrollbar",
        )
        scrollbar_layout = str(
            self.app._style.layout("Minimal.Vertical.TScrollbar")
        )
        self.assertIn("thumb", scrollbar_layout.lower())
        self.assertNotIn("arrow", scrollbar_layout.lower())
        self.assertEqual(self.app.minsize(), (720, 360))

        self.app.viewport_canvas.configure(height=240)
        self.app.update_idletasks()
        self.app._update_viewport_scroll_region()
        bounds = self.app.viewport_canvas.bbox("all")

        self.assertIsNotNone(bounds)
        self.assertGreater(bounds[3] - bounds[1], 240)

    def test_full_size_and_power_of_two_warning_update_immediately(self) -> None:
        self.app.cols_var.set(3)
        self.app.update_idletasks()

        self.assertEqual(
            self.app.full_size_var.get(), "完整尺寸：768 × 2048 pixel"
        )
        self.assertEqual(
            self.app.power_of_two_warning.winfo_manager(), "grid"
        )
        self.assertEqual(
            int(self.app.full_size_label.grid_info()["column"]), 2
        )
        self.assertEqual(
            int(self.app.fit_label.grid_info()["column"]), 2
        )
        self.assertEqual(
            int(self.app.power_of_two_warning.grid_info()["column"]), 3
        )

        self.app.cols_var.set(4)
        self.app.update_idletasks()

        self.assertEqual(
            self.app.full_size_var.get(), "完整尺寸：1024 × 2048 pixel"
        )
        self.assertEqual(self.app.power_of_two_warning.winfo_manager(), "")

        self.app.size_var.set(300)
        self.app.update_idletasks()

        self.assertEqual(
            self.app.full_size_var.get(), "完整尺寸：1200 × 2400 pixel"
        )
        self.assertEqual(
            self.app.power_of_two_warning.winfo_manager(), "grid"
        )

    def test_theme_toggle_is_in_the_top_right_and_defaults_to_dark(self) -> None:
        grid = self.app.theme_toggle_canvas.grid_info()

        self.assertEqual(self.app.theme_var.get(), GUI.THEME_DARK)
        self.assertEqual((int(grid["row"]), int(grid["column"])), (0, 0))
        self.assertIn("e", str(grid["sticky"]))
        self.assertEqual(int(self.app.theme_toggle_canvas.cget("width")), 34)
        self.assertEqual(int(self.app.theme_toggle_canvas.cget("height")), 20)
        self.assertEqual(self.app._theme_knob_x, 9.0)

    def test_light_theme_applies_palette_to_widgets_and_can_switch_back(self) -> None:
        light = GUI.THEME_PALETTES[GUI.THEME_LIGHT]
        dark = GUI.THEME_PALETTES[GUI.THEME_DARK]

        self.app._set_theme(GUI.THEME_LIGHT, animate=False)

        self.assertEqual(self.app.theme_var.get(), GUI.THEME_LIGHT)
        self.assertEqual(self.app.cget("background").upper(), light["window_bg"])
        self.assertEqual(
            self.app._style.lookup("TEntry", "fieldbackground").upper(),
            light["input_bg"],
        )
        self.assertEqual(
            self.app._style.lookup("Primary.TButton", "background").upper(),
            light["primary_button"],
        )
        self.assertEqual(
            self.app.detail_canvas.cget("background").upper(),
            light["section_bg"],
        )
        self.assertEqual(
            self.app.detail_canvas.itemcget(self.app.detail_text_id, "fill").upper(),
            light["helper_text"],
        )
        popdown = self.app.tk.call(
            "ttk::combobox::PopdownWindow", str(self.app.mode_combo)
        )
        self.assertEqual(
            self.app.tk.call(f"{popdown}.f.l", "cget", "-background").upper(),
            light["input_bg"],
        )
        self.assertEqual(self.app._theme_knob_x, 25.0)

        self.app._set_theme(GUI.THEME_DARK, animate=False)
        self.assertEqual(self.app.cget("background").upper(), dark["window_bg"])
        self.assertEqual(self.app._theme_knob_x, 9.0)

    def test_progress_bar_is_determinate_and_resets_after_completion(self) -> None:
        self.assertEqual(str(self.app.progress.cget("mode")), "determinate")
        self.assertEqual(float(self.app.progress.cget("maximum")), 100.0)

        self.app._set_progress(64.6)
        self.assertEqual(self.app.progress_var.get(), 65)
        self.assertEqual(self.app.progress_text_var.get(), "65%")

        self.app._busy = True
        self.app._finish_common()
        self.assertFalse(self.app._busy)
        self.assertEqual(self.app.progress_var.get(), 0)
        self.assertEqual(self.app.progress_text_var.get(), "0%")

    def test_drop_auto_selects_the_matching_source_type(self) -> None:
        image = self.folder / "frame_001.png"
        video = self.folder / "clip.mov"
        image.touch()
        video.touch()

        cases = (
            (image, GUI.SOURCE_IMAGE_FILE),
            (self.folder, GUI.SOURCE_IMAGE_FOLDER),
            (video, GUI.SOURCE_VIDEO),
        )
        for source, source_kind in cases:
            with self.subTest(source_kind=source_kind):
                apply_source = mock.Mock()
                self.app._apply_source = apply_source
                result = self.app._on_drop(SimpleNamespace(data=(str(source),)))

                self.assertEqual(result, GUI.COPY)
                apply_source.assert_called_once_with(
                    source.resolve(), source_kind, reset_output=True
                )

    def test_file_drag_enter_previews_before_the_path_is_available(self) -> None:
        self.app._show_overlay = mock.Mock()
        event = SimpleNamespace(
            data="", types=(GUI.DND_FILES,), type=GUI.DND_FILES
        )

        result = self.app._on_drop_enter(event)

        self.assertEqual(result, GUI.COPY)
        self.app._show_overlay.assert_called_once_with()
        self.assertTrue(self.app._drag_valid)

    def test_empty_enter_data_previews_without_platform_type_metadata(self) -> None:
        self.app._show_overlay = mock.Mock()

        result = self.app._on_drop_enter(SimpleNamespace(data=""))

        self.assertEqual(result, GUI.COPY)
        self.app._show_overlay.assert_called_once_with()

    def test_child_overlay_is_sized_when_it_is_primed(self) -> None:
        overlay = mock.Mock()
        self.app._overlay = overlay
        self.app._overlay_ready = False
        self.app._overlay_prime_after_id = "prime-callback"
        self.app._animate_overlay = mock.Mock()

        with mock.patch.object(self.app, "bind", return_value="configure-binding"):
            self.app._prime_overlay()

        overlay.resize.assert_called_once_with(
            self.app.winfo_width(), self.app.winfo_height()
        )
        overlay.set_alpha.assert_called_once_with(0.0)
        self.assertTrue(self.app._overlay_ready)

        overlay.reset_mock()
        self.app._show_overlay()
        overlay.resize.assert_not_called()
        self.app._animate_overlay.assert_called_once_with(
            GUI.OVERLAY_ALPHA, GUI.OVERLAY_FADE_IN_MS
        )

        self.app._overlay_alpha = GUI.OVERLAY_ALPHA
        self.app._finish_overlay_hide()
        overlay.set_alpha.assert_called_with(0.0)

    def test_invalid_drop_fades_preview_and_shakes_without_applying(self) -> None:
        unsupported = self.folder / "notes.txt"
        unsupported.touch()
        self.app.source_var.set("keep-this-source")
        self.app._apply_source = mock.Mock()
        self.app._hide_overlay = mock.Mock()
        self.app._queue_shake = mock.Mock()

        result = self.app._on_drop(SimpleNamespace(data=(str(unsupported),)))

        self.assertEqual(result, GUI.REFUSE_DROP)
        self.assertEqual(self.app.source_var.get(), "keep-this-source")
        self.app._apply_source.assert_not_called()
        self.app._hide_overlay.assert_called_once_with(
            animated=True, duration_ms=GUI.OVERLAY_REJECT_FADE_MS
        )
        self.app._queue_shake.assert_called_once_with()

    def test_drop_validation_result_is_cached_during_one_drag(self) -> None:
        image = self.folder / "frame_001.png"
        image.touch()

        with mock.patch.object(
            GUI, "classify_source_path", wraps=GUI.classify_source_path
        ) as classify:
            first = self.app._drop_item((str(image),))
            second = self.app._drop_item((str(image),))

        self.assertEqual(first, second)
        classify.assert_called_once_with(image)

    def test_overlay_uses_bounded_monotonic_alpha_updates(self) -> None:
        class FakeOverlay:
            def __init__(self) -> None:
                self.visible = True
                self.alpha_values: list[float] = []

            def set_alpha(self, value: float) -> None:
                self.alpha_values.append(value)

            def destroy(self) -> None:
                self.visible = False

        overlay = FakeOverlay()
        self.app._overlay = overlay
        self.app._overlay_alpha = 0.0
        self.app._overlay_target = 0.0
        clock = [0.0]
        callbacks: list[object] = []

        def queue_callback(delay: int, callback: object) -> str:
            self.assertEqual(delay, GUI.OVERLAY_FRAME_MS)
            callbacks.append(callback)
            return f"callback-{len(callbacks)}"

        with (
            mock.patch.object(GUI.time, "perf_counter", side_effect=lambda: clock[0]),
            mock.patch.object(self.app, "after", side_effect=queue_callback),
        ):
            self.app._animate_overlay(GUI.OVERLAY_ALPHA, GUI.OVERLAY_FADE_IN_MS)
            while callbacks:
                clock[0] += GUI.OVERLAY_FRAME_MS / 1000
                callbacks.pop(0)()

        values = overlay.alpha_values
        self.assertGreater(len(values), 2)
        self.assertLessEqual(len(values), 10)
        self.assertTrue(all(left <= right for left, right in zip(values, values[1:])))
        self.assertAlmostEqual(values[-1], GUI.OVERLAY_ALPHA)
        self.assertIsNone(self.app._overlay_after_id)


if __name__ == "__main__":
    unittest.main()
