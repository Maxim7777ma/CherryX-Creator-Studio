from __future__ import annotations

from django.test import SimpleTestCase

from studio import views


class VideoSubtitleFormatTests(SimpleTestCase):
    def test_parse_srt_and_render_vtt(self) -> None:
        cues = views._parse_subtitle_cues(
            "1\n00:00:01,500 --> 00:00:03,000\nHello <b>world</b>\n\n"
            "2\n00:00:04.000 --> 00:00:05.250\nSecond line\n",
            "sample.srt",
        )
        self.assertEqual(cues[0], {"start": 1.5, "end": 3.0, "text": "Hello world"})
        self.assertIn("00:00:04.000 --> 00:00:05.250", views._render_vtt(cues))

    def test_parse_ass_and_render_srt(self) -> None:
        cues = views._parse_subtitle_cues(
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:02.10,0:00:04.35,Default,,0,0,0,,First\\NSecond\n",
            "sample.ass",
        )
        self.assertEqual(cues, [{"start": 2.1, "end": 4.35, "text": "First\nSecond"}])
        self.assertIn("00:00:02,100 --> 00:00:04,350", views._render_srt(cues))


if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "test", "tests.test_video_subtitles"])
