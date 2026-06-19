from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .i18n import tr


def main_menu(lang: str, subscription_stars: int, mini_app_url: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=tr(lang, "pay", stars=subscription_stars), callback_data="pay")
    builder.button(text=tr(lang, "status"), callback_data="status")
    builder.button(text=tr(lang, "wallet"), callback_data="wallet")
    builder.button(text=tr(lang, "support"), callback_data="help:pay")
    builder.button(text=tr(lang, "language"), callback_data="language")
    if mini_app_url:
        builder.button(text=tr(lang, "open_app"), web_app=WebAppInfo(url=mini_app_url))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def help_navigation_keyboard(lang: str, subscription_stars: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Файлы", callback_data="help:files"),
            InlineKeyboardButton(text="YouTube", callback_data="help:youtube"),
        ],
        [
            InlineKeyboardButton(text=tr(lang, "resume_button"), callback_data="help:resume"),
            InlineKeyboardButton(text="Subtitles", callback_data="help:subtitles"),
        ],
        [
            InlineKeyboardButton(text="Pro / Stars", callback_data="help:pro"),
            InlineKeyboardButton(text=tr(lang, "status"), callback_data="status"),
        ],
        [InlineKeyboardButton(text=tr(lang, "pay", stars=subscription_stars), callback_data="pay")],
    ])


def persistent_menu_labels(lang: str = "ru") -> dict[str, str]:
    return {
        "pay": "Pay Stars",
        "status": "Status",
        "wallet": "Wallet",
        "help": "Support",
        "language": "Language",
    }


