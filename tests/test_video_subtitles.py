from __future__ import annotations

from django.test import SimpleTestCase

from studio import views
from src.youtube_tools import SubtitleCue, _normalize_caption_text, _split_segment_text_into_cues, normalize_subtitle_language


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

    def test_video_clip_base_filter_uses_reframe_values(self) -> None:
        clip = {"x": 82, "y": 18, "scale": 145, "style": {"fit": "crop"}}
        filter_text = views._video_clip_base_filter(clip, 720, 1280)
        self.assertIn("scale=1044:1856:force_original_aspect_ratio=increase", filter_text)
        self.assertIn("crop=720:1280:(iw-ow)*0.820000:(ih-oh)*0.180000", filter_text)

    def test_auto_subtitles_maps_asset_cues_to_timeline(self) -> None:
        cues = views._normalize_auto_subtitle_cues(
            [
                SubtitleCue(1.0, 2.0, "before clip"),
                SubtitleCue(3.25, 4.0, "first line"),
                SubtitleCue(4.8, 5.4, "clipped line"),
            ],
            {"timeline_start": 10, "source_start": 3, "source_end": 5, "clip_duration": 2},
        )

        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0], {"start": 10.25, "end": 11.0, "text": "First line"})
        self.assertEqual(cues[1], {"start": 11.8, "end": 12.0, "text": "Clipped line"})

    def test_subtitle_language_aliases_normalize_for_whisper(self) -> None:
        self.assertEqual(normalize_subtitle_language("ua"), "uk")
        self.assertEqual(normalize_subtitle_language("pt-BR"), "pt")
        self.assertEqual(normalize_subtitle_language("zh_CN"), "zh")
        self.assertIsNone(normalize_subtitle_language("auto"))
        self.assertIsNone(normalize_subtitle_language("not-a-language"))

    def test_caption_text_polishing_removes_spacing_noise(self) -> None:
        self.assertEqual(_normalize_caption_text(" hello  ,  hello   world ... "), "Hello, hello world…")

    def test_long_segment_text_splits_into_readable_cues(self) -> None:
        cues = _split_segment_text_into_cues(0, 6, "hello world. this is a longer sentence for subtitles")

        self.assertGreaterEqual(len(cues), 2)
        self.assertTrue(all(cue.end > cue.start for cue in cues))
        self.assertEqual(cues[0].text, "Hello world.")


if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "test", "tests.test_video_subtitles"])
