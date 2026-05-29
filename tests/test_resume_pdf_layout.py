from __future__ import annotations

import unittest

from src import bot


class ResumePdfLayoutTests(unittest.TestCase):
    def test_resume_skill_tags_are_unique_and_limited(self) -> None:
        tags = bot.resume_skill_tags("Python, SQL; python\nGit • Docker, SQL", limit=4)

        self.assertEqual(tags, ["Python", "SQL", "Git", "Docker"])

    def test_resume_link_lines_normalizes_common_separators(self) -> None:
        self.assertEqual(
            bot.resume_link_lines(" github.com/me, portfolio.dev\n- linkedin.com/in/me "),
            "github.com/me\nportfolio.dev\nlinkedin.com/in/me",
        )

    def test_resume_contact_items_detect_icons(self) -> None:
        items = bot.resume_contact_items({
            "contact": "+380 67 123 45 67 | ivan@example.com | @ivan_dev",
            "links": "instagram.com/ivan\nlinkedin.com/in/ivan\ngithub.com/ivan\nportfolio.dev",
        })

        icons = {item.icon for item in items}
        self.assertTrue({"TEL", "@", "TG", "IG", "IN", "GH", "WEB"}.issubset(icons))

    def test_resume_contact_table_is_created(self) -> None:
        styles = bot.build_resume_styles(bot.RESUME_TEMPLATES["1"])
        table = bot.build_resume_contact_table(
            {"contact": "+380 67 123 45 67 | ivan@example.com", "links": "instagram.com/ivan"},
            styles,
            bot.RESUME_TEMPLATES["1"],
            220,
        )

        self.assertIsNotNone(table)

    def test_resume_contact_icon_flowable_wraps_as_square(self) -> None:
        icon = bot.ResumeContactIconFlowable("instagram", bot.RESUME_TEMPLATES["1"], size=24)

        self.assertEqual(icon.wrap(100, 100), (24, 24))
        self.assertEqual(bot.resume_icon_color("telegram", bot.RESUME_TEMPLATES["1"]), "#229ED9")

    def test_resume_highlight_and_fill_blocks_are_created(self) -> None:
        styles = bot.build_resume_styles(bot.RESUME_TEMPLATES["1"])
        data = bot.resume_section_data({
            "name": "Ivan Test",
            "position": "Python Developer",
            "summary": "Builds reliable bots and automation.",
            "skills": "Python, SQL, Docker, Telegram bots",
        })

        highlights = bot.build_resume_highlight_strip(data, styles, bot.RESUME_TEMPLATES["1"], 180)
        filler = bot.build_resume_fill_panel(data, styles, bot.RESUME_TEMPLATES["1"], 180)

        self.assertTrue(highlights)
        self.assertTrue(filler)


class ResumePdfGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_resume_pdf_with_links(self) -> None:
        data = {
            "name": "Ivan Test",
            "position": "Python Developer",
            "contact": "ivan@example.com | @ivan",
            "links": "github.com/ivan\nportfolio.dev",
            "summary": "Builds reliable Telegram bots, automations and media tools.",
            "experience": "Acme / Developer / 2022-2025\n- Built bot flows\n- Improved conversion speed",
            "education": "Computer Science",
            "skills": "Python, SQL, Docker, aiogram, ffmpeg",
            "achievements": "Launched production bot\nReduced manual work",
            "additional": "English B2",
        }

        path = await bot.generate_resume_pdf(data, "4")
        try:
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
