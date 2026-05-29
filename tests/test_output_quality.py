from __future__ import annotations

import unittest
from pathlib import Path

import cv2
import numpy as np

from src import youtube_tools
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


if __name__ == "__main__":
    unittest.main()
