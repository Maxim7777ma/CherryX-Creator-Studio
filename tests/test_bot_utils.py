from __future__ import annotations

from dataclasses import dataclass
import time
import unittest

from src.bot_utils import (
    action_media_types_for,
    build_subscription_payload,
    cover_prompt_preview,
    day_start_timestamp,
    expired_mapping_keys,
    image_weight_note,
    normalize_cover_prompt_text,
    normalize_resume_text,
    normalize_subtitle_language,
    parse_convert_callback_data,
    polish_resume_block,
    polish_resume_skills,
    publication_description,
    publication_hashtags,
    re_words,
    resume_clip,
    resume_is_empty,
    resume_safe_text,
    resume_section_data,
    unique_archive_name,
    valid_subscription_payload,
)


class SubscriptionPayloadTests(unittest.TestCase):
    def test_builds_and_validates_payload(self) -> None:
        payload = build_subscription_payload(user_id=42, days=30, stars=100, created_at=1_700_000_000)

        self.assertEqual(payload, "subscription:42:30:100:1700000000")
        self.assertTrue(
            valid_subscription_payload(
                payload,
                expected_days=30,
                expected_stars=100,
                user_id=42,
                now=1_700_000_000,
            )
        )

    def test_rejects_bad_payloads(self) -> None:
        now = 1_700_000_000
        self.assertFalse(valid_subscription_payload("", 30, 100, now=now))
        self.assertFalse(valid_subscription_payload("subscription:bad:30:100:1", 30, 100, now=now))
        self.assertFalse(valid_subscription_payload("subscription:7:30:100:1", 30, 100, user_id=8, now=now))
        self.assertFalse(valid_subscription_payload("subscription:7:31:100:1", 30, 100, user_id=7, now=now))
        self.assertFalse(valid_subscription_payload("subscription:7:30:99:1", 30, 100, user_id=7, now=now))
        self.assertFalse(valid_subscription_payload("subscription:7:30:100:1700001000", 30, 100, user_id=7, now=now))


class CallbackParsingTests(unittest.TestCase):
    def test_parses_convert_callback(self) -> None:
        parsed = parse_convert_callback_data("convert:abc123:webp:quality")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.session_id, "abc123")
        self.assertEqual(parsed.target_format, "webp")
        self.assertEqual(parsed.image_mode, "quality")

    def test_parses_convert_callback_without_mode(self) -> None:
        parsed = parse_convert_callback_data("convert:abc123:mp4")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.session_id, "abc123")
        self.assertEqual(parsed.target_format, "mp4")
        self.assertIsNone(parsed.image_mode)

    def test_rejects_invalid_convert_callback(self) -> None:
        self.assertIsNone(parse_convert_callback_data(None))
        self.assertIsNone(parse_convert_callback_data("rename:abc"))
        self.assertIsNone(parse_convert_callback_data("convert::webp"))
        self.assertIsNone(parse_convert_callback_data("convert:abc:"))
        self.assertIsNone(parse_convert_callback_data("convert:abc:webp:quality:extra"))


class LimitAndSessionTests(unittest.TestCase):
    def test_action_media_types_are_copied(self) -> None:
        first = action_media_types_for("youtube")
        first.append("mutated")

        self.assertEqual(action_media_types_for("youtube"), ["youtube_shorts", "youtube_backstage", "youtube_preview"])
        self.assertEqual(action_media_types_for("unknown"), [])

    def test_day_start_timestamp_returns_local_midnight(self) -> None:
        now = time.mktime((2026, 5, 5, 15, 30, 45, 0, 0, -1))
        start = day_start_timestamp(now)
        local = time.localtime(start)

        self.assertEqual((local.tm_year, local.tm_mon, local.tm_mday), (2026, 5, 5))
        self.assertEqual((local.tm_hour, local.tm_min, local.tm_sec), (0, 0, 0))

    def test_expired_mapping_keys(self) -> None:
        @dataclass
        class Item:
            expires_at: int

        items = {
            "old": Item(10),
            "now": Item(20),
            "future": Item(21),
        }

        self.assertEqual(expired_mapping_keys(items, 20, lambda item: item.expires_at), ["old", "now"])


