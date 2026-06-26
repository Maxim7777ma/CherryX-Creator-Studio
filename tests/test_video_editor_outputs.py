from __future__ import annotations

from django.test import SimpleTestCase

from studio import views


class VideoEditorOutputActionTests(SimpleTestCase):
    def test_youtube_modes_have_canonical_english_labels_and_hints(self) -> None:
        modes = views._localized_youtube_modes("en")
        by_value = {item["value"]: item for item in modes}

        self.assertEqual(
            [(item["value"], item["label"], item["hint"]) for item in modes],
            [
                ("regular", "Shorts classic", "Balanced shorts for most videos"),
                ("dynamic", "Shorts dynamic", "Fast cuts, stronger hooks and more motion"),
                ("podcast", "Shorts podcast", "Keeps speech flow for interviews and talk videos"),
                ("calm", "Shorts calm", "Softer pacing for lessons, stories and quiet clips"),
                ("backstage30", "Preview 30s", "Wide preview montage for market pages and clients"),
                ("backstage60", "Preview 60s", "Wide preview montage for market pages and clients"),
                ("backstage90", "Preview 90s", "Wide preview montage for market pages and clients"),
                ("download", "Download MP4", "Download a clean MP4 source without cutting"),
                ("cover", "PNG cover", "Create a PNG cover from the video"),
            ],
        )
        self.assertEqual(by_value["regular"]["icon"], "classic")
        self.assertEqual(by_value["backstage90"]["icon"], "backstage")

    def test_mp4_short_output_can_open_in_video_editor(self) -> None:
        self.assertTrue(
            views._output_can_edit_video(
                {"name": "clip_short_01.mp4", "label": "Short 1", "media_type": "video/mp4"},
                {"kind": "youtube"},
            )
        )

    def test_zip_output_cannot_open_in_video_editor(self) -> None:
        self.assertFalse(
            views._output_can_edit_video(
                {"name": "shorts.zip", "label": "ZIP: 10 Shorts", "media_type": "application/zip"},
                {"kind": "youtube"},
            )
        )
