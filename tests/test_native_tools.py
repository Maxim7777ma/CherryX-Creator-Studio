from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from src import native_tools


class NativeToolsTests(unittest.TestCase):
    def test_missing_helpers_are_safe_fallbacks(self) -> None:
        with patch.object(native_tools, "NATIVE_BIN", Path("missing-native-bin")):
            self.assertFalse(native_tools.helper_available("audio_rms"))
            self.assertEqual(native_tools.audio_rms_windows(Path("missing.mp4"), 0, 1, 0.5), [])
            self.assertEqual(native_tools.visual_moment_scores(Path("missing.mp4"), 10, 2), [])
            self.assertIsNone(native_tools.pick_cover_second(Path("missing.mp4"), 10, [{"start": 1}]))
            self.assertEqual(native_tools.face_track_points(Path("missing.mp4"), 0, 10), [])

    def test_capabilities_missing_manifest_is_empty(self) -> None:
        with patch.object(native_tools, "NATIVE_ROOT", Path("missing-native-root")):
            self.assertEqual(native_tools.capabilities(), {})


if __name__ == "__main__":
    unittest.main()