class ContentHelperTests(unittest.TestCase):
    def test_cover_prompt_is_normalized_and_limited(self) -> None:
        raw = "  Большой   заголовок\r\n\r\n  описание   с   пробелами  "
        self.assertEqual(normalize_cover_prompt_text(raw), "Большой заголовок\nописание с пробелами")
        self.assertEqual(normalize_cover_prompt_text("   "), "")

        long_text = "слово " * 80
        normalized = normalize_cover_prompt_text(long_text, limit=40)
        self.assertLessEqual(len(normalized), 40)
        self.assertFalse(normalized.endswith(" "))

    def test_cover_prompt_preview(self) -> None:
        self.assertEqual(cover_prompt_preview(""), "без текста")
        self.assertEqual(cover_prompt_preview("Заголовок"), "Заголовок: Заголовок")
        self.assertEqual(
            cover_prompt_preview("Заголовок\nОписание\nеще"),
            "Заголовок: Заголовок\nОписание: Описание еще",
        )

    def test_subtitle_language_normalization(self) -> None:
        self.assertEqual(normalize_subtitle_language(" RU "), "ru")
        self.assertEqual(normalize_subtitle_language("uk"), "uk")
        self.assertEqual(normalize_subtitle_language("en"), "en")
        self.assertIsNone(normalize_subtitle_language("auto"))
        self.assertIsNone(normalize_subtitle_language("de"))

    def test_image_weight_note(self) -> None:
        self.assertIn("Экономия", image_weight_note(1000, 700))
        self.assertIn("30%", image_weight_note(1000, 700))
        self.assertIn("Файл стал тяжелее", image_weight_note(1000, 1200))
        self.assertIn("Файл стал тяжелее", image_weight_note(0, 1))

    def test_publication_text_helpers(self) -> None:
        words = re_words("Тест, Apple-2026! Ґанок і відео")
        self.assertEqual(words, ["Тест", "Apple", "2026", "Ґанок", "і", "відео"])

        tags = publication_hashtags("Apple Apple тестовое видео для канала")
        self.assertEqual(tags[:2], ["#shorts", "#video"])
        self.assertEqual(tags.count("#apple"), 1)
        self.assertLessEqual(len(tags), 8)

        description = publication_description(
            "  Мой ролик  ",
            "1:30",
            ["#shorts", "#video"],
            "субтитры готовы",
        )
        self.assertIn("Мой ролик", description)
        self.assertIn("Длительность: 1:30", description)
        self.assertIn("#shorts #video", description)

    def test_unique_archive_name_avoids_collisions(self) -> None:
        used = {"clip.mp4", "clip_1.mp4", ".env"}

        self.assertEqual(unique_archive_name("fresh.mp4", used), "fresh.mp4")
        self.assertEqual(unique_archive_name("clip.mp4", used), "clip_2.mp4")
        self.assertEqual(unique_archive_name(".env", used), ".env_1")


class ResumeTextHelperTests(unittest.TestCase):
    def test_resume_text_normalization_and_html_safety(self) -> None:
        self.assertEqual(normalize_resume_text("  one   two \n\n three\tfour "), "one two\nthree four")
        self.assertEqual(resume_safe_text("A < B\nC & D"), "A &lt; B<br/>C &amp; D")

    def test_resume_empty_values(self) -> None:
        for value in ("", "нет", "No", "none", "n/a", "NA", "-"):
            self.assertTrue(resume_is_empty(value))
        self.assertFalse(resume_is_empty("есть"))

    def test_resume_clip(self) -> None:
        self.assertEqual(resume_clip("short", limit=10), "short")
        self.assertEqual(resume_clip("1234567890", limit=6), "12345…")

    def test_polish_resume_block(self) -> None:
        raw = " • сделал первое \n - сделал второе "
        self.assertEqual(polish_resume_block(raw), "сделал первое\nсделал второе")
        self.assertEqual(polish_resume_block(raw, bulletize=True), "- сделал первое\n- сделал второе")

    def test_polish_resume_skills(self) -> None:
        raw = " Python; SQL • python\nGit,  SQL "
        self.assertEqual(polish_resume_skills(raw), "Python, SQL, Git")

    def test_resume_section_data(self) -> None:
        prepared = resume_section_data({
            "name": "  Ivan  ",
            "links": " github.com/ivan \n portfolio.dev ",
            "skills": "Python; SQL",
            "achievements": "нет",
            "additional": "n/a",
        })

        self.assertEqual(prepared["name"], "Ivan")
        self.assertEqual(prepared["links"], "github.com/ivan\nportfolio.dev")
        self.assertEqual(prepared["skills"], "Python, SQL")
        self.assertEqual(prepared["achievements"], "")
        self.assertEqual(prepared["additional"], "")
        self.assertEqual(prepared["position"], "")


if __name__ == "__main__":
    unittest.main()
