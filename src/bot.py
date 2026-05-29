from __future__ import annotations

import asyncio
from dataclasses import dataclass
from html import escape
import logging
from pathlib import Path
import re
import subprocess
import time
import uuid
import zipfile

import cv2
import numpy as np
from reportlab.lib import colors
from PIL import Image, ImageDraw, ImageFont, ImageOps

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendInvoice
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .config import Settings, get_settings
from .db import Database
from .i18n import lang_from_code, tr
from . import bot_keyboards
from .bot_utils import (
    action_media_types_for,
    build_subscription_payload,
    cover_prompt_preview as utils_cover_prompt_preview,
    day_start_timestamp as utils_day_start_timestamp,
    expired_mapping_keys,
    image_weight_note as utils_image_weight_note,
    normalize_cover_prompt_text as utils_normalize_cover_prompt_text,
    normalize_subtitle_language as utils_normalize_subtitle_language,
    parse_convert_callback_data,
    polish_resume_block as utils_polish_resume_block,
    polish_resume_skills as utils_polish_resume_skills,
    publication_description as utils_publication_description,
    publication_hashtags as utils_publication_hashtags,
    re_words as utils_re_words,
    resume_clip as utils_resume_clip,
    resume_is_empty as utils_resume_is_empty,
    resume_safe_text as utils_resume_safe_text,
    resume_section_data as utils_resume_section_data,
    unique_archive_name,
    normalize_resume_text as utils_normalize_resume_text,
    valid_subscription_payload as utils_valid_subscription_payload,
)
from .image_tools import available_image_formats, clean_base_name, convert_image, human_size, inspect_image, normalize_image_mode
from .video_tools import VIDEO_FORMATS, convert_video, ffmpeg_available, format_duration, inspect_video
from .youtube_tools import (
    SubtitleUnavailableError,
    calculate_smart_clip_starts,
    create_backstage_montage,
    create_business_cover,
    create_subtitle_assets,
    describe_clips,
    download_youtube_video,
    estimate_cut_time,
    estimate_download_time,
    extract_youtube_url,
    get_youtube_metadata,
    make_short_clip,
    planned_clip_count,
    render_subtitle_assets,
    transcribe_subtitle_cues,
    video_source_label,
    zip_clips,
)


SUBSCRIPTION_PERIOD_SECONDS = 2_592_000
TELEGRAM_SAFE_UPLOAD_BYTES = 48 * 1024 * 1024
JOB_TTL_SECONDS = 86_400

NEXT_STEP_HINT = (
    "\n\nЧто дальше:\n"
    "- выбери формат кнопкой ниже;\n"
    "- если нужно другое имя файла, нажми «Переименовать»;\n"
    "- для видео можно сразу сделать PNG-обложку;\n"
    "- для монтажа отправь YouTube-ссылку;\n"
    "- если передумал при переименовании, напиши /cancel."
)
AFTER_RESULT_HINT = (
    "\n\nЧто дальше:\n"
    "- отправь следующий файл или YouTube-ссылку;\n"
    "- для видео можно нажать кнопку субтитров или обложки PNG;\n"
    "- статус доступа: /status, история: /history."
)
FILE_PREP_STEPS = ["получаю файл", "проверяю размер и тип", "читаю параметры", "показываю варианты"]
IMAGE_CONVERT_STEPS = ["проверяю исходник", "конвертирую формат", "сохраняю результат", "отправляю файл"]
VIDEO_CONVERT_STEPS = ["проверяю видео", "запускаю кодирование", "сохраняю MP4/WEBM/GIF", "отправляю файл"]
SUBTITLE_STEPS = ["готовлю звук", "распознаю речь", "верстаю субтитры", "вшиваю в видео", "отправляю файл"]
SUBTITLE_STYLE_LABELS = {
    "pop": "Pop",
    "neon": "Neon",
    "candy": "Candy",
    "kinetic": "Kinetic",
    "bounce": "Bounce",
    "comic": "Comic",
    "clean": "Clean",
    "minimal": "Minimal",
    "editorial": "Editorial",
    "typewriter": "Typewriter",
    "headline": "Headline",
    "luxury": "Luxury",
    "mono": "Mono",
    "soft": "Soft",
}
SUBTITLE_LANGUAGE_LABELS = {
    "auto": "Auto",
    "ru": "Русский",
    "uk": "Українська",
    "en": "English",
}
COVER_STEPS = ["читаю параметры", "выбираю сильный кадр", "ищу тематические картинки", "собираю PNG-обложку", "отправляю файл"]
IMAGE_MODE_LABELS = {
    "light": "максимально легко",
    "balanced": "баланс",
    "quality": "качество",
}
PUBLICATION_STEPS = ["готовлю видео", "делаю обложку", "добавляю субтитры", "пишу описание", "собираю ZIP", "отправляю пакет"]


class RenameState(StatesGroup):
    waiting_name = State()


class CoverTextState(StatesGroup):
    waiting_text = State()


class ResumeState(StatesGroup):
    waiting_name = State()
    waiting_position = State()
    waiting_contact = State()
    waiting_links = State()
    waiting_summary = State()
    waiting_experience = State()
    waiting_education = State()
    waiting_skills = State()
    waiting_achievements = State()
    waiting_additional = State()
    waiting_photo = State()
    waiting_review = State()
    waiting_edit_value = State()
    waiting_template = State()


@dataclass
class FileSession:
    user_id: int
    path: Path
    original_name: str
    base_name: str
    kind: str
    expires_at: int
    cover_title: str | None = None


@dataclass(frozen=True)
class YouTubeRenderProfile:
    mode: str
    label: str
    is_backstage: bool
    max_shorts: int
    short_seconds: int
    backstage_output_seconds: int
    backstage_segment_seconds: int
    backstage_intro_seconds: int
    min_gap_seconds: int
    sample_limit: int


@dataclass(frozen=True)
class YouTubeReplayJob:
    user_id: int
    url: str
    lang: str
    created_at: int


@dataclass(frozen=True)
class SubtitleJob:
    user_id: int
    path: Path
    title: str
    created_at: int


@dataclass(frozen=True)
class CoverJob:
    user_id: int
    path: Path
    title: str
    duration_seconds: float | None
    created_at: int


settings: Settings = get_settings()
db = Database(settings.database_path)
router = Router()
sessions: dict[str, FileSession] = {}
user_latest_session: dict[int, str] = {}
pending_youtube_jobs: dict[str, tuple[int, str, str, int]] = {}
recent_youtube_jobs: dict[str, YouTubeReplayJob] = {}
subtitle_jobs: dict[str, SubtitleJob] = {}
cover_jobs: dict[str, CoverJob] = {}
language_overrides: dict[int, str] = {}
logger = logging.getLogger("converter_bot")
youtube_semaphore = asyncio.Semaphore(max(1, settings.youtube_workers))
subtitle_semaphore = asyncio.Semaphore(max(1, settings.subtitle_workers))
cover_semaphore = asyncio.Semaphore(max(1, settings.cover_workers))


NEXT_STEP_ITEM_TRANSLATIONS = {
    "en": {
        "отправь картинку или видео для конвертации": "send an image or video for conversion",
        "отправь YouTube-ссылку для Shorts или Preview": "send a YouTube link for Shorts or Preview",
        "после результата нажимай Subtitles или Redo, если нужно продолжить обработку": "after the result, use Subtitles or Redo if you want to continue",
        "отправь файл для конвертации": "send a file for conversion",
        "отправь YouTube-ссылку для монтажа": "send a YouTube link for editing",
        "после готового MP4 можно добавить субтитры": "after an MP4 is ready, you can add subtitles",
        "используй этот ID для списка бесплатного доступа": "use this ID for the free access list",
        "или отправь файл/ссылку для обработки": "or send a file/link to process",
        "отправь новый файл": "send a new file",
        "или YouTube-ссылку для монтажа": "or a YouTube link for editing",
        "нажми оплату ниже": "tap the payment button below",
        "или используй доступные Free-действия": "or use the available Free actions",
        "отправь файл": "send a file",
        "или YouTube-ссылку": "or a YouTube link",
        "активируй доступ кнопкой ниже": "activate access with the button below",
        "или используй доступный Free-лимит": "or use the available Free limit",
        "или напиши /id и добавь ID в FREE_USER_IDS": "or send /id and add the ID to FREE_USER_IDS",
        "отправь файл или YouTube-ссылку": "send a file or YouTube link",
        "после обработки результат появится здесь": "after processing, the result will appear here",
    },
    "uk": {
        "отправь картинку или видео для конвертации": "надішліть зображення або відео для конвертації",
        "отправь YouTube-ссылку для Shorts или Preview": "надішліть YouTube-посилання для Shorts або Preview",
        "после результата нажимай Subtitles или Redo, если нужно продолжить обработку": "після результату натискайте Subtitles або Redo, якщо потрібно продовжити",
        "отправь файл для конвертации": "надішліть файл для конвертації",
        "отправь YouTube-ссылку для монтажа": "надішліть YouTube-посилання для монтажу",
        "после готового MP4 можно добавить субтитры": "після готового MP4 можна додати субтитри",
        "используй этот ID для списка бесплатного доступа": "використовуйте цей ID для списку безкоштовного доступу",
        "или отправь файл/ссылку для обработки": "або надішліть файл/посилання для обробки",
        "отправь новый файл": "надішліть новий файл",
        "или YouTube-ссылку для монтажа": "або YouTube-посилання для монтажу",
        "нажми оплату ниже": "натисніть оплату нижче",
        "или используй доступные Free-действия": "або використовуйте доступні Free-дії",
        "отправь файл": "надішліть файл",
        "или YouTube-ссылку": "або YouTube-посилання",
        "активируй доступ кнопкой ниже": "активуйте доступ кнопкою нижче",
        "или используй доступный Free-лимит": "або використовуйте доступний Free-ліміт",
        "или напиши /id и добавь ID в FREE_USER_IDS": "або надішліть /id і додайте ID у FREE_USER_IDS",
        "отправь файл или YouTube-ссылку": "надішліть файл або YouTube-посилання",
        "после обработки результат появится здесь": "після обробки результат з'явиться тут",
    },
}


