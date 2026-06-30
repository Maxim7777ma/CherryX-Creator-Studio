from __future__ import annotations

from datetime import timedelta
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from pathlib import Path
from unittest.mock import patch

from studio import views
from studio.management.commands.run_worker import Command, RUNNING_RECOVERY_GRACE_SECONDS
from studio.models import JobEventRecord, JobRecord
from src.youtube_tools import SubtitleCue, SubtitleUnavailableError, _extract_whisper_audio, _normalize_caption_text, _split_segment_text_into_cues, normalize_subtitle_language


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

    def test_rich_caption_cues_keep_editor_style(self) -> None:
        state = {
            "aspect": "9 / 16",
            "subtitleWorkflow": {"style": "kinetic"},
            "clips": [
                {
                    "type": "caption",
                    "start": 1,
                    "duration": 2,
                    "text": "Editable caption",
                    "x": 52,
                    "y": 76,
                    "boxWidth": 44,
                    "style": {"size": 36, "color": "#ffffff", "stroke": "#db2777", "strokeWidth": 2, "bgAlpha": 0},
                    "subtitleSource": {"kind": "generated", "jobId": "job1", "style": "kinetic"},
                }
            ],
        }

        cues = views._video_project_caption_cues(state, rich=True)
        self.assertEqual(cues[0]["x"], 52)
        self.assertEqual(cues[0]["boxWidth"], 44)
        self.assertEqual(cues[0]["style"]["stroke"], "#db2777")
        self.assertEqual(cues[0]["source"]["kind"], "generated")

        ass = views._render_ass(cues, state)
        self.assertIn(r"\pos(", ass)
        self.assertIn(r"\3c&H00", ass)
        self.assertIn(r"\t(0,160,\fscx108\fscy108)", ass)

    def test_video_clip_base_filter_uses_reframe_values(self) -> None:
        clip = {"x": 82, "y": 18, "scale": 145, "style": {"fit": "crop"}}
        filter_text = views._video_clip_base_filter(clip, 720, 1280)
        self.assertIn("scale=1044:1856:force_original_aspect_ratio=increase", filter_text)
        self.assertIn("crop=720:1280:(iw-ow)*0.820000:(ih-oh)*0.180000", filter_text)

    def test_mp4_drawtext_position_uses_editor_coordinates(self) -> None:
        x_expr, y_expr = views._ffmpeg_drawtext_xy({"x": 25, "y": 84}, 1080, 1920)

        self.assertEqual(x_expr, "270-text_w/2")
        self.assertEqual(y_expr, "1612-text_h/2")

    def test_mp4_drawtext_position_allows_off_canvas_text(self) -> None:
        x_expr, y_expr = views._ffmpeg_drawtext_xy({"x": -20, "y": 128}, 1080, 1920)

        self.assertEqual(x_expr, "-216-text_w/2")
        self.assertEqual(y_expr, "2457-text_h/2")

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

    def test_auto_subtitles_transcribes_only_selected_source_window(self) -> None:
        start, duration, params = views._auto_subtitle_transcription_window(
            {"timeline_start": 10, "source_start": 941, "source_end": 1001, "clip_duration": 60}
        )

        self.assertEqual(start, 941)
        self.assertEqual(duration, 60)
        self.assertEqual(params["source_start"], 0.0)
        self.assertEqual(params["source_end"], 60)

        cues = views._normalize_auto_subtitle_cues([SubtitleCue(0.25, 1.0, "selected line")], params)
        self.assertEqual(cues[0], {"start": 10.25, "end": 11.0, "text": "Selected line"})

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

    def test_whisper_audio_extract_reports_missing_audio(self) -> None:
        with patch("src.youtube_tools.has_audio_stream", return_value=False):
            with self.assertRaisesMessage(SubtitleUnavailableError, "No audio stream found"):
                _extract_whisper_audio(Path("silent.mp4"))


class VideoSubtitleJobRecordTests(TestCase):
    def test_video_export_job_update_writes_database_without_memory_job(self) -> None:
        views._video_export_jobs.pop("subjob1", None)
        record = JobRecord.objects.create(
            job_id="subjob1",
            kind="video_subtitles",
            title="Auto subtitles",
            status="running",
            progress=2,
            message="Worker claimed task",
        )

        views._set_video_export_job("subjob1", status="done", progress=100, message="Subtitles added: 2", error="")

        record.refresh_from_db()
        self.assertEqual(record.status, "completed")
        self.assertEqual(record.progress, 100)
        self.assertEqual(record.message, "Subtitles added: 2")
        self.assertEqual(record.error, "")
        self.assertTrue(JobEventRecord.objects.filter(job=record, status="completed", progress=100).exists())

    def test_worker_recovery_leaves_fresh_running_jobs_alone(self) -> None:
        fresh = JobRecord.objects.create(
            job_id="fresh1",
            kind="video_subtitles",
            title="Fresh subtitles",
            status="running",
            progress=10,
            message="Transcribing audio",
        )
        stale = JobRecord.objects.create(
            job_id="stale1",
            kind="video_subtitles",
            title="Stale subtitles",
            status="running",
            progress=10,
            message="Transcribing audio",
        )
        JobRecord.objects.filter(id=stale.id).update(updated_at=timezone.now() - timedelta(seconds=RUNNING_RECOVERY_GRACE_SECONDS + 5))

        self.assertEqual(Command()._recover_interrupted_jobs(), 1)

        fresh.refresh_from_db()
        stale.refresh_from_db()
        self.assertEqual(fresh.status, "running")
        self.assertEqual(stale.status, "queued")


if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "test", "tests.test_video_subtitles"])
