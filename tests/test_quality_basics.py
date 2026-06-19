from __future__ import annotations

import unittest
from unittest.mock import patch

from src.config import parse_env_int, parse_id_set
from src.i18n import SUPPORTED_LANGS, lang_from_code, tr
from src.image_tools import clean_base_name, human_size, normalize_image_mode


MOJIBAKE_MARKERS = ("Рџ", "Рќ", "РЎ", "Рґ", "СЊ", "вЂ", "�")


class TranslationQualityTests(unittest.TestCase):
    def test_core_translations_are_readable(self) -> None:
        keys = (
            "pay",
            "status",
            "help_button",
            "resume_button",
            "next_steps",
            "start",
            "help",
        )
        for lang in SUPPORTED_LANGS:
            for key in keys:
                text = tr(lang, key, stars=100, days=30, image_mb=25, video_mb=80, yt_minutes=360, shorts=15, short_seconds=45)
                self.assertTrue(text.strip(), f"{lang}.{key} is empty")
                self.assertFalse(
                    any(marker in text for marker in MOJIBAKE_MARKERS),
                    f"{lang}.{key} looks mojibaked: {text[:80]}",
                )

    def test_language_detection_defaults_to_english(self) -> None:
        self.assertEqual(lang_from_code("ru-RU"), "ru")
        self.assertEqual(lang_from_code("uk"), "uk")
        self.assertEqual(lang_from_code("de"), "de")
        self.assertEqual(lang_from_code("fr-FR"), "fr")
        self.assertEqual(lang_from_code("es"), "es")
        self.assertEqual(lang_from_code(None), "en")


class HelperQualityTests(unittest.TestCase):
    def test_parse_id_set_ignores_bad_values(self) -> None:
        self.assertEqual(parse_id_set("1, 2; bad,3,, 2"), {1, 2, 3})

    def test_parse_env_int_uses_defaults_and_minimums(self) -> None:
        with patch.dict("os.environ", {"BAD_INT": "nope", "LOW_INT": "-10", "GOOD_INT": "42"}, clear=False):
            self.assertEqual(parse_env_int("BAD_INT", 7, min_value=1), 7)
            self.assertEqual(parse_env_int("LOW_INT", 7, min_value=0), 0)
            self.assertEqual(parse_env_int("GOOD_INT", 7, min_value=1), 42)
            self.assertEqual(parse_env_int("MISSING_INT", 9, min_value=1), 9)

    def test_file_name_and_size_helpers_are_stable(self) -> None:
        self.assertEqual(clean_base_name("..//bad:name?.png"), "bad_name")
        self.assertEqual(clean_base_name("   "), "converted")
        self.assertEqual(human_size(1536), "1.5 KB")
        self.assertEqual(normalize_image_mode("unknown"), "balanced")

if __name__ == "__main__":
    unittest.main()
