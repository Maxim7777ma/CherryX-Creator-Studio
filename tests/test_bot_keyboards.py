from __future__ import annotations

import unittest

from src import bot_keyboards


def inline_callback_data(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def inline_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


class KeyboardTests(unittest.TestCase):
    def test_main_menu_contains_core_actions_and_optional_mini_app(self) -> None:
        markup = bot_keyboards.main_menu("ru", subscription_stars=100, mini_app_url="https://example.com/app")

        self.assertEqual(inline_callback_data(markup), ["pay", "status", "help:menu", "help:resume", "language"])
        self.assertIn("Открыть Mini App", inline_texts(markup))

    def test_formats_keyboard_builds_convert_callbacks(self) -> None:
        markup = bot_keyboards.formats_keyboard("sess1", ["png", "webp"], "image")

        self.assertEqual(inline_callback_data(markup), ["convert:sess1:png", "convert:sess1:webp", "rename:sess1"])

    def test_video_formats_keyboard_adds_video_tools(self) -> None:
        markup = bot_keyboards.formats_keyboard("sess1", ["mp4"], "video")

        self.assertEqual(
            inline_callback_data(markup),
            ["convert:sess1:mp4", "rename:sess1", "cover_session:sess1", "video_help"],
        )

    def test_image_mode_keyboard_matches_convert_parser_contract(self) -> None:
        markup = bot_keyboards.image_mode_keyboard("sess1", "webp")

        self.assertEqual(
            inline_callback_data(markup),
            [
                "convert:sess1:webp:light",
                "convert:sess1:webp:balanced",
                "convert:sess1:webp:quality",
            ],
        )

    def test_youtube_mode_keyboard_callbacks(self) -> None:
        callbacks = inline_callback_data(bot_keyboards.youtube_mode_keyboard("job1"))

        self.assertIn("yt:download:job1", callbacks)
        self.assertIn("yt:dynamic:job1", callbacks)
        self.assertIn("yt:backstage90:job1", callbacks)
        self.assertIn("yt:cover:job1", callbacks)

    def test_subtitle_language_falls_back_to_pop_style(self) -> None:
        markup = bot_keyboards.subtitle_language_keyboard(
            "unknown",
            "job1",
            {"pop": "Pop"},
            {"auto": "Auto", "ru": "Русский"},
        )

        self.assertEqual(inline_callback_data(markup), ["cap:pop:auto:job1", "cap:pop:ru:job1", "capback:job1"])

    def test_share_keyboard_combines_optional_tools(self) -> None:
        callbacks = inline_callback_data(
            bot_keyboards.share_keyboard("sess1", "file.mp4", subtitle_job_id="sub1", cover_job_id="cover1")
        )

        self.assertIn("rename:sess1", callbacks)
        self.assertIn("cover:cover1", callbacks)
        self.assertIn("capstyle:pop:sub1", callbacks)

    def test_persistent_menu_labels_are_localized(self) -> None:
        self.assertEqual(bot_keyboards.persistent_menu_labels("en")["status"], "Status")
        self.assertEqual(bot_keyboards.persistent_menu_labels("uk")["help"], "Допомога")
        self.assertEqual(bot_keyboards.persistent_menu_labels("ru")["history"], "История")

    def test_resume_skip_keyboards(self) -> None:
        self.assertEqual(inline_callback_data(bot_keyboards.resume_achievements_skip_keyboard("ru")), ["resume_skip_achievements"])
        self.assertEqual(inline_callback_data(bot_keyboards.resume_additional_skip_keyboard("ru")), ["resume_skip_additional"])
        self.assertEqual(inline_callback_data(bot_keyboards.resume_links_skip_keyboard("ru")), ["resume_skip_links"])
        self.assertEqual(inline_callback_data(bot_keyboards.resume_photo_skip_keyboard("ru")), ["resume_photo_skip"])

    def test_resume_review_keyboard_callbacks(self) -> None:
        callbacks = inline_callback_data(bot_keyboards.resume_review_keyboard())

        self.assertEqual(callbacks[0:3], ["resume_choose_template", "resume_edit_photo", "resume_polish"])
        self.assertIn("resume_edit_experience", callbacks)
        self.assertIn("resume_edit_links", callbacks)
        self.assertIn("resume_remove_photo", callbacks)

    def test_resume_template_keyboard(self) -> None:
        templates = {
            "1": {"name": "Classic", "label": "clean"},
            "2": {"name": "Modern", "label": "accent"},
        }
        markup = bot_keyboards.resume_template_keyboard(templates)

        self.assertEqual(inline_callback_data(markup), ["template_1", "template_2", "resume_back_review"])
        self.assertIn("1. Classic — clean", inline_texts(markup))

    def test_resume_after_pdf_keyboard(self) -> None:
        self.assertEqual(
            inline_callback_data(bot_keyboards.resume_after_pdf_keyboard()),
            ["resume_choose_template_again", "resume_back_review", "resume_finish"],
        )


if __name__ == "__main__":
    unittest.main()
