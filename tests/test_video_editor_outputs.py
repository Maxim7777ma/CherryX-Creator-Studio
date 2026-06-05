from __future__ import annotations

from django.test import SimpleTestCase

from studio import views


class VideoEditorOutputActionTests(SimpleTestCase):
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
