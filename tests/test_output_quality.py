from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src import youtube_tools
from src import web_actions
from src.bot_utils import normalize_resume_text, repair_cyrillic_mojibake, resume_safe_text
from src.image_tools import JPEG_QUALITY_STEPS, WEBP_QUALITY_STEPS, _target_ratio
from src.video_tools import VIDEO_AUDIO_FILTER, VIDEO_SCALE_EVEN_FILTER


class OutputQualityDefaultsTests(unittest.TestCase):
    def test_video_conversion_quality_defaults(self) -> None:
        self.assertIn("trunc(iw/2)*2", VIDEO_SCALE_EVEN_FILTER)
        self.assertIn("flags=lanczos", VIDEO_SCALE_EVEN_FILTER)
        self.assertIn("loudnorm", VIDEO_AUDIO_FILTER)

    def test_image_quality_mode_stays_high_quality(self) -> None:
        self.assertGreaterEqual(min(WEBP_QUALITY_STEPS["quality"]), 80)
        self.assertGreaterEqual(min(JPEG_QUALITY_STEPS["quality"]), 88)
        self.assertEqual(_target_ratio("quality"), 1.0)

    def test_resume_text_repairs_cyrillic_mojibake_before_pdf(self) -> None:
        original = "Фінанси Україна Програмування Досвід роботи"
        mojibake = original.encode("utf-8").decode("cp1251")

        self.assertEqual(repair_cyrillic_mojibake(mojibake), original)
        self.assertIn("Україна", normalize_resume_text(mojibake))
        self.assertIn("Досвід роботи", resume_safe_text(mojibake))

    def test_vertical_shorts_filter_uses_lanczos(self) -> None:
        vf = youtube_tools.build_vertical_filter(
            Path("missing.mp4"),
            start_seconds=0,
            clip_seconds=10,
            width=1920,
            height=1080,
            focus_mode="center",
            face_detection_enabled=False,
        )

        self.assertIn("flags=lanczos", vf)
        self.assertIn("crop=1080:1920", vf)

    def test_vertical_fit_filter_keeps_full_frame_with_blurred_background(self) -> None:
        vf = youtube_tools.build_vertical_filter(
            Path("missing.mp4"),
            start_seconds=0,
            clip_seconds=10,
            width=1920,
            height=1080,
            focus_mode="fit",
            face_detection_enabled=False,
        )

        self.assertIn("boxblur", vf)
        self.assertIn("scale=270:480", vf)
        self.assertIn("force_original_aspect_ratio=decrease", vf)
        self.assertIn("overlay=(W-w)/2:(H-h)/2", vf)

    def test_wide_preview_uses_blurred_background_instead_of_black_bars(self) -> None:
        vf = youtube_tools._wide_preview_filter(5)

        self.assertIn("gblur", vf)
        self.assertIn("overlay=(W-w)/2:(H-h)/2", vf)
        self.assertIn("[vout]", vf)
        self.assertNotIn("pad=1280", vf)

    def test_youtube_encoding_quality_constants(self) -> None:
        self.assertEqual(youtube_tools.VIDEO_QUALITY_PRESET, "medium")
        self.assertLessEqual(int(youtube_tools.SHORTS_VIDEO_CRF), 21)
        self.assertLessEqual(int(youtube_tools.PREVIEW_VIDEO_CRF), 21)
        self.assertLessEqual(int(youtube_tools.SUBTITLE_VIDEO_CRF), 20)

    def test_youtube_download_prefers_h264_before_av1_mp4(self) -> None:
        fmt = youtube_tools._youtube_options(Path("."), 30)["format"]

        self.assertIn("vcodec^=avc1", fmt)
        self.assertIn("vcodec!*=av01", fmt)
        self.assertLess(fmt.index("vcodec^=avc1"), fmt.index("bv*[ext=mp4][height<=720]"))

    def test_requested_shorts_count_defaults_to_ten_and_clamps_to_server_limit(self) -> None:
        self.assertEqual(web_actions._normalize_requested_clip_count("", 15), 10)
        self.assertEqual(web_actions._normalize_requested_clip_count("3", 15), 3)
        self.assertLessEqual(web_actions._normalize_requested_clip_count("999", 15), web_actions.settings.youtube_max_shorts)

    def test_strict_render_probe_limit_uses_deep_candidate_queue(self) -> None:
        profile = web_actions.YouTubeProfile(
            mode="regular",
            label="Shorts classic",
            is_backstage=False,
            max_shorts=5,
            short_seconds=45,
            backstage_output_seconds=0,
            backstage_segment_seconds=0,
            backstage_intro_seconds=0,
            min_gap_seconds=45,
            sample_limit=240,
            strict_face=True,
        )

        self.assertEqual(web_actions._strict_render_probe_limit(profile), 40)

    def test_filter_unused_short_starts_skips_duplicates_and_nearby_done_clips(self) -> None:
        starts = web_actions._filter_unused_short_starts(
            [10, 12, 50, 50, 82],
            used_starts=[11],
            min_distance_seconds=5,
        )

        self.assertEqual(starts, [50, 82])

    def test_youtube_mode_profiles_carry_strict_focus_and_alignment(self) -> None:
        self.assertTrue(web_actions.youtube_render_profile("regular").strict_face)
        self.assertTrue(web_actions.youtube_render_profile("dynamic").strict_face)
        self.assertTrue(web_actions.youtube_render_profile("calm").strict_face)
        podcast = web_actions.youtube_render_profile("podcast")
        self.assertTrue(podcast.strict_face)
        self.assertEqual(podcast.alignment_mode, "podcast")
        self.assertFalse(web_actions.youtube_render_profile("backstage30").strict_face)

    def test_strict_selection_skips_weak_focus_candidates_without_fallback(self) -> None:
        starts = youtube_tools.select_smart_clip_starts_from_candidates(
            [
                {"start": 4, "score": 98, "strict_focus_ok": False},
                {"start": 38, "score": 72, "strict_focus_ok": True},
                {"start": 74, "score": 70, "strict_focus_ok": False},
            ],
            duration_seconds=120,
            max_clips=3,
            clip_seconds=20,
            strict_focus=True,
        )

        self.assertEqual(starts, [38])

    def test_strict_selection_probes_only_face_hint_candidates_without_base_fallback(self) -> None:
        starts = youtube_tools.select_smart_clip_starts_from_candidates(
            [
                {"start": 6, "score": 96, "strict_focus_ok": False, "focus_source": "face", "face_coverage": 0.12, "face_confidence": 0.14},
                {"start": 44, "score": 82, "strict_focus_ok": False, "focus_source": "none"},
                {"start": 72, "score": 78, "strict_focus_ok": False, "focus_source": "motion", "motion_focus_available": True},
            ],
            duration_seconds=130,
            max_clips=2,
            clip_seconds=20,
            strict_focus=True,
            allow_strict_probe=True,
        )

        self.assertEqual(starts, [6])

    def test_selection_uses_mode_gap_to_avoid_duplicate_moments(self) -> None:
        starts = youtube_tools.select_smart_clip_starts_from_candidates(
            [
                {"start": 10, "score": 100, "strict_focus_ok": True},
                {"start": 22, "score": 99, "strict_focus_ok": True},
                {"start": 72, "score": 85, "strict_focus_ok": True},
            ],
            duration_seconds=140,
            max_clips=2,
            clip_seconds=20,
            strict_focus=True,
            min_gap_seconds=35,
        )

        self.assertEqual(starts, [10, 72])

    def test_strict_focus_requires_speaker_lock_and_low_empty_risk(self) -> None:
        good = {
            "focus_source": "face",
            "focus_score": 0.55,
            "face_coverage": 0.4,
            "face_confidence": 0.35,
            "speaker_lock_score": 0.3,
            "empty_frame_risk": 0.42,
            "center_safety": 0.8,
            "size_safety": 0.7,
        }
        weak_speaker = {**good, "speaker_lock_score": 0.05}
        empty_risk = {**good, "empty_frame_risk": 0.9}
        side_face = {**good, "center_safety": 0.2}

        self.assertTrue(youtube_tools.candidate_has_strict_focus(good))
        self.assertFalse(youtube_tools.candidate_has_strict_focus(weak_speaker))
        self.assertFalse(youtube_tools.candidate_has_strict_focus(empty_risk))
        self.assertTrue(youtube_tools.candidate_has_strict_focus(side_face))

    def test_non_strict_selection_can_fill_from_fallback_starts(self) -> None:
        starts = youtube_tools.select_smart_clip_starts_from_candidates(
            [{"start": 12, "score": 90}],
            duration_seconds=120,
            max_clips=3,
            clip_seconds=20,
            strict_focus=False,
        )

        self.assertGreaterEqual(len(starts), 2)

    def test_best_effort_focus_fallback_ignores_center_only_candidates(self) -> None:
        starts = web_actions._select_best_effort_focus_starts(
            [
                {"start": 10, "score": 100, "focus_source": "none", "empty_frame_risk": 0.2},
                {
                    "start": 42,
                    "score": 90,
                    "focus_source": "face",
                    "face_coverage": 0.1,
                    "face_confidence": 0.14,
                    "focus_score": 0.2,
                    "empty_frame_risk": 0.4,
                },
            ],
            duration_seconds=180,
            max_clips=3,
            clip_seconds=20,
            min_gap_seconds=30,
        )

        self.assertEqual(starts, [42])

    def test_best_effort_focus_fallback_allows_motion_candidates(self) -> None:
        starts = web_actions._select_best_effort_focus_starts(
            [
                {"start": 10, "score": 100, "focus_source": "none", "empty_frame_risk": 0.2},
                {"start": 54, "score": 86, "focus_source": "none", "motion_focus_available": True, "empty_frame_risk": 0.4},
            ],
            duration_seconds=180,
            max_clips=3,
            clip_seconds=20,
            min_gap_seconds=30,
        )

        self.assertEqual(starts, [54])

    def test_best_effort_focus_fallback_prioritizes_person_candidates(self) -> None:
        starts = web_actions._select_best_effort_focus_starts(
            [
                {"start": 10, "score": 100, "focus_source": "none", "empty_frame_risk": 0.2},
                {"start": 58, "score": 82, "focus_source": "person", "person_focus_available": True, "person_focus_score": 0.42, "empty_frame_risk": 0.5},
            ],
            duration_seconds=180,
            max_clips=3,
            clip_seconds=20,
            min_gap_seconds=30,
        )

        self.assertEqual(starts, [58])

    def test_best_effort_focus_fallback_allows_visual_candidates(self) -> None:
        starts = web_actions._select_best_effort_focus_starts(
            [
                {"start": 10, "score": 100, "focus_source": "none", "empty_frame_risk": 0.2},
                {"start": 66, "score": 84, "focus_source": "visual", "visual_focus_available": True, "visual_focus_score": 0.32, "empty_frame_risk": 0.45},
            ],
            duration_seconds=180,
            max_clips=3,
            clip_seconds=20,
            min_gap_seconds=30,
        )

        self.assertEqual(starts, [66])

    def test_timeline_focus_fallback_scans_for_reels_focus_candidates(self) -> None:
        annotated = [
            {"start": 0, "score": 90, "focus_source": "none", "empty_frame_risk": 1.0},
            {"start": 60, "score": 88, "focus_source": "person", "person_focus_available": True, "person_focus_score": 0.44, "empty_frame_risk": 0.45},
            {"start": 120, "score": 82, "focus_source": "none", "empty_frame_risk": 1.0},
            {"start": 180, "score": 76, "focus_source": "visual", "visual_focus_available": True, "visual_focus_score": 0.36, "empty_frame_risk": 0.5},
        ]
        with patch.object(web_actions, "annotate_clip_candidate_focus", return_value=annotated) as annotate:
            starts, candidates = web_actions._select_timeline_focus_fallback_starts(
                Path("missing.mp4"),
                duration_seconds=200,
                max_clips=2,
                clip_seconds=20,
                min_gap_seconds=30,
                face_detection_enabled=True,
                selection_mode="regular",
                sample_count=4,
            )

        annotate.assert_called_once()
        self.assertEqual(starts, [60, 180])
        self.assertEqual(candidates, annotated)

    def test_guaranteed_short_starts_use_ranked_candidates_without_focus(self) -> None:
        starts = web_actions._select_guaranteed_short_starts(
            [
                {"start": 12, "score": 90, "focus_source": "none"},
                {"start": 74, "score": 70, "focus_source": "none"},
            ],
            duration_seconds=180,
            max_clips=2,
            clip_seconds=20,
            min_gap_seconds=30,
        )

        self.assertEqual(len(starts), 2)
        self.assertIn(12, starts)

    def test_focus_filter_can_fall_back_to_person_track(self) -> None:
        person_track = [youtube_tools.FaceTrackPoint(second=0, x=1260, y=430, width=420, height=520, confidence=0.44)]
        with patch.object(youtube_tools, "detect_face_track", return_value=[]), patch.object(
            youtube_tools,
            "_detect_person_focus_track",
            return_value=person_track,
        ), patch.object(youtube_tools, "_detect_visual_focus_track", return_value=[]):
            vf = youtube_tools.build_vertical_filter(
                Path("missing.mp4"),
                start_seconds=0,
                clip_seconds=10,
                width=1920,
                height=1080,
                focus_mode="focus",
                face_detection_enabled=True,
            )

        self.assertIn("crop=607:1080", vf)
        self.assertIn("scale=1080:1920", vf)

    def test_focus_filter_can_fall_back_to_visual_track(self) -> None:
        visual_track = [youtube_tools.FaceTrackPoint(second=0, x=1300, y=460, width=360, height=360, confidence=0.28)]
        with patch.object(youtube_tools, "detect_face_track", return_value=[]), patch.object(
            youtube_tools,
            "_detect_person_focus_track",
            return_value=[],
        ), patch.object(
            youtube_tools,
            "_detect_visual_focus_track",
            return_value=visual_track,
        ):
            vf = youtube_tools.build_vertical_filter(
                Path("missing.mp4"),
                start_seconds=0,
                clip_seconds=10,
                width=1920,
                height=1080,
                focus_mode="focus",
                face_detection_enabled=True,
            )

        self.assertIn("crop=607:1080", vf)
        self.assertIn("scale=1080:1920", vf)

    def test_focus_crop_positions_ignore_tiny_face_jitter(self) -> None:
        points = [
            youtube_tools.FaceTrackPoint(second=0, x=640, y=360, width=180, height=220, confidence=0.8),
            youtube_tools.FaceTrackPoint(second=2, x=646, y=360, width=180, height=220, confidence=0.8),
            youtube_tools.FaceTrackPoint(second=4, x=637, y=360, width=180, height=220, confidence=0.8),
            youtube_tools.FaceTrackPoint(second=6, x=642, y=360, width=180, height=220, confidence=0.8),
        ]
        positions = youtube_tools._face_safe_crop_positions(points, crop_size=405, source_size=1280, axis="x")

        self.assertEqual(len({offset for _second, offset in positions}), 1)

    def test_podcast_alignment_does_not_shorten_on_tiny_pause_before_end(self) -> None:
        with patch.object(youtube_tools, "align_clip_start_to_audio", return_value=10), patch.object(
            youtube_tools,
            "_find_nearby_audio_pause",
            return_value=54,
        ):
            start, duration = youtube_tools.align_clip_window_to_audio(
                Path("missing.mp4"),
                start_seconds=10,
                clip_seconds=50,
                duration_seconds=120,
                mode="podcast",
            )

        self.assertEqual(start, 10)
        self.assertEqual(duration, 50)

    def test_podcast_alignment_can_pull_start_to_phrase_beginning(self) -> None:
        with patch.object(youtube_tools, "_find_phrase_start_near", side_effect=[None, 13.0]), patch.object(
            youtube_tools,
            "_find_nearby_audio_pause",
            return_value=None,
        ):
            start = youtube_tools.align_clip_start_to_audio(
                Path("missing.mp4"),
                start_seconds=20,
                clip_seconds=50,
                duration_seconds=120,
                mode="podcast",
            )

        self.assertEqual(start, 13)

    def test_podcast_alignment_can_extend_to_natural_pause(self) -> None:
        with patch.object(youtube_tools, "align_clip_start_to_audio", return_value=10), patch.object(
            youtube_tools,
            "_find_nearby_audio_pause",
            return_value=63,
        ):
            _start, duration = youtube_tools.align_clip_window_to_audio(
                Path("missing.mp4"),
                start_seconds=10,
                clip_seconds=50,
                duration_seconds=120,
                mode="podcast",
            )

        self.assertEqual(duration, 53)

    def test_calm_alignment_can_extend_softly_to_natural_pause(self) -> None:
        with patch.object(youtube_tools, "align_clip_start_to_audio", return_value=10), patch.object(
            youtube_tools,
            "_find_nearby_audio_pause",
            return_value=63,
        ):
            _start, duration = youtube_tools.align_clip_window_to_audio(
                Path("missing.mp4"),
                start_seconds=10,
                clip_seconds=50,
                duration_seconds=120,
                mode="calm",
            )

        self.assertEqual(duration, 53)

    def test_phrase_end_after_finds_quiet_after_speech(self) -> None:
        windows = [
            (49.25, 320),
            (49.50, 340),
            (49.75, 330),
            (50.00, 310),
            (50.25, 305),
            (50.50, 95),
            (50.75, 85),
            (51.00, 80),
            (51.25, 78),
        ]
        with patch.object(youtube_tools, "_read_audio_rms_windows", return_value=windows):
            end = youtube_tools._find_phrase_end_after(Path("missing.mp4"), 50, after_seconds=3)

        self.assertIsNotNone(end)
        self.assertGreaterEqual(end, 50.3)

    def test_rendered_short_focus_validation_uses_final_crop(self) -> None:
        points = [
            youtube_tools.FaceTrackPoint(second=0, x=540, y=820, width=220, height=280, confidence=0.6),
            youtube_tools.FaceTrackPoint(second=2, x=545, y=830, width=220, height=280, confidence=0.62),
            youtube_tools.FaceTrackPoint(second=4, x=538, y=825, width=220, height=280, confidence=0.58),
        ]
        info = type("Info", (), {"width": 1080, "height": 1920, "duration_seconds": 6, "size_bytes": 1000})()
        with patch.object(youtube_tools, "detect_face_track", return_value=points), patch.object(youtube_tools, "inspect_video", return_value=info):
            result = youtube_tools.validate_rendered_short_focus(Path("short.mp4"), 6)

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["face_coverage"], 0.2)
        self.assertGreaterEqual(result["center_safety"], 0.4)
        self.assertGreaterEqual(result["size_safety"], 0.3)

    def test_rendered_short_focus_validation_rejects_edge_face(self) -> None:
        points = [
            youtube_tools.FaceTrackPoint(second=0, x=70, y=820, width=120, height=180, confidence=0.6),
            youtube_tools.FaceTrackPoint(second=2, x=72, y=825, width=120, height=180, confidence=0.6),
            youtube_tools.FaceTrackPoint(second=4, x=68, y=830, width=120, height=180, confidence=0.6),
        ]
        info = type("Info", (), {"width": 1080, "height": 1920, "duration_seconds": 6, "size_bytes": 1000})()
        with patch.object(youtube_tools, "detect_face_track", return_value=points), patch.object(youtube_tools, "inspect_video", return_value=info):
            result = youtube_tools.validate_rendered_short_focus(Path("short.mp4"), 6)

        self.assertFalse(result["ok"])
        self.assertIn("edge", result["reason"])

    def test_clip_window_ranking_prefers_strong_window_not_single_second(self) -> None:
        scores = [
            (0, 5.0),
            (5, 90.0),
            (10, 12.0),
            (45, 40.0),
            (50, 42.0),
            (55, 45.0),
            (60, 43.0),
        ]

        ranked = youtube_tools._rank_clip_windows(
            scores,
            duration_seconds=90,
            clip_seconds=20,
            step_seconds=5,
            lead_seconds=4,
        )

        self.assertTrue(ranked)
        self.assertGreaterEqual(ranked[0][0], 41)
        self.assertLessEqual(ranked[0][0], 51)

    def test_clip_window_modes_change_ranking_personality(self) -> None:
        scores = [
            (20, 12.0),
            (30, 105.0),
            (40, 10.0),
            (120, 48.0),
            (130, 52.0),
            (140, 50.0),
            (150, 49.0),
        ]

        dynamic = youtube_tools._rank_clip_windows(scores, 220, 30, 10, 5, selection_mode="dynamic")
        podcast = youtube_tools._rank_clip_windows(scores, 220, 30, 10, 5, selection_mode="podcast")

        self.assertTrue(dynamic)
        self.assertTrue(podcast)
        self.assertLess(dynamic[0][0], 60)
        self.assertGreaterEqual(podcast[0][0], 110)

    def test_local_peak_seconds_detects_peaks(self) -> None:
        peaks = youtube_tools._local_peak_seconds([(0, 1), (5, 10), (10, 3), (15, 12), (20, 2)], 5)

        self.assertEqual(peaks[:2], [15, 5])

    def test_diverse_clip_selection_spreads_good_moments(self) -> None:
        ranked = [
            (40, 100.0),
            (52, 96.0),
            (64, 94.0),
            (170, 88.0),
            (300, 84.0),
        ]

        selected = youtube_tools._select_diverse_ranked_starts(
            ranked,
            max_clips=3,
            min_gap_seconds=10,
            duration_seconds=360,
            clip_seconds=12,
        )

        self.assertEqual(len(selected), 3)
        self.assertIn(40, selected)
        self.assertIn(170, selected)
        self.assertIn(300, selected)

    def test_timeline_edge_penalty_discourages_intro_and_outro(self) -> None:
        middle = youtube_tools._timeline_edge_penalty(120, duration_seconds=300, clip_seconds=10)
        intro = youtube_tools._timeline_edge_penalty(0, duration_seconds=300, clip_seconds=10)
        outro = youtube_tools._timeline_edge_penalty(290, duration_seconds=300, clip_seconds=10)

        self.assertEqual(middle, 1.0)
        self.assertLess(intro, middle)
        self.assertLess(outro, middle)

    def test_visual_frame_interest_rewards_clear_colorful_frames(self) -> None:
        dull = np.full((90, 160, 3), 8, dtype=np.uint8)
        vivid = np.zeros((90, 160, 3), dtype=np.uint8)
        vivid[:, :80] = (30, 220, 40)
        vivid[:, 80:] = (230, 40, 210)

        dull_score = youtube_tools._visual_frame_interest_score(dull, cv2.cvtColor(dull, cv2.COLOR_BGR2GRAY))
        vivid_score = youtube_tools._visual_frame_interest_score(vivid, cv2.cvtColor(vivid, cv2.COLOR_BGR2GRAY))

        self.assertGreater(vivid_score, dull_score)

    def test_face_moment_score_prefers_clear_centered_face(self) -> None:
        centered = youtube_tools._face_moment_score([(430, 220, 220, 220)], 1080, 720)
        edge = youtube_tools._face_moment_score([(8, 20, 120, 120)], 1080, 720)

        self.assertGreater(centered, edge)

    def test_speaker_face_selection_can_switch_to_active_talker(self) -> None:
        previous = np.zeros((720, 1080), dtype=np.uint8)
        current = previous.copy()
        faces = [(210, 220, 180, 190), (690, 220, 180, 190)]
        x, y, w, h = faces[1]
        current[int(y + h * 0.50):int(y + h * 0.96), int(x + w * 0.14):int(x + w * 0.86)] = 255
        previous_point = youtube_tools.FaceTrackPoint(0, 300, 315, 180, 190, 0.8)

        selected = youtube_tools._select_speaker_face(faces, 1080, 720, current, previous, previous_point)

        self.assertIsNotNone(selected)
        self.assertGreater(selected[0], 600)

    def test_audio_moment_score_rewards_hook_after_pause(self) -> None:
        windows = []
        for index in range(48):
            second = index * 0.5
            if 5 <= second < 8:
                rms = 80
            elif 8 <= second < 11:
                rms = 860 if index % 2 == 0 else 620
            elif 22 <= second < 27:
                rms = 430
            else:
                rms = 130
            windows.append((second, rms))

        with patch.object(youtube_tools, "_read_audio_rms_windows", return_value=windows):
            scores = youtube_tools._score_audio_moments(Path("missing.mp4"), 30, 2, "dynamic")

        self.assertTrue(scores)
        best_second = max(scores, key=lambda item: item[1])[0]
        self.assertGreaterEqual(best_second, 8)
        self.assertLessEqual(best_second, 10)

    def test_clip_speech_activity_rewards_continuous_voice(self) -> None:
        active = [(index * 0.5, 420 + (index % 3) * 90) for index in range(20)]
        quiet = [(index * 0.5, 35 if index % 2 else 55) for index in range(20)]

        with patch.object(youtube_tools, "_read_audio_rms_windows", return_value=active):
            active_score = youtube_tools._clip_speech_activity_score(Path("missing.mp4"), 0, 10)
        with patch.object(youtube_tools, "_read_audio_rms_windows", return_value=quiet):
            quiet_score = youtube_tools._clip_speech_activity_score(Path("missing.mp4"), 0, 10)

        self.assertGreater(active_score, quiet_score)

    def test_cover_variant_profiles_are_distinct_and_editable(self) -> None:
        first = youtube_tools._cover_variant_profile("Big product launch", (920, 310), 1, 123)
        second = youtube_tools._cover_variant_profile("Big product launch", (920, 310), 2, 123)

        self.assertNotEqual(first["layout"], second["layout"])
        self.assertIn(first["mood"], {"premium", "neon", "urgent", "clean"})
        self.assertTrue(first["badge"])
        self.assertIn("panel_x", first)


if __name__ == "__main__":
    unittest.main()