async def safe_edit(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except Exception:
        pass


async def heartbeat(status: Message, state: dict[str, object]) -> None:
    while True:
        await asyncio.sleep(60)
        elapsed = format_duration(time.time() - float(state.get("started_at", time.time())))
        stage = str(state.get("stage", "Работаю"))
        detail = str(state.get("detail", ""))
        await safe_edit(
            status,
            f"{stage}\n{detail}\n\nЕще работаю. Прошло: {elapsed}. Бот не завис, можно писать /status или /help.",
        )


def process_stage_text(title: str, steps: list[str], active: int, detail: str = "", done: bool = False, lang: str = "ru") -> str:
    lines = [title]
    for index, step in enumerate(steps, start=1):
        marker = tr(lang, "done") if done or index < active else tr(lang, "now") if index == active else tr(lang, "next")
        lines.append(f"{marker}: {tr(lang, 'stage')} {index}/{len(steps)} - {step}")
    if detail:
        lines.append(f"\n{tr(lang, 'details')}: {detail}")
    return "\n".join(lines)


def next_steps_text(*items: str, lang: str = "ru") -> str:
    translations = NEXT_STEP_ITEM_TRANSLATIONS.get(lang, {})
    translated_items = [translations.get(item, item) for item in items if item]
    return f"\n\n{tr(lang, 'next_steps')}\n" + "\n".join(f"- {item}" for item in translated_items)


def user_lang(message_or_callback) -> str:
    user = getattr(message_or_callback, "from_user", None)
    user_id = getattr(user, "id", None)
    if user_id in language_overrides:
        return language_overrides[user_id]
    return lang_from_code(getattr(user, "language_code", None))


def main_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    return bot_keyboards.main_menu(lang, settings.subscription_stars, settings.mini_app_url)


def help_navigation_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return bot_keyboards.help_navigation_keyboard(lang, settings.subscription_stars)


def persistent_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    return bot_keyboards.persistent_menu_keyboard(lang, settings.mini_app_url)


def persistent_menu_labels(lang: str = "ru") -> dict[str, str]:
    return bot_keyboards.persistent_menu_labels(lang)


def formats_keyboard(session_id: str, formats: list[str], kind: str) -> InlineKeyboardMarkup:
    return bot_keyboards.formats_keyboard(session_id, formats, kind, settings.mini_app_url)


def image_mode_keyboard(session_id: str, target_format: str) -> InlineKeyboardMarkup:
    return bot_keyboards.image_mode_keyboard(session_id, target_format)


def share_keyboard(
    session_id: str,
    output_name: str,
    subtitle_job_id: str | None = None,
    cover_job_id: str | None = None,
) -> InlineKeyboardMarkup:
    return bot_keyboards.share_keyboard(session_id, output_name, subtitle_job_id, cover_job_id)


def youtube_mode_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return bot_keyboards.youtube_mode_keyboard(job_id)


def youtube_replay_keyboard(
    job_id: str,
    current_mode: str,
    subtitle_job_id: str | None = None,
    cover_job_id: str | None = None,
) -> InlineKeyboardMarkup:
    return bot_keyboards.youtube_replay_keyboard(job_id, current_mode, subtitle_job_id, cover_job_id)


def subtitle_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return bot_keyboards.subtitle_keyboard(job_id)


def media_tools_keyboard(
    subtitle_job_id: str | None = None,
    cover_job_id: str | None = None,
) -> InlineKeyboardMarkup:
    return bot_keyboards.media_tools_keyboard(subtitle_job_id, cover_job_id)


def cover_tools_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return bot_keyboards.cover_tools_keyboard(job_id)


def cover_tool_rows(job_id: str) -> list[list[InlineKeyboardButton]]:
    return bot_keyboards.cover_tool_rows(job_id)


def subtitle_keyboard_rows(job_id: str) -> list[list[InlineKeyboardButton]]:
    return bot_keyboards.subtitle_keyboard_rows(job_id)


def subtitle_language_keyboard(style: str, job_id: str) -> InlineKeyboardMarkup:
    return bot_keyboards.subtitle_language_keyboard(style, job_id, SUBTITLE_STYLE_LABELS, SUBTITLE_LANGUAGE_LABELS)


def remember_youtube_job(user_id: int, url: str, lang: str) -> str:
    now = int(time.time())
    expired = expired_mapping_keys(recent_youtube_jobs, now - JOB_TTL_SECONDS, lambda job: job.created_at)
    for job_id in expired:
        recent_youtube_jobs.pop(job_id, None)
    job_id = uuid.uuid4().hex[:10]
    recent_youtube_jobs[job_id] = YouTubeReplayJob(user_id=user_id, url=url, lang=lang, created_at=now)
    return job_id


def remember_subtitle_job(user_id: int, path: Path, title: str) -> str:
    now = int(time.time())
    expired = expired_mapping_keys(subtitle_jobs, now - JOB_TTL_SECONDS, lambda job: job.created_at)
    for job_id in expired:
        subtitle_jobs.pop(job_id, None)
    job_id = uuid.uuid4().hex[:10]
    subtitle_jobs[job_id] = SubtitleJob(user_id=user_id, path=path, title=title, created_at=now)
    return job_id


def remember_cover_job(user_id: int, path: Path, title: str, duration_seconds: float | None = None) -> str:
    now = int(time.time())
    expired = expired_mapping_keys(cover_jobs, now - JOB_TTL_SECONDS, lambda job: job.created_at)
    for job_id in expired:
        cover_jobs.pop(job_id, None)
    job_id = uuid.uuid4().hex[:10]
    cover_jobs[job_id] = CoverJob(
        user_id=user_id,
        path=path,
        title=title,
        duration_seconds=duration_seconds,
        created_at=now,
    )
    return job_id


def normalize_cover_prompt_text(value: str | None) -> str:
    return utils_normalize_cover_prompt_text(value)


def cover_prompt_preview(value: str) -> str:
    return utils_cover_prompt_preview(value)


def latest_video_session(user_id: int) -> FileSession | None:
    session = get_owned_session(user_latest_session.get(user_id), user_id)
    if not session or session.kind != "video":
        return None
    return session


def normalize_subtitle_language(value: str | None) -> str | None:
    return utils_normalize_subtitle_language(value)


def subtitle_language_label(value: str | None) -> str:
    return SUBTITLE_LANGUAGE_LABELS.get(value or "auto", SUBTITLE_LANGUAGE_LABELS["auto"])


def image_weight_note(source_size: int, output_size: int) -> str:
    return utils_image_weight_note(source_size, output_size)


def publication_hashtags(title: str) -> list[str]:
    return utils_publication_hashtags(title)


def re_words(text: str) -> list[str]:
    return utils_re_words(text)


def publication_description(title: str, duration_seconds: float | None, hashtags: list[str], subtitle_note: str) -> str:
    return utils_publication_description(title, format_duration(duration_seconds), hashtags, subtitle_note)


def zip_files(paths: list[Path], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        used_names: set[str] = set()
        for path in paths:
            if not path.exists() or path == output:
                continue
            arcname = unique_archive_name(path.name, used_names)
            used_names.add(arcname)
            archive.write(path, arcname=arcname)
    return output


def language_keyboard() -> InlineKeyboardMarkup:
    return bot_keyboards.language_keyboard()


def youtube_render_profile(mode: str) -> YouTubeRenderProfile:
    mode = (mode or "regular").lower()
    if mode == "backstage":
        mode = "backstage30"

    base_short_seconds = max(10, settings.youtube_short_seconds)
    if mode == "dynamic":
        return YouTubeRenderProfile(
            mode=mode,
            label="Shorts dynamic",
            is_backstage=False,
            max_shorts=min(settings.youtube_max_shorts, 12),
            short_seconds=max(18, min(30, base_short_seconds)),
            backstage_output_seconds=settings.backstage_output_seconds,
            backstage_segment_seconds=settings.backstage_segment_seconds,
            backstage_intro_seconds=settings.backstage_intro_seconds,
            min_gap_seconds=max(20, settings.backstage_min_gap_seconds // 2),
            sample_limit=max(settings.backstage_sample_limit, 520),
        )
    if mode == "podcast":
        return YouTubeRenderProfile(
            mode=mode,
            label="Shorts podcast",
            is_backstage=False,
            max_shorts=settings.youtube_max_shorts,
            short_seconds=max(45, min(60, base_short_seconds + 10)),
            backstage_output_seconds=settings.backstage_output_seconds,
            backstage_segment_seconds=settings.backstage_segment_seconds,
            backstage_intro_seconds=settings.backstage_intro_seconds,
            min_gap_seconds=settings.backstage_min_gap_seconds,
            sample_limit=max(settings.backstage_sample_limit, 620),
        )
    if mode == "calm":
        return YouTubeRenderProfile(
            mode=mode,
            label="Shorts calm",
            is_backstage=False,
            max_shorts=max(1, min(settings.youtube_max_shorts, 8)),
            short_seconds=max(35, min(55, base_short_seconds)),
            backstage_output_seconds=settings.backstage_output_seconds,
            backstage_segment_seconds=settings.backstage_segment_seconds,
            backstage_intro_seconds=settings.backstage_intro_seconds,
            min_gap_seconds=settings.backstage_min_gap_seconds,
            sample_limit=settings.backstage_sample_limit,
        )
    if mode.startswith("backstage"):
        seconds = {"backstage30": 30, "backstage60": 60, "backstage90": 90}.get(mode, settings.backstage_output_seconds)
        return YouTubeRenderProfile(
            mode=mode,
            label=f"Preview {seconds}s",
            is_backstage=True,
            max_shorts=settings.youtube_max_shorts,
            short_seconds=base_short_seconds,
            backstage_output_seconds=seconds,
            backstage_segment_seconds=5 if seconds >= 60 else settings.backstage_segment_seconds,
            backstage_intro_seconds=1 if seconds <= 30 else 2,
            min_gap_seconds=max(18, min(settings.backstage_min_gap_seconds, seconds)),
            sample_limit=max(settings.backstage_sample_limit, 700 if seconds >= 60 else settings.backstage_sample_limit),
        )
    return YouTubeRenderProfile(
        mode="regular",
        label="Shorts classic",
        is_backstage=False,
        max_shorts=settings.youtube_max_shorts,
        short_seconds=base_short_seconds,
        backstage_output_seconds=settings.backstage_output_seconds,
        backstage_segment_seconds=settings.backstage_segment_seconds,
        backstage_intro_seconds=settings.backstage_intro_seconds,
        min_gap_seconds=settings.backstage_min_gap_seconds,
        sample_limit=settings.backstage_sample_limit,
    )


def youtube_mode_label(mode: str) -> str:
    return youtube_render_profile(mode).label


def is_free_user(user_id: int) -> bool:
    return user_id in settings.free_user_ids


async def ensure_user(message: Message) -> None:
    if message.from_user:
        await db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        if message.from_user.id not in language_overrides:
            saved_language = await db.get_language(message.from_user.id)
            if saved_language:
                language_overrides[message.from_user.id] = saved_language


async def ensure_callback_user(callback: CallbackQuery) -> None:
    if callback.from_user:
        await db.upsert_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
        if callback.from_user.id not in language_overrides:
            saved_language = await db.get_language(callback.from_user.id)
            if saved_language:
                language_overrides[callback.from_user.id] = saved_language


async def has_access(user_id: int) -> bool:
    return is_free_user(user_id) or (await db.get_subscription(user_id)).is_active


async def is_pro_user(user_id: int) -> bool:
    return is_free_user(user_id) or (await db.get_subscription(user_id)).is_active


def free_action_limit(action: str) -> int:
    return {
        "image": settings.free_daily_image_conversions,
        "video": settings.free_daily_video_conversions,
        "cover": settings.free_daily_cover_generations,
        "youtube": settings.free_daily_youtube_jobs,
        "subtitles": settings.free_daily_subtitle_jobs,
        "package": settings.free_daily_package_jobs,
    }.get(action, 0)


def action_media_types(action: str) -> list[str]:
    return action_media_types_for(action)


def day_start_timestamp() -> int:
    return utils_day_start_timestamp()


async def free_usage_count(user_id: int, action: str) -> int:
    return await db.count_conversions_since(user_id, action_media_types(action), day_start_timestamp())


async def ensure_paid_access(message: Message, user_id: int, feature: str) -> bool:
    if await is_pro_user(user_id):
        return True
    lang = user_lang(message)
    await message.answer(
        f"{feature} доступно после оплаты Stars.\n\n"
        "Если ваш Telegram ID добавлен в FREE_USER_IDS в .env, доступ будет бесплатным автоматически."
        + next_steps_text("нажми оплату ниже", "или напиши /id и добавь ID в FREE_USER_IDS", lang=lang),
        reply_markup=main_menu(lang),
    )
    return False


async def ensure_action_allowed(message: Message, user_id: int, action: str, detail: str = "") -> bool:
    paid_only_features = {
        "image": "Конвертация изображений",
        "video": "Конвертация видео",
        "resume": "PDF-резюме",
        "cover": "PNG-обложки",
        "youtube": "YouTube-монтаж",
        "subtitles": "Автосубтитры",
        "package": "Пакет публикации ZIP",
    }
    if action in paid_only_features:
        return await ensure_paid_access(message, user_id, paid_only_features[action])
    if await is_pro_user(user_id):
        return True
    limit = free_action_limit(action)
    used = await free_usage_count(user_id, action)
    if used < limit:
        return True
    await message.answer(
        pro_limit_text(action, used, limit, detail),
        reply_markup=main_menu(user_lang(message)),
    )
    return False


async def ensure_pro_feature(message: Message, user_id: int, feature: str) -> bool:
    return await ensure_paid_access(message, user_id, feature)


def pro_limit_text(action: str, used: int, limit: int, detail: str = "") -> str:
    labels = {
        "image": "конвертаций изображений",
        "video": "конвертаций видео",
        "resume": "PDF-резюме",
        "cover": "обложек",
        "youtube": "YouTube-монтажей",
        "subtitles": "субтитров",
        "package": "пакетов публикации",
    }
    feature = labels.get(action, "обработок")
    limit_text = f"{used}/{limit}" if limit else "0"
    lines = [
        f"Free-лимит на сегодня исчерпан: {limit_text} {feature}.",
        "Pro открывает полный набор: YouTube, субтитры, обложки, пакеты публикации и больше обработок.",
    ]
    if detail:
        lines.append(detail)
    lines.append(next_steps_text("нажми оплату ниже", "или вернись завтра к Free-лимиту"))
    return "\n".join(lines)


def max_size_bytes(kind: str) -> int:
    mb = settings.max_video_mb if kind == "video" else settings.max_image_mb
    return mb * 1024 * 1024


def prune_sessions() -> None:
    now = int(time.time())
    expired = expired_mapping_keys(sessions, now, lambda session: session.expires_at)
    for session_id in expired:
        session = sessions.pop(session_id, None)
        if session:
            session.path.unlink(missing_ok=True)
            if user_latest_session.get(session.user_id) == session_id:
                user_latest_session.pop(session.user_id, None)


@router.message(CommandStart())
async def start(message: Message) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    await message.answer(
        tr(
            lang,
            "start",
            shorts=settings.youtube_max_shorts,
            stars=settings.subscription_stars,
            days=settings.subscription_days,
        )
        + next_steps_text(
            "отправь картинку или видео для конвертации",
            "отправь YouTube-ссылку для Shorts или Preview",
            "после результата нажимай Subtitles или Redo, если нужно продолжить обработку",
            lang=lang,
        ),
        reply_markup=persistent_menu_keyboard(lang),
    )
    await message.answer(tr(lang, "quick_actions"), reply_markup=main_menu(lang))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    await message.answer(
        tr(lang, "help_menu")
        + next_steps_text(
            "отправь файл для конвертации",
            "отправь YouTube-ссылку для монтажа",
            "после готового MP4 можно добавить субтитры",
            lang=lang,
        ),
        reply_markup=help_navigation_keyboard(lang),
    )


@router.message(Command("id"))
async def id_command(message: Message) -> None:
    await ensure_user(message)
    if message.from_user:
        lang = user_lang(message)
        await message.answer(
            tr(lang, "id", user_id=message.from_user.id)
            + next_steps_text("используй этот ID для списка бесплатного доступа", "или отправь файл/ссылку для обработки", lang=lang)
        )


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    await state.clear()
    await message.answer(
        tr(lang, "cancelled")
        + next_steps_text("отправь новый файл", "или отправь YouTube-ссылку для монтажа", lang=lang)
    )


@router.message(Command("language", "lang"))
async def language_command(message: Message) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    await message.answer(
        tr(lang, "language_prompt"),
        reply_markup=language_keyboard(),
    )


@router.message(Command("subscribe"))
async def subscribe(message: Message, bot: Bot) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    if message.from_user and is_free_user(message.from_user.id):
        await message.answer(
            tr(lang, "free_access")
            + next_steps_text("отправь файл для конвертации", "или YouTube-ссылку для монтажа", lang=lang)
        )
        return
    await send_subscription_invoice(message, bot)


@router.message(Command("pro"))
async def pro_command(message: Message) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    await message.answer(
        tr(lang, "help_pro", days=settings.subscription_days),
        reply_markup=help_navigation_keyboard(lang),
    )


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    await ensure_user(message)
    await send_status(message)


@router.message(Command("history"))
async def history_command(message: Message) -> None:
    await ensure_user(message)
    await send_history(message)


@router.message(Command("resume"))
async def resume_command(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    if not message.from_user:
        return
    if not await ensure_pro_feature(message, message.from_user.id, "PDF-резюме"):
        return
    lang = user_lang(message)
    await state.set_state(ResumeState.waiting_name)
    await state.update_data(lang=lang)
    await message.answer(tr(lang, "resume_start"))


@router.message(ResumeState.waiting_name)
async def resume_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_position)
    await message.answer(tr(lang, "resume_position"))


@router.message(ResumeState.waiting_position)
async def resume_position(message: Message, state: FSMContext) -> None:
    await state.update_data(position=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_contact)
    await message.answer(tr(lang, "resume_contact"))


@router.message(ResumeState.waiting_contact)
async def resume_contact(message: Message, state: FSMContext) -> None:
    await state.update_data(contact=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_links)
    await message.answer(
        "Ссылки: LinkedIn, GitHub, Behance, портфолио, сайт или Telegram-канал. Можно пропустить.",
        reply_markup=bot_keyboards.resume_links_skip_keyboard(lang),
    )


@router.callback_query(ResumeState.waiting_links, F.data == "resume_skip_links")
async def resume_skip_links(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(links="")
    lang = (await state.get_data()).get("lang", user_lang(callback))
    await state.set_state(ResumeState.waiting_summary)
    if callback.message:
        await callback.message.answer(tr(lang, "resume_summary"))


@router.message(ResumeState.waiting_links)
async def resume_links(message: Message, state: FSMContext) -> None:
    await state.update_data(links=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_summary)
    await message.answer(tr(lang, "resume_summary"))


@router.message(ResumeState.waiting_summary)
async def resume_summary(message: Message, state: FSMContext) -> None:
    await state.update_data(summary=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_experience)
    await message.answer(tr(lang, "resume_experience"))


@router.message(ResumeState.waiting_experience)
async def resume_experience(message: Message, state: FSMContext) -> None:
    await state.update_data(experience=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_education)
    await message.answer(tr(lang, "resume_education"))


@router.message(ResumeState.waiting_education)
async def resume_education(message: Message, state: FSMContext) -> None:
    await state.update_data(education=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_skills)
    await message.answer(tr(lang, "resume_skills"))


@router.message(ResumeState.waiting_skills)
async def resume_skills(message: Message, state: FSMContext) -> None:
    await state.update_data(skills=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_achievements)
    await message.answer(
        tr(lang, "resume_achievements"),
        reply_markup=bot_keyboards.resume_achievements_skip_keyboard(lang),
    )


@router.callback_query(ResumeState.waiting_achievements, F.data == "resume_skip_achievements")
async def resume_skip_achievements(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(achievements="")
    lang = (await state.get_data()).get("lang", user_lang(callback))
    await state.set_state(ResumeState.waiting_additional)
    if callback.message:
        await callback.message.answer(
            tr(lang, "resume_additional"),
            reply_markup=bot_keyboards.resume_additional_skip_keyboard(lang),
        )


@router.message(ResumeState.waiting_achievements)
async def resume_achievements(message: Message, state: FSMContext) -> None:
    await state.update_data(achievements=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_additional)
    await message.answer(
        tr(lang, "resume_additional"),
        reply_markup=bot_keyboards.resume_additional_skip_keyboard(lang),
    )


@router.callback_query(ResumeState.waiting_additional, F.data == "resume_skip_additional")
async def resume_skip_additional(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(additional="")
    lang = (await state.get_data()).get("lang", user_lang(callback))
    await state.set_state(ResumeState.waiting_photo)
    if callback.message:
        await callback.message.answer(tr(lang, "resume_photo"), reply_markup=bot_keyboards.resume_photo_skip_keyboard(lang))


@router.message(ResumeState.waiting_additional)
async def resume_additional(message: Message, state: FSMContext) -> None:
    await state.update_data(additional=message.text)
    lang = (await state.get_data()).get("lang", user_lang(message))
    await state.set_state(ResumeState.waiting_photo)
    await message.answer(
        tr(lang, "resume_photo"),
        reply_markup=bot_keyboards.resume_photo_skip_keyboard(lang),
    )


@router.callback_query(ResumeState.waiting_photo, F.data == "resume_photo_skip")
async def resume_photo_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(photo_path="")
    await show_resume_review(callback.message, state)


@router.message(ResumeState.waiting_photo, F.photo | F.document)
async def resume_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user:
        return
    lang = (await state.get_data()).get("lang", user_lang(message))

    file_id: str | None = None
    original_name = f"resume_photo_{message.message_id}.jpg"
    if message.photo:
        file_id = message.photo[-1].file_id
        if message.photo[-1].file_size and message.photo[-1].file_size > max_size_bytes("image"):
            await message.answer(f"Фото слишком большое. Лимит: {settings.max_image_mb} MB.")
            return
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id
        original_name = message.document.file_name or original_name
        if message.document.file_size and message.document.file_size > max_size_bytes("image"):
            await message.answer(f"Картинка слишком большая. Лимит: {settings.max_image_mb} MB.")
            return

    if not file_id:
        await message.answer(tr(lang, "resume_photo_wrong"))
        return

    photo_dir = settings.storage_dir / str(message.from_user.id) / "resume_photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_name).suffix or ".jpg"
    photo_path = photo_dir / f"{uuid.uuid4().hex[:12]}{suffix}"

    tg_file = await bot.get_file(file_id)
    await bot.download_file(tg_file.file_path, destination=photo_path)
    await state.update_data(photo_path=str(photo_path))
    await message.answer(tr(lang, "resume_photo_added"))
    await show_resume_review(message, state)


@router.message(ResumeState.waiting_photo)
async def resume_photo_wrong_input(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", user_lang(message))
    await message.answer(tr(lang, "resume_photo_wrong"))


RESUME_FIELD_LABELS = {
    "name": "Имя",
    "position": "Должность",
    "contact": "Контакты",
    "links": "Ссылки",
    "summary": "О себе",
    "experience": "Опыт",
    "education": "Образование",
    "skills": "Навыки",
    "achievements": "Достижения",
    "additional": "Дополнительно",
}


RESUME_FIELD_HINTS = {
    "name": "Введите имя и фамилию.",
    "position": "Введите желаемую должность или роль.",
    "contact": "Введите контакты: телефон, email, Telegram, LinkedIn, город.",
    "links": "Введите ссылки: LinkedIn, GitHub, портфолио, сайт, Behance или Telegram-канал. Если ссылок нет, напишите «нет».",
    "summary": "Введите короткий профессиональный профиль на 1-3 предложения.",
    "experience": "Введите опыт. Можно с переносами строк и списками через дефис.",
    "education": "Введите образование, курсы или сертификаты.",
    "skills": "Введите навыки через запятую.",
    "achievements": "Введите достижения/проекты или напишите «нет».",
    "additional": "Введите языки, инструменты, детали или напишите «нет».",
}


def resume_clip(value: str, limit: int = 260) -> str:
    return utils_resume_clip(value, limit)


def resume_review_text(data: dict) -> str:
    prepared = resume_section_data(data)
    rows = ["Проверьте резюме перед PDF:\n"]
    for key, label in RESUME_FIELD_LABELS.items():
        value = prepared.get(key) or "не указано"
        rows.append(f"<b>{label}:</b> {escape(resume_clip(value), quote=False)}")
    rows.append(f"<b>Фото:</b> {'добавлено' if data.get('photo_path') else 'без фото'}")
    rows.append("\nМожно отредактировать любой блок или сразу выбрать шаблон.")
    return "\n".join(rows)


def resume_review_keyboard() -> InlineKeyboardMarkup:
    return bot_keyboards.resume_review_keyboard()


async def show_resume_review(target: Message | None, state: FSMContext) -> None:
    if target is None:
        return
    await state.set_state(ResumeState.waiting_review)
    data = await state.get_data()
    await target.answer(resume_review_text(data), reply_markup=resume_review_keyboard())


@router.callback_query(ResumeState.waiting_review, F.data == "resume_choose_template")
async def resume_choose_template(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await show_resume_templates(callback.message, state)


def polish_resume_block(value: str, bulletize: bool = False) -> str:
    return utils_polish_resume_block(value, bulletize)


def polish_resume_skills(value: str) -> str:
    return utils_polish_resume_skills(value)


@router.callback_query(ResumeState.waiting_review, F.data == "resume_polish")
async def resume_polish(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(
        name=polish_resume_block(data.get("name", "")),
        position=polish_resume_block(data.get("position", "")),
        contact=polish_resume_block(data.get("contact", "")),
        links="" if resume_is_empty(normalize_resume_text(data.get("links"))) else polish_resume_block(data.get("links", "")),
        summary=polish_resume_block(data.get("summary", "")),
        experience=polish_resume_block(data.get("experience", ""), bulletize=True),
        education=polish_resume_block(data.get("education", "")),
        skills=polish_resume_skills(data.get("skills", "")),
        achievements="" if resume_is_empty(normalize_resume_text(data.get("achievements"))) else polish_resume_block(data.get("achievements", ""), bulletize=True),
        additional="" if resume_is_empty(normalize_resume_text(data.get("additional"))) else polish_resume_block(data.get("additional", "")),
    )
    await callback.answer("Структуру привел в порядок")
    await show_resume_review(callback.message, state)


@router.callback_query(ResumeState.waiting_review, F.data == "resume_remove_photo")
async def resume_remove_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Фото убрано")
    await state.update_data(photo_path="")
    await show_resume_review(callback.message, state)


@router.callback_query(ResumeState.waiting_review, F.data == "resume_edit_photo")
async def resume_edit_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang = (await state.get_data()).get("lang", user_lang(callback))
    await state.set_state(ResumeState.waiting_photo)
    if callback.message:
        await callback.message.answer(tr(lang, "resume_photo_wrong"), reply_markup=bot_keyboards.resume_photo_skip_keyboard(lang))


@router.callback_query(ResumeState.waiting_review, F.data.startswith("resume_edit_"))
async def resume_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.removeprefix("resume_edit_")
    if field not in RESUME_FIELD_LABELS:
        await callback.answer()
        return
    await callback.answer()
    await state.update_data(edit_field=field)
    await state.set_state(ResumeState.waiting_edit_value)
    if callback.message:
        current = normalize_resume_text((await state.get_data()).get(field))
        await callback.message.answer(
            f"Редактируем: {RESUME_FIELD_LABELS[field]}.\n"
            f"{RESUME_FIELD_HINTS[field]}\n\n"
            f"Сейчас:\n{current or 'пусто'}"
        )


@router.message(ResumeState.waiting_edit_value)
async def resume_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("edit_field")
    if field not in RESUME_FIELD_LABELS:
        await show_resume_review(message, state)
        return
    await state.update_data(**{field: message.text or "", "edit_field": ""})
    await message.answer("Обновил блок.")
    await show_resume_review(message, state)


async def show_resume_templates(target: Message | None, state: FSMContext) -> None:
    if target is None:
        return
    await state.set_state(ResumeState.waiting_template)
    preview_path: Path | None = None
    try:
        preview_path = await asyncio.to_thread(create_resume_template_preview_sheet, settings.output_dir)
        await target.answer_photo(
            FSInputFile(preview_path),
            caption="Примерно так отличаются шаблоны по расположению блоков. Ниже выберите номер.",
        )
    except Exception:
        logger.exception("Could not create resume template preview")
    finally:
        if preview_path:
            preview_path.unlink(missing_ok=True)
    data = await state.get_data()
    await target.answer(
        tr(data.get("lang", "ru"), "resume_template_prompt"),
        reply_markup=bot_keyboards.resume_template_keyboard(RESUME_TEMPLATES),
    )


@router.callback_query(ResumeState.waiting_template, F.data == "resume_back_review")
async def resume_back_review(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await show_resume_review(callback.message, state)


def resume_after_pdf_keyboard() -> InlineKeyboardMarkup:
    return bot_keyboards.resume_after_pdf_keyboard()


@router.callback_query(ResumeState.waiting_template, F.data == "resume_choose_template_again")
async def resume_choose_template_again(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await show_resume_templates(callback.message, state)


@router.callback_query(ResumeState.waiting_template, F.data == "resume_finish")
async def resume_finish(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Готово")
    await state.clear()
    if callback.message:
        await callback.message.answer("Ок, мастер резюме закрыт. Для нового резюме используйте /resume.")


@router.callback_query(ResumeState.waiting_template, F.data.startswith("template_"))
async def resume_template(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer("Готовлю PDF...")
    template = callback.data.split("_")[1]
    data = await state.get_data()
    await state.update_data(last_template=template)
    pdf_path: Path | None = None
    try:
        pdf_path = await generate_resume_pdf(data, template)
        await bot.send_document(
            callback.from_user.id,
            FSInputFile(pdf_path),
            caption="Ваше резюме готово. Можно сразу собрать другой шаблон или отредактировать данные.",
            reply_markup=resume_after_pdf_keyboard(),
        )
        await db.add_conversion(
            callback.from_user.id,
            "resume",
            "resume_form",
            pdf_path.name,
            "pdf",
            0,
            pdf_path.stat().st_size,
        )
    except Exception as exc:
        logger.exception("Resume PDF generation failed")
        if callback.message:
            await callback.message.answer(f"Не получилось собрать PDF-резюме: {exc}")
    finally:
        if pdf_path:
            pdf_path.unlink(missing_ok=True)


@router.message(StateFilter(None), F.text.in_({"Статус", "Status"}))
async def status_button(message: Message) -> None:
    await ensure_user(message)
    await send_status(message)


@router.message(StateFilter(None), F.text.in_({"Помощь", "Help", "Допомога"}))
async def help_button(message: Message) -> None:
    await help_command(message)


@router.message(StateFilter(None), F.text.in_({"История", "History", "Історія"}))
async def history_button(message: Message) -> None:
    await history_command(message)


@router.message(StateFilter(None), F.text.in_({"Язык", "Language", "Мова"}))
async def language_button(message: Message) -> None:
    await language_command(message)


@router.message(StateFilter(None), F.text.in_({"Резюме", "Resume"}))
async def resume_button(message: Message, state: FSMContext) -> None:
    await resume_command(message, state)


@router.message(StateFilter(None), F.text.in_({"Shorts / Preview", "Shorts / Backstage"}))
async def youtube_hint_button(message: Message) -> None:
    await ensure_user(message)
    await message.answer(
        "Отправь ссылку YouTube, и я дам кнопки: Shorts, Preview или обложка PNG.\n\n"
        "Shorts теперь выбираются по лицам, движению и сменам кадра. "
        "Preview собирает один широкий 16:9 ролик с лучшими моментами.",
        reply_markup=persistent_menu_keyboard(user_lang(message)),
    )


@router.callback_query(F.data == "pay")
async def pay_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await ensure_callback_user(callback)
    if callback.from_user and is_free_user(callback.from_user.id):
        if callback.message:
            lang = user_lang(callback)
            await callback.message.answer(
                tr(lang, "free_access")
                + next_steps_text("отправь файл", "или YouTube-ссылку", lang=lang)
            )
        return
    if callback.message:
        await send_subscription_invoice(callback.message, bot)


@router.callback_query(F.data == "status")
async def status_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await ensure_callback_user(callback)
    if callback.message and callback.from_user:
        await send_status(callback.message, callback.from_user.id, user_lang(callback))


@router.callback_query(F.data.startswith("help:"))
async def help_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await ensure_callback_user(callback)
    if not callback.message or not callback.data:
        return
    lang = user_lang(callback)
    section = callback.data.split(":", 1)[1]
    key_map = {
        "menu": "help_menu",
        "files": "help_files",
        "youtube": "help_youtube",
        "resume": "help_resume",
        "subtitles": "help_subtitles",
        "pro": "help_pro",
    }
    key = key_map.get(section, "help_menu")
    await callback.message.answer(
        tr(
            lang,
            key,
            image_mb=settings.max_image_mb,
            video_mb=settings.max_video_mb,
            days=settings.subscription_days,
        ),
        reply_markup=help_navigation_keyboard(lang),
    )


@router.callback_query(F.data == "language")
async def language_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await ensure_callback_user(callback)
    if callback.message:
        await callback.message.answer(
            tr(user_lang(callback), "language_prompt"),
            reply_markup=language_keyboard(),
        )


@router.callback_query(F.data.startswith("lang:"))
async def set_language_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message or not callback.data:
        return
    await db.upsert_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    lang = callback.data.split(":", 1)[1]
    if lang not in {"ru", "uk", "en"}:
        await callback.message.answer(tr(user_lang(callback), "unknown_language"))
        return
    language_overrides[callback.from_user.id] = lang
    await db.set_language(callback.from_user.id, lang)
    labels = {"ru": "Русский", "uk": "Українська", "en": "English"}
    await callback.message.answer(
        tr(lang, "language_saved", language=labels[lang]),
        reply_markup=persistent_menu_keyboard(lang),
    )
    await callback.message.answer(tr(lang, "quick_actions"), reply_markup=main_menu(lang))


@router.callback_query(F.data == "video_help")
async def video_help(callback: CallbackQuery) -> None:
    await callback.answer()
    text = (
        "Видео-конвертация активна: MP4, WEBM, GIF.\n"
        "Процесс: принимаю файл, проверяю параметры, кодирую выбранный формат, отправляю результат."
        + next_steps_text("отправь видеофайл", "или отправь YouTube-ссылку для монтажа", "после MP4 можно добавить субтитры")
        if ffmpeg_available()
        else "Обработчик видео недоступен." + next_steps_text("обнови зависимости", "перезапусти бота")
    )
    if callback.message:
        await callback.message.answer(text)


async def send_subscription_invoice(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id if message.from_user else message.chat.id
    payload = build_subscription_payload(user_id, settings.subscription_days, settings.subscription_stars)
    lang = user_lang(message)
    await message.answer(
        tr(lang, "pay_intro", stars=settings.subscription_stars, days=settings.subscription_days),
        reply_markup=help_navigation_keyboard(lang),
    )
    await message.answer(
        process_stage_text(
            "Подготовка доступа",
            ["проверяю запрос", "формирую счет", "жду подтверждение оплаты"],
            2,
            f"Период: {settings.subscription_days} дней",
            lang=lang,
        )
        + next_steps_text("оплати счет ниже", "после оплаты отправь файл или YouTube-ссылку", lang=lang)
    )
    await bot(
        SendInvoice(
            chat_id=message.chat.id,
            title="Image Converter Pro",
            description=f"Доступ к видео, фото, PDF-резюме, YouTube, субтитрам и обложкам на {settings.subscription_days} дней.",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"{settings.subscription_days} дней", amount=settings.subscription_stars)],
            subscription_period=SUBSCRIPTION_PERIOD_SECONDS,
        )
    )


async def send_status(message: Message, user_id: int | None = None, lang: str | None = None) -> None:
    if not message.from_user and not user_id:
        return
    current_user_id = user_id or message.from_user.id
    lang = lang or language_overrides.get(current_user_id, user_lang(message))
    if is_free_user(current_user_id):
        await message.answer(
            tr(lang, "free_access")
            + next_steps_text("отправь файл для конвертации", "или отправь YouTube-ссылку для монтажа", lang=lang)
        )
        return
    sub = await db.get_subscription(current_user_id)
    if sub.is_active:
        payments = await db.recent_payments(current_user_id, 1)
        payment_note = ""
        if payments:
            paid = payments[0]
            paid_at = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(paid.created_at))
            payment_note = f"\nПоследняя оплата: {paid.total_amount} Stars, {paid_at}."
        await message.answer(
            tr(lang, "sub_active", date=sub.active_until_text)
            + "\n\nПлан: Pro\nДоступно: YouTube, субтитры, обложки, пакеты публикации, больше обработок."
            + payment_note
            + next_steps_text("отправь файл", "или отправь YouTube-ссылку", lang=lang)
        )
    else:
        await message.answer(
            tr(lang, "sub_inactive")
            + "\n\nПлан: без активной подписки\n"
            + "Функции видео, фото, PDF-резюме, YouTube, субтитры и обложки доступны после оплаты Stars.\n"
            + "Пользователи из FREE_USER_IDS в .env получают тот же доступ бесплатно."
            + next_steps_text("активируй доступ кнопкой ниже", "или напиши /id и добавь ID в FREE_USER_IDS", lang=lang),
            reply_markup=main_menu(lang),
        )


async def free_usage_lines(user_id: int) -> list[str]:
    items = [
        ("image", "изображения"),
        ("video", "видео"),
        ("cover", "обложки"),
        ("youtube", "YouTube"),
        ("subtitles", "субтитры"),
        ("package", "пакеты"),
    ]
    lines: list[str] = []
    for action, label in items:
        limit = free_action_limit(action)
        used = await free_usage_count(user_id, action)
        lines.append(f"- {label}: {min(used, limit)}/{limit}")
    return lines


async def send_history(message: Message) -> None:
    if not message.from_user:
        return
    records = await db.recent_conversions(message.from_user.id, 10)
    if not records:
        await message.answer(
            "История пока пустая."
            + next_steps_text("отправь файл или YouTube-ссылку", "после обработки результат появится здесь")
        )
        return
    lines = ["Последние обработки:"]
    for index, record in enumerate(records, start=1):
        created = time.strftime("%Y-%m-%d %H:%M", time.localtime(record.created_at))
        lines.append(
            f"{index}. {created} | {record.media_type} | {record.output_format.upper()} | "
            f"{human_size(record.output_size)}\n{record.output_name}"
        )
    await message.answer(
        "\n\n".join(lines)
        + next_steps_text("отправь новый файл или ссылку", "для свежих MP4 можно добавить субтитры кнопкой под результатом")
    )


def valid_subscription_payload(payload: str, user_id: int | None = None) -> bool:
    return utils_valid_subscription_payload(
        payload,
        expected_days=settings.subscription_days,
        expected_stars=settings.subscription_stars,
        user_id=user_id,
    )


@router.pre_checkout_query()
async def pre_checkout(query) -> None:
    if query.currency != "XTR":
        await query.answer(ok=False, error_message="Оплата принимается только Telegram Stars.")
        return
    if query.total_amount != settings.subscription_stars:
        await query.answer(ok=False, error_message="Сумма счета не совпадает с текущим тарифом.")
        return
    if not valid_subscription_payload(query.invoice_payload, query.from_user.id):
        await query.answer(ok=False, error_message="Счет устарел. Нажмите оплату еще раз.")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    if not message.from_user or not message.successful_payment:
        return
    payment = message.successful_payment
    if payment.currency != "XTR" or payment.total_amount != settings.subscription_stars:
        logger.warning("Unexpected payment from %s: %s %s", message.from_user.id, payment.currency, payment.total_amount)
        return
    if not valid_subscription_payload(payment.invoice_payload, message.from_user.id):
        logger.warning("Unexpected payment payload from %s: %s", message.from_user.id, payment.invoice_payload)
        return
    current = await db.get_subscription(message.from_user.id)
    base_until = max(current.active_until, int(time.time()))
    active_until = payment.subscription_expiration_date or base_until + settings.subscription_days * 86400
    await db.set_subscription(message.from_user.id, active_until, payment.telegram_payment_charge_id)
    await db.add_payment(
        message.from_user.id,
        payment.currency,
        payment.total_amount,
        payment.invoice_payload,
        payment.telegram_payment_charge_id,
        payment.provider_payment_charge_id,
        active_until,
    )
    await message.answer(
        "Оплата прошла.\n"
        f"Подписка активна до {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(active_until))}.\n"
        + next_steps_text("отправь изображение или видео", "или отправь YouTube-ссылку для монтажа")
    )


@router.message(StateFilter(None), F.text)
async def receive_text(message: Message, bot: Bot) -> None:
    await ensure_user(message)
    if not message.from_user:
        return

    url = extract_youtube_url(message.text)
    if not url:
        session = latest_video_session(message.from_user.id)
        prompt = normalize_cover_prompt_text(message.text)
        if session and prompt and len(prompt) >= 4:
            session.cover_title = prompt
            job_id = remember_cover_job(message.from_user.id, session.path, prompt, None)
            await message.answer(
                "Текст для обложки принят.\n"
                f"{cover_prompt_preview(prompt)}\n\n"
                "Теперь нажми «Сгенерировать обложку PNG» или «Еще 3 варианта», и я подставлю этот текст в макет.",
                reply_markup=cover_tools_keyboard(job_id),
            )
        return

    lang = user_lang(message)
    source_label = video_source_label(url)
    if not await ensure_action_allowed(message, message.from_user.id, "youtube", f"{source_label}-монтаж входит в Pro-функции."):
        return

    job_id = uuid.uuid4().hex[:10]
    pending_youtube_jobs[job_id] = (message.from_user.id, url, lang, int(time.time()))
    await message.answer(
        f"{source_label}-ссылка принята.\n\n"
        "Выбери режим:\n"
        "- Скачать MP4: скачать доступный файл и при необходимости конвертировать в MP4.\n"
        "- Shorts dynamic: короче, плотнее, больше опоры на пики звука и смены кадра.\n"
        "- Shorts podcast: длиннее, больше внимания лицам и паузам речи.\n"
        "- Shorts calm: меньше клипов, спокойнее темп.\n"
        "- Preview 30/60/90: один широкий 16:9 ролик с лучшими моментами и мягкими переходами.\n\n"
        f"- Обложка PNG: анализ видео и яркая 1280x720 обложка для {source_label}.\n\n"
        "После выбора буду писать этапы. На долгих видео статус обновляется примерно раз в минуту.",
        reply_markup=youtube_mode_keyboard(job_id),
    )


@router.callback_query(F.data.startswith("yt:"))
async def youtube_mode_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message or not callback.data:
        return
    _prefix, mode, job_id = callback.data.split(":", 2)
    job = pending_youtube_jobs.pop(job_id, None)
    if not job:
        await callback.message.answer("Эта YouTube-задача уже недоступна. Отправь ссылку еще раз.")
        return
    user_id, url, lang, created_at = job
    source_label = video_source_label(url)
    if user_id != callback.from_user.id:
        await callback.message.answer(f"Эта кнопка от другой задачи. Отправь свою {source_label}-ссылку.")
        return
    if mode == "cancel":
        await callback.message.answer(
            f"Ок, {source_label}-задача отменена."
            + next_steps_text("отправь другую ссылку", "или отправь файл для конвертации")
        )
        return
    if int(time.time()) - created_at > 900:
        await callback.message.answer(f"Задача устарела. Отправь {source_label}-ссылку еще раз.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "youtube", f"{source_label}-монтаж и обложки по ссылке входят в Pro-функции."):
        return
    if mode == "download":
        if youtube_semaphore.locked():
            await callback.message.answer(f"Сейчас уже идет {source_label}-обработка. Поставил скачивание в очередь.")
        async with youtube_semaphore:
            await process_video_download_link(callback.message, bot, url, lang, user_id)
        return
    if mode == "cover":
        if youtube_semaphore.locked():
            await callback.message.answer(f"Сейчас уже идет {source_label}-обработка. Поставил обложку в очередь.")
        async with youtube_semaphore:
            await process_youtube_cover_link(callback.message, bot, url, lang, user_id)
        return
    if youtube_semaphore.locked():
        await callback.message.answer(f"Сейчас уже идет {source_label}-нарезка. Поставил задачу в очередь.")
    async with youtube_semaphore:
        await process_youtube_link(callback.message, bot, url, lang, user_id, mode)


@router.callback_query(F.data.startswith("redo:"))
async def youtube_redo_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message or not callback.data:
        return
    _prefix, mode, job_id = callback.data.split(":", 2)
    job = recent_youtube_jobs.get(job_id)
    if not job:
        await callback.message.answer("Эта ссылка уже не хранится. Отправь YouTube-ссылку еще раз.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Эта кнопка от другой задачи. Отправь свою YouTube-ссылку.")
        return
    if int(time.time()) - job.created_at > 86400:
        recent_youtube_jobs.pop(job_id, None)
        await callback.message.answer("Задача устарела. Отправь YouTube-ссылку еще раз.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "youtube", "Повторная YouTube-обработка входит в Pro-функции."):
        return
    if youtube_semaphore.locked():
        await callback.message.answer("Сейчас уже идет монтаж. Поставил переделку в очередь.")
    async with youtube_semaphore:
        await process_youtube_link(callback.message, bot, job.url, job.lang, job.user_id, mode)


@router.callback_query(F.data.startswith("capstyle:"))
async def subtitle_style_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message or not callback.data:
        return
    _prefix, style, job_id = callback.data.split(":", 2)
    job = subtitle_jobs.get(job_id)
    if not job:
        await callback.message.answer("Это видео уже не хранится в очереди субтитров. Пересобери ролик или отправь файл заново.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Эта кнопка от другого видео. Отправь свое видео или YouTube-ссылку.")
        return
    style = style if style in SUBTITLE_STYLE_LABELS else "pop"
    await callback.message.answer(
        f"Стиль субтитров: {SUBTITLE_STYLE_LABELS[style]}.\nВыбери язык речи для распознавания:",
        reply_markup=subtitle_language_keyboard(style, job_id),
    )


@router.callback_query(F.data.startswith("cappreview:"))
async def subtitle_preview_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message or not callback.data:
        return
    job_id = callback.data.split(":", 1)[1]
    job = subtitle_jobs.get(job_id)
    if not job or job.user_id != callback.from_user.id:
        await callback.message.answer("Это видео уже недоступно для субтитров. Отправь файл или ссылку заново.")
        return
    preview_path: Path | None = None
    try:
        preview_path = await asyncio.to_thread(create_subtitle_style_preview_sheet, settings.output_dir)
        await callback.message.answer_photo(
            FSInputFile(preview_path),
            caption="Примеры стилей субтитров. После просмотра выберите стиль кнопкой ниже.",
            reply_markup=subtitle_keyboard(job_id),
        )
    finally:
        if preview_path:
            preview_path.unlink(missing_ok=True)


@router.callback_query(F.data.startswith("capback:"))
async def subtitle_back_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message or not callback.data:
        return
    job_id = callback.data.split(":", 1)[1]
    job = subtitle_jobs.get(job_id)
    if not job or job.user_id != callback.from_user.id:
        await callback.message.answer("Это видео уже недоступно для субтитров. Отправь файл или ссылку заново.")
        return
    await callback.message.answer("Выбери стиль субтитров:", reply_markup=subtitle_keyboard(job_id))


@router.callback_query(F.data.startswith("cap:"))
async def subtitle_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message or not callback.data:
        return
    parts = callback.data.split(":")
    if len(parts) == 3:
        _prefix, style, job_id = parts
        subtitle_language = normalize_subtitle_language(settings.subtitle_language)
    elif len(parts) == 4:
        _prefix, style, language_code, job_id = parts
        subtitle_language = normalize_subtitle_language(language_code)
    else:
        await callback.message.answer("Не понял выбранный вариант субтитров. Нажми стиль еще раз.")
        return
    job = subtitle_jobs.get(job_id)
    if not job:
        await callback.message.answer("Это видео уже не хранится в очереди субтитров. Пересобери ролик или отправь файл заново.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Эта кнопка от другого видео. Отправь свое видео или YouTube-ссылку.")
        return
    if not job.path.exists():
        subtitle_jobs.pop(job_id, None)
        await callback.message.answer("Файл уже недоступен. Пересобери ролик, и я снова дам кнопку субтитров.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "subtitles", "Субтитры входят в Pro-функции."):
        return

    if subtitle_semaphore.locked():
        await callback.message.answer("Сейчас уже делаю субтитры. Поставил задачу в очередь.")

    async with subtitle_semaphore:
        await process_subtitles(callback.message, bot, job, style, subtitle_language)


async def process_subtitles(
    message: Message,
    bot: Bot,
    job: SubtitleJob,
    style: str,
    subtitle_language: str | None = None,
) -> None:
    style = style if style in SUBTITLE_STYLE_LABELS else "pop"
    subtitle_language = normalize_subtitle_language(subtitle_language)
    style_label = SUBTITLE_STYLE_LABELS[style]
    language_label = subtitle_language_label(subtitle_language)
    started_at = time.time()
    state: dict[str, object] = {
        "started_at": started_at,
        "stage": "Субтитры: подготовка",
        "detail": job.path.name,
    }
    status = await message.answer(
        process_stage_text(
            "Добавление субтитров",
            SUBTITLE_STEPS,
            1,
            f"Стиль: {style_label}. Язык: {language_label}. Беру чистый MP4 без повторного наложения.",
        )
    )
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
        state["stage"] = "Субтитры: распознаю речь и верстаю текст"
        await safe_edit(
            status,
            process_stage_text("Добавление субтитров", SUBTITLE_STEPS, 2, "Извлекаю звук и ищу фразы"),
        )
        cues = await asyncio.to_thread(
            transcribe_subtitle_cues,
            job.path,
            settings.subtitle_model,
            subtitle_language,
        )
        if not cues:
            await safe_edit(
                status,
                "Не нашел речь для субтитров."
                + next_steps_text("попробуй другой фрагмент", "или отправь видео с более чистым звуком"),
            )
            return
        state["stage"] = "Субтитры: верстаю стиль"
        await safe_edit(
            status,
            process_stage_text(
                "Добавление субтитров",
                SUBTITLE_STEPS,
                3,
                f"Фраз найдено: {len(cues)}. Раскладываю текст по экрану.",
            ),
        )
        assets = await asyncio.to_thread(
            create_subtitle_assets,
            job.path,
            job.path.parent,
            f"{job.title}_{subtitle_language or 'auto'}",
            cues,
            style,
        )
        await safe_edit(
            status,
            process_stage_text("Добавление субтитров", SUBTITLE_STEPS, 4, "Вшиваю оформленные строки в видео"),
        )
        output = await asyncio.to_thread(
            render_subtitle_assets,
            job.path,
            assets,
            settings.subtitle_timeout_seconds,
        )
        await db.add_conversion(
            job.user_id,
            "youtube_subtitles",
            job.path.name,
            output.path.name,
            "mp4",
            job.path.stat().st_size,
            output.path.stat().st_size,
        )
        state["stage"] = "Субтитры: отправляю готовый MP4"
        state["detail"] = f"Размер: {human_size(output.path.stat().st_size)}"
        await safe_edit(
            status,
            process_stage_text(
                "Добавление субтитров",
                SUBTITLE_STEPS,
                5,
                f"Размер: {human_size(output.path.stat().st_size)}",
            ),
        )
        new_job_id = remember_subtitle_job(job.user_id, job.path, job.title)
        await message.answer_document(
            FSInputFile(output.path),
            caption=(
                "Готово: видео с вшитыми субтитрами\n"
                f"Стиль: {style_label}\n"
                f"Язык: {language_label}\n"
                f"Вес: {human_size(output.path.stat().st_size)}\n"
                f"Время обработки: {format_duration(time.time() - started_at)}"
                + next_steps_text(
                    "скачай версию с субтитрами",
                    "можно нажать другой стиль субтитров",
                    "можно отправить следующий файл или ссылку",
                )
            ),
            reply_markup=subtitle_keyboard(new_job_id),
        )
        await safe_edit(
            status,
            process_stage_text("Добавление субтитров", SUBTITLE_STEPS, 5, "Файл отправлен", done=True)
            + next_steps_text("проверь читаемость", "если стиль не подходит, нажми другой вариант"),
        )
    except SubtitleUnavailableError as exc:
        await safe_edit(
            status,
            str(exc) + next_steps_text("обнови зависимости", "перезапусти бота", "нажми кнопку субтитров еще раз"),
        )
    except Exception as exc:
        logger.exception("Subtitle job failed")
        await safe_edit(
            status,
            f"Не получилось сделать субтитры: {exc}"
            + next_steps_text("попробуй другой стиль", "если в ролике мало речи, отправь другой фрагмент"),
        )
    finally:
        heartbeat_task.cancel()


@router.callback_query(F.data.startswith("covertext:"))
async def cover_text_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message or not callback.data:
        return
    job_id = callback.data.split(":", 1)[1]
    job = cover_jobs.get(job_id)
    if not job:
        await callback.message.answer("Это видео уже не хранится для обложки. Отправь файл или ссылку заново.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Эта кнопка от другого видео. Отправь свое видео или YouTube-ссылку.")
        return
    if not job.path.exists():
        cover_jobs.pop(job_id, None)
        await callback.message.answer("Файл уже недоступен. Отправь видео заново.")
        return
    await state.set_state(CoverTextState.waiting_text)
    await state.update_data(cover_job_id=job_id)
    await callback.message.answer(
        "Напиши текст для обложки одним сообщением.\n\n"
        "1 строка — крупный заголовок.\n"
        "2 строка — описание/крючок помельче.\n\n"
        "Пример:\n"
        "Как он поднял продажи\n"
        "разбор главного приема"
    )


@router.message(CoverTextState.waiting_text, F.text)
async def cover_text_received(message: Message, bot: Bot, state: FSMContext) -> None:
    await ensure_user(message)
    if not message.from_user:
        return
    data = await state.get_data()
    job_id = str(data.get("cover_job_id") or "")
    job = cover_jobs.get(job_id)
    if not job or job.user_id != message.from_user.id or not job.path.exists():
        await state.clear()
        await message.answer("Видео для обложки уже недоступно. Отправь файл или ссылку заново.")
        return
    prompt = normalize_cover_prompt_text(message.text)
    if not prompt:
        await message.answer("Пришли заголовок и описание текстом. Первая строка будет главным заголовком.")
        return
    await state.clear()
    if not await ensure_action_allowed(message, message.from_user.id, "cover"):
        return
    if cover_semaphore.locked():
        await message.answer("Сейчас уже собираю обложку. Поставил задачу в очередь.")
    async with cover_semaphore:
        await process_video_cover(
            message,
            bot,
            job.user_id,
            job.path,
            prompt,
            job.duration_seconds,
        )


@router.callback_query(F.data.startswith("cover_session:"))
async def cover_session_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer("Готовлю обложку...")
    if not callback.from_user or not callback.message or not callback.data:
        return
    session_id = callback.data.split(":", 1)[1]
    session = get_owned_session(session_id, callback.from_user.id)
    if not session:
        await callback.message.answer("Этот файл уже недоступен. Отправь видео заново.")
        return
    if session.kind != "video":
        await callback.message.answer("Обложку можно сделать только для видео.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "cover"):
        return
    if cover_semaphore.locked():
        await callback.message.answer("Сейчас уже собираю обложку. Поставил задачу в очередь.")
    async with cover_semaphore:
        await process_video_cover(
            callback.message,
            bot,
            callback.from_user.id,
            session.path,
            session.cover_title or session.base_name,
            None,
        )


@router.callback_query(F.data.startswith("cover:"))
async def cover_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer("Готовлю обложку...")
    if not callback.from_user or not callback.message or not callback.data:
        return
    job_id = callback.data.split(":", 1)[1]
    job = cover_jobs.get(job_id)
    if not job:
        await callback.message.answer("Это видео уже не хранится для обложки. Отправь файл или ссылку заново.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Эта кнопка от другого видео. Отправь свое видео или YouTube-ссылку.")
        return
    if not job.path.exists():
        cover_jobs.pop(job_id, None)
        await callback.message.answer("Файл уже недоступен. Пересобери ролик или отправь видео заново.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "cover"):
        return
    if cover_semaphore.locked():
        await callback.message.answer("Сейчас уже собираю обложку. Поставил задачу в очередь.")
    async with cover_semaphore:
        await process_video_cover(
            callback.message,
            bot,
            job.user_id,
            job.path,
            job.title,
            job.duration_seconds,
        )


@router.callback_query(F.data.startswith("cover3:"))
async def cover_variants_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer("Делаю 3 варианта...")
    if not callback.from_user or not callback.message or not callback.data:
        return
    job_id = callback.data.split(":", 1)[1]
    job = cover_jobs.get(job_id)
    if not job:
        await callback.message.answer("Это видео уже не хранится для обложки. Отправь файл или ссылку заново.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Эта кнопка от другого видео. Отправь свое видео или YouTube-ссылку.")
        return
    if not job.path.exists():
        cover_jobs.pop(job_id, None)
        await callback.message.answer("Файл уже недоступен. Пересобери ролик или отправь видео заново.")
        return
    if not await ensure_pro_feature(callback.message, callback.from_user.id, "Еще 3 варианта обложки"):
        return
    if cover_semaphore.locked():
        await callback.message.answer("Сейчас уже собираю обложки. Поставил задачу в очередь.")
    async with cover_semaphore:
        await process_cover_variants(callback.message, bot, job, 3)


@router.callback_query(F.data.startswith("package:"))
async def publication_package_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer("Собираю пакет...")
    if not callback.from_user or not callback.message or not callback.data:
        return
    job_id = callback.data.split(":", 1)[1]
    job = cover_jobs.get(job_id)
    if not job:
        await callback.message.answer("Это видео уже не хранится для пакета. Отправь файл или ссылку заново.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Эта кнопка от другого видео. Отправь свое видео или YouTube-ссылку.")
        return
    if not job.path.exists():
        cover_jobs.pop(job_id, None)
        await callback.message.answer("Файл уже недоступен. Пересобери ролик или отправь видео заново.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "package", "Пакет публикации входит в Pro-функции."):
        return
    if cover_semaphore.locked():
        await callback.message.answer("Сейчас уже собираю пакет. Поставил задачу в очередь.")
    async with cover_semaphore:
        await process_publication_package(callback.message, bot, job)


async def process_cover_variants(message: Message, bot: Bot, job: CoverJob, count: int = 3) -> list[Path]:
    started_at = time.time()
    output_dir = settings.output_dir / str(job.user_id) / "cover_variants" / uuid.uuid4().hex[:10]
    status = await message.answer(process_stage_text("Варианты обложки", ["готовлю видео", "генерирую варианты", "собираю ZIP", "отправляю PNG"], 1, job.title))
    state: dict[str, object] = {"started_at": started_at, "stage": "Обложки: готовлю варианты", "detail": job.title}
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    covers: list[Path] = []
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        for index in range(1, count + 1):
            state["stage"] = f"Обложки: вариант {index}/{count}"
            await safe_edit(
                status,
                process_stage_text("Варианты обложки", ["готовлю видео", "генерирую варианты", "собираю ZIP", "отправляю PNG"], 2, f"Вариант {index}/{count}"),
            )
            cover_path = await asyncio.to_thread(
                create_business_cover,
                job.path,
                output_dir / f"variant_{index}",
                job.title,
                job.duration_seconds,
                settings.video_timeout_seconds,
                settings.face_detection_enabled,
            )
            covers.append(cover_path)
            await db.add_conversion(
                job.user_id,
                "cover",
                job.path.name,
                cover_path.name,
                "png",
                job.path.stat().st_size,
                cover_path.stat().st_size,
            )
            await message.answer_document(
                FSInputFile(cover_path),
                caption=f"Обложка {index}/{count}\nВес: {human_size(cover_path.stat().st_size)}",
            )
        zip_path = output_dir / "cover_variants.zip"
        await asyncio.to_thread(zip_files, covers, zip_path)
        await safe_edit(
            status,
            process_stage_text("Варианты обложки", ["готовлю видео", "генерирую варианты", "собираю ZIP", "отправляю PNG"], 4, "Варианты отправлены", done=True),
        )
        await message.answer_document(
            FSInputFile(zip_path),
            caption=(
                f"Готово: {count} варианта обложки одним ZIP\n"
                f"Время: {format_duration(time.time() - started_at)}"
                + next_steps_text("выбери лучший PNG", "если нужен полный набор, нажми «Пакет публикации ZIP»")
            ),
            reply_markup=cover_tools_keyboard(remember_cover_job(job.user_id, job.path, job.title, job.duration_seconds)),
        )
        return covers
    except Exception as exc:
        logger.exception("Cover variants failed")
        await safe_edit(status, f"Не получилось сделать варианты обложки: {exc}")
        return covers
    finally:
        heartbeat_task.cancel()


async def process_video_cover(
    message: Message,
    bot: Bot,
    user_id: int,
    source: Path,
    title: str,
    duration_seconds: float | None = None,
) -> Path | None:
    started_at = time.time()
    output_dir = settings.output_dir / str(user_id) / "covers" / uuid.uuid4().hex[:10]
    state: dict[str, object] = {"started_at": started_at, "stage": "Обложка PNG: подготовка", "detail": source.name}
    status = await message.answer(process_stage_text("Генерация обложки PNG", COVER_STEPS, 1, source.name))
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        info = await asyncio.to_thread(inspect_video, source)
        duration = duration_seconds or info.duration_seconds or 0
        resolution = f"{info.width}x{info.height}" if info.width and info.height else "unknown"
        state["stage"] = "Обложка PNG: выбираю кадр"
        state["detail"] = f"{title}\n{resolution}, {format_duration(duration)}"
        await safe_edit(
            status,
            process_stage_text(
                "Генерация обложки PNG",
                COVER_STEPS,
                2,
                f"Видео: {resolution}, длительность: {format_duration(duration)}",
            ),
        )
        state["stage"] = "Обложка PNG: ищу тему и картинки"
        await safe_edit(
            status,
            process_stage_text("Генерация обложки PNG", COVER_STEPS, 3, "Определяю тему по названию и ищу подходящие визуальные вставки"),
        )
        state["stage"] = "Обложка PNG: собираю макет"
        cover_path = await asyncio.to_thread(
            create_business_cover,
            source,
            output_dir,
            title,
            duration,
            settings.video_timeout_seconds,
            settings.face_detection_enabled,
        )
        state["stage"] = "Обложка PNG: отправляю файл"
        state["detail"] = f"Размер: {human_size(cover_path.stat().st_size)}"
        await safe_edit(
            status,
            process_stage_text("Генерация обложки PNG", COVER_STEPS, 5, f"Размер: {human_size(cover_path.stat().st_size)}"),
        )
        await db.add_conversion(
            user_id,
            "cover",
            source.name,
            cover_path.name,
            "png",
            source.stat().st_size,
            cover_path.stat().st_size,
        )
        tools_job_id = remember_cover_job(user_id, source, title, duration)
        await message.answer_document(
            FSInputFile(cover_path),
            caption=(
                "Готово: PNG-обложка для видео\n"
                f"Формат: 1280x720 PNG\n"
                f"Вес: {human_size(cover_path.stat().st_size)}\n"
                f"Время обработки: {format_duration(time.time() - started_at)}"
                + next_steps_text("скачай PNG", "нажми «Еще 3 варианта», если хочешь выбор", "можно собрать пакет публикации ZIP")
            ),
            reply_markup=cover_tools_keyboard(tools_job_id),
        )
        await safe_edit(
            status,
            process_stage_text("Генерация обложки PNG", COVER_STEPS, 5, "Файл отправлен", done=True)
            + next_steps_text("скачай PNG", "для другого кадра нажми кнопку обложки еще раз"),
        )
        return cover_path
    except Exception as exc:
        logger.exception("Cover job failed")
        await safe_edit(
            status,
            f"Не получилось сделать обложку: {exc}"
            + next_steps_text("попробуй другое видео", "или отправь YouTube-ссылку и выбери обложку"),
        )
        return None
    finally:
        heartbeat_task.cancel()


async def process_publication_package(message: Message, bot: Bot, job: CoverJob) -> Path | None:
    started_at = time.time()
    output_dir = settings.output_dir / str(job.user_id) / "publication_package" / uuid.uuid4().hex[:10]
    output_dir.mkdir(parents=True, exist_ok=True)
    status = await message.answer(process_stage_text("Пакет публикации", PUBLICATION_STEPS, 1, job.title))
    state: dict[str, object] = {"started_at": started_at, "stage": "Пакет публикации: подготовка", "detail": job.title}
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    package_files: list[Path] = []
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        info = await asyncio.to_thread(inspect_video, job.path)
        package_files.append(job.path)

        state["stage"] = "Пакет публикации: обложка"
        await safe_edit(status, process_stage_text("Пакет публикации", PUBLICATION_STEPS, 2, "Генерирую PNG-обложку"))
        cover_path = await asyncio.to_thread(
            create_business_cover,
            job.path,
            output_dir / "cover",
            job.title,
            job.duration_seconds or info.duration_seconds,
            settings.video_timeout_seconds,
            settings.face_detection_enabled,
        )
        package_files.append(cover_path)

        state["stage"] = "Пакет публикации: субтитры"
        await safe_edit(status, process_stage_text("Пакет публикации", PUBLICATION_STEPS, 3, "Пробую добавить Pop-субтитры"))
        subtitled_path: Path | None = None
        subtitle_note = "Субтитры: речь не найдена или распознавание недоступно."
        try:
            cues = await asyncio.to_thread(
                transcribe_subtitle_cues,
                job.path,
                settings.subtitle_model,
                settings.subtitle_language or None,
            )
            if cues:
                assets = await asyncio.to_thread(
                    create_subtitle_assets,
                    job.path,
                    output_dir / "subtitles",
                    f"{job.title}_package",
                    cues,
                    "pop",
                )
                result = await asyncio.to_thread(render_subtitle_assets, job.path, assets, settings.subtitle_timeout_seconds)
                subtitled_path = result.path
                package_files.append(subtitled_path)
                subtitle_note = f"Субтитры: добавлены, фраз найдено: {len(cues)}."
        except Exception:
            logger.exception("Publication package subtitles failed")

        state["stage"] = "Пакет публикации: описание"
        await safe_edit(status, process_stage_text("Пакет публикации", PUBLICATION_STEPS, 4, "Пишу описание и хештеги"))
        description_path = output_dir / "description.txt"
        hashtags = publication_hashtags(job.title)
        description_path.write_text(
            publication_description(job.title, info.duration_seconds, hashtags, subtitle_note),
            encoding="utf-8",
        )
        package_files.append(description_path)

        manifest_path = output_dir / "package_manifest.txt"
        manifest_path.write_text(
            "\n".join(
                [
                    "Publication package",
                    f"Title: {job.title}",
                    f"Video: {job.path.name}",
                    f"Cover: {cover_path.name}",
                    f"Subtitled: {subtitled_path.name if subtitled_path else 'not included'}",
                    f"Hashtags: {' '.join(hashtags)}",
                ]
            ),
            encoding="utf-8",
        )
        package_files.append(manifest_path)

        state["stage"] = "Пакет публикации: ZIP"
        await safe_edit(status, process_stage_text("Пакет публикации", PUBLICATION_STEPS, 5, "Упаковываю файлы"))
        zip_path = output_dir / f"{clean_base_name(job.title, 'publication')}_package.zip"
        await asyncio.to_thread(zip_files, package_files, zip_path)
        await db.add_conversion(
            job.user_id,
            "publication_package",
            job.path.name,
            zip_path.name,
            "zip",
            job.path.stat().st_size,
            zip_path.stat().st_size,
        )

        state["stage"] = "Пакет публикации: отправляю"
        await safe_edit(status, process_stage_text("Пакет публикации", PUBLICATION_STEPS, 6, f"Размер ZIP: {human_size(zip_path.stat().st_size)}"))
        caption = (
            "Готово: пакет публикации ZIP\n"
            "Внутри: видео, PNG-обложка, описание, хештеги"
            + (", версия с субтитрами" if subtitled_path else "")
            + f"\nВес: {human_size(zip_path.stat().st_size)}\n"
            f"Время: {format_duration(time.time() - started_at)}"
        )
        if zip_path.stat().st_size <= TELEGRAM_SAFE_UPLOAD_BYTES:
            await message.answer_document(FSInputFile(zip_path), caption=caption)
        else:
            await message.answer(caption + "\nZIP большой для отправки одним файлом, отправляю ключевые файлы отдельно.")
            await message.answer_document(FSInputFile(cover_path), caption="PNG-обложка из пакета")
            await message.answer_document(FSInputFile(description_path), caption="Описание и хештеги")
            if subtitled_path:
                await message.answer_document(FSInputFile(subtitled_path), caption="Видео с субтитрами")
        await safe_edit(
            status,
            process_stage_text("Пакет публикации", PUBLICATION_STEPS, 6, "Пакет отправлен", done=True)
            + next_steps_text("скачай ZIP", "выбери обложку или отправь новый файл"),
        )
        return zip_path
    except Exception as exc:
        logger.exception("Publication package failed")
        await safe_edit(
            status,
            f"Не получилось собрать пакет публикации: {exc}"
            + next_steps_text("попробуй короче видео", "или отдельно сделай обложку/субтитры"),
        )
        return None
    finally:
        heartbeat_task.cancel()


async def process_video_download_link(message: Message, bot: Bot, url: str, lang: str, user_id: int) -> None:
    started_at = time.time()
    source_label = video_source_label(url)
    job_id = uuid.uuid4().hex[:10]
    source_dir = settings.storage_dir / str(user_id) / "source_download" / job_id
    output_dir = settings.output_dir / str(user_id) / "source_download" / job_id
    state: dict[str, object] = {"started_at": started_at, "stage": f"{source_label}: читаю видео", "detail": ""}
    status = await message.answer(
        f"{source_label}-ссылка принята.\n\n"
        "Режим: скачать MP4\n"
        "Я скачаю доступный файл и при необходимости конвертирую его в MP4. Удаление watermark не выполняется."
    )
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        metadata = await asyncio.to_thread(get_youtube_metadata, url, settings.youtube_download_timeout_seconds)
        max_duration = settings.youtube_max_duration_minutes * 60
        if metadata.duration_seconds > max_duration:
            await safe_edit(
                status,
                f"Видео слишком длинное: {format_duration(metadata.duration_seconds)}.\n"
                f"Лимит сейчас: {settings.youtube_max_duration_minutes} минут.",
            )
            return
        state["stage"] = f"{source_label}: скачиваю файл"
        state["detail"] = f"{metadata.title}\nДлительность: {format_duration(metadata.duration_seconds)}"
        await safe_edit(
            status,
            f"Скачиваю {source_label}-видео.\n"
            f"Название: {metadata.title}\n"
            f"Длительность: {format_duration(metadata.duration_seconds)}",
        )
        download = await asyncio.to_thread(download_youtube_video, url, source_dir, settings.youtube_download_timeout_seconds)
        source_size = download.path.stat().st_size
        result_path = download.path
        result_info = inspect_video(result_path)
        if result_path.suffix.lower() != ".mp4":
            state["stage"] = f"{source_label}: конвертирую в MP4"
            await safe_edit(
                status,
                f"Источник скачался как {result_path.suffix.lstrip('.').upper() or 'видео'}.\n"
                "Конвертирую в MP4, чтобы Telegram отправил именно видеофайл.",
            )
            converted = await asyncio.to_thread(
                convert_video,
                result_path,
                output_dir,
                "mp4",
                clean_base_name(download.title, "source_video"),
                settings.video_timeout_seconds,
            )
            result_path = converted.path
            result_info = converted.output
        size = result_path.stat().st_size
        if size > TELEGRAM_SAFE_UPLOAD_BYTES:
            await safe_edit(
                status,
                f"Файл скачан, но он слишком большой для отправки ботом: {human_size(size)}.\n"
                "Можно выбрать Shorts или Preview, чтобы получить меньший ролик.",
            )
            return
        subtitle_id = remember_subtitle_job(user_id, result_path, download.title)
        cover_id = remember_cover_job(user_id, result_path, download.title, download.duration_seconds)
        await db.add_conversion(
            user_id,
            "source_download",
            download.webpage_url,
            result_path.name,
            "mp4",
            source_size,
            size,
        )
        await message.answer_document(
            FSInputFile(result_path),
            caption=(
                f"{source_label}: MP4 готов\n"
                f"Файл: {download.title}\n"
                f"Длительность: {format_duration(result_info.duration_seconds or download.duration_seconds)}\n"
                f"Вес: {human_size(size)}\n\n"
                "Удаление watermark не выполняется. Ниже можно добавить субтитры или сделать обложку."
            ),
            reply_markup=media_tools_keyboard(subtitle_id, cover_id),
        )
        await safe_edit(status, f"Готово: {source_label}-MP4 отправлен.")
    except Exception as exc:
        logger.exception("%s source download failed", source_label)
        await safe_edit(
            status,
            f"Не получилось скачать {source_label}-ссылку: {exc}\n"
            "Если это приватное видео или источник ограничил скачивание, отправь видео файлом.",
        )
    finally:
        heartbeat_task.cancel()


async def process_youtube_cover_link(message: Message, bot: Bot, url: str, lang: str, user_id: int) -> None:
    started_at = time.time()
    source_label = video_source_label(url)
    job_id = uuid.uuid4().hex[:10]
    source_dir = settings.storage_dir / str(user_id) / "youtube_cover" / job_id
    output_dir = settings.output_dir / str(user_id) / "youtube_cover" / job_id
    state: dict[str, object] = {"started_at": started_at, "stage": f"Обложка {source_label}: читаю видео", "detail": ""}
    status = await message.answer(
        f"Принял {source_label}-ссылку. Подготовлю PNG-обложку по видео.\n\n"
        "Режим: обложка PNG\n"
        "Этап 1/5: читаю данные видео."
    )
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        metadata = await asyncio.to_thread(get_youtube_metadata, url, settings.youtube_download_timeout_seconds)
        max_duration = settings.youtube_max_duration_minutes * 60
        if metadata.duration_seconds > max_duration:
            await safe_edit(
                status,
                f"Видео слишком длинное: {format_duration(metadata.duration_seconds)}.\n"
                f"Лимит сейчас: {settings.youtube_max_duration_minutes} минут.",
            )
            return
        size_text = human_size(metadata.estimated_size_bytes) if metadata.estimated_size_bytes else "не удалось оценить заранее"
        state["stage"] = f"Обложка {source_label}: скачиваю видео"
        state["detail"] = f"{metadata.title}\nДлительность: {format_duration(metadata.duration_seconds)}"
        await safe_edit(
            status,
            "Режим: обложка PNG\n"
            "Этап 2/5: скачиваю видео.\n"
            f"Название: {metadata.title}\n"
            f"Длительность: {format_duration(metadata.duration_seconds)}\n"
            f"Примерный размер: {size_text}",
        )
        download = await asyncio.to_thread(download_youtube_video, url, source_dir, settings.youtube_download_timeout_seconds)
        state["stage"] = "Обложка YouTube: выбираю кадр"
        state["detail"] = f"Скачано: {human_size(download.path.stat().st_size)}"
        await safe_edit(
            status,
            "Режим: обложка PNG\n"
            "Этап 3/5: видео скачано, выбираю сильный кадр.\n"
            f"Файл: {download.title}\n"
            f"Скачано: {human_size(download.path.stat().st_size)}",
        )
        state["stage"] = "Обложка YouTube: собираю PNG"
        await safe_edit(
            status,
            "Режим: обложка PNG\n"
            "Этап 4/5: определяю тему, ищу визуальные вставки и собираю яркую 1280x720 PNG-обложку.",
        )
        cover_path = await asyncio.to_thread(
            create_business_cover,
            download.path,
            output_dir,
            download.title,
            download.duration_seconds,
            settings.video_timeout_seconds,
            settings.face_detection_enabled,
        )
        await db.add_conversion(
            user_id,
            "youtube_cover",
            download.path.name,
            cover_path.name,
            "png",
            download.path.stat().st_size,
            cover_path.stat().st_size,
        )
        cover_job_id = remember_cover_job(user_id, download.path, download.title, download.duration_seconds)
        state["stage"] = "Обложка YouTube: отправляю PNG"
        state["detail"] = f"Размер: {human_size(cover_path.stat().st_size)}"
        await safe_edit(
            status,
            "Режим: обложка PNG\n"
            "Этап 5/5: отправляю готовый PNG.\n"
            f"Размер: {human_size(cover_path.stat().st_size)}",
        )
        await message.answer_document(
            FSInputFile(cover_path),
            caption=(
                "Готово: PNG-обложка по YouTube-ссылке\n"
                f"Источник: {download.title}\n"
                f"Формат: 1280x720 PNG\n"
                f"Вес: {human_size(cover_path.stat().st_size)}\n"
                f"Время обработки: {format_duration(time.time() - started_at)}"
                + next_steps_text("скачай PNG", "можно снова отправить ссылку и выбрать монтаж или Shorts")
            ),
            reply_markup=cover_tools_keyboard(cover_job_id),
        )
        await safe_edit(
            status,
            "Готово. PNG-обложка отправлена."
            + next_steps_text("скачай PNG", "для монтажа отправь ссылку еще раз и выбери Shorts или Preview"),
        )
    except Exception as exc:
        logger.exception("YouTube cover job failed")
        await safe_edit(
            status,
            f"Не получилось сделать обложку по YouTube-ссылке: {exc}"
            + next_steps_text("попробуй другую ссылку", "или отправь видео файлом"),
        )
    finally:
        heartbeat_task.cancel()


async def process_youtube_link(message: Message, bot: Bot, url: str, lang: str, user_id: int, mode: str = "regular") -> None:
    started_at = time.time()
    source_label = video_source_label(url)
    job_id = uuid.uuid4().hex[:10]
    source_dir = settings.storage_dir / str(user_id) / "youtube" / job_id
    output_dir = settings.output_dir / str(user_id) / "youtube" / job_id
    profile = youtube_render_profile(mode)
    mode = profile.mode
    mode_label = profile.label
    state: dict[str, object] = {"started_at": started_at, "stage": "Этап 1/6: читаю данные видео", "detail": ""}
    status = await message.answer(
        f"Принял {source_label}-ссылку. Скачаю видео и обработаю выбранный режим.\n\n"
        f"Режим: {mode_label}\n"
        "Этап 1/6: читаю данные видео.\n"
        "Что происходит: получаю название, длительность и примерный размер без скачивания."
    )
    heartbeat_task = asyncio.create_task(heartbeat(status, state))

    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
        metadata = await asyncio.to_thread(get_youtube_metadata, url, settings.youtube_download_timeout_seconds)
        max_duration = settings.youtube_max_duration_minutes * 60
        if metadata.duration_seconds > max_duration:
            await safe_edit(
                status,
                f"Видео слишком длинное: {format_duration(metadata.duration_seconds)}.\n"
                f"Лимит сейчас: {settings.youtube_max_duration_minutes} минут.",
            )
            return

        if profile.is_backstage:
            planned_clips = max(
                1,
                (max(6, profile.backstage_output_seconds - profile.backstage_intro_seconds))
                // max(1, profile.backstage_segment_seconds),
            )
            output_length = min(profile.backstage_output_seconds, max(1, int(metadata.duration_seconds)))
            if metadata.duration_seconds < max(6, profile.backstage_segment_seconds):
                await safe_edit(status, "Видео слишком короткое для Preview-монтажа.")
                return
            plan_text = (
                f"План: один широкий ролик 16:9 до {output_length} сек., "
                f"монтажных фрагментов: {planned_clips}, заставка: {profile.backstage_intro_seconds} сек."
            )
            cut_estimate = estimate_cut_time(
                metadata.duration_seconds,
                planned_clips,
                profile.backstage_segment_seconds,
                settings.face_detection_enabled,
            )
        else:
            planned_clips = planned_clip_count(
                metadata.duration_seconds,
                profile.max_shorts,
                profile.short_seconds,
            )
            if planned_clips == 0:
                await safe_edit(status, "Видео слишком короткое для Shorts-нарезки.")
                return
            plan_text = f"План клипов: {planned_clips} x {profile.short_seconds} сек."
            cut_estimate = estimate_cut_time(
                metadata.duration_seconds,
                planned_clips,
                profile.short_seconds,
                settings.face_detection_enabled,
            )

        size_text = human_size(metadata.estimated_size_bytes) if metadata.estimated_size_bytes else "не удалось оценить заранее"
        state["stage"] = "Этап 2/6: скачиваю видео"
        state["detail"] = f"{metadata.title}\nДлительность: {format_duration(metadata.duration_seconds)}"
        await safe_edit(
            status,
            f"Режим: {mode_label}\n"
            "Этап 2/6: скачиваю видео.\n"
            f"Название: {metadata.title}\n"
            f"Длительность: {format_duration(metadata.duration_seconds)}\n"
            f"Примерный размер загрузки: {size_text}\n"
            f"Примерное время загрузки: {estimate_download_time(metadata.estimated_size_bytes)}\n"
            f"{plan_text}\n"
            f"Оценка обработки после загрузки: {cut_estimate}\n\n"
            "Почему может быть долго: YouTube отдает длинные видео кусками, скорость зависит от сети и самого YouTube.",
        )

        download = await asyncio.to_thread(download_youtube_video, url, source_dir, settings.youtube_download_timeout_seconds)
        state["stage"] = "Этап 3/6: готовлю точки нарезки"
        state["detail"] = f"Скачано: {human_size(download.path.stat().st_size)}"
        await safe_edit(
            status,
            f"Режим: {mode_label}\n"
            "Этап 3/6: видео скачано, готовлю точки нарезки.\n"
            f"Файл: {download.title}\n"
            f"Скачано: {human_size(download.path.stat().st_size)}\n"
            f"Длительность: {format_duration(download.duration_seconds)}\n"
            + (
                "Дальше соберу один широкий Preview-ролик со заставкой."
                if profile.is_backstage
                else "Дальше каждый готовый клип отправлю сразу, не дожидаясь всей пачки."
            ),
        )

        if profile.is_backstage and settings.youtube_backstage_enabled:
            state["stage"] = "Этап 4/6: собираю широкий Preview-монтаж"
            state["detail"] = "Ищу моменты, делаю заставку и склеиваю 16:9"
            await safe_edit(
                status,
                f"Режим: {mode_label}\n"
                "Этап 4/6: собираю широкий Preview-монтаж.\n"
                "Что происходит: анализирую движение, лица, смены кадра, паузы и интонационные всплески, делаю заставку и склейку.\n"
                f"Формат: 16:9, до {profile.backstage_output_seconds} сек.\n"
                "Это может занять несколько минут на длинном видео.",
            )
            montage = await asyncio.to_thread(
                create_backstage_montage,
                download.path,
                output_dir,
                download.title,
                download.duration_seconds,
                settings.video_timeout_seconds,
                profile.backstage_output_seconds,
                profile.backstage_segment_seconds,
                profile.backstage_intro_seconds,
                profile.sample_limit,
                profile.min_gap_seconds,
                settings.face_detection_enabled,
            )
            await db.add_conversion(
                user_id,
                "youtube_preview",
                download.path.name,
                montage.path.name,
                "mp4",
                download.path.stat().st_size,
                montage.path.stat().st_size,
            )
            state["stage"] = "Этап 5/6: отправляю Preview-ролик"
            state["detail"] = f"Размер: {human_size(montage.path.stat().st_size)}"
            await safe_edit(
                status,
                f"Режим: {mode_label}\n"
                "Этап 5/6: ролик готов, отправляю файл.\n"
                f"Размер: {human_size(montage.path.stat().st_size)}",
            )
            replay_id = remember_youtube_job(user_id, url, lang)
            subtitle_id = remember_subtitle_job(user_id, montage.path, montage.path.stem)
            cover_id = remember_cover_job(user_id, montage.path, download.title, montage.duration_seconds)
            cover_path = None
            try:
                cover_path = await asyncio.to_thread(
                    create_business_cover,
                    montage.path,
                    output_dir,
                    download.title,
                    montage.duration_seconds,
                    settings.video_timeout_seconds,
                    settings.face_detection_enabled,
                )
            except Exception:
                logger.exception("Cover generation failed")
            await message.answer_document(
                FSInputFile(montage.path),
                caption=(
                    "Готово: Preview-монтаж\n"
                    f"Источник: {download.title}\n"
                    "Формат: широкое видео 16:9, MP4\n"
                    f"Длина: до {profile.backstage_output_seconds} сек.\n"
                    f"Вес: {human_size(montage.path.stat().st_size)}\n"
                    f"Общее время обработки: {format_duration(time.time() - started_at)}"
                    f"{AFTER_RESULT_HINT}"
                ),
                reply_markup=youtube_replay_keyboard(replay_id, mode, subtitle_id, cover_id),
            )
            if cover_path:
                await message.answer_document(FSInputFile(cover_path), caption="PNG-обложка для этого монтажа.")
            await safe_edit(
                status,
                "Готово. Preview-ролик отправлен."
                + next_steps_text(
                    "скачай MP4",
                    "нажми Subtitles, если нужны субтитры",
                    "нажми Redo, если хочешь другой темп монтажа",
                    "отправь следующий файл или ссылку",
                ),
            )
            return

        starts = await asyncio.to_thread(
            calculate_smart_clip_starts,
            download.path,
            download.duration_seconds,
            profile.max_shorts,
            profile.short_seconds,
            profile.sample_limit,
            settings.face_detection_enabled,
        )
        clips = []
        base_name = clean_base_name(download.title, "youtube_short")
        state["stage"] = "Этап 4/6: читаю параметры видео"
        state["detail"] = "Готовлю face-focus и вертикальный crop"
        source_info = await asyncio.to_thread(inspect_video, download.path)

        for index, start_second in enumerate(starts, start=1):
            state["detail"] = f"Клип {index}/{len(starts)}, старт {format_duration(start_second)}"
            await safe_edit(
                status,
                f"Режим: {mode_label}\n"
                "Этап 4/6: режу Shorts по одному.\n"
                f"Сейчас: клип {index}/{len(starts)}\n"
            f"Старт фрагмента: {format_duration(start_second)}\n"
            "Что происходит: выбираю момент по лицам, движению, паузам и интонации, делаю вертикальный 1080x1920, кодирую MP4.\n"
                "Как только клип готов, сразу отправляю его сюда.",
            )
            clip = await asyncio.to_thread(
                make_short_clip,
                download.path,
                output_dir,
                base_name,
                download.duration_seconds,
                start_second,
                index,
                profile.short_seconds,
                settings.video_timeout_seconds,
                settings.shorts_focus_mode,
                settings.face_detection_enabled,
                source_info.width,
                source_info.height,
            )
            clips.append(clip)
            subtitle_id = remember_subtitle_job(user_id, clip.path, clip.path.stem)
            cover_id = remember_cover_job(user_id, clip.path, clip.path.stem, clip.duration_seconds)
            await message.answer_document(
                FSInputFile(clip.path),
                caption=(
                    f"Shorts {index}/{len(starts)}\n"
                    f"Старт: {format_duration(clip.start_seconds)}\n"
                    f"Длина: {format_duration(clip.duration_seconds)}\n"
                    f"Вес: {human_size(clip.path.stat().st_size)}\n\n"
                    f"Готово {index}/{len(starts)}. Осталось: {len(starts) - index}."
                ),
                reply_markup=media_tools_keyboard(subtitle_id, cover_id),
            )

        if not clips:
            await safe_edit(status, "Не получилось сделать клипы: видео слишком короткое.")
            return

        state["stage"] = "Этап 5/6: упаковываю ZIP"
        state["detail"] = f"Клипов: {len(clips)}"
        await safe_edit(
            status,
            f"Режим: {mode_label}\n"
            "Этап 5/6: клипы уже отправлены, дополнительно упаковываю ZIP.\n"
            f"Клипов: {len(clips)}\n"
            f"Старты: {describe_clips(clips)}\n"
            "ZIP нужен, чтобы все клипы можно было скачать одним файлом.",
        )
        zip_path = await asyncio.to_thread(zip_clips, clips, output_dir / f"{base_name}_shorts.zip")
        await db.add_conversion(
            user_id,
            "youtube_shorts",
            download.path.name,
            zip_path.name,
            "zip",
            download.path.stat().st_size,
            zip_path.stat().st_size,
        )
        replay_id = remember_youtube_job(user_id, url, lang)
        cover_id = remember_cover_job(user_id, download.path, download.title, download.duration_seconds)
        cover_path = None
        try:
            cover_path = await asyncio.to_thread(
                create_business_cover,
                download.path,
                output_dir,
                download.title,
                download.duration_seconds,
                settings.video_timeout_seconds,
                settings.face_detection_enabled,
            )
        except Exception:
            logger.exception("Cover generation failed")

        caption = (
            f"Готово: {len(clips)} Shorts\n"
            f"Источник: {download.title}\n"
            f"Старты клипов: {describe_clips(clips)}\n"
            f"Вес архива: {human_size(zip_path.stat().st_size)}\n"
            f"Общее время обработки: {format_duration(time.time() - started_at)}"
            f"{AFTER_RESULT_HINT}"
        )
        state["stage"] = "Этап 6/6: отправляю ZIP"
        state["detail"] = f"Размер ZIP: {human_size(zip_path.stat().st_size)}"
        await safe_edit(
            status,
            f"Режим: {mode_label}\n"
            "Этап 6/6: отправляю общий ZIP-архив.\n"
            f"Размер ZIP: {human_size(zip_path.stat().st_size)}",
        )

        if zip_path.stat().st_size <= TELEGRAM_SAFE_UPLOAD_BYTES:
            await message.answer_document(FSInputFile(zip_path), caption=caption, reply_markup=youtube_replay_keyboard(replay_id, mode, cover_job_id=cover_id))
        else:
            await message.answer(caption + "\nZIP большой, поэтому клипы уже отправлены отдельно выше.", reply_markup=youtube_replay_keyboard(replay_id, mode, cover_job_id=cover_id))
        if cover_path:
            await message.answer_document(FSInputFile(cover_path), caption="PNG-обложка для Shorts-пачки.")
        await safe_edit(
            status,
            "Готово. Все клипы отправлены."
            + next_steps_text(
                "скачай отдельные клипы или общий ZIP",
                "нажми Subtitles на нужном клипе",
                "нажми Redo, если хочешь другую нарезку",
                "отправь следующий файл или ссылку",
            ),
        )
    except Exception as exc:
        logger.exception("YouTube shorts job failed")
        await safe_edit(status, f"Не получилось обработать YouTube-ссылку: {exc}")
    finally:
        heartbeat_task.cancel()


@router.message(F.photo | F.document | F.video)
async def receive_file(message: Message, bot: Bot) -> None:
    prune_sessions()
    await ensure_user(message)
    if not message.from_user:
        return

    file_id, original_name, kind, file_size = extract_file_meta(message)
    if not file_id:
        return
    if not await ensure_paid_access(message, message.from_user.id, "Конвертация видео" if kind == "video" else "Конвертация изображений"):
        return

    if file_size and file_size > max_size_bytes(kind):
        await message.answer(
            f"Файл слишком большой. Лимит для {'видео' if kind == 'video' else 'изображений'}: "
            f"{settings.max_video_mb if kind == 'video' else settings.max_image_mb} MB."
            + next_steps_text("сожми файл или отправь более короткий фрагмент", "можно попробовать YouTube-ссылку вместо файла")
        )
        return

    status = await message.answer(
        process_stage_text("Подготовка файла", FILE_PREP_STEPS, 1, f"Файл: {original_name}")
    )
    session_id = uuid.uuid4().hex[:12]
    source_dir = settings.storage_dir / str(message.from_user.id)
    source_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_name).suffix or (".mp4" if kind == "video" else ".bin")
    source_path = source_dir / f"{session_id}_{clean_base_name(original_name)}{suffix}"

    await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
    tg_file = await bot.get_file(file_id)
    await bot.download_file(tg_file.file_path, destination=source_path)
    await safe_edit(
        status,
        process_stage_text("Подготовка файла", FILE_PREP_STEPS, 2, f"Загружено: {human_size(source_path.stat().st_size)}"),
    )

    if source_path.stat().st_size > max_size_bytes(kind):
        source_path.unlink(missing_ok=True)
        await safe_edit(
            status,
            "Файл оказался больше лимита после загрузки."
            + next_steps_text("отправь файл меньше", "для видео можно прислать ссылку и выбрать режим монтажа"),
        )
        return

    sessions[session_id] = FileSession(
        user_id=message.from_user.id,
        path=source_path,
        original_name=original_name,
        base_name=clean_base_name(original_name),
        kind=kind,
        expires_at=int(time.time()) + settings.session_ttl_minutes * 60,
        cover_title=normalize_cover_prompt_text(message.caption) if kind == "video" else None,
    )
    user_latest_session[message.from_user.id] = session_id
    await safe_edit(status, process_stage_text("Подготовка файла", FILE_PREP_STEPS, 3, "Читаю параметры файла"))

    if kind == "video":
        await prepare_video_message(message, session_id, source_path, status)
    else:
        await prepare_image_message(message, session_id, source_path, status)


def extract_file_meta(message: Message) -> tuple[str | None, str, str, int | None]:
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, f"photo_{message.message_id}.jpg", "image", photo.file_size
    if message.video:
        return message.video.file_id, message.video.file_name or f"video_{message.message_id}.mp4", "video", message.video.file_size
    if message.document:
        mime_type = message.document.mime_type or ""
        name = message.document.file_name or f"document_{message.message_id}"
        ext = Path(name).suffix.lower()
        is_video = mime_type.startswith("video/") or ext in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
        return message.document.file_id, name, "video" if is_video else "image", message.document.file_size
    return None, "file", "image", None


async def prepare_image_message(message: Message, session_id: str, source_path: Path, status: Message | None = None) -> None:
    try:
        info = await asyncio.to_thread(inspect_image, source_path)
    except Exception:
        if status:
            await safe_edit(
                status,
                "Не смог открыть файл как изображение."
                + next_steps_text("отправь PNG, JPG, WEBP, GIF, TIFF или BMP", "или отправь видео/YouTube-ссылку"),
            )
        else:
            await message.answer("Не смог открыть файл как изображение." + next_steps_text("отправь другой файл"))
        source_path.unlink(missing_ok=True)
        sessions.pop(session_id, None)
        return
    if status:
        await safe_edit(
            status,
            process_stage_text(
                "Подготовка файла",
                FILE_PREP_STEPS,
                4,
                f"Формат: {info.format}, размер: {info.width}x{info.height}, вес: {human_size(info.size_bytes)}",
                done=True,
            ),
        )

    await message.answer(
        "Изображение принято.\n"
        f"Формат: {info.format}, размер: {info.width}x{info.height}, кадров: {info.frames}, вес: {human_size(info.size_bytes)}.\n"
        "Выбери формат, потом режим сжатия:"
        f"{NEXT_STEP_HINT}",
        reply_markup=formats_keyboard(session_id, available_image_formats(source_path), "image"),
    )


async def prepare_video_message(message: Message, session_id: str, source_path: Path, status: Message | None = None) -> None:
    if not ffmpeg_available():
        text = "Видео принято, но обработчик видео недоступен." + next_steps_text("обнови зависимости", "перезапусти бота и отправь файл заново")
        if status:
            await safe_edit(status, text)
        else:
            await message.answer(text)
        return
    try:
        info = await asyncio.to_thread(inspect_video, source_path)
        resolution = f"{info.width}x{info.height}" if info.width and info.height else "unknown"
        details = f"Разрешение: {resolution}, длительность: {format_duration(info.duration_seconds)}, вес: {human_size(info.size_bytes)}.\n"
    except Exception:
        details = "Не удалось прочитать метаданные, но можно попробовать конвертацию.\n"

    if status:
        await safe_edit(
            status,
            process_stage_text("Подготовка файла", FILE_PREP_STEPS, 4, details.strip(), done=True),
        )

    session = sessions.get(session_id)
    if session and session.cover_title:
        cover_hint = "\nТекст для обложки уже взял из подписи к видео.\n"
    else:
        cover_hint = "\nДля обложки можно следующим сообщением прислать название и описание: первая строка — заголовок, вторая — крючок.\n"

    await message.answer(
        "Видео принято.\n" + details + cover_hint + "Выбери формат:" + NEXT_STEP_HINT,
        reply_markup=formats_keyboard(session_id, VIDEO_FORMATS, "video"),
    )


@router.callback_query(F.data.startswith("rename:"))
async def rename_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    session_id = callback.data.split(":", 1)[1]
    session = get_owned_session(session_id, callback.from_user.id if callback.from_user else 0)
    if not session:
        if callback.message:
            await callback.message.answer("Этот файл уже недоступен. Отправь его заново.")
        return
    await state.set_state(RenameState.waiting_name)
    await state.update_data(session_id=session_id)
    if callback.message:
        await callback.message.answer(
            "Переименование: жду новое имя файла без расширения."
            + next_steps_text("напиши новое имя одним сообщением", "для отмены напиши /cancel")
        )


@router.message(RenameState.waiting_name)
async def rename_finish(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Напиши новое имя текстом." + next_steps_text("или отправь /cancel для отмены"))
        return
    if message.text.strip().lower() in {"/cancel", "cancel", "отмена", "скасувати"}:
        await state.clear()
        await message.answer(
            "Ок, переименование отменено."
            + next_steps_text("выбери формат кнопкой", "или отправь новый файл")
        )
        return

    data = await state.get_data()
    session_id = data.get("session_id")
    session = get_owned_session(session_id, message.from_user.id if message.from_user else 0)
    await state.clear()
    if not session:
        await message.answer("Этот файл уже недоступен. Отправь его заново.")
        return
    session.base_name = clean_base_name(message.text or session.base_name)
    formats = VIDEO_FORMATS if session.kind == "video" else available_image_formats(session.path)
    await message.answer(
        f"Имя обновлено: {session.base_name}."
        + next_steps_text("выбери формат кнопкой ниже", "или отправь новый файл"),
        reply_markup=formats_keyboard(session_id, formats, session.kind),
    )


@router.callback_query(F.data.startswith("convert:"))
async def convert_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer("Конвертирую...")
    if not callback.from_user or not callback.message:
        return
    parsed = parse_convert_callback_data(callback.data)
    if not parsed:
        await callback.message.answer("Не понял параметры конвертации. Выбери формат еще раз.")
        return
    session_id = parsed.session_id
    target_format = parsed.target_format
    image_mode = normalize_image_mode(parsed.image_mode)
    session = get_owned_session(session_id, callback.from_user.id)
    if not session:
        await callback.message.answer("Этот файл уже недоступен. Отправь его заново.")
        return
    await bot.send_chat_action(callback.message.chat.id, ChatAction.UPLOAD_DOCUMENT)
    if session.kind == "video":
        if not await ensure_action_allowed(callback.message, callback.from_user.id, "video"):
            return
        await convert_video_callback(callback, session_id, session, target_format)
    else:
        if parsed.image_mode is None:
            await callback.message.answer(
                f"Формат: {target_format.upper()}.\nВыбери режим сжатия:",
                reply_markup=image_mode_keyboard(session_id, target_format),
            )
            return
        if not await ensure_action_allowed(callback.message, callback.from_user.id, "image"):
            return
        await convert_image_callback(callback, session_id, session, target_format, image_mode)


def get_owned_session(session_id: str | None, user_id: int) -> FileSession | None:
    prune_sessions()
    if not session_id:
        return None
    session = sessions.get(session_id)
    if not session or session.user_id != user_id:
        return None
    return session


async def convert_image_callback(
    callback: CallbackQuery,
    session_id: str,
    session: FileSession,
    target_format: str,
    image_mode: str,
) -> None:
    assert callback.message and callback.from_user
    mode_label = IMAGE_MODE_LABELS[image_mode]
    status = await callback.message.answer(
        process_stage_text("Конвертация изображения", IMAGE_CONVERT_STEPS, 1, f"Формат: {target_format.upper()}, режим: {mode_label}")
    )
    try:
        await safe_edit(status, process_stage_text("Конвертация изображения", IMAGE_CONVERT_STEPS, 1, "Проверяю исходный файл"))
        source_info = await asyncio.to_thread(inspect_image, session.path)
        await safe_edit(status, process_stage_text("Конвертация изображения", IMAGE_CONVERT_STEPS, 2, "Меняю формат и сохраняю качество"))
        output_path, output_info = await asyncio.to_thread(
            convert_image,
            session.path,
            settings.output_dir / str(callback.from_user.id),
            target_format,
            session.base_name,
            image_mode,
        )
        safe_output: tuple[Path, object] | None = None
        if output_info.size_bytes > source_info.size_bytes and target_format != "webp":
            safe_path, safe_info = await asyncio.to_thread(
                convert_image,
                session.path,
                settings.output_dir / str(callback.from_user.id),
                "webp",
                f"{session.base_name}_safe_light",
                "light",
            )
            safe_output = (safe_path, safe_info)
    except Exception as exc:
        logger.exception("Image conversion failed")
        await safe_edit(
            status,
            f"Не получилось конвертировать изображение: {exc}"
            + next_steps_text("попробуй другой формат", "если файл поврежден, отправь его заново"),
        )
        return

    await safe_edit(
        status,
        process_stage_text("Конвертация изображения", IMAGE_CONVERT_STEPS, 3, f"Результат: {output_path.name}"),
    )
    await db.add_conversion(callback.from_user.id, "image", session.original_name, output_path.name, target_format, source_info.size_bytes, output_info.size_bytes)
    await safe_edit(status, process_stage_text("Конвертация изображения", IMAGE_CONVERT_STEPS, 4, "Отправляю готовый файл"))
    await callback.message.answer_document(
        FSInputFile(output_path),
        caption=(
            f"{output_path.name}\n"
            f"{source_info.format} -> {output_info.format}\n"
            f"{output_info.width}x{output_info.height}, кадров: {output_info.frames}\n"
            f"Режим: {mode_label}\n"
            f"Вес: {human_size(source_info.size_bytes)} -> {human_size(output_info.size_bytes)}"
            f"{image_weight_note(source_info.size_bytes, output_info.size_bytes)}"
            f"{AFTER_RESULT_HINT}"
        ),
        reply_markup=share_keyboard(session_id, output_path.name),
        disable_content_type_detection=True,
    )
    if safe_output:
        safe_path, safe_info = safe_output
        await callback.message.answer_document(
            FSInputFile(safe_path),
            caption=(
                "Защита веса: выбранный формат получился тяжелее исходника, поэтому дополнительно сделал легкую WEBP-версию.\n"
                f"Вес: {human_size(source_info.size_bytes)} -> {human_size(safe_info.size_bytes)}"
            ),
            disable_content_type_detection=True,
        )
    await safe_edit(
        status,
        process_stage_text("Конвертация изображения", IMAGE_CONVERT_STEPS, 4, "Файл отправлен", done=True)
        + next_steps_text("скачай результат", "выбери другой формат или отправь новый файл"),
    )


async def convert_video_callback(callback: CallbackQuery, session_id: str, session: FileSession, target_format: str) -> None:
    assert callback.message and callback.from_user
    if not ffmpeg_available():
        await callback.message.answer(
            "Обработчик видео недоступен."
            + next_steps_text("обнови зависимости", "перезапусти бота и отправь видео заново")
        )
        return
    status = await callback.message.answer(
        process_stage_text("Конвертация видео", VIDEO_CONVERT_STEPS, 1, f"Формат: {target_format.upper()}")
    )
    try:
        await safe_edit(status, process_stage_text("Конвертация видео", VIDEO_CONVERT_STEPS, 2, "Кодирую видео и звук"))
        result = await asyncio.to_thread(
            convert_video,
            session.path,
            settings.output_dir / str(callback.from_user.id),
            target_format,
            session.base_name,
            settings.video_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        await safe_edit(
            status,
            "Видео слишком долго конвертируется."
            + next_steps_text("попробуй файл короче или легче", "для длинных роликов отправь YouTube-ссылку и выбери монтаж"),
        )
        return
    except Exception as exc:
        logger.exception("Video conversion failed")
        await safe_edit(
            status,
            f"Не получилось конвертировать видео: {exc}"
            + next_steps_text("попробуй другой формат", "если видео повреждено, отправь файл заново"),
        )
        return

    await safe_edit(
        status,
        process_stage_text("Конвертация видео", VIDEO_CONVERT_STEPS, 3, f"Результат: {result.path.name}"),
    )
    await db.add_conversion(callback.from_user.id, "video", session.original_name, result.path.name, target_format, result.source.size_bytes, result.output.size_bytes)
    resolution = f"{result.output.width}x{result.output.height}" if result.output.width and result.output.height else "unknown"
    subtitle_id = remember_subtitle_job(callback.from_user.id, result.path, result.path.stem) if target_format == "mp4" else None
    cover_id = remember_cover_job(callback.from_user.id, result.path, result.path.stem, result.output.duration_seconds)
    await safe_edit(status, process_stage_text("Конвертация видео", VIDEO_CONVERT_STEPS, 4, "Отправляю готовый файл"))
    await callback.message.answer_document(
        FSInputFile(result.path),
        caption=(
            f"{result.path.name}\n"
            f"Видео -> {target_format.upper()}\n"
            f"Разрешение: {resolution}, длительность: {format_duration(result.output.duration_seconds)}\n"
            f"Вес: {human_size(result.source.size_bytes)} -> {human_size(result.output.size_bytes)}"
            f"{AFTER_RESULT_HINT}"
        ),
        reply_markup=share_keyboard(session_id, result.path.name, subtitle_id, cover_id),
    )
    await safe_edit(
        status,
        process_stage_text("Конвертация видео", VIDEO_CONVERT_STEPS, 4, "Файл отправлен", done=True)
        + next_steps_text(
            "скачай результат",
            "для MP4 нажми Subtitles, если нужны субтитры",
            "отправь новый файл или YouTube-ссылку",
        ),
    )


async def cleanup_loop() -> None:
    while True:
        prune_sessions()
        await asyncio.sleep(settings.cleanup_interval_seconds)


def normalize_resume_text(value: str | None) -> str:
    return utils_normalize_resume_text(value)


def resume_safe_text(value: str) -> str:
    return utils_resume_safe_text(value)


def resume_is_empty(value: str) -> bool:
    return utils_resume_is_empty(value)


def register_resume_fonts() -> tuple[str, str]:
    candidates = [
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in candidates:
        if Path(regular).exists() and Path(bold).exists():
            try:
                if "ResumeRegular" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("ResumeRegular", regular))
                if "ResumeBold" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("ResumeBold", bold))
                return "ResumeRegular", "ResumeBold"
            except Exception:
                logger.exception("Could not register resume font")
    return "Helvetica", "Helvetica-Bold"


RESUME_TEMPLATES: dict[str, dict[str, str]] = {
    "1": {"name": "Classic", "label": "чистый ATS", "accent": "#2563eb", "dark": "#111827", "muted": "#4b5563", "soft": "#eff6ff", "layout": "single"},
    "2": {"name": "Executive", "label": "строгий премиум", "accent": "#0f766e", "dark": "#10201f", "muted": "#475569", "soft": "#ecfdf5", "layout": "band"},
    "3": {"name": "Creative", "label": "яркий профиль", "accent": "#c026d3", "dark": "#2f1234", "muted": "#5b5061", "soft": "#fdf4ff", "layout": "two"},
    "4": {"name": "Modern", "label": "современный блок", "accent": "#ea580c", "dark": "#1f2937", "muted": "#57534e", "soft": "#fff7ed", "layout": "cards"},
    "5": {"name": "Tech", "label": "IT и digital", "accent": "#0891b2", "dark": "#0f172a", "muted": "#475569", "soft": "#ecfeff", "layout": "two"},
    "6": {"name": "Minimal", "label": "европейский стиль", "accent": "#52525b", "dark": "#18181b", "muted": "#52525b", "soft": "#f4f4f5", "layout": "single"},
    "7": {"name": "Premium", "label": "сильная колонка", "accent": "#b45309", "dark": "#1c1917", "muted": "#57534e", "soft": "#fffbeb", "layout": "two"},
    "8": {"name": "Focus", "label": "акцент на опыт", "accent": "#7c3aed", "dark": "#2e1065", "muted": "#5b5566", "soft": "#f5f3ff", "layout": "rail"},
    "9": {"name": "Nordic", "label": "спокойный HR", "accent": "#0369a1", "dark": "#0c2538", "muted": "#475569", "soft": "#f0f9ff", "layout": "two"},
    "10": {"name": "Legal", "label": "консервативный", "accent": "#374151", "dark": "#111827", "muted": "#4b5563", "soft": "#f9fafb", "layout": "single"},
    "11": {"name": "Startup", "label": "энергичный", "accent": "#16a34a", "dark": "#052e16", "muted": "#4b5563", "soft": "#f0fdf4", "layout": "cards"},
    "12": {"name": "Finance", "label": "деловой", "accent": "#1d4ed8", "dark": "#172554", "muted": "#475569", "soft": "#eef2ff", "layout": "band"},
    "13": {"name": "Academic", "label": "образование", "accent": "#7f1d1d", "dark": "#1f1717", "muted": "#57534e", "soft": "#fef2f2", "layout": "photo_left"},
    "14": {"name": "Compact", "label": "плотно и ясно", "accent": "#0d9488", "dark": "#134e4a", "muted": "#475569", "soft": "#f0fdfa", "layout": "split"},
}


def resume_preview_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_preview_line(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, color: str, height: int = 5) -> None:
    draw.rounded_rectangle((x, y, x + width, y + height), radius=height // 2, fill=color)


def draw_preview_photo(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, color: str) -> None:
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color, outline="white", width=2)
    draw.ellipse((cx - radius // 3, cy - radius // 2, cx + radius // 3, cy + radius // 6), fill="white")
    draw.pieslice((cx - radius // 2, cy, cx + radius // 2, cy + radius), 180, 360, fill="white")


def draw_resume_template_thumb(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], key: str, template: dict[str, str], fonts: dict[str, ImageFont.ImageFont]) -> None:
    x, y, w, h = box
    accent = template["accent"]
    dark = template["dark"]
    soft = template["soft"]
    layout = template["layout"]
    draw.rounded_rectangle((x, y, x + w, y + h), radius=16, fill="white", outline="#d9dee8", width=2)
    inner = (x + 14, y + 14, w - 28, h - 28)
    ix, iy, iw, ih = inner

    if layout == "band":
        draw.rounded_rectangle((ix, iy, ix + iw, iy + 54), radius=10, fill=dark)
        draw_preview_photo(draw, ix + iw - 28, iy + 27, 17, accent)
        draw_preview_line(draw, ix + 12, iy + 15, iw - 70, "white", 7)
        draw_preview_line(draw, ix + 12, iy + 30, iw - 95, "#dbeafe", 5)
        for col in range(3):
            cx = ix + col * ((iw - 12) // 3)
            draw.rounded_rectangle((cx, iy + 67, cx + (iw - 20) // 3, iy + 105), radius=7, fill=soft, outline="#e5e7eb")
        start_y = iy + 122
    elif layout == "two":
        side_w = 48
        draw.rounded_rectangle((ix, iy, ix + side_w, iy + ih), radius=10, fill=dark)
        draw_preview_photo(draw, ix + side_w // 2, iy + 30, 16, accent)
        for n in range(5):
            draw_preview_line(draw, ix + 9, iy + 62 + n * 16, side_w - 18, "white", 4)
        draw_preview_line(draw, ix + side_w + 14, iy + 8, iw - side_w - 24, dark, 8)
        draw_preview_line(draw, ix + side_w + 14, iy + 24, iw - side_w - 54, accent, 5)
        start_y = iy + 48
        for n in range(7):
            draw_preview_line(draw, ix + side_w + 14, start_y + n * 15, iw - side_w - 26 - (n % 3) * 18, "#9ca3af", 4)
    elif layout == "cards":
        draw_preview_line(draw, ix, iy + 4, iw - 42, dark, 8)
        draw_preview_photo(draw, ix + iw - 20, iy + 18, 17, accent)
        draw_preview_line(draw, ix, iy + 22, iw - 82, accent, 5)
        card_w = (iw - 10) // 2
        for row in range(2):
            for col in range(2):
                cx = ix + col * (card_w + 10)
                cy = iy + 52 + row * 52
                draw.rounded_rectangle((cx, cy, cx + card_w, cy + 41), radius=8, fill=soft, outline="#e5e7eb")
                draw_preview_line(draw, cx + 8, cy + 9, card_w - 20, accent, 5)
                draw_preview_line(draw, cx + 8, cy + 22, card_w - 14, "#9ca3af", 4)
        start_y = iy + 164
    elif layout == "rail":
        draw_preview_line(draw, ix + 34, iy + 4, iw - 64, dark, 8)
        draw_preview_photo(draw, ix + iw - 20, iy + 17, 16, accent)
        for n in range(4):
            cy = iy + 48 + n * 39
            draw.rounded_rectangle((ix, cy, ix + 36, cy + 25), radius=6, fill=accent)
            draw_preview_line(draw, ix + 46, cy + 3, iw - 58, "#6b7280", 5)
            draw_preview_line(draw, ix + 46, cy + 16, iw - 82, "#cbd5e1", 4)
        start_y = iy + ih - 15
    elif layout == "photo_left":
        draw.rounded_rectangle((ix, iy, ix + 52, iy + 78), radius=10, fill=dark)
        draw_preview_photo(draw, ix + 26, iy + 28, 18, accent)
        draw_preview_line(draw, ix + 9, iy + 58, 34, "white", 4)
        draw_preview_line(draw, ix + 66, iy + 8, iw - 70, dark, 8)
        draw_preview_line(draw, ix + 66, iy + 26, iw - 100, accent, 5)
        draw.rounded_rectangle((ix + 66, iy + 48, ix + iw, iy + 86), radius=8, fill=soft, outline="#e5e7eb")
        start_y = iy + 103
    elif layout == "split":
        left_w = 70
        draw.rounded_rectangle((ix, iy, ix + left_w, iy + ih), radius=10, fill=dark)
        draw_preview_photo(draw, ix + left_w // 2, iy + 30, 17, accent)
        draw_preview_line(draw, ix + 10, iy + 62, left_w - 20, "white", 6)
        for n in range(5):
            draw_preview_line(draw, ix + 10, iy + 86 + n * 15, left_w - 22, "#d1d5db", 4)
        draw_preview_line(draw, ix + left_w + 14, iy + 9, iw - left_w - 30, dark, 8)
        draw.rounded_rectangle((ix + left_w + 14, iy + 36, ix + iw, iy + 83), radius=8, fill=soft, outline="#e5e7eb")
        start_y = iy + 103
    else:
        draw_preview_line(draw, ix, iy + 8, iw - 45, dark, 9)
        draw_preview_photo(draw, ix + iw - 20, iy + 20, 17, accent)
        draw_preview_line(draw, ix, iy + 29, iw - 80, accent, 5)
        draw.rounded_rectangle((ix, iy + 50, ix + iw, iy + 90), radius=8, fill=soft, outline="#e5e7eb")
        start_y = iy + 106

    if layout not in {"two", "rail", "cards"}:
        for n in range(5):
            draw_preview_line(draw, ix, start_y + n * 14, iw - 10 - (n % 3) * 24, "#9ca3af", 4)

    label = f"{key}. {template['name']}"
    draw.text((x + 10, y + h - 25), label, fill=dark, font=fonts["label"])
    draw.text((x + 10, y + h - 10), template["layout"], fill=accent, font=fonts["tiny"], anchor="la")


def create_resume_template_preview_sheet(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"resume_templates_preview_{uuid.uuid4().hex}.png"
    width = 1600
    margin = 34
    gap = 22
    cols = 2
    card_w = (width - margin * 2 - gap) // cols
    card_h = 260
    rows = (len(RESUME_TEMPLATES) + cols - 1) // cols
    header_h = 96
    height = header_h + margin + rows * card_h + (rows - 1) * gap + margin
    image = Image.new("RGB", (width, height), "#f3f6fb")
    draw = ImageDraw.Draw(image)
    fonts = {
        "title": resume_preview_font(34, bold=True),
        "subtitle": resume_preview_font(18),
        "label": resume_preview_font(18, bold=True),
        "tiny": resume_preview_font(12),
    }
    draw.text((margin, 28), "Resume templates preview", fill="#111827", font=fonts["title"])
    draw.text((margin, 67), "Мини-пример расположения блоков, фото, карточек и колонок перед выбором PDF", fill="#4b5563", font=fonts["subtitle"])
    for index, (key, template) in enumerate(RESUME_TEMPLATES.items()):
        row = index // cols
        col = index % cols
        x = margin + col * (card_w + gap)
        y = header_h + margin + row * (card_h + gap)
        draw_resume_template_thumb(draw, (x, y, card_w, card_h), key, template, fonts)
    image.save(path, quality=92)
    return path


def create_subtitle_style_preview_sheet(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"subtitle_styles_preview_{uuid.uuid4().hex}.png"
    width = 1500
    card_w = 330
    card_h = 155
    margin = 34
    gap = 22
    cols = 4
    styles = list(SUBTITLE_STYLE_LABELS.items())
    rows = (len(styles) + cols - 1) // cols
    header_h = 90
    height = header_h + margin + rows * card_h + (rows - 1) * gap + margin
    image = Image.new("RGB", (width, height), "#101318")
    draw = ImageDraw.Draw(image)
    fonts = {
        "title": resume_preview_font(34, bold=True),
        "label": resume_preview_font(18, bold=True),
        "body": resume_preview_font(25, bold=True),
        "mono": resume_preview_font(22, bold=False),
        "small": resume_preview_font(13),
    }
    draw.text((margin, 24), "Subtitle style preview", fill="white", font=fonts["title"])
    draw.text((margin, 62), "Выберите стиль кнопкой ниже. Это пример шрифта, цвета и подачи.", fill="#cbd5e1", font=fonts["small"])
    palettes = {
        "pop": ("#ffcc33", "#ffffff", "#111827"),
        "neon": ("#ff38d4", "#00f5ff", "#170026"),
        "candy": ("#ff7bd5", "#ffe66d", "#311047"),
        "kinetic": ("#34d399", "#ffffff", "#050816"),
        "bounce": ("#facc15", "#ffffff", "#24104f"),
        "comic": ("#ff4d4d", "#ffe600", "#101010"),
        "clean": ("#ffffff", "#d1d5db", "#1f2937"),
        "minimal": ("#e5e7eb", "#9ca3af", "#111827"),
        "editorial": ("#f8fafc", "#94a3b8", "#172554"),
        "typewriter": ("#fef3c7", "#f59e0b", "#1c1917"),
        "headline": ("#ffffff", "#ef4444", "#111827"),
        "luxury": ("#fef3c7", "#d4af37", "#17120a"),
        "mono": ("#bbf7d0", "#22c55e", "#07130c"),
        "soft": ("#ffffff", "#93c5fd", "#172033"),
    }
    for index, (style, label) in enumerate(styles):
        row = index // cols
        col = index % cols
        x = margin + col * (card_w + gap)
        y = header_h + margin + row * (card_h + gap)
        primary, accent, bg = palettes.get(style, palettes["pop"])
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=18, fill=bg, outline="#334155", width=2)
        draw.text((x + 16, y + 14), label, fill=accent, font=fonts["label"])
        sample_font = fonts["mono"] if style in {"mono", "typewriter"} else fonts["body"]
        sample = "BIG RESULT" if style in {"pop", "headline", "kinetic"} else "Чистый текст"
        draw.text((x + 18, y + 58), sample, fill=primary, font=sample_font, stroke_width=2 if style in {"pop", "comic", "headline"} else 1, stroke_fill="#000000")
        draw.text((x + 18, y + 100), "пример строки субтитров", fill=accent, font=fonts["small"])
        if style in {"neon", "candy", "bounce"}:
            draw.arc((x + card_w - 74, y + 28, x + card_w - 18, y + 84), 15, 325, fill=accent, width=4)
        if style in {"clean", "minimal", "editorial"}:
            draw.line((x + 18, y + 128, x + card_w - 18, y + 128), fill=accent, width=2)
    image.save(path, quality=92)
    return path


def add_resume_section(story: list, title: str, content: str, styles: dict, heading_style: str = "ResumeSection") -> None:
    if not content:
        return
    block = [Paragraph(title, styles[heading_style]), Spacer(1, 4)]
    paragraphs = [line.strip() for line in content.splitlines() if line.strip()]
    for line in paragraphs or [content]:
        prefix = "• " if line.startswith(("-", "•", "*")) else ""
        clean = line[1:].strip() if prefix else line
        block.append(Paragraph(f"{prefix}{resume_safe_text(clean)}", styles["ResumeBody"]))
        block.append(Spacer(1, 3))
    block.append(Spacer(1, 8))
    if len(paragraphs) <= 4:
        story.append(KeepTogether(block))
    else:
        story.extend(block)


def add_resume_contact_section(
    story: list,
    title: str,
    data: dict[str, str],
    styles: dict,
    template: dict[str, str],
    content_width: float,
) -> None:
    table = build_resume_contact_table(data, styles, template, content_width, max_columns=2)
    if not table:
        return
    story.append(Paragraph(title, styles["ResumeSection"]))
    story.append(table)
    story.append(Spacer(1, 8))


def detect_resume_face_box(image: Image.Image) -> tuple[int, int, int, int] | None:
    try:
        rgb = image.convert("RGB")
        array = np.array(rgb)
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
        gray = cv2.equalizeHist(gray)
        cascades = [
            Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml",
            Path(cv2.data.haarcascades) / "haarcascade_profileface.xml",
        ]
        faces: list[tuple[int, int, int, int]] = []
        for cascade_path in cascades:
            classifier = cv2.CascadeClassifier(str(cascade_path))
            if classifier.empty():
                continue
            detected = classifier.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(48, 48))
            faces.extend(tuple(map(int, face)) for face in detected)
            flipped = cv2.flip(gray, 1)
            flipped_detected = classifier.detectMultiScale(flipped, scaleFactor=1.08, minNeighbors=4, minSize=(48, 48))
            width = image.width
            faces.extend((width - x - w, y, w, h) for x, y, w, h in flipped_detected)
        if not faces:
            return None
        return max(faces, key=lambda face: face[2] * face[3])
    except Exception:
        logger.exception("Could not detect face for resume photo")
        return None


def face_aware_square_crop(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGBA")
    face = detect_resume_face_box(image)
    width, height = image.size
    side = min(width, height)
    if face:
        x, y, w, h = face
        center_x = x + w / 2
        center_y = y + h * 0.58
        side = min(width, height, max(w, h) * 3.0)
    else:
        center_x = width / 2
        center_y = height * 0.42
    side = int(max(1, side))
    left = int(round(center_x - side / 2))
    top = int(round(center_y - side / 2))
    left = max(0, min(left, width - side))
    top = max(0, min(top, height - side))
    return image.crop((left, top, left + side, top + side))


def make_resume_avatar(photo_path: str | None, output_dir: Path) -> Path | None:
    if not photo_path:
        return None
    source = Path(photo_path)
    if not source.exists():
        return None
    try:
        with Image.open(source) as image:
            image = face_aware_square_crop(image)
            image = image.resize((520, 520), Image.Resampling.LANCZOS)
            mask = Image.new("L", image.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, image.width - 1, image.height - 1), fill=255)
            image.putalpha(mask)
            avatar = output_dir / f"resume_avatar_{uuid.uuid4().hex}.png"
            image.save(avatar)
            return avatar
    except Exception:
        logger.exception("Could not prepare resume photo")
        return None


def build_resume_styles(template: dict[str, str]) -> dict:
    regular, bold = register_resume_fonts()
    styles = getSampleStyleSheet()
    accent = colors.HexColor(template["accent"])
    dark = colors.HexColor(template["dark"])
    muted = colors.HexColor(template["muted"])
    soft = colors.HexColor(template["soft"])

    styles["Normal"].fontName = regular
    compact = template["name"] == "Compact"
    styles["Normal"].fontSize = 9 if compact else 9.5
    styles["Normal"].leading = 11.8 if compact else 12.5
    styles["Normal"].textColor = dark

    custom = {
        "ResumeName": ParagraphStyle("ResumeName", parent=styles["Normal"], fontName=bold, fontSize=23 if compact else 25, leading=27 if compact else 29, textColor=dark, spaceAfter=4, alignment=TA_LEFT),
        "ResumeRole": ParagraphStyle("ResumeRole", parent=styles["Normal"], fontName=bold, fontSize=12, leading=15, textColor=accent, spaceAfter=7),
        "ResumeContact": ParagraphStyle("ResumeContact", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=muted, spaceAfter=8),
        "ResumeSection": ParagraphStyle("ResumeSection", parent=styles["Normal"], fontName=bold, fontSize=10.2 if compact else 10.5, leading=12.5 if compact else 13, textColor=accent, spaceBefore=7, spaceAfter=4, alignment=TA_LEFT),
        "ResumeBody": ParagraphStyle("ResumeBody", parent=styles["Normal"], fontSize=8.9 if compact else 9.2, leading=11.7 if compact else 12.2, textColor=dark, alignment=TA_LEFT),
        "ResumeSummary": ParagraphStyle("ResumeSummary", parent=styles["Normal"], fontSize=9 if compact else 9.5, leading=12 if compact else 12.8, textColor=dark, backColor=soft, borderColor=accent, borderWidth=0.5, borderPadding=7, spaceAfter=9, alignment=TA_LEFT),
        "ResumeSideTitle": ParagraphStyle("ResumeSideTitle", parent=styles["Normal"], fontName=bold, fontSize=9, leading=11, textColor=colors.white, spaceBefore=7, spaceAfter=4),
        "ResumeSideBody": ParagraphStyle("ResumeSideBody", parent=styles["Normal"], fontSize=8.2, leading=10.5, textColor=colors.white),
        "ResumeWhiteName": ParagraphStyle("ResumeWhiteName", parent=styles["Normal"], fontName=bold, fontSize=23 if compact else 25, leading=27 if compact else 29, textColor=colors.white, spaceAfter=4),
        "ResumeWhiteRole": ParagraphStyle("ResumeWhiteRole", parent=styles["Normal"], fontName=bold, fontSize=11.5, leading=14, textColor=colors.HexColor("#f8fafc"), spaceAfter=7),
        "ResumeWhiteBody": ParagraphStyle("ResumeWhiteBody", parent=styles["Normal"], fontSize=8.6, leading=10.8, textColor=colors.white),
        "ResumeCardTitle": ParagraphStyle("ResumeCardTitle", parent=styles["Normal"], fontName=bold, fontSize=9.5, leading=12, textColor=accent, spaceAfter=4),
        "ResumeCardBody": ParagraphStyle("ResumeCardBody", parent=styles["Normal"], fontSize=8.7, leading=11.2, textColor=dark),
        "ResumeRailTitle": ParagraphStyle("ResumeRailTitle", parent=styles["Normal"], fontName=bold, fontSize=8.8, leading=11, textColor=colors.white, alignment=TA_CENTER),
        "ResumeTiny": ParagraphStyle("ResumeTiny", parent=styles["Normal"], fontSize=7.5, leading=9.5, textColor=muted, alignment=TA_CENTER),
        "ResumeContactIcon": ParagraphStyle("ResumeContactIcon", parent=styles["Normal"], fontName=bold, fontSize=6.4, leading=7.6, textColor=colors.white, alignment=TA_CENTER),
        "ResumeContactText": ParagraphStyle("ResumeContactText", parent=styles["Normal"], fontSize=8.2, leading=9.7, textColor=muted, alignment=TA_LEFT),
        "ResumeContactTextDark": ParagraphStyle("ResumeContactTextDark", parent=styles["Normal"], fontSize=8.2, leading=9.7, textColor=dark, alignment=TA_LEFT),
        "ResumeContactTextLight": ParagraphStyle("ResumeContactTextLight", parent=styles["Normal"], fontSize=8.1, leading=9.7, textColor=colors.white, alignment=TA_LEFT),
        "ResumeMetricLabel": ParagraphStyle("ResumeMetricLabel", parent=styles["Normal"], fontName=bold, fontSize=7.6, leading=9, textColor=accent, alignment=TA_CENTER),
        "ResumeMetricValue": ParagraphStyle("ResumeMetricValue", parent=styles["Normal"], fontName=bold, fontSize=8.8, leading=10.5, textColor=dark, alignment=TA_CENTER),
        "ResumeChip": ParagraphStyle("ResumeChip", parent=styles["Normal"], fontSize=7.8, leading=9.6, textColor=dark, alignment=TA_CENTER),
    }
    for style in custom.values():
        if style.name not in styles:
            styles.add(style)
    return styles


def draw_resume_page(canvas, doc, template: dict[str, str]) -> None:
    width, height = A4
    accent = colors.HexColor(template["accent"])
    soft = colors.HexColor(template["soft"])
    canvas.saveState()
    canvas.setFillColor(soft)
    canvas.rect(0, height - 18 * mm, width, 18 * mm, stroke=0, fill=1)
    canvas.setFillColor(accent)
    canvas.rect(0, height - 18 * mm, width, 2.2 * mm, stroke=0, fill=1)
    canvas.setStrokeColor(colors.HexColor("#e5e7eb"))
    canvas.setLineWidth(0.4)
    canvas.line(doc.leftMargin, 13 * mm, width - doc.rightMargin, 13 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#9ca3af"))
    canvas.drawRightString(width - doc.rightMargin, 8 * mm, f"Resume • {template['name']}")
    canvas.restoreState()


def resume_section_data(data: dict) -> dict[str, str]:
    return utils_resume_section_data(data)


@dataclass(frozen=True)
class ResumeContactItem:
    kind: str
    icon: str
    value: str


class ResumeContactIconFlowable(Flowable):
    def __init__(self, kind: str, template: dict[str, str], size: float = 8.8 * mm) -> None:
        super().__init__()
        self.kind = kind
        self.template = template
        self.width = size
        self.height = size

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self) -> None:
        canvas = self.canv
        size = self.width
        bg = colors.HexColor(resume_icon_color(self.kind, self.template))
        canvas.saveState()
        canvas.setFillColor(bg)
        canvas.setStrokeColor(bg)
        canvas.roundRect(0, 0, size, size, radius=size * 0.25, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setStrokeColor(colors.white)
        canvas.setLineWidth(max(0.6, size * 0.055))
        self._draw_symbol(canvas, size)
        canvas.restoreState()

    def _draw_symbol(self, canvas, size: float) -> None:
        kind = self.kind
        if kind == "email":
            x, y, w, h = size * 0.20, size * 0.29, size * 0.60, size * 0.42
            canvas.roundRect(x, y, w, h, radius=size * 0.04, stroke=1, fill=0)
            canvas.line(x, y + h, x + w / 2, y + h * 0.48)
            canvas.line(x + w, y + h, x + w / 2, y + h * 0.48)
            canvas.line(x, y, x + w * 0.40, y + h * 0.35)
            canvas.line(x + w, y, x + w * 0.60, y + h * 0.35)
        elif kind == "phone":
            canvas.setLineWidth(max(1.2, size * 0.12))
            canvas.line(size * 0.33, size * 0.68, size * 0.43, size * 0.78)
            canvas.line(size * 0.43, size * 0.78, size * 0.66, size * 0.55)
            canvas.line(size * 0.66, size * 0.55, size * 0.76, size * 0.65)
            canvas.line(size * 0.28, size * 0.30, size * 0.72, size * 0.74)
        elif kind == "telegram":
            path = canvas.beginPath()
            path.moveTo(size * 0.18, size * 0.52)
            path.lineTo(size * 0.82, size * 0.76)
            path.lineTo(size * 0.64, size * 0.18)
            path.lineTo(size * 0.50, size * 0.42)
            path.lineTo(size * 0.38, size * 0.34)
            path.close()
            canvas.drawPath(path, stroke=0, fill=1)
        elif kind == "instagram":
            canvas.roundRect(size * 0.22, size * 0.22, size * 0.56, size * 0.56, radius=size * 0.14, stroke=1, fill=0)
            canvas.circle(size * 0.50, size * 0.50, size * 0.13, stroke=1, fill=0)
            canvas.circle(size * 0.66, size * 0.66, size * 0.035, stroke=0, fill=1)
        elif kind == "linkedin":
            self._draw_center_text(canvas, "in", size, scale=0.48)
        elif kind == "github":
            canvas.circle(size * 0.50, size * 0.54, size * 0.22, stroke=1, fill=0)
            canvas.line(size * 0.34, size * 0.72, size * 0.26, size * 0.82)
            canvas.line(size * 0.66, size * 0.72, size * 0.74, size * 0.82)
            canvas.line(size * 0.42, size * 0.30, size * 0.42, size * 0.16)
            canvas.line(size * 0.58, size * 0.30, size * 0.58, size * 0.16)
        elif kind == "web":
            canvas.circle(size * 0.50, size * 0.50, size * 0.28, stroke=1, fill=0)
            canvas.line(size * 0.22, size * 0.50, size * 0.78, size * 0.50)
            canvas.line(size * 0.50, size * 0.22, size * 0.50, size * 0.78)
            canvas.arc(size * 0.33, size * 0.25, size * 0.67, size * 0.75, 90, 180)
            canvas.arc(size * 0.33, size * 0.25, size * 0.67, size * 0.75, 270, 180)
        elif kind == "behance":
            self._draw_center_text(canvas, "Be", size, scale=0.42)
        else:
            self._draw_center_text(canvas, "i", size, scale=0.56)

    @staticmethod
    def _draw_center_text(canvas, text: str, size: float, scale: float) -> None:
        canvas.setFont("Helvetica-Bold", size * scale)
        canvas.drawCentredString(size / 2, size * 0.32, text)


def resume_icon_color(kind: str, template: dict[str, str]) -> str:
    colors_by_kind = {
        "email": "#ef4444",
        "phone": "#16a34a",
        "telegram": "#229ED9",
        "instagram": "#c13584",
        "linkedin": "#0a66c2",
        "github": "#24292f",
        "behance": "#1769ff",
        "web": template["accent"],
    }
    return colors_by_kind.get(kind, template["accent"])


def resume_contact_items(data: dict[str, str]) -> list[ResumeContactItem]:
    raw_parts: list[str] = []
    for field in ("contact", "links"):
        value = normalize_resume_text(data.get(field))
        if value:
            raw_parts.extend(re.split(r"[\n,|;]+", value))

    items: list[ResumeContactItem] = []
    seen: set[str] = set()
    for raw in raw_parts:
        value = " ".join(raw.strip(" -*\t").split())
        if not value:
            continue
        kind, icon = resume_contact_kind(value)
        key = re.sub(r"\s+", "", value.lower())
        if key in seen:
            continue
        seen.add(key)
        items.append(ResumeContactItem(kind=kind, icon=icon, value=value[:96]))
    return items


def resume_contact_kind(value: str) -> tuple[str, str]:
    lower = value.lower()
    if re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", value, flags=re.IGNORECASE):
        return "email", "@"
    if "instagram.com" in lower or lower.startswith("ig:") or lower.startswith("inst:") or " instagram" in f" {lower}":
        return "instagram", "IG"
    if "linkedin.com" in lower or lower.startswith("in:"):
        return "linkedin", "IN"
    if "github.com" in lower or lower.startswith("gh:"):
        return "github", "GH"
    if "t.me/" in lower or "telegram.me/" in lower or lower.startswith("tg:") or re.fullmatch(r"@[A-Za-z0-9_]{4,}", value):
        return "telegram", "TG"
    digits = re.sub(r"\D+", "", value)
    if len(digits) >= 7 and (value.lstrip().startswith("+") or re.search(r"\b(phone|tel|тел|номер|моб)", lower)):
        return "phone", "TEL"
    if "behance.net" in lower:
        return "behance", "BE"
    if re.search(r"(https?://|www\.|[a-z0-9-]+\.[a-z]{2,})", lower):
        return "web", "WEB"
    return "contact", "ID"


def resume_pdf_labels(language: str) -> dict[str, str]:
    code = (language or "ru").lower()
    if code.startswith("uk"):
        return {
            "experience": "Досвід роботи",
            "experience_short": "Досвід",
            "education": "Освіта",
            "skills": "Навички",
            "achievements": "Досягнення та проєкти",
            "projects": "Проєкти",
            "contacts": "Контакти та посилання",
            "contacts_short": "Контакти",
            "additional": "Додатково",
            "more": "Ще",
        }
    if code.startswith("en"):
        return {
            "experience": "Work experience",
            "experience_short": "Experience",
            "education": "Education",
            "skills": "Skills",
            "achievements": "Achievements and projects",
            "projects": "Projects",
            "contacts": "Contacts and links",
            "contacts_short": "Contacts",
            "additional": "Additional",
            "more": "More",
        }
    return {
        "experience": "Опыт работы",
        "experience_short": "Опыт",
        "education": "Образование",
        "skills": "Навыки",
        "achievements": "Достижения и проекты",
        "projects": "Проекты",
        "contacts": "Контакты и ссылки",
        "contacts_short": "Контакты",
        "additional": "Дополнительно",
        "more": "Еще",
    }


def build_resume_contact_table(
    data: dict[str, str],
    styles: dict,
    template: dict[str, str],
    width: float,
    light: bool = False,
    max_columns: int = 2,
) -> Table | None:
    items = resume_contact_items(data)
    if not items:
        return None
    max_columns = max(1, min(3, max_columns))
    icon_width = 10 * mm
    gap_width = 3 * mm
    item_width = (width - gap_width * (max_columns - 1)) / max_columns
    text_width = max(16 * mm, item_width - icon_width)

    rows: list[list] = []
    for index in range(0, len(items), max_columns):
        row: list = []
        for item_index, item in enumerate(items[index:index + max_columns]):
            row.extend([
                ResumeContactIconFlowable(item.kind, template),
                Paragraph(resume_safe_text(item.value), styles["ResumeContactTextLight" if light else "ResumeContactText"]),
                "",
            ])
        row = row[:-1]
        while len(row) < max_columns * 3 - 1:
            row.append("")
        rows.append(row)

    col_widths: list[float] = []
    for index in range(max_columns):
        col_widths.extend([icon_width, text_width])
        if index < max_columns - 1:
            col_widths.append(gap_width)
    table = Table(rows, colWidths=col_widths, hAlign="LEFT")
    style_commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for col in range(0, max_columns * 3 - 1, 3):
        style_commands.append(("ALIGN", (col, 0), (col, -1), "CENTER"))
    table.setStyle(TableStyle(style_commands))
    return table


def resume_contact_flow(
    data: dict[str, str],
    styles: dict,
    template: dict[str, str],
    width: float,
    light: bool = False,
    max_columns: int = 2,
) -> list:
    table = build_resume_contact_table(data, styles, template, width, light=light, max_columns=max_columns)
    return [table] if table else []


def build_resume_header(
    data: dict[str, str],
    styles: dict,
    avatar_path: Path | None,
    template: dict[str, str],
    content_width: float,
    show_contact: bool = True,
) -> Table:
    header_items: list = [
        Paragraph(resume_safe_text(data["name"] or "Резюме"), styles["ResumeName"]),
    ]
    if data["position"]:
        header_items.append(Paragraph(resume_safe_text(data["position"]), styles["ResumeRole"]))
    if show_contact:
        header_items.extend(resume_contact_flow(data, styles, template, content_width - (38 * mm if avatar_path else 0), max_columns=2))

    if avatar_path:
        avatar = RLImage(str(avatar_path), width=30 * mm, height=30 * mm)
        table = Table([[header_items, avatar]], colWidths=[content_width - 38 * mm, 38 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return table

    table = Table([[header_items]], colWidths=[content_width], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def build_resume_main_flow(data: dict[str, str], styles: dict, template: dict[str, str], content_width: float) -> list:
    story: list = []
    if data["summary"]:
        story.append(Paragraph(resume_safe_text(data["summary"]), styles["ResumeSummary"]))
    story.extend(build_resume_highlight_strip(data, styles, template, content_width))
    add_resume_section(story, "Опыт работы", data["experience"], styles)
    add_resume_section(story, "Образование", data["education"], styles)
    add_resume_section(story, "Навыки", data["skills"], styles)
    add_resume_contact_section(story, "Контакты и ссылки", data, styles, template, content_width)
    add_resume_section(story, "Достижения и проекты", data["achievements"], styles)
    add_resume_section(story, "Дополнительно", data["additional"], styles)
    story.extend(build_resume_fill_panel(data, styles, template, content_width))
    return story


def resume_skill_tags(value: str, limit: int = 12) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;\n•]+", value or ""):
        item = " ".join(raw.strip(" -*\t").split())
        key = item.lower()
        if item and key not in seen:
            tags.append(item[:38])
            seen.add(key)
        if len(tags) >= limit:
            break
    return tags


def resume_link_lines(value: str) -> str:
    links = []
    for raw in normalize_resume_text(value).replace(",", "\n").splitlines():
        item = raw.strip(" •-*")
        if item:
            links.append(item)
    return "\n".join(links)


def resume_content_score(data: dict[str, str]) -> int:
    return sum(len(value or "") for value in data.values()) + len(resume_skill_tags(data.get("skills", ""))) * 18


def build_resume_highlight_strip(data: dict[str, str], styles: dict, template: dict[str, str], content_width: float) -> list:
    items = [
        ("Фокус", data.get("position") or "Целевая роль"),
        ("Профиль", data.get("summary") or data.get("experience") or "Краткий профессиональный профиль"),
        ("Навыки", ", ".join(resume_skill_tags(data.get("skills", ""), 4)) or "Ключевые компетенции"),
    ]
    card_width = content_width / 3
    row = []
    for title, value in items:
        cell = [
            Paragraph(resume_safe_text(title.upper()), styles["ResumeMetricLabel"]),
            Spacer(1, 2),
            Paragraph(resume_safe_text(resume_clip(value, 74)), styles["ResumeMetricValue"]),
        ]
        row.append(cell)
    table = Table([row], colWidths=[card_width, card_width, card_width], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(template["soft"])),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#e5e7eb")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe4ef")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [table, Spacer(1, 8)]


def build_resume_skill_cloud(data: dict[str, str], styles: dict, template: dict[str, str], content_width: float) -> list:
    tags = resume_skill_tags(data.get("skills", ""))
    if len(tags) < 4:
        return []
    cols = 3
    gap = 4 * mm
    col_width = (content_width - gap * (cols - 1)) / cols
    rows: list = []
    for index in range(0, len(tags), cols):
        row = []
        for tag in tags[index:index + cols]:
            row.append(Paragraph(resume_safe_text(tag), styles["ResumeChip"]))
            row.append("")
        row = row[:-1]
        while len(row) < cols * 2 - 1:
            row.append("")
        rows.append(row)
    widths = []
    for index in range(cols):
        widths.append(col_width)
        if index < cols - 1:
            widths.append(gap)
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(template["soft"])),
        ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [Paragraph("Ключевые навыки", styles["ResumeSection"]), table, Spacer(1, 8)]


def build_resume_fill_panel(data: dict[str, str], styles: dict, template: dict[str, str], content_width: float) -> list:
    if resume_content_score(data) > 780:
        return []
    focus = data.get("position") or "целевой роли"
    skills = ", ".join(resume_skill_tags(data.get("skills", ""), 5)) or "ключевых задач"
    text = (
        f"Готов(а) закрывать задачи на позиции {focus}: работать с приоритетами, "
        f"быстро погружаться в контекст и применять {skills} для измеримого результата."
    )
    table = Table(
        [[Paragraph("Профессиональный фокус", styles["ResumeCardTitle"]), Paragraph(resume_safe_text(text), styles["ResumeCardBody"])]],
        colWidths=[40 * mm, content_width - 40 * mm],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(template["soft"])),
        ("LINEBEFORE", (1, 0), (1, 0), 1.2, colors.HexColor(template["accent"])),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [Spacer(1, 4), table]


def paragraph_lines(content: str, styles: dict, style_name: str = "ResumeBody") -> list:
    lines: list = []
    for line in [item.strip() for item in content.splitlines() if item.strip()]:
        prefix = "• " if line.startswith(("-", "•", "*")) else ""
        clean = line[1:].strip() if prefix else line
        lines.append(Paragraph(f"{prefix}{resume_safe_text(clean)}", styles[style_name]))
        lines.append(Spacer(1, 3))
    return lines


def resume_card(title: str, content: str, styles: dict, width: float, template: dict[str, str]) -> Table | None:
    if not content:
        return None
    body = [Paragraph(title, styles["ResumeCardTitle"]), *paragraph_lines(content, styles, "ResumeCardBody")]
    table = Table([[body]], colWidths=[width], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(template["soft"])),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def build_resume_band_header(data: dict[str, str], styles: dict, avatar_path: Path | None, template: dict[str, str], content_width: float) -> Table:
    left = [
        Paragraph(resume_safe_text(data["name"] or "Резюме"), styles["ResumeWhiteName"]),
    ]
    if data["position"]:
        left.append(Paragraph(resume_safe_text(data["position"]), styles["ResumeWhiteRole"]))
    left.extend(resume_contact_flow(data, styles, template, content_width - 38 * mm, light=True, max_columns=2))
    right: list = []
    if avatar_path:
        right.append(RLImage(str(avatar_path), width=30 * mm, height=30 * mm))
    else:
        right.append(Paragraph(template["name"], styles["ResumeRailTitle"]))
    table = Table([[left, right]], colWidths=[content_width - 38 * mm, 38 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(template["dark"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return table


def build_resume_card_grid(data: dict[str, str], styles: dict, template: dict[str, str], content_width: float) -> list:
    story: list = []
    if data["summary"]:
        story.append(Paragraph(resume_safe_text(data["summary"]), styles["ResumeSummary"]))
    card_gap = 6 * mm
    card_width = (content_width - card_gap) / 2
    card_rows: list = []
    cards = [
        resume_card("Навыки", data["skills"], styles, card_width, template),
        resume_card("Образование", data["education"], styles, card_width, template),
        resume_card("Достижения", data["achievements"], styles, card_width, template),
        resume_card("Ссылки", resume_link_lines(data.get("links", "")), styles, card_width, template),
        resume_card("Дополнительно", data["additional"], styles, card_width, template),
    ]
    cards = [card for card in cards if card is not None]
    for index in range(0, len(cards), 2):
        left = cards[index]
        right = cards[index + 1] if index + 1 < len(cards) else ""
        card_rows.append([left, "", right])
    if card_rows:
        grid = Table(card_rows, colWidths=[card_width, card_gap, card_width], hAlign="LEFT")
        grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(grid)
        story.append(Spacer(1, 5))
    add_resume_section(story, "Опыт работы", data["experience"], styles)
    story.extend(build_resume_fill_panel(data, styles, template, content_width))
    return story


def build_resume_photo_left_intro(data: dict[str, str], styles: dict, avatar_path: Path | None, template: dict[str, str], content_width: float) -> Table:
    photo_block: list = []
    if avatar_path:
        photo_block.append(RLImage(str(avatar_path), width=38 * mm, height=38 * mm))
    else:
        photo_block.append(Paragraph(template["name"], styles["ResumeRailTitle"]))
    contacts = resume_contact_flow(data, styles, template, 42 * mm, light=True, max_columns=1)
    if contacts:
        photo_block.extend([Spacer(1, 6), *contacts])
    text_block = [
        Paragraph(resume_safe_text(data["name"] or "Резюме"), styles["ResumeName"]),
    ]
    if data["position"]:
        text_block.append(Paragraph(resume_safe_text(data["position"]), styles["ResumeRole"]))
    if data["summary"]:
        text_block.append(Paragraph(resume_safe_text(data["summary"]), styles["ResumeSummary"]))
    side_width = 48 * mm
    table = Table([[photo_block, text_block]], colWidths=[side_width, content_width - side_width], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(template["dark"])),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (0, 0), 8),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("TOPPADDING", (0, 0), (0, 0), 9),
        ("BOTTOMPADDING", (0, 0), (0, 0), 9),
        ("LEFTPADDING", (1, 0), (1, 0), 12),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (1, 0), (1, 0), 0),
        ("BOTTOMPADDING", (1, 0), (1, 0), 0),
    ]))
    return table


def build_resume_split_intro(data: dict[str, str], styles: dict, avatar_path: Path | None, template: dict[str, str], content_width: float) -> Table:
    left_width = 72 * mm
    right_width = content_width - left_width - 7 * mm
    left: list = []
    if avatar_path:
        left.append(RLImage(str(avatar_path), width=34 * mm, height=34 * mm))
        left.append(Spacer(1, 8))
    left.append(Paragraph(resume_safe_text(data["name"] or "Резюме"), styles["ResumeWhiteName"]))
    if data["position"]:
        left.append(Paragraph(resume_safe_text(data["position"]), styles["ResumeWhiteRole"]))
    contact_block = resume_contact_flow(data, styles, template, left_width - 20, light=True, max_columns=1)
    if contact_block:
        left.append(Paragraph("Контакты", styles["ResumeSideTitle"]))
        left.extend(contact_block)
    for title, content in (("Навыки", data["skills"]), ("Дополнительно", data["additional"])):
        if content:
            left.append(Paragraph(title, styles["ResumeSideTitle"]))
            if title == "Навыки":
                content = "\n".join(item.strip() for item in content.split(",") if item.strip())
            left.append(Paragraph(resume_safe_text(content), styles["ResumeSideBody"]))
    right: list = []
    if data["summary"]:
        right.append(Paragraph(resume_safe_text(data["summary"]), styles["ResumeSummary"]))
    right.append(Paragraph("Основной профиль", styles["ResumeSection"]))
    right.append(Paragraph("Опыт, образование и проекты вынесены ниже в широкие секции, чтобы PDF аккуратно переносился между страницами.", styles["ResumeBody"]))
    table = Table([[left, "", right]], colWidths=[left_width, 7 * mm, right_width], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(template["dark"])),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("RIGHTPADDING", (0, 0), (0, 0), 10),
        ("TOPPADDING", (0, 0), (0, 0), 12),
        ("BOTTOMPADDING", (0, 0), (0, 0), 12),
        ("LEFTPADDING", (1, 0), (1, 0), 0),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("LEFTPADDING", (2, 0), (2, 0), 0),
        ("RIGHTPADDING", (2, 0), (2, 0), 0),
        ("TOPPADDING", (2, 0), (2, 0), 0),
    ]))
    return table


def add_resume_rail_section(story: list, title: str, content: str, styles: dict, template: dict[str, str], content_width: float) -> None:
    if not content:
        return
    rail_width = 26 * mm
    main_width = content_width - rail_width - 6 * mm
    body = paragraph_lines(content, styles)
    table = Table(
        [[Paragraph(title.upper(), styles["ResumeRailTitle"]), body]],
        colWidths=[rail_width, main_width],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(template["accent"])),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 5),
        ("RIGHTPADDING", (0, 0), (0, 0), 5),
        ("TOPPADDING", (0, 0), (0, 0), 7),
        ("BOTTOMPADDING", (0, 0), (0, 0), 7),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (1, 0), (1, 0), 3),
        ("BOTTOMPADDING", (1, 0), (1, 0), 8),
        ("LINEBELOW", (1, 0), (1, 0), 0.4, colors.HexColor("#e5e7eb")),
    ]))
    story.append(table)
    story.append(Spacer(1, 5))


def build_resume_sidebar(data: dict[str, str], styles: dict, avatar_path: Path | None, template: dict[str, str]) -> list:
    side: list = []
    if avatar_path:
        side.append(RLImage(str(avatar_path), width=32 * mm, height=32 * mm))
        side.append(Spacer(1, 8))
    contact_block = resume_contact_flow(data, styles, template, 50 * mm - 18, light=True, max_columns=1)
    if contact_block:
        side.append(Paragraph("Контакты", styles["ResumeSideTitle"]))
        side.extend(contact_block)
    if data["skills"]:
        side.append(Paragraph("Ключевые навыки", styles["ResumeSideTitle"]))
        skills = "<br/>".join(escape(item.strip(), quote=False) for item in data["skills"].split(",") if item.strip())
        side.append(Paragraph(skills, styles["ResumeSideBody"]))
    if data["additional"]:
        side.append(Paragraph("Дополнительно", styles["ResumeSideTitle"]))
        side.append(Paragraph(resume_safe_text(data["additional"]), styles["ResumeSideBody"]))
    return side


async def generate_resume_pdf(data: dict, template: str) -> Path:
    """Генерирует PDF резюме на основе данных и шаблона."""
    filename = f"resume_{uuid.uuid4().hex}.pdf"
    filepath = settings.output_dir / filename
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    selected = RESUME_TEMPLATES.get(template, RESUME_TEMPLATES["1"])
    prepared = resume_section_data(data)
    labels = resume_pdf_labels(str(data.get("lang") or "ru"))
    avatar_path = make_resume_avatar(data.get("photo_path"), settings.output_dir)
    styles = build_resume_styles(selected)

    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=18 * mm,
        bottomMargin=14 * mm,
    )
    content_width = doc.width

    if selected["layout"] == "band":
        story = [build_resume_band_header(prepared, styles, avatar_path, selected, content_width), Spacer(1, 10)]
        if prepared["summary"]:
            story.append(Paragraph(resume_safe_text(prepared["summary"]), styles["ResumeSummary"]))
        story.extend(build_resume_highlight_strip(prepared, styles, selected, content_width))
        meta_cards = []
        card_gap = 5 * mm
        card_width = (content_width - card_gap * 2) / 3
        for title, content in (
            (labels["skills"], prepared["skills"]),
            (labels["education"], prepared["education"]),
            (labels["additional"], prepared["additional"]),
        ):
            card = resume_card(title, content, styles, card_width, selected)
            if card:
                meta_cards.append(card)
        if meta_cards:
            while len(meta_cards) < 3:
                meta_cards.append("")
            meta_table = Table([meta_cards[:3]], colWidths=[card_width, card_width, card_width], hAlign="LEFT")
            meta_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(meta_table)
        add_resume_section(story, labels["experience"], prepared["experience"], styles)
        add_resume_section(story, labels["achievements"], prepared["achievements"], styles)
        add_resume_contact_section(story, labels["contacts"], prepared, styles, selected, content_width)
        story.extend(build_resume_fill_panel(prepared, styles, selected, content_width))
    elif selected["layout"] == "photo_left":
        story = [build_resume_photo_left_intro(prepared, styles, avatar_path, selected, content_width), Spacer(1, 9)]
        story.extend(build_resume_highlight_strip(prepared, styles, selected, content_width))
        add_resume_section(story, labels["experience"], prepared["experience"], styles)
        add_resume_section(story, labels["education"], prepared["education"], styles)
        story.extend(build_resume_skill_cloud(prepared, styles, selected, content_width))
        add_resume_section(story, labels["skills"], prepared["skills"], styles)
        add_resume_section(story, labels["achievements"], prepared["achievements"], styles)
        add_resume_contact_section(story, labels["contacts"], prepared, styles, selected, content_width)
        add_resume_section(story, labels["additional"], prepared["additional"], styles)
    elif selected["layout"] == "split":
        story = [build_resume_split_intro(prepared, styles, avatar_path, selected, content_width), Spacer(1, 9)]
        story.extend(build_resume_highlight_strip(prepared, styles, selected, content_width))
        add_resume_section(story, labels["experience"], prepared["experience"], styles)
        add_resume_section(story, labels["education"], prepared["education"], styles)
        add_resume_section(story, labels["achievements"], prepared["achievements"], styles)
        add_resume_contact_section(story, labels["contacts"], prepared, styles, selected, content_width)
    elif selected["layout"] == "cards":
        story = [build_resume_header(prepared, styles, avatar_path, selected, content_width), Spacer(1, 8)]
        story.extend(build_resume_highlight_strip(prepared, styles, selected, content_width))
        story.extend(build_resume_card_grid(prepared, styles, selected, content_width))
    elif selected["layout"] == "rail":
        story = [build_resume_header(prepared, styles, avatar_path, selected, content_width), Spacer(1, 8)]
        if prepared["summary"]:
            story.append(Paragraph(resume_safe_text(prepared["summary"]), styles["ResumeSummary"]))
        story.extend(build_resume_highlight_strip(prepared, styles, selected, content_width))
        add_resume_rail_section(story, labels["experience_short"], prepared["experience"], styles, selected, content_width)
        add_resume_rail_section(story, labels["skills"], prepared["skills"], styles, selected, content_width)
        add_resume_rail_section(story, labels["education"], prepared["education"], styles, selected, content_width)
        add_resume_rail_section(story, labels["projects"], prepared["achievements"], styles, selected, content_width)
        add_resume_contact_section(story, labels["contacts_short"], prepared, styles, selected, content_width)
        add_resume_rail_section(story, labels["more"], prepared["additional"], styles, selected, content_width)
    elif selected["layout"] == "two":
        side_width = 50 * mm if selected["name"] != "Compact" else 47 * mm
        gutter_width = 8 * mm
        main_width = content_width - side_width - gutter_width
        intro: list = [build_resume_header(prepared, styles, None, selected, main_width, show_contact=False)]
        if prepared["summary"]:
            intro.extend([Spacer(1, 6), Paragraph(resume_safe_text(prepared["summary"]), styles["ResumeSummary"])])
        sidebar = build_resume_sidebar(prepared, styles, avatar_path, selected)
        if not sidebar:
            sidebar = [Paragraph(selected["name"], styles["ResumeSideTitle"])]
        table = Table([[sidebar, "", intro]], colWidths=[side_width, gutter_width, main_width], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(selected["dark"])),
            ("BOX", (0, 0), (0, 0), 0, colors.HexColor(selected["dark"])),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 9),
            ("RIGHTPADDING", (0, 0), (0, 0), 9),
            ("TOPPADDING", (0, 0), (0, 0), 10),
            ("BOTTOMPADDING", (0, 0), (0, 0), 10),
            ("LEFTPADDING", (1, 0), (1, 0), 0),
            ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ("TOPPADDING", (1, 0), (1, 0), 0),
            ("BOTTOMPADDING", (1, 0), (1, 0), 0),
            ("LEFTPADDING", (2, 0), (2, 0), 0),
            ("RIGHTPADDING", (2, 0), (2, 0), 0),
            ("TOPPADDING", (2, 0), (2, 0), 0),
            ("BOTTOMPADDING", (2, 0), (2, 0), 0),
        ]))
        story: list = [table, Spacer(1, 9)]
        story.extend(build_resume_highlight_strip(prepared, styles, selected, content_width))
        add_resume_section(story, labels["experience"], prepared["experience"], styles)
        add_resume_section(story, labels["education"], prepared["education"], styles)
        add_resume_section(story, labels["achievements"], prepared["achievements"], styles)
        add_resume_contact_section(story, labels["contacts"], prepared, styles, selected, content_width)
    else:
        story = [build_resume_header(prepared, styles, avatar_path, selected, content_width), Spacer(1, 8)]
        main_flow = build_resume_main_flow(prepared, styles, selected, content_width)
        story.extend(main_flow)

    doc.build(
        story,
        onFirstPage=lambda canvas, document: draw_resume_page(canvas, document, selected),
        onLaterPages=lambda canvas, document: draw_resume_page(canvas, document, selected),
    )
    if avatar_path:
        avatar_path.unlink(missing_ok=True)
    return filepath


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    await db.init()
    language_overrides.update(await db.all_languages())

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="subscribe", description="Подписка за Stars"),
            BotCommand(command="pro", description="Что дает Pro"),
            BotCommand(command="status", description="Статус доступа"),
            BotCommand(command="history", description="История обработок"),
            BotCommand(command="resume", description="Создать PDF-резюме"),
            BotCommand(command="language", description="Сменить язык"),
            BotCommand(command="id", description="Мой Telegram ID"),
            BotCommand(command="cancel", description="Отменить текущее действие"),
            BotCommand(command="help", description="Как пользоваться"),
        ]
    )
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Main menu"),
            BotCommand(command="subscribe", description="Stars subscription"),
            BotCommand(command="pro", description="What Pro includes"),
            BotCommand(command="status", description="Access status"),
            BotCommand(command="history", description="Conversion history"),
            BotCommand(command="resume", description="Create PDF resume"),
            BotCommand(command="language", description="Change language"),
            BotCommand(command="id", description="My Telegram ID"),
            BotCommand(command="cancel", description="Cancel current action"),
            BotCommand(command="help", description="How to use"),
        ],
        language_code="en",
    )
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Головне меню"),
            BotCommand(command="subscribe", description="Підписка за Stars"),
            BotCommand(command="pro", description="Що дає Pro"),
            BotCommand(command="status", description="Статус доступу"),
            BotCommand(command="history", description="Історія обробок"),
            BotCommand(command="resume", description="Створити PDF-резюме"),
            BotCommand(command="language", description="Змінити мову"),
            BotCommand(command="id", description="Мій Telegram ID"),
            BotCommand(command="cancel", description="Скасувати дію"),
            BotCommand(command="help", description="Як користуватися"),
        ],
        language_code="uk",
    )
    if settings.mini_app_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Mini App", web_app=WebAppInfo(url=settings.mini_app_url)))

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    asyncio.create_task(cleanup_loop())
    logger.info("Bot started. Free users: %s. FFmpeg: %s", sorted(settings.free_user_ids), ffmpeg_available())
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