def persistent_menu_keyboard(lang: str, mini_app_url: str = "") -> ReplyKeyboardMarkup:
    labels = persistent_menu_labels(lang)
    rows = [
        [KeyboardButton(text=labels["pay"]), KeyboardButton(text=labels["status"])],
        [KeyboardButton(text=labels["wallet"]), KeyboardButton(text=labels["help"])],
        [KeyboardButton(text=labels["language"])],
    ]
    if mini_app_url:
        rows.append([KeyboardButton(text="Mini App", web_app=WebAppInfo(url=mini_app_url))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def persistent_menu_labels(lang: str = "ru") -> dict[str, str]:
    if lang == "en":
        return {
            "youtube": "Shorts / Preview",
            "status": "Status",
            "history": "History",
            "help": "Help",
            "language": "Language",
            "resume": "Resume",
        }
    if lang == "uk":
        return {
            "youtube": "Shorts / Preview",
            "status": "Статус",
            "history": "Історія",
            "help": "Допомога",
            "language": "Мова",
            "resume": "Резюме",
        }
    return {
        "youtube": "Shorts / Preview",
        "status": "Статус",
        "history": "История",
        "help": "Помощь",
        "language": "Язык",
        "resume": "Резюме",
    }


def persistent_menu_keyboard(lang: str, mini_app_url: str = "") -> ReplyKeyboardMarkup:
    labels = persistent_menu_labels(lang)
    rows = [
        [KeyboardButton(text=labels["youtube"]), KeyboardButton(text=labels["status"])],
        [KeyboardButton(text=labels["history"]), KeyboardButton(text=labels["help"])],
        [KeyboardButton(text=labels["language"]), KeyboardButton(text=labels["resume"])],
    ]
    if mini_app_url:
        rows.append([KeyboardButton(text="Mini App", web_app=WebAppInfo(url=mini_app_url))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def formats_keyboard(session_id: str, formats: list[str], kind: str, mini_app_url: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for fmt in formats:
        builder.button(text=fmt.upper(), callback_data=f"convert:{session_id}:{fmt}")
    builder.button(text="Переименовать", callback_data=f"rename:{session_id}")
    if kind == "video":
        builder.button(text="Обложка PNG", callback_data=f"cover_session:{session_id}")
        builder.button(text="Про видео", callback_data="video_help")
    if mini_app_url:
        builder.button(text="Mini App", web_app=WebAppInfo(url=mini_app_url))
    builder.adjust(3, 1, 1)
    return builder.as_markup()


def image_mode_keyboard(session_id: str, target_format: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Максимально легко", callback_data=f"convert:{session_id}:{target_format}:light")],
            [InlineKeyboardButton(text="Баланс", callback_data=f"convert:{session_id}:{target_format}:balanced")],
            [InlineKeyboardButton(text="Качество", callback_data=f"convert:{session_id}:{target_format}:quality")],
        ]
    )


def cover_tool_rows(job_id: str) -> list[list[InlineKeyboardButton]]:
    return [
        [InlineKeyboardButton(text="Сгенерировать обложку PNG", callback_data=f"cover:{job_id}")],
        [InlineKeyboardButton(text="Название/описание для PNG", callback_data=f"covertext:{job_id}")],
        [InlineKeyboardButton(text="Еще 3 варианта обложки", callback_data=f"cover3:{job_id}")],
        [InlineKeyboardButton(text="Пакет публикации ZIP", callback_data=f"package:{job_id}")],
    ]


def subtitle_keyboard_rows(job_id: str) -> list[list[InlineKeyboardButton]]:
    styles = [
        ("pop", "Pop"),
        ("neon", "Neon"),
        ("candy", "Candy"),
        ("kinetic", "Kinetic"),
        ("bounce", "Bounce"),
        ("comic", "Comic"),
        ("clean", "Clean"),
        ("minimal", "Minimal"),
        ("editorial", "Editorial"),
        ("typewriter", "Typewriter"),
        ("headline", "Headline"),
        ("luxury", "Luxury"),
        ("mono", "Mono"),
        ("soft", "Soft"),
    ]
    rows = [
        [
            InlineKeyboardButton(text=f"Sub {label}", callback_data=f"capstyle:{style}:{job_id}")
            for style, label in styles[index : index + 2]
        ]
        for index in range(0, len(styles), 2)
    ]
    rows.insert(0, [InlineKeyboardButton(text="Примеры стилей субтитров", callback_data=f"cappreview:{job_id}")])
    return rows


def share_keyboard(
    session_id: str,
    output_name: str,
    subtitle_job_id: str | None = None,
    cover_job_id: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Поделиться", switch_inline_query=f"Файл готов: {output_name}")],
        [InlineKeyboardButton(text="Переименовать", callback_data=f"rename:{session_id}")],
    ]
    if cover_job_id:
        rows.extend(cover_tool_rows(cover_job_id))
    if subtitle_job_id:
        rows.extend(subtitle_keyboard_rows(subtitle_job_id))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def youtube_mode_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Скачать MP4", callback_data=f"yt:download:{job_id}")],
        [
            InlineKeyboardButton(text="Shorts dynamic", callback_data=f"yt:dynamic:{job_id}"),
            InlineKeyboardButton(text="Shorts podcast", callback_data=f"yt:podcast:{job_id}"),
        ],
        [
            InlineKeyboardButton(text="Shorts classic", callback_data=f"yt:regular:{job_id}"),
            InlineKeyboardButton(text="Shorts calm", callback_data=f"yt:calm:{job_id}"),
        ],
        [
            InlineKeyboardButton(text="Preview 30s", callback_data=f"yt:backstage30:{job_id}"),
            InlineKeyboardButton(text="Preview 60s", callback_data=f"yt:backstage60:{job_id}"),
        ],
        [
            InlineKeyboardButton(text="Preview 90s", callback_data=f"yt:backstage90:{job_id}"),
            InlineKeyboardButton(text="Cancel", callback_data=f"yt:cancel:{job_id}"),
        ],
        [InlineKeyboardButton(text="Сгенерировать обложку PNG", callback_data=f"yt:cover:{job_id}")],
    ])


def youtube_replay_keyboard(
    job_id: str,
    current_mode: str,
    subtitle_job_id: str | None = None,
    cover_job_id: str | None = None,
) -> InlineKeyboardMarkup:
    rows = []
    if cover_job_id:
        rows.extend(cover_tool_rows(cover_job_id))
    if subtitle_job_id:
        rows.extend(subtitle_keyboard_rows(subtitle_job_id))
    rows.extend([
        [
            InlineKeyboardButton(text="Redo dynamic", callback_data=f"redo:dynamic:{job_id}"),
            InlineKeyboardButton(text="Podcast version", callback_data=f"redo:podcast:{job_id}"),
        ],
        [
            InlineKeyboardButton(text="Preview 60", callback_data=f"redo:backstage60:{job_id}"),
            InlineKeyboardButton(text="Preview 90", callback_data=f"redo:backstage90:{job_id}"),
        ],
    ])
    if current_mode not in {"regular", "backstage30"}:
        rows.append([InlineKeyboardButton(text="Classic version", callback_data=f"redo:regular:{job_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subtitle_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=subtitle_keyboard_rows(job_id))


def media_tools_keyboard(
    subtitle_job_id: str | None = None,
    cover_job_id: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if cover_job_id:
        rows.extend(cover_tool_rows(cover_job_id))
    if subtitle_job_id:
        rows.extend(subtitle_keyboard_rows(subtitle_job_id))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cover_tools_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=cover_tool_rows(job_id))


def subtitle_language_keyboard(
    style: str,
    job_id: str,
    style_labels: dict[str, str],
    language_labels: dict[str, str],
) -> InlineKeyboardMarkup:
    style = style if style in style_labels else "pop"
    languages = list(language_labels.items())
    rows = [
        [
            InlineKeyboardButton(text=label, callback_data=f"cap:{style}:{code}:{job_id}")
            for code, label in languages[index : index + 2]
        ]
        for index in range(0, len(languages), 2)
    ]
    rows.append([InlineKeyboardButton(text="Назад к стилям", callback_data=f"capback:{job_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="Українська", callback_data="lang:uk"),
                InlineKeyboardButton(text="English", callback_data="lang:en"),
            ],
            [
                InlineKeyboardButton(text="Français", callback_data="lang:fr"),
                InlineKeyboardButton(text="Deutsch", callback_data="lang:de"),
                InlineKeyboardButton(text="Español", callback_data="lang:es"),
            ],
            [
                InlineKeyboardButton(text="ქართული", callback_data="lang:ka"),
                InlineKeyboardButton(text="Հայերեն", callback_data="lang:hy"),
                InlineKeyboardButton(text="Italiano", callback_data="lang:it"),
            ],
        ]
    )

def single_callback_keyboard(text: str, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=callback_data)]
    ])


def resume_achievements_skip_keyboard(lang: str) -> InlineKeyboardMarkup:
    return single_callback_keyboard(tr(lang, "resume_skip_achievements"), "resume_skip_achievements")


def resume_additional_skip_keyboard(lang: str) -> InlineKeyboardMarkup:
    return single_callback_keyboard(tr(lang, "resume_skip_additional"), "resume_skip_additional")


def resume_links_skip_keyboard(lang: str) -> InlineKeyboardMarkup:
    labels = {
        "en": "Skip links",
        "uk": "Пропустити посилання",
    }
    return single_callback_keyboard(labels.get(lang, "Пропустить ссылки"), "resume_skip_links")


def resume_photo_skip_keyboard(lang: str) -> InlineKeyboardMarkup:
    return single_callback_keyboard(tr(lang, "resume_skip_photo"), "resume_photo_skip")


def resume_review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Собрать PDF", callback_data="resume_choose_template"),
            InlineKeyboardButton(text="Другое фото", callback_data="resume_edit_photo"),
        ],
        [InlineKeyboardButton(text="Авто-улучшить структуру", callback_data="resume_polish")],
        [
            InlineKeyboardButton(text="Имя", callback_data="resume_edit_name"),
            InlineKeyboardButton(text="Должность", callback_data="resume_edit_position"),
            InlineKeyboardButton(text="Контакты", callback_data="resume_edit_contact"),
        ],
        [InlineKeyboardButton(text="Ссылки", callback_data="resume_edit_links")],
        [
            InlineKeyboardButton(text="О себе", callback_data="resume_edit_summary"),
            InlineKeyboardButton(text="Опыт", callback_data="resume_edit_experience"),
            InlineKeyboardButton(text="Навыки", callback_data="resume_edit_skills"),
        ],
        [
            InlineKeyboardButton(text="Образование", callback_data="resume_edit_education"),
            InlineKeyboardButton(text="Достижения", callback_data="resume_edit_achievements"),
        ],
        [
            InlineKeyboardButton(text="Дополнительно", callback_data="resume_edit_additional"),
            InlineKeyboardButton(text="Убрать фото", callback_data="resume_remove_photo"),
        ],
    ])


def resume_template_keyboard(templates: dict[str, dict[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{key}. {template['name']} — {template['label']}",
                callback_data=f"template_{key}",
            )
        ]
        for key, template in templates.items()
    ]
    rows.append([InlineKeyboardButton(text="Вернуться к редактированию", callback_data="resume_back_review")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def resume_after_pdf_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Другой шаблон", callback_data="resume_choose_template_again"),
            InlineKeyboardButton(text="Редактировать", callback_data="resume_back_review"),
        ],
        [InlineKeyboardButton(text="Завершить", callback_data="resume_finish")],
    ])

