from __future__ import annotations

import asyncio
from dataclasses import dataclass
from html import escape
import json
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
from reportlab.platypus import Flowable, KeepTogether, PageBreak, Paragraph as RLParagraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
    KeyboardButton,
    LabeledPrice,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .config import Settings, get_settings
from .db import Database
from .django_bridge import (
    claim_payment_intent,
    create_account_for_paid_intent,
    create_direct_payment_intent,
    create_direct_topup_by_stars,
    get_payment_intent_by_payload,
    link_telegram_account,
    record_intent_payment,
    record_stars_payment,
    telegram_wallet,
    upsert_bot_user,
)
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
    repair_cyrillic_mojibake as utils_repair_cyrillic_mojibake,
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


def Paragraph(text, *args, **kwargs):
    return RLParagraph(utils_repair_cyrillic_mojibake(str(text or "")), *args, **kwargs)


SUBSCRIPTION_PERIOD_SECONDS = 2_592_000
TELEGRAM_SAFE_UPLOAD_BYTES = 48 * 1024 * 1024
JOB_TTL_SECONDS = 86_400

NEXT_STEP_HINT = (
    "\n\nР§С‚Рѕ РґР°Р»СЊС€Рµ:\n"
    "- РІС‹Р±РµСЂРё С„РѕСЂРјР°С‚ РєРЅРѕРїРєРѕР№ РЅРёР¶Рµ;\n"
    "- РµСЃР»Рё РЅСѓР¶РЅРѕ РґСЂСѓРіРѕРµ РёРјСЏ С„Р°Р№Р»Р°, РЅР°Р¶РјРё В«РџРµСЂРµРёРјРµРЅРѕРІР°С‚СЊВ»;\n"
    "- РґР»СЏ РІРёРґРµРѕ РјРѕР¶РЅРѕ СЃСЂР°Р·Сѓ СЃРґРµР»Р°С‚СЊ PNG-РѕР±Р»РѕР¶РєСѓ;\n"
    "- РґР»СЏ РјРѕРЅС‚Р°Р¶Р° РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ;\n"
    "- РµСЃР»Рё РїРµСЂРµРґСѓРјР°Р» РїСЂРё РїРµСЂРµРёРјРµРЅРѕРІР°РЅРёРё, РЅР°РїРёС€Рё /cancel."
)
AFTER_RESULT_HINT = (
    "\n\nР§С‚Рѕ РґР°Р»СЊС€Рµ:\n"
    "- РѕС‚РїСЂР°РІСЊ СЃР»РµРґСѓСЋС‰РёР№ С„Р°Р№Р» РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ;\n"
    "- РґР»СЏ РІРёРґРµРѕ РјРѕР¶РЅРѕ РЅР°Р¶Р°С‚СЊ РєРЅРѕРїРєСѓ СЃСѓР±С‚РёС‚СЂРѕРІ РёР»Рё РѕР±Р»РѕР¶РєРё PNG;\n"
    "- СЃС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїР°: /status, РёСЃС‚РѕСЂРёСЏ: /history."
)
FILE_PREP_STEPS = ["РїРѕР»СѓС‡Р°СЋ С„Р°Р№Р»", "РїСЂРѕРІРµСЂСЏСЋ СЂР°Р·РјРµСЂ Рё С‚РёРї", "С‡РёС‚Р°СЋ РїР°СЂР°РјРµС‚СЂС‹", "РїРѕРєР°Р·С‹РІР°СЋ РІР°СЂРёР°РЅС‚С‹"]
IMAGE_CONVERT_STEPS = ["РїСЂРѕРІРµСЂСЏСЋ РёСЃС…РѕРґРЅРёРє", "РєРѕРЅРІРµСЂС‚РёСЂСѓСЋ С„РѕСЂРјР°С‚", "СЃРѕС…СЂР°РЅСЏСЋ СЂРµР·СѓР»СЊС‚Р°С‚", "РѕС‚РїСЂР°РІР»СЏСЋ С„Р°Р№Р»"]
VIDEO_CONVERT_STEPS = ["РїСЂРѕРІРµСЂСЏСЋ РІРёРґРµРѕ", "Р·Р°РїСѓСЃРєР°СЋ РєРѕРґРёСЂРѕРІР°РЅРёРµ", "СЃРѕС…СЂР°РЅСЏСЋ MP4/WEBM/GIF", "РѕС‚РїСЂР°РІР»СЏСЋ С„Р°Р№Р»"]
SUBTITLE_STEPS = ["РіРѕС‚РѕРІР»СЋ Р·РІСѓРє", "СЂР°СЃРїРѕР·РЅР°СЋ СЂРµС‡СЊ", "РІРµСЂСЃС‚Р°СЋ СЃСѓР±С‚РёС‚СЂС‹", "РІС€РёРІР°СЋ РІ РІРёРґРµРѕ", "РѕС‚РїСЂР°РІР»СЏСЋ С„Р°Р№Р»"]
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
    "ru": "Р СѓСЃСЃРєРёР№",
    "uk": "РЈРєСЂР°С—РЅСЃСЊРєР°",
    "en": "English",
}
COVER_STEPS = ["С‡РёС‚Р°СЋ РїР°СЂР°РјРµС‚СЂС‹", "РІС‹Р±РёСЂР°СЋ СЃРёР»СЊРЅС‹Р№ РєР°РґСЂ", "РёС‰Сѓ С‚РµРјР°С‚РёС‡РµСЃРєРёРµ РєР°СЂС‚РёРЅРєРё", "СЃРѕР±РёСЂР°СЋ PNG-РѕР±Р»РѕР¶РєСѓ", "РѕС‚РїСЂР°РІР»СЏСЋ С„Р°Р№Р»"]
IMAGE_MODE_LABELS = {
    "light": "РјР°РєСЃРёРјР°Р»СЊРЅРѕ Р»РµРіРєРѕ",
    "balanced": "Р±Р°Р»Р°РЅСЃ",
    "quality": "РєР°С‡РµСЃС‚РІРѕ",
}
PUBLICATION_STEPS = ["РіРѕС‚РѕРІР»СЋ РІРёРґРµРѕ", "РґРµР»Р°СЋ РѕР±Р»РѕР¶РєСѓ", "РґРѕР±Р°РІР»СЏСЋ СЃСѓР±С‚РёС‚СЂС‹", "РїРёС€Сѓ РѕРїРёСЃР°РЅРёРµ", "СЃРѕР±РёСЂР°СЋ ZIP", "РѕС‚РїСЂР°РІР»СЏСЋ РїР°РєРµС‚"]


class RenameState(StatesGroup):
    waiting_name = State()


class CoverTextState(StatesGroup):
    waiting_text = State()


class BillingAccountState(StatesGroup):
    waiting_email = State()
    waiting_topup_stars = State()


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
BOT_LANGUAGE_CODES = {"ru", "uk", "en", "fr", "de", "es", "ka", "hy", "it"}
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
        "РѕС‚РїСЂР°РІСЊ РєР°СЂС‚РёРЅРєСѓ РёР»Рё РІРёРґРµРѕ РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†РёРё": "send an image or video for conversion",
        "РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ Shorts РёР»Рё Preview": "send a YouTube link for Shorts or Preview",
        "РїРѕСЃР»Рµ СЂРµР·СѓР»СЊС‚Р°С‚Р° РЅР°Р¶РёРјР°Р№ Subtitles РёР»Рё Redo, РµСЃР»Рё РЅСѓР¶РЅРѕ РїСЂРѕРґРѕР»Р¶РёС‚СЊ РѕР±СЂР°Р±РѕС‚РєСѓ": "after the result, use Subtitles or Redo if you want to continue",
        "РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†РёРё": "send a file for conversion",
        "РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°": "send a YouTube link for editing",
        "РїРѕСЃР»Рµ РіРѕС‚РѕРІРѕРіРѕ MP4 РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ СЃСѓР±С‚РёС‚СЂС‹": "after an MP4 is ready, you can add subtitles",
        "РёСЃРїРѕР»СЊР·СѓР№ СЌС‚РѕС‚ ID РґР»СЏ СЃРїРёСЃРєР° Р±РµСЃРїР»Р°С‚РЅРѕРіРѕ РґРѕСЃС‚СѓРїР°": "use this ID for the free access list",
        "РёР»Рё РѕС‚РїСЂР°РІСЊ С„Р°Р№Р»/СЃСЃС‹Р»РєСѓ РґР»СЏ РѕР±СЂР°Р±РѕС‚РєРё": "or send a file/link to process",
        "РѕС‚РїСЂР°РІСЊ РЅРѕРІС‹Р№ С„Р°Р№Р»": "send a new file",
        "РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°": "or a YouTube link for editing",
        "РЅР°Р¶РјРё РѕРїР»Р°С‚Сѓ РЅРёР¶Рµ": "tap the payment button below",
        "РёР»Рё РёСЃРїРѕР»СЊР·СѓР№ РґРѕСЃС‚СѓРїРЅС‹Рµ Free-РґРµР№СЃС‚РІРёСЏ": "or use the available Free actions",
        "РѕС‚РїСЂР°РІСЊ С„Р°Р№Р»": "send a file",
        "РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ": "or a YouTube link",
        "Р°РєС‚РёРІРёСЂСѓР№ РґРѕСЃС‚СѓРї РєРЅРѕРїРєРѕР№ РЅРёР¶Рµ": "activate access with the button below",
        "РёР»Рё РёСЃРїРѕР»СЊР·СѓР№ РґРѕСЃС‚СѓРїРЅС‹Р№ Free-Р»РёРјРёС‚": "or use the available Free limit",
        "РёР»Рё РЅР°РїРёС€Рё /id Рё РґРѕР±Р°РІСЊ ID РІ FREE_USER_IDS": "or send /id and add the ID to FREE_USER_IDS",
        "РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ": "send a file or YouTube link",
        "РїРѕСЃР»Рµ РѕР±СЂР°Р±РѕС‚РєРё СЂРµР·СѓР»СЊС‚Р°С‚ РїРѕСЏРІРёС‚СЃСЏ Р·РґРµСЃСЊ": "after processing, the result will appear here",
    },
    "uk": {
        "РѕС‚РїСЂР°РІСЊ РєР°СЂС‚РёРЅРєСѓ РёР»Рё РІРёРґРµРѕ РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†РёРё": "РЅР°РґС–С€Р»С–С‚СЊ Р·РѕР±СЂР°Р¶РµРЅРЅСЏ Р°Р±Рѕ РІС–РґРµРѕ РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†С–С—",
        "РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ Shorts РёР»Рё Preview": "РЅР°РґС–С€Р»С–С‚СЊ YouTube-РїРѕСЃРёР»Р°РЅРЅСЏ РґР»СЏ Shorts Р°Р±Рѕ Preview",
        "РїРѕСЃР»Рµ СЂРµР·СѓР»СЊС‚Р°С‚Р° РЅР°Р¶РёРјР°Р№ Subtitles РёР»Рё Redo, РµСЃР»Рё РЅСѓР¶РЅРѕ РїСЂРѕРґРѕР»Р¶РёС‚СЊ РѕР±СЂР°Р±РѕС‚РєСѓ": "РїС–СЃР»СЏ СЂРµР·СѓР»СЊС‚Р°С‚Сѓ РЅР°С‚РёСЃРєР°Р№С‚Рµ Subtitles Р°Р±Рѕ Redo, СЏРєС‰Рѕ РїРѕС‚СЂС–Р±РЅРѕ РїСЂРѕРґРѕРІР¶РёС‚Рё",
        "РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†РёРё": "РЅР°РґС–С€Р»С–С‚СЊ С„Р°Р№Р» РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†С–С—",
        "РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°": "РЅР°РґС–С€Р»С–С‚СЊ YouTube-РїРѕСЃРёР»Р°РЅРЅСЏ РґР»СЏ РјРѕРЅС‚Р°Р¶Сѓ",
        "РїРѕСЃР»Рµ РіРѕС‚РѕРІРѕРіРѕ MP4 РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ СЃСѓР±С‚РёС‚СЂС‹": "РїС–СЃР»СЏ РіРѕС‚РѕРІРѕРіРѕ MP4 РјРѕР¶РЅР° РґРѕРґР°С‚Рё СЃСѓР±С‚РёС‚СЂРё",
        "РёСЃРїРѕР»СЊР·СѓР№ СЌС‚РѕС‚ ID РґР»СЏ СЃРїРёСЃРєР° Р±РµСЃРїР»Р°С‚РЅРѕРіРѕ РґРѕСЃС‚СѓРїР°": "РІРёРєРѕСЂРёСЃС‚РѕРІСѓР№С‚Рµ С†РµР№ ID РґР»СЏ СЃРїРёСЃРєСѓ Р±РµР·РєРѕС€С‚РѕРІРЅРѕРіРѕ РґРѕСЃС‚СѓРїСѓ",
        "РёР»Рё РѕС‚РїСЂР°РІСЊ С„Р°Р№Р»/СЃСЃС‹Р»РєСѓ РґР»СЏ РѕР±СЂР°Р±РѕС‚РєРё": "Р°Р±Рѕ РЅР°РґС–С€Р»С–С‚СЊ С„Р°Р№Р»/РїРѕСЃРёР»Р°РЅРЅСЏ РґР»СЏ РѕР±СЂРѕР±РєРё",
        "РѕС‚РїСЂР°РІСЊ РЅРѕРІС‹Р№ С„Р°Р№Р»": "РЅР°РґС–С€Р»С–С‚СЊ РЅРѕРІРёР№ С„Р°Р№Р»",
        "РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°": "Р°Р±Рѕ YouTube-РїРѕСЃРёР»Р°РЅРЅСЏ РґР»СЏ РјРѕРЅС‚Р°Р¶Сѓ",
        "РЅР°Р¶РјРё РѕРїР»Р°С‚Сѓ РЅРёР¶Рµ": "РЅР°С‚РёСЃРЅС–С‚СЊ РѕРїР»Р°С‚Сѓ РЅРёР¶С‡Рµ",
        "РёР»Рё РёСЃРїРѕР»СЊР·СѓР№ РґРѕСЃС‚СѓРїРЅС‹Рµ Free-РґРµР№СЃС‚РІРёСЏ": "Р°Р±Рѕ РІРёРєРѕСЂРёСЃС‚РѕРІСѓР№С‚Рµ РґРѕСЃС‚СѓРїРЅС– Free-РґС–С—",
        "РѕС‚РїСЂР°РІСЊ С„Р°Р№Р»": "РЅР°РґС–С€Р»С–С‚СЊ С„Р°Р№Р»",
        "РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ": "Р°Р±Рѕ YouTube-РїРѕСЃРёР»Р°РЅРЅСЏ",
        "Р°РєС‚РёРІРёСЂСѓР№ РґРѕСЃС‚СѓРї РєРЅРѕРїРєРѕР№ РЅРёР¶Рµ": "Р°РєС‚РёРІСѓР№С‚Рµ РґРѕСЃС‚СѓРї РєРЅРѕРїРєРѕСЋ РЅРёР¶С‡Рµ",
        "РёР»Рё РёСЃРїРѕР»СЊР·СѓР№ РґРѕСЃС‚СѓРїРЅС‹Р№ Free-Р»РёРјРёС‚": "Р°Р±Рѕ РІРёРєРѕСЂРёСЃС‚РѕРІСѓР№С‚Рµ РґРѕСЃС‚СѓРїРЅРёР№ Free-Р»С–РјС–С‚",
        "РёР»Рё РЅР°РїРёС€Рё /id Рё РґРѕР±Р°РІСЊ ID РІ FREE_USER_IDS": "Р°Р±Рѕ РЅР°РґС–С€Р»С–С‚СЊ /id С– РґРѕРґР°Р№С‚Рµ ID Сѓ FREE_USER_IDS",
        "РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ": "РЅР°РґС–С€Р»С–С‚СЊ С„Р°Р№Р» Р°Р±Рѕ YouTube-РїРѕСЃРёР»Р°РЅРЅСЏ",
        "РїРѕСЃР»Рµ РѕР±СЂР°Р±РѕС‚РєРё СЂРµР·СѓР»СЊС‚Р°С‚ РїРѕСЏРІРёС‚СЃСЏ Р·РґРµСЃСЊ": "РїС–СЃР»СЏ РѕР±СЂРѕР±РєРё СЂРµР·СѓР»СЊС‚Р°С‚ Р·'СЏРІРёС‚СЊСЃСЏ С‚СѓС‚",
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
        stage = str(state.get("stage", "Р Р°Р±РѕС‚Р°СЋ"))
        detail = str(state.get("detail", ""))
        await safe_edit(
            status,
            f"{stage}\n{detail}\n\nР•С‰Рµ СЂР°Р±РѕС‚Р°СЋ. РџСЂРѕС€Р»Рѕ: {elapsed}. Р‘РѕС‚ РЅРµ Р·Р°РІРёСЃ, РјРѕР¶РЅРѕ РїРёСЃР°С‚СЊ /status РёР»Рё /help.",
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


def billing_bot_mode() -> bool:
    return settings.bot_mode == "billing"


def admin_user_ids() -> set[int]:
    return settings.bot_admin_ids or settings.free_user_ids


def is_admin_user(user_id: int | None) -> bool:
    return bool(user_id and user_id in admin_user_ids())


def main_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    return bot_keyboards.main_menu(lang, settings.subscription_stars, settings.mini_app_url)


def help_navigation_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return bot_keyboards.help_navigation_keyboard(lang, settings.subscription_stars)


def persistent_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    if billing_bot_mode():
        rows = [
            [KeyboardButton(text=billing_text(lang, "pay_button")), KeyboardButton(text=billing_text(lang, "status_button"))],
            [KeyboardButton(text=billing_text(lang, "wallet_button")), KeyboardButton(text=billing_text(lang, "support_button"))],
            [KeyboardButton(text=billing_text(lang, "language_button"))],
        ]
        if settings.mini_app_url:
            rows.append([KeyboardButton(text=billing_text(lang, "mini_app"), web_app=WebAppInfo(url=settings.mini_app_url))])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)
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


def publication_hashtags(title: str, transcript_text: str = "") -> list[str]:
    return utils_publication_hashtags(title, transcript_text)


def re_words(text: str) -> list[str]:
    return utils_re_words(text)


def publication_description(title: str, duration_seconds: float | None, hashtags: list[str], subtitle_note: str, transcript_text: str = "", language: str | None = None) -> str:
    return utils_publication_description(title, format_duration(duration_seconds), hashtags, subtitle_note, transcript_text, language)


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
        await asyncio.to_thread(
            upsert_bot_user,
            message.from_user.id,
            message.from_user.username or "",
            message.from_user.first_name or "",
            getattr(message.from_user, "language_code", "") or "",
        )
        if message.from_user.id not in language_overrides:
            saved_language = await db.get_language(message.from_user.id)
            if saved_language:
                language_overrides[message.from_user.id] = saved_language


async def ensure_callback_user(callback: CallbackQuery) -> None:
    if callback.from_user:
        await db.upsert_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
        await asyncio.to_thread(
            upsert_bot_user,
            callback.from_user.id,
            callback.from_user.username or "",
            callback.from_user.first_name or "",
            getattr(callback.from_user, "language_code", "") or "",
        )
        if callback.from_user.id not in language_overrides:
            saved_language = await db.get_language(callback.from_user.id)
            if saved_language:
                language_overrides[callback.from_user.id] = saved_language


async def has_access(user_id: int) -> bool:
    return is_free_user(user_id) or (await db.get_subscription(user_id)).is_active


async def is_pro_user(user_id: int) -> bool:
    return is_free_user(user_id) or (await db.get_subscription(user_id)).is_active


def billing_intro_text() -> str:
    return (
        "CherryX Pay bot\n\n"
        f"- Stars invoice: {settings.subscription_stars} Stars / {settings.subscription_days} days\n"
        "- Link website account: /link CODE\n"
        "- Check access: /status\n"
        "- Check wallet: /wallet\n"
        "- Payment help: /paysupport"
    )


def billing_help_text() -> str:
    return (
        "This bot is used only for CherryX payments and account monitoring.\n\n"
        "Commands:\n"
        "/subscribe - pay with Telegram Stars\n"
        "/status - access status\n"
        "/wallet - CherryX balance and linked account\n"
        "/link CODE - link Telegram with the website account\n"
        "/paysupport - payment support\n"
        "/id - show Telegram ID"
    )


def billing_only_text() -> str:
    return "This bot accepts payments and monitors CherryX access only. Use /subscribe, /status, /wallet or /paysupport."


def billing_direct_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Start - 100 CherryX", callback_data="tgplan:free"),
            InlineKeyboardButton(text="Starter - 900", callback_data="tgplan:starter"),
        ],
        [
            InlineKeyboardButton(text="Creator Pro - 1900", callback_data="tgplan:pro"),
            InlineKeyboardButton(text="Studio - 4900", callback_data="tgplan:studio"),
        ],
        [
            InlineKeyboardButton(text="РџРѕРїРѕР»РЅРёС‚СЊ Р±Р°Р»Р°РЅСЃ", callback_data="tgtopup:custom"),
        ],
    ])


async def send_intent_invoice(message: Message, bot: Bot, intent: dict[str, object]) -> None:
    await message.answer(
        f"{intent.get('title')}\n"
        f"{intent.get('description')}\n\n"
        f"Price: {intent.get('stars_amount')} Telegram Stars."
    )
    await bot(
        SendInvoice(
            chat_id=message.chat.id,
            title=str(intent.get("title") or "CherryX"),
            description=str(intent.get("description") or "CherryX payment"),
            payload=str(intent.get("payload") or ""),
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=str(intent.get("title") or "CherryX"), amount=int(intent.get("stars_amount") or 1))],
        )
    )


BILLING_TEXT = {
    "ru": {
        "intro": "CherryX Pay Р±РѕС‚\n\nР—РґРµСЃСЊ РјРѕР¶РЅРѕ РѕРїР»Р°С‚РёС‚СЊ РїР°РєРµС‚, РїРѕРїРѕР»РЅРёС‚СЊ Р±Р°Р»Р°РЅСЃ Рё РїСЂРѕРІРµСЂРёС‚СЊ Р°РєРєР°СѓРЅС‚.\n\n/link CODE - РїСЂРёРІСЏР·Р°С‚СЊ Р°РєРєР°СѓРЅС‚ СЃР°Р№С‚Р°\n/status - СЃС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїР°\n/wallet - Р±Р°Р»Р°РЅСЃ CherryX\n/paysupport - РїРѕРјРѕС‰СЊ СЃ РѕРїР»Р°С‚РѕР№",
        "help": "Р­С‚РѕС‚ Р±РѕС‚ СЂР°Р±РѕС‚Р°РµС‚ С‚РѕР»СЊРєРѕ РґР»СЏ РѕРїР»Р°С‚ CherryX Рё РјРѕРЅРёС‚РѕСЂРёРЅРіР° Р°РєРєР°СѓРЅС‚Р°.\n\n/subscribe - РѕРїР»Р°С‚Р° С‡РµСЂРµР· Telegram Stars\n/status - СЃС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїР°\n/wallet - Р±Р°Р»Р°РЅСЃ Рё РїСЂРёРІСЏР·РєР°\n/link CODE - РїСЂРёРІСЏР·Р°С‚СЊ Р°РєРєР°СѓРЅС‚ СЃР°Р№С‚Р°\n/paysupport - РїРѕРјРѕС‰СЊ СЃ РѕРїР»Р°С‚РѕР№\n/id - Telegram ID",
        "only": "Р‘РѕС‚ РїСЂРёРЅРёРјР°РµС‚ РѕРїР»Р°С‚С‹ Рё РїРѕРєР°Р·С‹РІР°РµС‚ СЃС‚Р°С‚СѓСЃ CherryX. РСЃРїРѕР»СЊР·СѓР№С‚Рµ /subscribe, /status, /wallet РёР»Рё /paysupport.",
        "choose": "Р’С‹Р±РµСЂРёС‚Рµ РїР°РєРµС‚ РёР»Рё РїРѕРїРѕР»РЅРµРЅРёРµ Р±Р°Р»Р°РЅСЃР°:",
        "topup": "РџРѕРїРѕР»РЅРёС‚СЊ Р±Р°Р»Р°РЅСЃ",
        "enter_stars": "Р’РІРµРґРёС‚Рµ СЃСѓРјРјСѓ РїРѕРїРѕР»РЅРµРЅРёСЏ РІ Telegram Stars.\nРњРёРЅРёРјСѓРј: 1 Star. РњР°РєСЃРёРјСѓРј: 150000 Stars.\nРќР° Р±Р°Р»Р°РЅСЃ CherryX РїСЂРёРґРµС‚ СЃСѓРјРјР° РїРѕ С‚РµРєСѓС‰РµРјСѓ РєСѓСЂСЃСѓ.",
        "invalid_stars": "Р’РІРµРґРёС‚Рµ С†РµР»РѕРµ С‡РёСЃР»Рѕ Stars РѕС‚ 1 РґРѕ 150000.",
        "stars_range": "РЎСѓРјРјР° РґРѕР»Р¶РЅР° Р±С‹С‚СЊ РѕС‚ 1 РґРѕ 150000 Telegram Stars.",
        "invoice": "{title}\n{description}\n\nРљ РѕРїР»Р°С‚Рµ: {stars} Telegram Stars.",
        "intent_error": "РћРїР»Р°С‚Р° РїРѕР»СѓС‡РµРЅР°, РЅРѕ РЅРµ СЃРјРѕРі РїСЂРёРјРµРЅРёС‚СЊ РµРµ Рє Р°РєРєР°СѓРЅС‚Сѓ. РќР°РїРёС€РёС‚Рµ /paysupport.",
        "need_email": "РћРїР»Р°С‚Р° РїРѕР»СѓС‡РµРЅР°.\nРћС‚РїСЂР°РІСЊС‚Рµ email, Рё СЏ СЃРѕР·РґР°Рј CherryX Р°РєРєР°СѓРЅС‚, РїСЂРёРјРµРЅСЋ РїР°РєРµС‚ РёР»Рё Р±Р°Р»Р°РЅСЃ Рё РїСЂРёС€Р»СЋ РґР°РЅРЅС‹Рµ РґР»СЏ РІС…РѕРґР°.",
        "applied": "РћРїР»Р°С‚Р° РїСЂРѕС€Р»Р° Рё РїСЂРёРјРµРЅРµРЅР°.\n{title}\nCherryX: {cherryx}",
        "account_created": "CherryX Р°РєРєР°СѓРЅС‚ СЃРѕР·РґР°РЅ, РѕРїР»Р°С‚Р° РїСЂРёРјРµРЅРµРЅР°.\n\nР›РѕРіРёРЅ: {email}\nРџР°СЂРѕР»СЊ: {password}\nРЎСЃС‹Р»РєР° РґР»СЏ РІС…РѕРґР°: {login_url}\n\nРџРѕСЃР»Рµ РїРµСЂРІРѕРіРѕ РІС…РѕРґР° СЃРјРµРЅРёС‚Рµ РїР°СЂРѕР»СЊ.",
        "open_cherryx": "РћС‚РєСЂС‹С‚СЊ CherryX",
        "email_exists": "РўР°РєРѕР№ email СѓР¶Рµ РµСЃС‚СЊ РІ CherryX.\nР’РѕР№РґРёС‚Рµ РЅР° СЃР°Р№С‚Рµ, РѕС‚РєСЂРѕР№С‚Рµ CherryX Pay, СЃРєРѕРїРёСЂСѓР№С‚Рµ /link CODE Рё РѕС‚РїСЂР°РІСЊС‚Рµ СЃСЋРґР°. РћРїР»Р°С‚Р° Р±СѓРґРµС‚ Р¶РґР°С‚СЊ РїСЂРёРІСЏР·РєРё.",
        "email_invalid": "РћС‚РїСЂР°РІСЊС‚Рµ РєРѕСЂСЂРµРєС‚РЅС‹Р№ email.",
    },
    "uk": {
        "intro": "CherryX Pay Р±РѕС‚\n\nРўСѓС‚ РјРѕР¶РЅР° РѕРїР»Р°С‚РёС‚Рё РїР°РєРµС‚, РїРѕРїРѕРІРЅРёС‚Рё Р±Р°Р»Р°РЅСЃ С– РїРµСЂРµРІС–СЂРёС‚Рё Р°РєР°СѓРЅС‚.\n\n/link CODE - РїСЂРёРІ'СЏР·Р°С‚Рё Р°РєР°СѓРЅС‚ СЃР°Р№С‚Сѓ\n/status - СЃС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїСѓ\n/wallet - Р±Р°Р»Р°РЅСЃ CherryX\n/paysupport - РґРѕРїРѕРјРѕРіР° Р· РѕРїР»Р°С‚РѕСЋ",
        "help": "Р¦РµР№ Р±РѕС‚ РїСЂР°С†СЋС” С‚С–Р»СЊРєРё РґР»СЏ РѕРїР»Р°С‚ CherryX С– РјРѕРЅС–С‚РѕСЂРёРЅРіСѓ Р°РєР°СѓРЅС‚Р°.\n\n/subscribe - РѕРїР»Р°С‚Р° С‡РµСЂРµР· Telegram Stars\n/status - СЃС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїСѓ\n/wallet - Р±Р°Р»Р°РЅСЃ С– РїСЂРёРІ'СЏР·РєР°\n/link CODE - РїСЂРёРІ'СЏР·Р°С‚Рё Р°РєР°СѓРЅС‚ СЃР°Р№С‚Сѓ\n/paysupport - РґРѕРїРѕРјРѕРіР° Р· РѕРїР»Р°С‚РѕСЋ\n/id - Telegram ID",
        "only": "Р‘РѕС‚ РїСЂРёР№РјР°С” РѕРїР»Р°С‚Рё С– РїРѕРєР°Р·СѓС” СЃС‚Р°С‚СѓСЃ CherryX. Р’РёРєРѕСЂРёСЃС‚РѕРІСѓР№С‚Рµ /subscribe, /status, /wallet Р°Р±Рѕ /paysupport.",
        "choose": "РћР±РµСЂС–С‚СЊ РїР°РєРµС‚ Р°Р±Рѕ РїРѕРїРѕРІРЅРµРЅРЅСЏ Р±Р°Р»Р°РЅСЃСѓ:",
        "topup": "РџРѕРїРѕРІРЅРёС‚Рё Р±Р°Р»Р°РЅСЃ",
        "enter_stars": "Р’РІРµРґС–С‚СЊ СЃСѓРјСѓ РїРѕРїРѕРІРЅРµРЅРЅСЏ РІ Telegram Stars.\nРњС–РЅС–РјСѓРј: 1 Star. РњР°РєСЃРёРјСѓРј: 150000 Stars.\nРќР° Р±Р°Р»Р°РЅСЃ CherryX РїСЂРёР№РґРµ СЃСѓРјР° Р·Р° РїРѕС‚РѕС‡РЅРёРј РєСѓСЂСЃРѕРј.",
        "invalid_stars": "Р’РІРµРґС–С‚СЊ С†С–Р»Рµ С‡РёСЃР»Рѕ Stars РІС–Рґ 1 РґРѕ 150000.",
        "stars_range": "РЎСѓРјР° РјР°С” Р±СѓС‚Рё РІС–Рґ 1 РґРѕ 150000 Telegram Stars.",
        "invoice": "{title}\n{description}\n\nР”Рѕ РѕРїР»Р°С‚Рё: {stars} Telegram Stars.",
        "intent_error": "РћРїР»Р°С‚Сѓ РѕС‚СЂРёРјР°РЅРѕ, Р°Р»Рµ РЅРµ РІРґР°Р»РѕСЃСЏ Р·Р°СЃС‚РѕСЃСѓРІР°С‚Рё С—С— РґРѕ Р°РєР°СѓРЅС‚Р°. РќР°РїРёС€С–С‚СЊ /paysupport.",
        "need_email": "РћРїР»Р°С‚Сѓ РѕС‚СЂРёРјР°РЅРѕ.\nРќР°РґС–С€Р»С–С‚СЊ email, С– СЏ СЃС‚РІРѕСЂСЋ CherryX Р°РєР°СѓРЅС‚, Р·Р°СЃС‚РѕСЃСѓСЋ РїР°РєРµС‚ Р°Р±Рѕ Р±Р°Р»Р°РЅСЃ С– РЅР°РґС–С€Р»СЋ РґР°РЅС– РґР»СЏ РІС…РѕРґСѓ.",
        "applied": "РћРїР»Р°С‚Сѓ РїСЂРѕРІРµРґРµРЅРѕ С– Р·Р°СЃС‚РѕСЃРѕРІР°РЅРѕ.\n{title}\nCherryX: {cherryx}",
        "account_created": "CherryX Р°РєР°СѓРЅС‚ СЃС‚РІРѕСЂРµРЅРѕ, РѕРїР»Р°С‚Сѓ Р·Р°СЃС‚РѕСЃРѕРІР°РЅРѕ.\n\nР›РѕРіС–РЅ: {email}\nРџР°СЂРѕР»СЊ: {password}\nРџРѕСЃРёР»Р°РЅРЅСЏ РґР»СЏ РІС…РѕРґСѓ: {login_url}\n\nРџС–СЃР»СЏ РїРµСЂС€РѕРіРѕ РІС…РѕРґСѓ Р·РјС–РЅС–С‚СЊ РїР°СЂРѕР»СЊ.",
        "open_cherryx": "Р’С–РґРєСЂРёС‚Рё CherryX",
        "email_exists": "РўР°РєРёР№ email РІР¶Рµ С” РІ CherryX.\nРЈРІС–Р№РґС–С‚СЊ РЅР° СЃР°Р№С‚С–, РІС–РґРєСЂРёР№С‚Рµ CherryX Pay, СЃРєРѕРїС–СЋР№С‚Рµ /link CODE С– РЅР°РґС–С€Р»С–С‚СЊ СЃСЋРґРё. РћРїР»Р°С‚Р° С‡РµРєР°С‚РёРјРµ РїСЂРёРІ'СЏР·РєРё.",
        "email_invalid": "РќР°РґС–С€Р»С–С‚СЊ РєРѕСЂРµРєС‚РЅРёР№ email.",
    },
    "en": {
        "intro": "CherryX Pay bot\n\nPay for a package, top up balance, and monitor your account.\n\n/link CODE - link website account\n/status - access status\n/wallet - CherryX balance\n/paysupport - payment help",
        "help": "This bot is used only for CherryX payments and account monitoring.\n\n/subscribe - pay with Telegram Stars\n/status - access status\n/wallet - CherryX balance and linked account\n/link CODE - link Telegram with the website account\n/paysupport - payment support\n/id - Telegram ID",
        "only": "This bot accepts payments and monitors CherryX access only. Use /subscribe, /status, /wallet or /paysupport.",
        "choose": "Choose a package or top up balance:",
        "topup": "Top up balance",
        "enter_stars": "Enter the top up amount in Telegram Stars.\nMinimum: 1 Star. Maximum: 150000 Stars.\nCherryX will be credited by the current rate.",
        "invalid_stars": "Enter a whole Stars amount from 1 to 150000.",
        "stars_range": "Amount must be from 1 to 150000 Telegram Stars.",
        "invoice": "{title}\n{description}\n\nTo pay: {stars} Telegram Stars.",
        "intent_error": "Payment was received, but it could not be applied. Please contact /paysupport.",
        "need_email": "Payment received.\nSend your email and I will create your CherryX account, apply the package or balance, and send login details.",
        "applied": "Payment received and applied.\n{title}\nCherryX: {cherryx}",
        "account_created": "CherryX account created and payment applied.\n\nLogin: {email}\nPassword: {password}\nLogin URL: {login_url}\n\nChange the password after first login.",
        "open_cherryx": "Open CherryX",
        "email_exists": "This email already exists on CherryX.\nLog in on the website, open CherryX Pay, copy /link CODE and send it here. The paid intent will wait for linking.",
        "email_invalid": "Please send a valid email address.",
    },
}
for _code in ("fr", "de", "es", "ka", "hy", "it"):
    BILLING_TEXT[_code] = BILLING_TEXT["en"]
BILLING_TEXT["fr"] = {
    **BILLING_TEXT["en"],
    "intro": "Bot CherryX Pay\n\nPayez un forfait, rechargez le solde et vГ©rifiez votre compte.\n\n/link CODE - lier le compte du site\n/status - statut d'accГЁs\n/wallet - solde CherryX\n/paysupport - aide au paiement",
    "choose": "Choisissez un forfait ou rechargez le solde:",
    "topup": "Recharger le solde",
    "enter_stars": "Entrez le montant en Telegram Stars.\nMinimum: 1 Star. Maximum: 150000 Stars.\nCherryX sera crГ©ditГ© selon le taux actuel.",
    "invalid_stars": "Entrez un nombre entier de Stars entre 1 et 150000.",
    "stars_range": "Le montant doit ГЄtre entre 1 et 150000 Telegram Stars.",
    "invoice": "{title}\n{description}\n\nГЂ payer: {stars} Telegram Stars.",
    "need_email": "Paiement reГ§u.\nEnvoyez votre email et je crГ©erai votre compte CherryX, puis j'appliquerai le forfait ou le solde.",
    "applied": "Paiement reГ§u et appliquГ©.\n{title}\nCherryX: {cherryx}",
    "account_created": "Compte CherryX crГ©Г©, paiement appliquГ©.\n\nLogin: {email}\nMot de passe: {password}\nURL de connexion: {login_url}\n\nChangez le mot de passe aprГЁs la premiГЁre connexion.",
}
BILLING_TEXT["de"] = {
    **BILLING_TEXT["en"],
    "intro": "CherryX Pay Bot\n\nPaket bezahlen, Guthaben aufladen und Konto prГјfen.\n\n/link CODE - Website-Konto verknГјpfen\n/status - Zugriffsstatus\n/wallet - CherryX Guthaben\n/paysupport - Zahlungshilfe",
    "choose": "Paket wГ¤hlen oder Guthaben aufladen:",
    "topup": "Guthaben aufladen",
    "enter_stars": "Geben Sie den Betrag in Telegram Stars ein.\nMinimum: 1 Star. Maximum: 150000 Stars.\nCherryX wird zum aktuellen Kurs gutgeschrieben.",
    "invalid_stars": "Geben Sie eine ganze Stars-Zahl von 1 bis 150000 ein.",
    "stars_range": "Der Betrag muss zwischen 1 und 150000 Telegram Stars liegen.",
    "invoice": "{title}\n{description}\n\nZu zahlen: {stars} Telegram Stars.",
    "need_email": "Zahlung erhalten.\nSenden Sie Ihre E-Mail, dann erstelle ich Ihr CherryX-Konto und wende Paket oder Guthaben an.",
    "applied": "Zahlung erhalten und angewendet.\n{title}\nCherryX: {cherryx}",
    "account_created": "CherryX-Konto erstellt, Zahlung angewendet.\n\nLogin: {email}\nPasswort: {password}\nLogin-URL: {login_url}\n\nГ„ndern Sie das Passwort nach dem ersten Login.",
}
BILLING_TEXT["es"] = {
    **BILLING_TEXT["en"],
    "intro": "Bot CherryX Pay\n\nPaga un paquete, recarga saldo y revisa tu cuenta.\n\n/link CODE - vincular cuenta web\n/status - estado de acceso\n/wallet - saldo CherryX\n/paysupport - ayuda con pagos",
    "choose": "Elige un paquete o recarga saldo:",
    "topup": "Recargar saldo",
    "enter_stars": "Introduce el importe en Telegram Stars.\nMГ­nimo: 1 Star. MГЎximo: 150000 Stars.\nCherryX se acreditarГЎ segГєn el tipo actual.",
    "invalid_stars": "Introduce un nГєmero entero de Stars entre 1 y 150000.",
    "stars_range": "El importe debe estar entre 1 y 150000 Telegram Stars.",
    "invoice": "{title}\n{description}\n\nA pagar: {stars} Telegram Stars.",
    "need_email": "Pago recibido.\nEnvГ­a tu email y crearГ© tu cuenta CherryX, aplicando el paquete o saldo.",
    "applied": "Pago recibido y aplicado.\n{title}\nCherryX: {cherryx}",
    "account_created": "Cuenta CherryX creada, pago aplicado.\n\nLogin: {email}\nContraseГ±a: {password}\nURL de acceso: {login_url}\n\nCambia la contraseГ±a despuГ©s del primer acceso.",
}
BILLING_TEXT["it"] = {
    **BILLING_TEXT["en"],
    "intro": "Bot CherryX Pay\n\nPaga un pacchetto, ricarica il saldo e controlla l'account.\n\n/link CODE - collega account web\n/status - stato accesso\n/wallet - saldo CherryX\n/paysupport - supporto pagamenti",
    "choose": "Scegli un pacchetto o ricarica il saldo:",
    "topup": "Ricarica saldo",
    "enter_stars": "Inserisci l'importo in Telegram Stars.\nMinimo: 1 Star. Massimo: 150000 Stars.\nCherryX verrГ  accreditato al tasso attuale.",
    "invalid_stars": "Inserisci un numero intero di Stars da 1 a 150000.",
    "stars_range": "L'importo deve essere tra 1 e 150000 Telegram Stars.",
    "invoice": "{title}\n{description}\n\nDa pagare: {stars} Telegram Stars.",
    "need_email": "Pagamento ricevuto.\nInvia la tua email e creerГІ l'account CherryX, applicando pacchetto o saldo.",
    "applied": "Pagamento ricevuto e applicato.\n{title}\nCherryX: {cherryx}",
    "account_created": "Account CherryX creato, pagamento applicato.\n\nLogin: {email}\nPassword: {password}\nURL login: {login_url}\n\nCambia la password dopo il primo accesso.",
}
BILLING_TEXT["ru"] = {
    **BILLING_TEXT["en"],
    "intro": "CherryX Pay Р±РѕС‚\n\nР—РґРµСЃСЊ РјРѕР¶РЅРѕ РѕРїР»Р°С‚РёС‚СЊ РїР°РєРµС‚, РїРѕРїРѕР»РЅРёС‚СЊ Р±Р°Р»Р°РЅСЃ Рё РїСЂРѕРІРµСЂРёС‚СЊ Р°РєРєР°СѓРЅС‚.\n\n/link CODE - РїСЂРёРІСЏР·Р°С‚СЊ Р°РєРєР°СѓРЅС‚ СЃР°Р№С‚Р°\n/status - СЃС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїР°\n/wallet - Р±Р°Р»Р°РЅСЃ CherryX\n/paysupport - РїРѕРјРѕС‰СЊ СЃ РѕРїР»Р°С‚РѕР№",
    "help": "Р­С‚РѕС‚ Р±РѕС‚ СЂР°Р±РѕС‚Р°РµС‚ РґР»СЏ РѕРїР»Р°С‚ CherryX Рё РјРѕРЅРёС‚РѕСЂРёРЅРіР° Р°РєРєР°СѓРЅС‚Р°.\n\n/subscribe - РѕРїР»Р°С‚Р° С‡РµСЂРµР· Telegram Stars\n/status - СЃС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїР°\n/wallet - Р±Р°Р»Р°РЅСЃ Рё РїСЂРёРІСЏР·РєР°\n/link CODE - РїСЂРёРІСЏР·Р°С‚СЊ Р°РєРєР°СѓРЅС‚ СЃР°Р№С‚Р°\n/paysupport - РїРѕРјРѕС‰СЊ СЃ РѕРїР»Р°С‚РѕР№\n/id - Telegram ID",
    "only": "Р‘РѕС‚ РїСЂРёРЅРёРјР°РµС‚ РѕРїР»Р°С‚С‹ Рё РїРѕРєР°Р·С‹РІР°РµС‚ СЃС‚Р°С‚СѓСЃ CherryX. РСЃРїРѕР»СЊР·СѓР№С‚Рµ /subscribe, /status, /wallet РёР»Рё /paysupport.",
    "choose": "Р’С‹Р±РµСЂРёС‚Рµ РїР°РєРµС‚ РёР»Рё РїРѕРїРѕР»РЅРµРЅРёРµ Р±Р°Р»Р°РЅСЃР°:",
    "topup": "РџРѕРїРѕР»РЅРёС‚СЊ Р±Р°Р»Р°РЅСЃ",
    "enter_stars": "Р’РІРµРґРёС‚Рµ СЃСѓРјРјСѓ РїРѕРїРѕР»РЅРµРЅРёСЏ РІ Telegram Stars.\nРњРёРЅРёРјСѓРј: 1 Star. РњР°РєСЃРёРјСѓРј: 150000 Stars.\nРќР° Р±Р°Р»Р°РЅСЃ CherryX РїСЂРёРґРµС‚ СЃСѓРјРјР° РїРѕ С‚РµРєСѓС‰РµРјСѓ РєСѓСЂСЃСѓ.",
    "invalid_stars": "Р’РІРµРґРёС‚Рµ С†РµР»РѕРµ С‡РёСЃР»Рѕ Stars РѕС‚ 1 РґРѕ 150000.",
    "stars_range": "РЎСѓРјРјР° РґРѕР»Р¶РЅР° Р±С‹С‚СЊ РѕС‚ 1 РґРѕ 150000 Telegram Stars.",
    "invoice": "{title}\n{description}\n\nРљ РѕРїР»Р°С‚Рµ: {stars} Telegram Stars.",
    "intent_error": "РћРїР»Р°С‚Р° РїРѕР»СѓС‡РµРЅР°, РЅРѕ РЅРµ СЃРјРѕРі РїСЂРёРјРµРЅРёС‚СЊ РµРµ Рє Р°РєРєР°СѓРЅС‚Сѓ. РќР°РїРёС€РёС‚Рµ /paysupport.",
    "need_email": "РћРїР»Р°С‚Р° РїРѕР»СѓС‡РµРЅР°.\nРћС‚РїСЂР°РІСЊС‚Рµ email, Рё СЏ СЃРѕР·РґР°Рј CherryX Р°РєРєР°СѓРЅС‚, РїСЂРёРјРµРЅСЋ РїР°РєРµС‚ РёР»Рё Р±Р°Р»Р°РЅСЃ Рё РїСЂРёС€Р»СЋ РґР°РЅРЅС‹Рµ РґР»СЏ РІС…РѕРґР°.",
    "applied": "РћРїР»Р°С‚Р° РїСЂРѕС€Р»Р° Рё РїСЂРёРјРµРЅРµРЅР°.\n{title}\nCherryX: {cherryx}",
    "account_created": "CherryX Р°РєРєР°СѓРЅС‚ СЃРѕР·РґР°РЅ, РѕРїР»Р°С‚Р° РїСЂРёРјРµРЅРµРЅР°.\n\nР›РѕРіРёРЅ: {email}\nРџР°СЂРѕР»СЊ: {password}\nРЎСЃС‹Р»РєР° РґР»СЏ РІС…РѕРґР°: {login_url}\n\nРџРѕСЃР»Рµ РїРµСЂРІРѕРіРѕ РІС…РѕРґР° СЃРјРµРЅРёС‚Рµ РїР°СЂРѕР»СЊ.",
    "open_cherryx": "РћС‚РєСЂС‹С‚СЊ CherryX",
    "email_exists": "РўР°РєРѕР№ email СѓР¶Рµ РµСЃС‚СЊ РІ CherryX.\nР’РѕР№РґРёС‚Рµ РЅР° СЃР°Р№С‚Рµ, РѕС‚РєСЂРѕР№С‚Рµ CherryX Pay, СЃРєРѕРїРёСЂСѓР№С‚Рµ /link CODE Рё РѕС‚РїСЂР°РІСЊС‚Рµ СЃСЋРґР°. РћРїР»Р°С‚Р° Р±СѓРґРµС‚ Р¶РґР°С‚СЊ РїСЂРёРІСЏР·РєРё.",
    "email_invalid": "РћС‚РїСЂР°РІСЊС‚Рµ РєРѕСЂСЂРµРєС‚РЅС‹Р№ email.",
}
BILLING_TEXT["uk"] = {
    **BILLING_TEXT["en"],
    "intro": "CherryX Pay Р±РѕС‚\n\nРўСѓС‚ РјРѕР¶РЅР° РѕРїР»Р°С‚РёС‚Рё РїР°РєРµС‚, РїРѕРїРѕРІРЅРёС‚Рё Р±Р°Р»Р°РЅСЃ С– РїРµСЂРµРІС–СЂРёС‚Рё Р°РєР°СѓРЅС‚.\n\n/link CODE - РїСЂРёРІ'СЏР·Р°С‚Рё Р°РєР°СѓРЅС‚ СЃР°Р№С‚Сѓ\n/status - СЃС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїСѓ\n/wallet - Р±Р°Р»Р°РЅСЃ CherryX\n/paysupport - РґРѕРїРѕРјРѕРіР° Р· РѕРїР»Р°С‚РѕСЋ",
    "help": "Р¦РµР№ Р±РѕС‚ РїСЂР°С†СЋС” РґР»СЏ РѕРїР»Р°С‚ CherryX С– РјРѕРЅС–С‚РѕСЂРёРЅРіСѓ Р°РєР°СѓРЅС‚Р°.\n\n/subscribe - РѕРїР»Р°С‚Р° С‡РµСЂРµР· Telegram Stars\n/status - СЃС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїСѓ\n/wallet - Р±Р°Р»Р°РЅСЃ С– РїСЂРёРІ'СЏР·РєР°\n/link CODE - РїСЂРёРІ'СЏР·Р°С‚Рё Р°РєР°СѓРЅС‚ СЃР°Р№С‚Сѓ\n/paysupport - РґРѕРїРѕРјРѕРіР° Р· РѕРїР»Р°С‚РѕСЋ\n/id - Telegram ID",
    "only": "Р‘РѕС‚ РїСЂРёР№РјР°С” РѕРїР»Р°С‚Рё С– РїРѕРєР°Р·СѓС” СЃС‚Р°С‚СѓСЃ CherryX. Р’РёРєРѕСЂРёСЃС‚РѕРІСѓР№С‚Рµ /subscribe, /status, /wallet Р°Р±Рѕ /paysupport.",
    "choose": "РћР±РµСЂС–С‚СЊ РїР°РєРµС‚ Р°Р±Рѕ РїРѕРїРѕРІРЅРµРЅРЅСЏ Р±Р°Р»Р°РЅСЃСѓ:",
    "topup": "РџРѕРїРѕРІРЅРёС‚Рё Р±Р°Р»Р°РЅСЃ",
    "enter_stars": "Р’РІРµРґС–С‚СЊ СЃСѓРјСѓ РїРѕРїРѕРІРЅРµРЅРЅСЏ РІ Telegram Stars.\nРњС–РЅС–РјСѓРј: 1 Star. РњР°РєСЃРёРјСѓРј: 150000 Stars.\nРќР° Р±Р°Р»Р°РЅСЃ CherryX РїСЂРёР№РґРµ СЃСѓРјР° Р·Р° РїРѕС‚РѕС‡РЅРёРј РєСѓСЂСЃРѕРј.",
    "invalid_stars": "Р’РІРµРґС–С‚СЊ С†С–Р»Рµ С‡РёСЃР»Рѕ Stars РІС–Рґ 1 РґРѕ 150000.",
    "stars_range": "РЎСѓРјР° РјР°С” Р±СѓС‚Рё РІС–Рґ 1 РґРѕ 150000 Telegram Stars.",
    "invoice": "{title}\n{description}\n\nР”Рѕ РѕРїР»Р°С‚Рё: {stars} Telegram Stars.",
    "intent_error": "РћРїР»Р°С‚Сѓ РѕС‚СЂРёРјР°РЅРѕ, Р°Р»Рµ РЅРµ РІРґР°Р»РѕСЃСЏ Р·Р°СЃС‚РѕСЃСѓРІР°С‚Рё С—С— РґРѕ Р°РєР°СѓРЅС‚Р°. РќР°РїРёС€С–С‚СЊ /paysupport.",
    "need_email": "РћРїР»Р°С‚Сѓ РѕС‚СЂРёРјР°РЅРѕ.\nРќР°РґС–С€Р»С–С‚СЊ email, С– СЏ СЃС‚РІРѕСЂСЋ CherryX Р°РєР°СѓРЅС‚, Р·Р°СЃС‚РѕСЃСѓСЋ РїР°РєРµС‚ Р°Р±Рѕ Р±Р°Р»Р°РЅСЃ С– РЅР°РґС–С€Р»СЋ РґР°РЅС– РґР»СЏ РІС…РѕРґСѓ.",
    "applied": "РћРїР»Р°С‚Сѓ РїСЂРѕРІРµРґРµРЅРѕ С– Р·Р°СЃС‚РѕСЃРѕРІР°РЅРѕ.\n{title}\nCherryX: {cherryx}",
    "account_created": "CherryX Р°РєР°СѓРЅС‚ СЃС‚РІРѕСЂРµРЅРѕ, РѕРїР»Р°С‚Сѓ Р·Р°СЃС‚РѕСЃРѕРІР°РЅРѕ.\n\nР›РѕРіС–РЅ: {email}\nРџР°СЂРѕР»СЊ: {password}\nРџРѕСЃРёР»Р°РЅРЅСЏ РґР»СЏ РІС…РѕРґСѓ: {login_url}\n\nРџС–СЃР»СЏ РїРµСЂС€РѕРіРѕ РІС…РѕРґСѓ Р·РјС–РЅС–С‚СЊ РїР°СЂРѕР»СЊ.",
    "open_cherryx": "Р’С–РґРєСЂРёС‚Рё CherryX",
    "email_exists": "РўР°РєРёР№ email СѓР¶Рµ С” РІ CherryX.\nРЈРІС–Р№РґС–С‚СЊ РЅР° СЃР°Р№С‚С–, РІС–РґРєСЂРёР№С‚Рµ CherryX Pay, СЃРєРѕРїС–СЋР№С‚Рµ /link CODE С– РЅР°РґС–С€Р»С–С‚СЊ СЃСЋРґРё. РћРїР»Р°С‚Р° С‡РµРєР°С‚РёРјРµ РїСЂРёРІ'СЏР·РєРё.",
    "email_invalid": "РќР°РґС–С€Р»С–С‚СЊ РєРѕСЂРµРєС‚РЅРёР№ email.",
}
BILLING_TEXT["ka"] = {
    **BILLING_TEXT["en"],
    "intro": "CherryX Pay бѓ‘бѓќбѓўбѓ\n\nбѓђбѓҐ бѓЁбѓ”бѓ’бѓбѓ«бѓљбѓбѓђбѓ— бѓћбѓђбѓ™бѓ”бѓўбѓбѓЎ бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓђ, бѓ‘бѓђбѓљбѓђбѓњбѓЎбѓбѓЎ бѓЁбѓ”бѓ•бѓЎбѓ”бѓ‘бѓђ бѓ“бѓђ бѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓбѓЎ бѓЁбѓ”бѓ›бѓќбѓ¬бѓ›бѓ”бѓ‘бѓђ.\n\n/link CODE - бѓЎбѓђбѓбѓўбѓбѓЎ бѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓбѓЎ бѓ›бѓбѓ‘бѓ›бѓђ\n/status - бѓ¬бѓ•бѓ“бѓќбѓ›бѓбѓЎ бѓЎбѓўбѓђбѓўбѓЈбѓЎбѓ\n/wallet - CherryX бѓ‘бѓђбѓљбѓђбѓњбѓЎбѓ\n/paysupport - бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓбѓЎ бѓ“бѓђбѓ®бѓ›бѓђбѓ бѓ”бѓ‘бѓђ",
    "choose": "бѓђбѓбѓ бѓ©бѓбѓ”бѓ— бѓћбѓђбѓ™бѓ”бѓўбѓ бѓђбѓњ бѓ‘бѓђбѓљбѓђбѓњбѓЎбѓбѓЎ бѓЁбѓ”бѓ•бѓЎбѓ”бѓ‘бѓђ:",
    "topup": "бѓ‘бѓђбѓљбѓђбѓњбѓЎбѓбѓЎ бѓЁбѓ”бѓ•бѓЎбѓ”бѓ‘бѓђ",
    "enter_stars": "бѓЁбѓ”бѓбѓ§бѓ•бѓђбѓњбѓ”бѓ— бѓ—бѓђбѓњбѓ®бѓђ Telegram Stars-бѓЁбѓ.\nбѓ›бѓбѓњбѓбѓ›бѓЈбѓ›бѓ: 1 Star. бѓ›бѓђбѓҐбѓЎбѓбѓ›бѓЈбѓ›бѓ: 150000 Stars.\nCherryX бѓ©бѓђбѓбѓ бѓбѓЄбѓ®бѓ”бѓ‘бѓђ бѓ›бѓбѓ›бѓ“бѓбѓњбѓђбѓ бѓ” бѓ™бѓЈбѓ бѓЎбѓбѓ—.",
    "invalid_stars": "бѓЁбѓ”бѓбѓ§бѓ•бѓђбѓњбѓ”бѓ— бѓ›бѓ—бѓ”бѓљбѓ бѓ бѓбѓЄбѓ®бѓ•бѓ 1-бѓ“бѓђбѓњ 150000 Stars-бѓ›бѓ“бѓ”.",
    "stars_range": "бѓ—бѓђбѓњбѓ®бѓђ бѓЈбѓњбѓ“бѓђ бѓбѓ§бѓќбѓЎ 1-бѓ“бѓђбѓњ 150000 Telegram Stars-бѓ›бѓ“бѓ”.",
    "invoice": "{title}\n{description}\n\nбѓ’бѓђбѓ“бѓђбѓЎбѓђбѓ®бѓ“бѓ”бѓљбѓ: {stars} Telegram Stars.",
    "need_email": "бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓђ бѓ›бѓбѓ¦бѓ”бѓ‘бѓЈбѓљбѓбѓђ.\nбѓ’бѓђбѓ›бѓќбѓ’бѓ–бѓђбѓ•бѓњбѓ”бѓ— email бѓ“бѓђ бѓЁбѓ”бѓ•бѓҐбѓ›бѓњбѓ CherryX бѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓЎ, бѓ›бѓбѓ•бѓђбѓ‘бѓђбѓ› бѓћбѓђбѓ™бѓ”бѓўбѓЎ бѓђбѓњ бѓ‘бѓђбѓљбѓђбѓњбѓЎбѓЎ бѓ“бѓђ бѓ’бѓђбѓ›бѓќбѓ’бѓбѓ’бѓ–бѓђбѓ•бѓњбѓбѓ— бѓЁбѓ”бѓЎбѓ•бѓљбѓбѓЎ бѓ›бѓќбѓњбѓђбѓЄбѓ”бѓ›бѓ”бѓ‘бѓЎ.",
    "applied": "бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓђ бѓ›бѓбѓ¦бѓ”бѓ‘бѓЈбѓљбѓбѓђ бѓ“бѓђ бѓ’бѓђбѓ›бѓќбѓ§бѓ”бѓњбѓ”бѓ‘бѓЈбѓљбѓбѓђ.\n{title}\nCherryX: {cherryx}",
    "account_created": "CherryX бѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓ бѓЁбѓ”бѓбѓҐбѓ›бѓњбѓђ бѓ“бѓђ бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓђ бѓ’бѓђбѓ›бѓќбѓ§бѓ”бѓњбѓ”бѓ‘бѓЈбѓљбѓбѓђ.\n\nLogin: {email}\nPassword: {password}\nLogin URL: {login_url}\n\nбѓћбѓбѓ бѓ•бѓ”бѓљбѓ бѓЁбѓ”бѓЎбѓ•бѓљбѓбѓЎ бѓЁбѓ”бѓ›бѓ“бѓ”бѓ’ бѓЁбѓ”бѓЄбѓ•бѓђбѓљбѓ”бѓ— бѓћбѓђбѓ бѓќбѓљбѓ.",
    "open_cherryx": "CherryX-бѓбѓЎ бѓ’бѓђбѓ®бѓЎбѓњбѓђ",
    "email_invalid": "бѓ’бѓ—бѓ®бѓќбѓ•бѓ—, бѓ’бѓђбѓ›бѓќбѓ’бѓ–бѓђбѓ•бѓњбѓќбѓ— бѓЎбѓ¬бѓќбѓ бѓ email.",
}
BILLING_TEXT["hy"] = {
    **BILLING_TEXT["en"],
    "intro": "CherryX Pay ХўХёХї\n\nФ±ХµХЅХїХҐХІ ХЇХЎЦЂХёХІ ХҐЦ„ ХѕХіХЎЦЂХҐХ¬ ЦѓХЎХ©ХҐХ©Х« Х°ХЎХґХЎЦЂ, Х°ХЎХґХЎХ¬ЦЂХҐХ¬ ХўХЎХ¬ХЎХ¶ХЅХЁ Ц‡ ХЅХїХёЦ‚ХЈХҐХ¬ Х°ХЎХ·Х«ХѕХЁЦ‰\n\n/link CODE - ХЇХЎХєХҐХ¬ ХЇХЎХµЦ„Х« Х°ХЎХ·Х«ХѕХЁ\n/status - Х°ХЎХЅХЎХ¶ХҐХ¬Х«ХёЦ‚Х©ХµХЎХ¶ ХЇХЎЦЂХЈХЎХѕХ«ХіХЎХЇ\n/wallet - CherryX ХўХЎХ¬ХЎХ¶ХЅ\n/paysupport - ХѕХіХЎЦЂХґХЎХ¶ Ц…ХЈХ¶ХёЦ‚Х©ХµХёЦ‚Х¶",
    "choose": "ФёХ¶ХїЦЂХҐЦ„ ЦѓХЎХ©ХҐХ© ХЇХЎХґ ХўХЎХ¬ХЎХ¶ХЅХ« Х°ХЎХґХЎХ¬ЦЂХёЦ‚Хґ.",
    "topup": "ХЂХЎХґХЎХ¬ЦЂХҐХ¬ ХўХЎХ¬ХЎХ¶ХЅХЁ",
    "enter_stars": "Х„ХёЦ‚ХїЦ„ХЎХЈЦЂХҐЦ„ Х°ХЎХґХЎХ¬ЦЂХґХЎХ¶ ХЈХёЦ‚ХґХЎЦЂХЁ Telegram Stars-ХёХѕЦ‰\nХ†ХѕХЎХ¦ХЎХЈХёЦ‚ХµХ¶ХЁХќ 1 StarЦ‰ Ф±ХјХЎХѕХҐХ¬ХЎХЈХёЦ‚ХµХ¶ХЁХќ 150000 StarsЦ‰\nCherryX-ХЁ ХЇХЎХѕХҐХ¬ХЎЦЃХѕХ« ХЁХ¶Х©ХЎЦЃХ«ХЇ ЦѓХёХ­ХЎЦЂХЄХҐЦ„ХёХѕЦ‰",
    "invalid_stars": "Х„ХёЦ‚ХїЦ„ХЎХЈЦЂХҐЦ„ ХЎХґХўХёХІХ» Х©Х«Хѕ 1-Х«ЦЃ 150000 Stars ХґХ«Х»ХЎХЇХЎХµЦ„ХёЦ‚ХґЦ‰",
    "stars_range": "ФіХёЦ‚ХґХЎЦЂХЁ ХєХҐХїЦ„ Х§ Х¬Х«Х¶Х« 1-Х«ЦЃ 150000 Telegram StarsЦ‰",
    "invoice": "{title}\n{description}\n\nХЋХіХЎЦЂХґХЎХ¶ ХҐХ¶Х©ХЎХЇХЎХќ {stars} Telegram StarsЦ‰",
    "need_email": "ХЋХіХЎЦЂХёЦ‚ХґХЁ ХЅХїХЎЦЃХѕХҐХ¬ Х§Ц‰\nХ€Ц‚ХІХЎЦЂХЇХҐЦ„ email-ХЁ, Ц‡ ХҐХЅ ХЇХЅХїХҐХІХ®ХҐХґ CherryX Х°ХЎХ·Х«Хѕ, ХЇХЇХ«ЦЂХЎХјХҐХґ ЦѓХЎХ©ХҐХ©ХЁ ХЇХЎХґ ХўХЎХ¬ХЎХ¶ХЅХЁ Ц‡ ХЇХёЦ‚ХІХЎЦЂХЇХҐХґ ХґХёЦ‚ХїЦ„Х« ХїХѕХµХЎХ¬Х¶ХҐЦЂХЁЦ‰",
    "applied": "ХЋХіХЎЦЂХёЦ‚ХґХЁ ХЅХїХЎЦЃХѕХҐХ¬ Ц‡ ХЇХ«ЦЂХЎХјХѕХҐХ¬ Х§Ц‰\n{title}\nCherryX: {cherryx}",
    "account_created": "CherryX Х°ХЎХ·Х«ХѕХЁ ХЅХїХҐХІХ®ХѕХҐХ¬ Х§, ХѕХіХЎЦЂХёЦ‚ХґХЁ ХЇХ«ЦЂХЎХјХѕХҐХ¬ Х§Ц‰\n\nLogin: {email}\nPassword: {password}\nLogin URL: {login_url}\n\nФ±ХјХЎХ»Х«Х¶ ХґХёЦ‚ХїЦ„Х«ЦЃ Х°ХҐХїХё ЦѓХёХ­ХҐЦ„ ХЈХЎХІХїХ¶ХЎХўХЎХјХЁЦ‰",
    "open_cherryx": "ФІХЎЦЃХҐХ¬ CherryX-ХЁ",
    "email_invalid": "ФЅХ¶Х¤ЦЂХёЦ‚Хґ ХҐХ¶Ц„ ХёЦ‚ХІХЎЦЂХЇХҐХ¬ ХіХ«Х·Хї emailЦ‰",
}
BILLING_TEXT.update({
    "ru": {
        **BILLING_TEXT["ru"],
        "pay_button": "РћРїР»Р°С‚РёС‚СЊ Stars",
        "status_button": "РЎС‚Р°С‚СѓСЃ",
        "wallet_button": "Р‘Р°Р»Р°РЅСЃ",
        "support_button": "РџРѕРґРґРµСЂР¶РєР°",
        "language_button": "РЇР·С‹Рє",
        "mini_app": "РћС‚РєСЂС‹С‚СЊ CherryX",
        "payment_link_invalid": "РЎСЃС‹Р»РєР° РЅР° РѕРїР»Р°С‚Сѓ СѓСЃС‚Р°СЂРµР»Р° РёР»Рё РЅРµРґРѕСЃС‚СѓРїРЅР°.",
        "cancelled": "РћРє, РѕС‚РјРµРЅРёР».",
        "pro_price": "Р”РѕСЃС‚СѓРї CherryX СЃС‚РѕРёС‚ {stars} Stars РЅР° {days} РґРЅРµР№.",
        "wallet_error": "РќРµ СЃРјРѕРі РїСЂРѕРІРµСЂРёС‚СЊ Р°РєРєР°СѓРЅС‚ СЃРµР№С‡Р°СЃ. РџРѕРїСЂРѕР±СѓР№С‚Рµ /wallet РїРѕР·Р¶Рµ.",
        "wallet_linked": "CherryX Р°РєРєР°СѓРЅС‚ РїСЂРёРІСЏР·Р°РЅ.\nР‘Р°Р»Р°РЅСЃ: {balance} CherryX.\nР”РѕСЃС‚СѓРї: {access}.",
        "wallet_not_linked": "Telegram РїРѕРєР° РЅРµ РїСЂРёРІСЏР·Р°РЅ Рє Р°РєРєР°СѓРЅС‚Сѓ CherryX.\nРћР¶РёРґР°РµС‚ РїСЂРёРІСЏР·РєРё: {pending} CherryX.\n\nРћС‚РєСЂРѕР№С‚Рµ CherryX Pay РЅР° СЃР°Р№С‚Рµ, СЃРєРѕРїРёСЂСѓР№С‚Рµ /link CODE Рё РѕС‚РїСЂР°РІСЊС‚Рµ СЃСЋРґР°.",
        "not_active": "РЅРµС‚ Р°РєС‚РёРІРЅРѕРіРѕ РґРѕСЃС‚СѓРїР°",
        "link_missing": "РћС‚РїСЂР°РІСЊС‚Рµ РєРѕРјР°РЅРґСѓ СЃ РєРѕРґРѕРј РёР· CherryX Pay: /link CODE",
        "link_failed": "РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ РїСЂРёРІСЏР·Р°С‚СЊ Р°РєРєР°СѓРЅС‚. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР»СѓС‡РёС‚СЊ РЅРѕРІС‹Р№ РєРѕРґ РІ CherryX Pay.",
        "link_not_found": "РљРѕРґ РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ РёСЃРїРѕР»СЊР·РѕРІР°РЅ. РџРѕР»СѓС‡РёС‚Рµ РЅРѕРІС‹Р№ РєРѕРґ РІ CherryX Pay Рё РѕС‚РїСЂР°РІСЊС‚Рµ /link CODE.",
        "link_success": "Р“РѕС‚РѕРІРѕ, Telegram РїСЂРёРІСЏР·Р°РЅ Рє CherryX Р°РєРєР°СѓРЅС‚Сѓ.\nР‘Р°Р»Р°РЅСЃ: {balance} CherryX.\nРўРµРїРµСЂСЊ РѕРїР»Р°С‚С‹ Stars С‡РµСЂРµР· Р±РѕС‚Р° Р±СѓРґСѓС‚ РїРѕРїР°РґР°С‚СЊ РІ СЌС‚РѕС‚ Р°РєРєР°СѓРЅС‚.",
        "pay_support": "РџРѕРґРґРµСЂР¶РєР° РѕРїР»Р°С‚ CherryX С‡РµСЂРµР· Telegram Stars.\n\nР•СЃР»Рё Stars СЃРїРёСЃР°Р»РёСЃСЊ, РЅРѕ РґРѕСЃС‚СѓРї РёР»Рё Р±Р°Р»Р°РЅСЃ РЅРµ РїРѕСЏРІРёР»СЃСЏ: РѕС‚РїСЂР°РІСЊС‚Рµ СЃСЋРґР° СЃРєСЂРёРЅ РѕРїР»Р°С‚С‹, Telegram ID РёР· /id Рё РїСЂРёРјРµСЂРЅРѕРµ РІСЂРµРјСЏ РїР»Р°С‚РµР¶Р°.\nР”Р»СЏ РїСЂРёРІСЏР·РєРё Р°РєРєР°СѓРЅС‚Р° РёСЃРїРѕР»СЊР·СѓР№С‚Рµ /link CODE РёР· CherryX Pay. Р”Р»СЏ РїСЂРѕРІРµСЂРєРё Р±Р°Р»Р°РЅСЃР° вЂ” /wallet.",
        "topup_invalid": "РќРµРєРѕСЂСЂРµРєС‚РЅР°СЏ СЃСѓРјРјР° РїРѕРїРѕР»РЅРµРЅРёСЏ.",
        "precheckout_currency": "РћРїР»Р°С‚Р° РїСЂРёРЅРёРјР°РµС‚СЃСЏ С‚РѕР»СЊРєРѕ РІ Telegram Stars.",
        "precheckout_expired": "РЎСЃС‹Р»РєР° РЅР° РѕРїР»Р°С‚Сѓ СѓСЃС‚Р°СЂРµР»Р° РёР»Рё СѓР¶Рµ РёСЃРїРѕР»СЊР·РѕРІР°РЅР°.",
        "precheckout_amount": "РЎСѓРјРјР° СЃС‡РµС‚Р° РЅРµ СЃРѕРІРїР°РґР°РµС‚.",
    },
    "uk": {
        **BILLING_TEXT["uk"],
        "pay_button": "РћРїР»Р°С‚РёС‚Рё Stars",
        "status_button": "РЎС‚Р°С‚СѓСЃ",
        "wallet_button": "Р‘Р°Р»Р°РЅСЃ",
        "support_button": "РџС–РґС‚СЂРёРјРєР°",
        "language_button": "РњРѕРІР°",
        "mini_app": "Р’С–РґРєСЂРёС‚Рё CherryX",
        "payment_link_invalid": "РџРѕСЃРёР»Р°РЅРЅСЏ РЅР° РѕРїР»Р°С‚Сѓ Р·Р°СЃС‚Р°СЂС–Р»Рѕ Р°Р±Рѕ РЅРµРґРѕСЃС‚СѓРїРЅРµ.",
        "cancelled": "РћРє, СЃРєР°СЃРѕРІР°РЅРѕ.",
        "pro_price": "Р”РѕСЃС‚СѓРї CherryX РєРѕС€С‚СѓС” {stars} Stars РЅР° {days} РґРЅС–РІ.",
        "wallet_error": "РќРµ РІРґР°Р»РѕСЃСЏ РїРµСЂРµРІС–СЂРёС‚Рё Р°РєР°СѓРЅС‚ Р·Р°СЂР°Р·. РЎРїСЂРѕР±СѓР№С‚Рµ /wallet РїС–Р·РЅС–С€Рµ.",
        "wallet_linked": "CherryX Р°РєР°СѓРЅС‚ РїСЂРёРІ'СЏР·Р°РЅРѕ.\nР‘Р°Р»Р°РЅСЃ: {balance} CherryX.\nР”РѕСЃС‚СѓРї: {access}.",
        "wallet_not_linked": "Telegram РїРѕРєРё РЅРµ РїСЂРёРІ'СЏР·Р°РЅРёР№ РґРѕ Р°РєР°СѓРЅС‚Р° CherryX.\nРћС‡С–РєСѓС” РїСЂРёРІ'СЏР·РєРё: {pending} CherryX.\n\nР’С–РґРєСЂРёР№С‚Рµ CherryX Pay РЅР° СЃР°Р№С‚С–, СЃРєРѕРїС–СЋР№С‚Рµ /link CODE С– РЅР°РґС–С€Р»С–С‚СЊ СЃСЋРґРё.",
        "not_active": "РЅРµРјР°С” Р°РєС‚РёРІРЅРѕРіРѕ РґРѕСЃС‚СѓРїСѓ",
        "link_missing": "РќР°РґС–С€Р»С–С‚СЊ РєРѕРјР°РЅРґСѓ Р· РєРѕРґРѕРј С–Р· CherryX Pay: /link CODE",
        "link_failed": "РќРµ РІРґР°Р»РѕСЃСЏ РїСЂРёРІ'СЏР·Р°С‚Рё Р°РєР°СѓРЅС‚. РЎРїСЂРѕР±СѓР№С‚Рµ РѕС‚СЂРёРјР°С‚Рё РЅРѕРІРёР№ РєРѕРґ Сѓ CherryX Pay.",
        "link_not_found": "РљРѕРґ РЅРµ Р·РЅР°Р№РґРµРЅРѕ Р°Р±Рѕ РІР¶Рµ РІРёРєРѕСЂРёСЃС‚Р°РЅРѕ. РћС‚СЂРёРјР°Р№С‚Рµ РЅРѕРІРёР№ РєРѕРґ Сѓ CherryX Pay С– РЅР°РґС–С€Р»С–С‚СЊ /link CODE.",
        "link_success": "Р“РѕС‚РѕРІРѕ, Telegram РїСЂРёРІ'СЏР·Р°РЅРѕ РґРѕ CherryX Р°РєР°СѓРЅС‚Р°.\nР‘Р°Р»Р°РЅСЃ: {balance} CherryX.\nРўРµРїРµСЂ РѕРїР»Р°С‚Рё Stars С‡РµСЂРµР· Р±РѕС‚Р° РїРѕС‚СЂР°РїР»СЏС‚РёРјСѓС‚СЊ Сѓ С†РµР№ Р°РєР°СѓРЅС‚.",
        "pay_support": "РџС–РґС‚СЂРёРјРєР° РѕРїР»Р°С‚ CherryX С‡РµСЂРµР· Telegram Stars.\n\nРЇРєС‰Рѕ Stars СЃРїРёСЃР°Р»РёСЃСЊ, Р°Р»Рµ РґРѕСЃС‚СѓРї Р°Р±Рѕ Р±Р°Р»Р°РЅСЃ РЅРµ Р·'СЏРІРёРІСЃСЏ: РЅР°РґС–С€Р»С–С‚СЊ СЃСЋРґРё СЃРєСЂРёРЅ РѕРїР»Р°С‚Рё, Telegram ID Р· /id С– РїСЂРёР±Р»РёР·РЅРёР№ С‡Р°СЃ РїР»Р°С‚РµР¶Сѓ.\nР”Р»СЏ РїСЂРёРІ'СЏР·РєРё Р°РєР°СѓРЅС‚Р° РІРёРєРѕСЂРёСЃС‚РѕРІСѓР№С‚Рµ /link CODE С–Р· CherryX Pay. Р”Р»СЏ РїРµСЂРµРІС–СЂРєРё Р±Р°Р»Р°РЅСЃСѓ вЂ” /wallet.",
        "topup_invalid": "РќРµРєРѕСЂРµРєС‚РЅР° СЃСѓРјР° РїРѕРїРѕРІРЅРµРЅРЅСЏ.",
        "precheckout_currency": "РћРїР»Р°С‚Р° РїСЂРёР№РјР°С”С‚СЊСЃСЏ С‚С–Р»СЊРєРё РІ Telegram Stars.",
        "precheckout_expired": "РџРѕСЃРёР»Р°РЅРЅСЏ РЅР° РѕРїР»Р°С‚Сѓ Р·Р°СЃС‚Р°СЂС–Р»Рѕ Р°Р±Рѕ РІР¶Рµ РІРёРєРѕСЂРёСЃС‚Р°РЅРµ.",
        "precheckout_amount": "РЎСѓРјР° СЂР°С…СѓРЅРєСѓ РЅРµ Р·Р±С–РіР°С”С‚СЊСЃСЏ.",
    },
    "en": {
        **BILLING_TEXT["en"],
        "pay_button": "Pay Stars",
        "status_button": "Status",
        "wallet_button": "Wallet",
        "support_button": "Support",
        "language_button": "Language",
        "mini_app": "Open CherryX",
        "payment_link_invalid": "Payment link is expired or unavailable.",
        "cancelled": "Cancelled.",
        "pro_price": "CherryX access costs {stars} Stars for {days} days.",
        "wallet_error": "Could not check wallet now. Try /wallet later.",
        "wallet_linked": "CherryX account linked.\nBalance: {balance} CherryX.\nAccess: {access}.",
        "wallet_not_linked": "Telegram is not linked to a CherryX account yet.\nPending: {pending} CherryX.\n\nOpen CherryX Pay on the website, copy /link CODE and send it here.",
        "not_active": "not active",
        "link_missing": "Send the command with the code from CherryX Pay: /link CODE",
        "link_failed": "Could not link the account. Try getting a new code in CherryX Pay.",
        "link_not_found": "Code was not found or has already been used. Get a new code in CherryX Pay and send /link CODE.",
        "link_success": "Done, Telegram is linked to your CherryX account.\nBalance: {balance} CherryX.\nStars payments through the bot will now go to this account.",
        "pay_support": "CherryX payment support via Telegram Stars.\n\nIf Stars were charged but access or balance did not appear, send a payment screenshot, Telegram ID from /id, and the approximate payment time.\nTo link an account, use /link CODE from CherryX Pay. To check balance, use /wallet.",
        "topup_invalid": "Invalid top up amount.",
        "precheckout_currency": "Payment is accepted only in Telegram Stars.",
        "precheckout_expired": "Payment link is expired or already used.",
        "precheckout_amount": "Invoice amount does not match.",
    },
    "fr": {
        **BILLING_TEXT["fr"],
        "pay_button": "Payer Stars",
        "status_button": "Statut",
        "wallet_button": "Solde",
        "support_button": "Support",
        "language_button": "Langue",
        "mini_app": "Ouvrir CherryX",
        "payment_link_invalid": "Le lien de paiement a expirГ© ou n'est pas disponible.",
        "cancelled": "AnnulГ©.",
        "pro_price": "L'accГЁs CherryX coГ»te {stars} Stars pour {days} jours.",
        "wallet_error": "Impossible de vГ©rifier le solde maintenant. RГ©essayez avec /wallet plus tard.",
        "wallet_linked": "Compte CherryX liГ©.\nSolde : {balance} CherryX.\nAccГЁs : {access}.",
        "wallet_not_linked": "Telegram n'est pas encore liГ© Г  un compte CherryX.\nEn attente : {pending} CherryX.\n\nOuvrez CherryX Pay sur le site, copiez /link CODE et envoyez-le ici.",
        "not_active": "non actif",
        "link_missing": "Envoyez la commande avec le code de CherryX Pay : /link CODE",
        "link_failed": "Impossible de lier le compte. GГ©nГ©rez un nouveau code dans CherryX Pay.",
        "link_not_found": "Code introuvable ou dГ©jГ  utilisГ©. GГ©nГ©rez un nouveau code dans CherryX Pay et envoyez /link CODE.",
        "link_success": "C'est fait, Telegram est liГ© au compte CherryX.\nSolde : {balance} CherryX.\nLes paiements Stars via le bot iront maintenant sur ce compte.",
        "pay_support": "Support des paiements CherryX via Telegram Stars.\n\nSi les Stars ont Г©tГ© dГ©bitГ©es mais que l'accГЁs ou le solde n'apparaГ®t pas, envoyez une capture du paiement, votre Telegram ID depuis /id et l'heure approximative du paiement.\nPour lier un compte, utilisez /link CODE depuis CherryX Pay. Pour vГ©rifier le solde, utilisez /wallet.",
        "topup_invalid": "Montant de recharge invalide.",
        "precheckout_currency": "Le paiement est acceptГ© uniquement en Telegram Stars.",
        "precheckout_expired": "Le lien de paiement a expirГ© ou a dГ©jГ  Г©tГ© utilisГ©.",
        "precheckout_amount": "Le montant de la facture ne correspond pas.",
    },
    "de": {
        **BILLING_TEXT["de"],
        "pay_button": "Stars zahlen",
        "status_button": "Status",
        "wallet_button": "Guthaben",
        "support_button": "Support",
        "language_button": "Sprache",
        "mini_app": "CherryX Г¶ffnen",
        "payment_link_invalid": "Der Zahlungslink ist abgelaufen oder nicht verfГјgbar.",
        "cancelled": "Abgebrochen.",
        "pro_price": "CherryX-Zugang kostet {stars} Stars fГјr {days} Tage.",
        "wallet_error": "Guthaben konnte jetzt nicht geprГјft werden. Versuchen Sie spГ¤ter /wallet.",
        "wallet_linked": "CherryX-Konto verknГјpft.\nGuthaben: {balance} CherryX.\nZugang: {access}.",
        "wallet_not_linked": "Telegram ist noch nicht mit einem CherryX-Konto verknГјpft.\nWartend: {pending} CherryX.\n\nГ–ffnen Sie CherryX Pay auf der Website, kopieren Sie /link CODE und senden Sie ihn hier.",
        "not_active": "nicht aktiv",
        "link_missing": "Senden Sie den Befehl mit dem Code aus CherryX Pay: /link CODE",
        "link_failed": "Konto konnte nicht verknГјpft werden. Holen Sie einen neuen Code in CherryX Pay.",
        "link_not_found": "Code nicht gefunden oder bereits verwendet. Holen Sie einen neuen Code in CherryX Pay und senden Sie /link CODE.",
        "link_success": "Fertig, Telegram ist mit dem CherryX-Konto verknГјpft.\nGuthaben: {balance} CherryX.\nStars-Zahlungen Гјber den Bot gehen jetzt auf dieses Konto.",
        "pay_support": "CherryX-Zahlungssupport Гјber Telegram Stars.\n\nWenn Stars abgebucht wurden, aber Zugang oder Guthaben nicht erschienen sind, senden Sie einen Zahlungs-Screenshot, Telegram ID aus /id und die ungefГ¤hre Zahlungszeit.\nZum VerknГјpfen nutzen Sie /link CODE aus CherryX Pay. Zum PrГјfen des Guthabens nutzen Sie /wallet.",
        "topup_invalid": "UngГјltiger Aufladebetrag.",
        "precheckout_currency": "Zahlung wird nur in Telegram Stars akzeptiert.",
        "precheckout_expired": "Der Zahlungslink ist abgelaufen oder bereits verwendet.",
        "precheckout_amount": "Der Rechnungsbetrag stimmt nicht Гјberein.",
    },
    "es": {
        **BILLING_TEXT["es"],
        "pay_button": "Pagar Stars",
        "status_button": "Estado",
        "wallet_button": "Saldo",
        "support_button": "Soporte",
        "language_button": "Idioma",
        "mini_app": "Abrir CherryX",
        "payment_link_invalid": "El enlace de pago expirГі o no estГЎ disponible.",
        "cancelled": "Cancelado.",
        "pro_price": "El acceso CherryX cuesta {stars} Stars por {days} dГ­as.",
        "wallet_error": "No se pudo consultar el saldo ahora. Prueba /wallet mГЎs tarde.",
        "wallet_linked": "Cuenta CherryX vinculada.\nSaldo: {balance} CherryX.\nAcceso: {access}.",
        "wallet_not_linked": "Telegram aГєn no estГЎ vinculado a una cuenta CherryX.\nPendiente: {pending} CherryX.\n\nAbre CherryX Pay en el sitio, copia /link CODE y envГ­alo aquГ­.",
        "not_active": "no activo",
        "link_missing": "EnvГ­a el comando con el cГіdigo de CherryX Pay: /link CODE",
        "link_failed": "No se pudo vincular la cuenta. Genera un cГіdigo nuevo en CherryX Pay.",
        "link_not_found": "CГіdigo no encontrado o ya usado. Genera un cГіdigo nuevo en CherryX Pay y envГ­a /link CODE.",
        "link_success": "Listo, Telegram estГЎ vinculado a la cuenta CherryX.\nSaldo: {balance} CherryX.\nLos pagos Stars desde el bot irГЎn ahora a esta cuenta.",
        "pay_support": "Soporte de pagos CherryX con Telegram Stars.\n\nSi se cobraron Stars pero no apareciГі el acceso o saldo, envГ­a una captura del pago, Telegram ID de /id y la hora aproximada del pago.\nPara vincular una cuenta, usa /link CODE desde CherryX Pay. Para revisar saldo, usa /wallet.",
        "topup_invalid": "Importe de recarga invГЎlido.",
        "precheckout_currency": "El pago solo se acepta en Telegram Stars.",
        "precheckout_expired": "El enlace de pago expirГі o ya fue usado.",
        "precheckout_amount": "El importe de la factura no coincide.",
    },
    "it": {
        **BILLING_TEXT["it"],
        "pay_button": "Paga Stars",
        "status_button": "Stato",
        "wallet_button": "Saldo",
        "support_button": "Supporto",
        "language_button": "Lingua",
        "mini_app": "Apri CherryX",
        "payment_link_invalid": "Il link di pagamento ГЁ scaduto o non disponibile.",
        "cancelled": "Annullato.",
        "pro_price": "L'accesso CherryX costa {stars} Stars per {days} giorni.",
        "wallet_error": "Impossibile controllare il saldo ora. Prova /wallet piГ№ tardi.",
        "wallet_linked": "Account CherryX collegato.\nSaldo: {balance} CherryX.\nAccesso: {access}.",
        "wallet_not_linked": "Telegram non ГЁ ancora collegato a un account CherryX.\nIn attesa: {pending} CherryX.\n\nApri CherryX Pay sul sito, copia /link CODE e invialo qui.",
        "not_active": "non attivo",
        "link_missing": "Invia il comando con il codice da CherryX Pay: /link CODE",
        "link_failed": "Impossibile collegare l'account. Genera un nuovo codice in CherryX Pay.",
        "link_not_found": "Codice non trovato o giГ  usato. Genera un nuovo codice in CherryX Pay e invia /link CODE.",
        "link_success": "Fatto, Telegram ГЁ collegato all'account CherryX.\nSaldo: {balance} CherryX.\nI pagamenti Stars tramite bot andranno ora su questo account.",
        "pay_support": "Supporto pagamenti CherryX tramite Telegram Stars.\n\nSe gli Stars sono stati addebitati ma accesso o saldo non sono apparsi, invia screenshot del pagamento, Telegram ID da /id e orario approssimativo del pagamento.\nPer collegare un account usa /link CODE da CherryX Pay. Per controllare il saldo usa /wallet.",
        "topup_invalid": "Importo di ricarica non valido.",
        "precheckout_currency": "Il pagamento ГЁ accettato solo in Telegram Stars.",
        "precheckout_expired": "Il link di pagamento ГЁ scaduto o giГ  usato.",
        "precheckout_amount": "L'importo della fattura non corrisponde.",
    },
    "ka": {
        **BILLING_TEXT["ka"],
        "pay_button": "Stars бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓђ",
        "status_button": "бѓЎбѓўбѓђбѓўбѓЈбѓЎбѓ",
        "wallet_button": "бѓ‘бѓђбѓљбѓђбѓњбѓЎбѓ",
        "support_button": "бѓ›бѓ®бѓђбѓ бѓ“бѓђбѓ­бѓ”бѓ бѓђ",
        "language_button": "бѓ”бѓњбѓђ",
        "mini_app": "CherryX-бѓбѓЎ бѓ’бѓђбѓ®бѓЎбѓњбѓђ",
        "payment_link_invalid": "бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓбѓЎ бѓ‘бѓ›бѓЈбѓљбѓ бѓ•бѓђбѓ“бѓђбѓ’бѓђбѓЎбѓЈбѓљбѓбѓђ бѓђбѓњ бѓ›бѓбѓЈбѓ¬бѓ•бѓ“бѓќбѓ›бѓ”бѓљбѓбѓђ.",
        "cancelled": "бѓ’бѓђбѓЈбѓҐбѓ›бѓ“бѓђ.",
        "pro_price": "CherryX бѓ¬бѓ•бѓ“бѓќбѓ›бѓђ бѓ¦бѓбѓ бѓЎ {stars} Stars {days} бѓ“бѓ¦бѓбѓ—.",
        "wallet_error": "бѓ‘бѓђбѓљбѓђбѓњбѓЎбѓбѓЎ бѓЁбѓ”бѓ›бѓќбѓ¬бѓ›бѓ”бѓ‘бѓђ бѓђбѓ®бѓљбѓђ бѓ•бѓ”бѓ  бѓ›бѓќбѓ®бѓ”бѓ бѓ®бѓ“бѓђ. бѓЎбѓЄбѓђбѓ“бѓ”бѓ— /wallet бѓ›бѓќбѓ’бѓ•бѓбѓђбѓњбѓ”бѓ‘бѓбѓ—.",
        "wallet_linked": "CherryX бѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓ бѓ›бѓбѓ‘бѓ›бѓЈбѓљбѓбѓђ.\nбѓ‘бѓђбѓљбѓђбѓњбѓЎбѓ: {balance} CherryX.\nбѓ¬бѓ•бѓ“бѓќбѓ›бѓђ: {access}.",
        "wallet_not_linked": "Telegram бѓЇбѓ”бѓ  бѓђбѓ  бѓђбѓ бѓбѓЎ бѓ›бѓбѓ‘бѓ›бѓЈбѓљбѓ CherryX бѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓ—бѓђбѓњ.\nбѓ›бѓќбѓљбѓќбѓ“бѓбѓњбѓЁбѓбѓђ: {pending} CherryX.\n\nбѓ’бѓђбѓ®бѓЎбѓ”бѓњбѓбѓ— CherryX Pay бѓЎбѓђбѓбѓўбѓ–бѓ”, бѓ“бѓђбѓђбѓ™бѓќбѓћбѓбѓ бѓ”бѓ— /link CODE бѓ“бѓђ бѓ’бѓђбѓ›бѓќбѓ’бѓ–бѓђбѓ•бѓњбѓ”бѓ— бѓђбѓҐ.",
        "not_active": "бѓђбѓ бѓђбѓђбѓҐбѓўбѓбѓЈбѓ бѓ",
        "link_missing": "бѓ’бѓђбѓ›бѓќбѓ’бѓ–бѓђбѓ•бѓњбѓ”бѓ— бѓ‘бѓ бѓ«бѓђбѓњбѓ”бѓ‘бѓђ CherryX Pay-бѓбѓЎ бѓ™бѓќбѓ“бѓбѓ—: /link CODE",
        "link_failed": "бѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓбѓЎ бѓ›бѓбѓ‘бѓ›бѓђ бѓ•бѓ”бѓ  бѓ›бѓќбѓ®бѓ”бѓ бѓ®бѓ“бѓђ. бѓ›бѓбѓбѓ¦бѓ”бѓ— бѓђбѓ®бѓђбѓљбѓ бѓ™бѓќбѓ“бѓ CherryX Pay-бѓЁбѓ.",
        "link_not_found": "бѓ™бѓќбѓ“бѓ бѓ•бѓ”бѓ  бѓ›бѓќбѓбѓ«бѓ”бѓ‘бѓњбѓђ бѓђбѓњ бѓЈбѓ™бѓ•бѓ” бѓ’бѓђбѓ›бѓќбѓ§бѓ”бѓњбѓ”бѓ‘бѓЈбѓљбѓбѓђ. бѓ›бѓбѓбѓ¦бѓ”бѓ— бѓђбѓ®бѓђбѓљбѓ бѓ™бѓќбѓ“бѓ CherryX Pay-бѓЁбѓ бѓ“бѓђ бѓ’бѓђбѓ›бѓќбѓ’бѓ–бѓђбѓ•бѓњбѓ”бѓ— /link CODE.",
        "link_success": "бѓ›бѓ–бѓђбѓ“бѓђбѓђ, Telegram бѓ›бѓбѓ‘бѓ›бѓЈбѓљбѓбѓђ CherryX бѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓ—бѓђбѓњ.\nбѓ‘бѓђбѓљбѓђбѓњбѓЎбѓ: {balance} CherryX.\nStars бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓ”бѓ‘бѓ бѓ‘бѓќбѓўбѓбѓ“бѓђбѓњ бѓђбѓ®бѓљбѓђ бѓђбѓ› бѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓ–бѓ” бѓ©бѓђбѓбѓ бѓбѓЄбѓ®бѓ”бѓ‘бѓђ.",
        "pay_support": "CherryX бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓ”бѓ‘бѓбѓЎ бѓ›бѓ®бѓђбѓ бѓ“бѓђбѓ­бѓ”бѓ бѓђ Telegram Stars-бѓбѓ—.\n\nбѓ—бѓЈ Stars бѓ©бѓђбѓ›бѓќбѓбѓ­бѓ бѓђ, бѓ›бѓђбѓ’бѓ бѓђбѓ› бѓ¬бѓ•бѓ“бѓќбѓ›бѓђ бѓђбѓњ бѓ‘бѓђбѓљбѓђбѓњбѓЎбѓ бѓђбѓ  бѓ’бѓђбѓ›бѓќбѓ©бѓњбѓ“бѓђ, бѓ’бѓђбѓ›бѓќбѓ’бѓ–бѓђбѓ•бѓњбѓ”бѓ— бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓбѓЎ бѓЎбѓҐбѓ бѓбѓњбѓ, Telegram ID /id-бѓ“бѓђбѓњ бѓ“бѓђ бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓбѓЎ бѓЎбѓђбѓ•бѓђбѓ бѓђбѓЈбѓ“бѓќ бѓ“бѓ бѓќ.\nбѓђбѓњбѓ’бѓђбѓ бѓбѓЁбѓбѓЎ бѓ›бѓбѓЎбѓђбѓ‘бѓ›бѓ”бѓљбѓђбѓ“ бѓ’бѓђбѓ›бѓќбѓбѓ§бѓ”бѓњбѓ”бѓ— /link CODE CherryX Pay-бѓ“бѓђбѓњ. бѓ‘бѓђбѓљбѓђбѓњбѓЎбѓбѓЎ бѓЁбѓ”бѓЎбѓђбѓ›бѓќбѓ¬бѓ›бѓ”бѓ‘бѓљбѓђбѓ“ бѓ’бѓђбѓ›бѓќбѓбѓ§бѓ”бѓњбѓ”бѓ— /wallet.",
        "topup_invalid": "бѓЁбѓ”бѓ•бѓЎбѓ”бѓ‘бѓбѓЎ бѓ—бѓђбѓњбѓ®бѓђ бѓђбѓ бѓђбѓЎбѓ¬бѓќбѓ бѓбѓђ.",
        "precheckout_currency": "бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓђ бѓ›бѓбѓбѓ¦бѓ”бѓ‘бѓђ бѓ›бѓ®бѓќбѓљбѓќбѓ“ Telegram Stars-бѓбѓ—.",
        "precheckout_expired": "бѓ’бѓђбѓ“бѓђбѓ®бѓ“бѓбѓЎ бѓ‘бѓ›бѓЈбѓљбѓ бѓ•бѓђбѓ“бѓђбѓ’бѓђбѓЎбѓЈбѓљбѓбѓђ бѓђбѓњ бѓЈбѓ™бѓ•бѓ” бѓ’бѓђбѓ›бѓќбѓ§бѓ”бѓњбѓ”бѓ‘бѓЈбѓљбѓбѓђ.",
        "precheckout_amount": "бѓбѓњбѓ•бѓќбѓбѓЎбѓбѓЎ бѓ—бѓђбѓњбѓ®бѓђ бѓђбѓ  бѓ”бѓ›бѓ—бѓ®бѓ•бѓ”бѓ•бѓђ.",
    },
    "hy": {
        **BILLING_TEXT["hy"],
        "pay_button": "ХЋХіХЎЦЂХҐХ¬ Stars",
        "status_button": "ФїХЎЦЂХЈХЎХѕХ«ХіХЎХЇ",
        "wallet_button": "ФІХЎХ¬ХЎХ¶ХЅ",
        "support_button": "Ф±Х»ХЎХЇЦЃХёЦ‚Х©ХµХёЦ‚Х¶",
        "language_button": "ФјХҐХ¦ХёЦ‚",
        "mini_app": "ФІХЎЦЃХҐХ¬ CherryX-ХЁ",
        "payment_link_invalid": "ХЋХіХЎЦЂХґХЎХ¶ Х°ХІХёЦ‚ХґХЁ ХЄХЎХґХЇХҐХїХЎХ¶ЦЃ Х§ ХЇХЎХґ ХЎХ¶Х°ХЎХЅХЎХ¶ХҐХ¬Х«Ц‰",
        "cancelled": "Х‰ХҐХІХЎЦЂХЇХѕХЎХ® Х§Ц‰",
        "pro_price": "CherryX Х°ХЎХЅХЎХ¶ХҐХ¬Х«ХёЦ‚Х©ХµХёЦ‚Х¶ХЁ ХЎЦЂХЄХҐ {stars} Stars {days} Ц…ЦЂХёХѕЦ‰",
        "wallet_error": "Х‰Х°ХЎХ»ХёХІХѕХҐЦЃ ХЅХїХёЦ‚ХЈХҐХ¬ ХўХЎХ¬ХЎХ¶ХЅХЁ Х°Х«ХґХЎЦ‰ Х“ХёЦЂХ±ХҐЦ„ /wallet ХЎХѕХҐХ¬Х« ХёЦ‚Х·Ц‰",
        "wallet_linked": "CherryX Х°ХЎХ·Х«ХѕХЁ ХЇХЎХєХѕХЎХ® Х§Ц‰\nФІХЎХ¬ХЎХ¶ХЅХќ {balance} CherryXЦ‰\nХЂХЎХЅХЎХ¶ХҐХ¬Х«ХёЦ‚Х©ХµХёЦ‚Х¶Хќ {access}Ц‰",
        "wallet_not_linked": "Telegram-ХЁ Х¤ХҐХј ХЇХЎХєХѕХЎХ® Х№Х§ CherryX Х°ХЎХ·ХѕХ« Х°ХҐХїЦ‰\nХЌХєХЎХЅХёЦ‚Хґ Х§Хќ {pending} CherryXЦ‰\n\nФІХЎЦЃХҐЦ„ CherryX Pay-ХЁ ХЇХЎХµЦ„ХёЦ‚Хґ, ХєХЎХїХіХҐХ¶ХҐЦ„ /link CODE Ц‡ ХёЦ‚ХІХЎЦЂХЇХҐЦ„ ХЎХµХЅХїХҐХІЦ‰",
        "not_active": "ХЎХЇХїХ«Хѕ Х№Х§",
        "link_missing": "Х€Ц‚ХІХЎЦЂХЇХҐЦ„ Х°ЦЂХЎХґХЎХ¶ХЁ CherryX Pay-Х« ХЇХёХ¤ХёХѕХќ /link CODE",
        "link_failed": "Х‰Х°ХЎХ»ХёХІХѕХҐЦЃ ХЇХЎХєХҐХ¬ Х°ХЎХ·Х«ХѕХЁЦ‰ ХЌХїХЎЦЃХҐЦ„ Х¶ХёЦЂ ХЇХёХ¤ CherryX Pay-ХёЦ‚ХґЦ‰",
        "link_not_found": "ФїХёХ¤ХЁ Х№Х« ХЈХїХ¶ХѕХҐХ¬ ХЇХЎХґ ХЎЦЂХ¤ХҐХ¶ Ц…ХЈХїХЎХЈХёЦЂХ®ХѕХҐХ¬ Х§Ц‰ ХЌХїХЎЦЃХҐЦ„ Х¶ХёЦЂ ХЇХёХ¤ CherryX Pay-ХёЦ‚Хґ Ц‡ ХёЦ‚ХІХЎЦЂХЇХҐЦ„ /link CODEЦ‰",
        "link_success": "ХЉХЎХїЦЂХЎХЅХї Х§, Telegram-ХЁ ХЇХЎХєХѕХЎХ® Х§ CherryX Х°ХЎХ·ХѕХ« Х°ХҐХїЦ‰\nФІХЎХ¬ХЎХ¶ХЅХќ {balance} CherryXЦ‰\nBot-Х« Stars ХѕХіХЎЦЂХёЦ‚ХґХ¶ХҐЦЂХЁ ХЎХµХЄХґ ХЇХЈХ¶ХЎХ¶ ХЎХµХЅ Х°ХЎХ·ХѕХ«Х¶Ц‰",
        "pay_support": "CherryX ХѕХіХЎЦЂХёЦ‚ХґХ¶ХҐЦЂХ« ХЎХ»ХЎХЇЦЃХёЦ‚Х©ХµХёЦ‚Х¶ Telegram Stars-ХёХѕЦ‰\n\nФµХ©ХҐ Stars-ХЁ ХЈХЎХ¶Х±ХѕХҐХ¬ Х§, ХўХЎХµЦЃ Х°ХЎХЅХЎХ¶ХҐХ¬Х«ХёЦ‚Х©ХµХёЦ‚Х¶ХЁ ХЇХЎХґ ХўХЎХ¬ХЎХ¶ХЅХЁ Х№Х« Х°ХЎХµХїХ¶ХѕХҐХ¬, ХёЦ‚ХІХЎЦЂХЇХҐЦ„ ХѕХіХЎЦЂХґХЎХ¶ ХЅЦ„ЦЂХ«Х¶ХЁ, Telegram ID-Х¶ /id-Х«ЦЃ Ц‡ ХѕХіХЎЦЂХґХЎХ¶ ХґХёХїХЎХѕХёЦЂ ХЄХЎХґХЁЦ‰\nХЂХЎХ·Х«Хѕ ХЇХЎХєХҐХ¬ХёЦ‚ Х°ХЎХґХЎЦЂ Ц…ХЈХїХЎХЈХёЦЂХ®ХҐЦ„ /link CODE CherryX Pay-Х«ЦЃЦ‰ ФІХЎХ¬ХЎХ¶ХЅХЁ ХЅХїХёЦ‚ХЈХҐХ¬ХёЦ‚ Х°ХЎХґХЎЦЂХќ /walletЦ‰",
        "topup_invalid": "ХЂХЎХґХЎХ¬ЦЂХґХЎХ¶ ХЈХёЦ‚ХґХЎЦЂХЁ ХЅХ­ХЎХ¬ Х§Ц‰",
        "precheckout_currency": "ХЋХіХЎЦЂХёЦ‚ХґХ¶ ХЁХ¶Х¤ХёЦ‚Х¶ХѕХёЦ‚Хґ Х§ ХґХ«ХЎХµХ¶ Telegram Stars-ХёХѕЦ‰",
        "precheckout_expired": "ХЋХіХЎЦЂХґХЎХ¶ Х°ХІХёЦ‚ХґХЁ ХЄХЎХґХЇХҐХїХЎХ¶ЦЃ Х§ ХЇХЎХґ ХЎЦЂХ¤ХҐХ¶ Ц…ХЈХїХЎХЈХёЦЂХ®ХѕХҐХ¬ Х§Ц‰",
        "precheckout_amount": "Ф»Х¶ХѕХёХµХЅХ« ХЈХёЦ‚ХґХЎЦЂХЁ Х№Х« Х°ХЎХґХЁХ¶ХЇХ¶ХёЦ‚ХґЦ‰",
    },
})


BILLING_TEXT.update({
    "ru": {
        **BILLING_TEXT["ru"],
        "pay_button": "Оплатить Stars",
        "status_button": "Статус",
        "wallet_button": "Баланс",
        "support_button": "Поддержка",
        "language_button": "Язык",
        "mini_app": "Открыть CherryX",
        "payment_link_invalid": "Ссылка на оплату устарела или недоступна.",
        "cancelled": "Ок, отменил.",
        "pro_price": "Доступ CherryX стоит {stars} Stars на {days} дней.",
        "wallet_error": "Не смог проверить баланс сейчас. Попробуйте /wallet позже.",
        "wallet_linked": "CherryX аккаунт привязан.\nБаланс: {balance} CherryX.\nДоступ: {access}.",
        "wallet_not_linked": "Telegram пока не привязан к аккаунту CherryX.\nОжидает привязки: {pending} CherryX.\n\nОткройте CherryX Pay на сайте, скопируйте /link CODE и отправьте сюда.",
        "not_active": "нет активного доступа",
        "link_missing": "Отправьте команду с кодом из CherryX Pay: /link CODE",
        "link_failed": "Не получилось привязать аккаунт. Попробуйте получить новый код в CherryX Pay.",
        "link_not_found": "Код не найден или уже использован. Получите новый код в CherryX Pay и отправьте /link CODE.",
        "link_success": "Готово, Telegram привязан к CherryX аккаунту.\nБаланс: {balance} CherryX.\nТеперь оплаты Stars через бота будут попадать в этот аккаунт.",
        "pay_support": "Поддержка оплат CherryX через Telegram Stars.\n\nЕсли Stars списались, но доступ или баланс не появился: отправьте сюда скрин оплаты, Telegram ID из /id и примерное время платежа.\nДля привязки аккаунта используйте /link CODE из CherryX Pay. Для проверки баланса — /wallet.",
        "topup_invalid": "Некорректная сумма пополнения.",
        "precheckout_currency": "Оплата принимается только в Telegram Stars.",
        "precheckout_expired": "Ссылка на оплату устарела или уже использована.",
        "precheckout_amount": "Сумма счета не совпадает.",
    },
    "uk": {
        **BILLING_TEXT["uk"],
        "pay_button": "Оплатити Stars",
        "status_button": "Статус",
        "wallet_button": "Баланс",
        "support_button": "Підтримка",
        "language_button": "Мова",
        "mini_app": "Відкрити CherryX",
        "payment_link_invalid": "Посилання на оплату застаріло або недоступне.",
        "cancelled": "Ок, скасовано.",
        "pro_price": "Доступ CherryX коштує {stars} Stars на {days} днів.",
        "wallet_error": "Не вдалося перевірити баланс зараз. Спробуйте /wallet пізніше.",
        "wallet_linked": "CherryX акаунт прив'язано.\nБаланс: {balance} CherryX.\nДоступ: {access}.",
        "wallet_not_linked": "Telegram поки не прив'язаний до акаунта CherryX.\nОчікує прив'язки: {pending} CherryX.\n\nВідкрийте CherryX Pay на сайті, скопіюйте /link CODE і надішліть сюди.",
        "not_active": "немає активного доступу",
        "link_missing": "Надішліть команду з кодом із CherryX Pay: /link CODE",
        "link_failed": "Не вдалося прив'язати акаунт. Спробуйте отримати новий код у CherryX Pay.",
        "link_not_found": "Код не знайдено або вже використано. Отримайте новий код у CherryX Pay і надішліть /link CODE.",
        "link_success": "Готово, Telegram прив'язано до CherryX акаунта.\nБаланс: {balance} CherryX.\nТепер оплати Stars через бота потраплятимуть у цей акаунт.",
        "pay_support": "Підтримка оплат CherryX через Telegram Stars.\n\nЯкщо Stars списались, але доступ або баланс не з'явився: надішліть сюди скрин оплати, Telegram ID з /id і приблизний час платежу.\nДля прив'язки акаунта використовуйте /link CODE із CherryX Pay. Для перевірки балансу — /wallet.",
        "topup_invalid": "Некоректна сума поповнення.",
        "precheckout_currency": "Оплата приймається тільки в Telegram Stars.",
        "precheckout_expired": "Посилання на оплату застаріло або вже використане.",
        "precheckout_amount": "Сума рахунку не збігається.",
    },
    "en": {
        **BILLING_TEXT["en"],
        "pay_button": "Pay Stars",
        "status_button": "Status",
        "wallet_button": "Wallet",
        "support_button": "Support",
        "language_button": "Language",
        "mini_app": "Open CherryX",
        "payment_link_invalid": "Payment link is expired or unavailable.",
        "cancelled": "Cancelled.",
        "pro_price": "CherryX access costs {stars} Stars for {days} days.",
        "wallet_error": "Could not check wallet now. Try /wallet later.",
        "wallet_linked": "CherryX account linked.\nBalance: {balance} CherryX.\nAccess: {access}.",
        "wallet_not_linked": "Telegram is not linked to a CherryX account yet.\nPending: {pending} CherryX.\n\nOpen CherryX Pay on the website, copy /link CODE and send it here.",
        "not_active": "not active",
        "link_missing": "Send the command with the code from CherryX Pay: /link CODE",
        "link_failed": "Could not link the account. Try getting a new code in CherryX Pay.",
        "link_not_found": "Code was not found or has already been used. Get a new code in CherryX Pay and send /link CODE.",
        "link_success": "Done, Telegram is linked to your CherryX account.\nBalance: {balance} CherryX.\nStars payments through the bot will now go to this account.",
        "pay_support": "CherryX payment support via Telegram Stars.\n\nIf Stars were charged but access or balance did not appear, send a payment screenshot, Telegram ID from /id, and the approximate payment time.\nTo link an account, use /link CODE from CherryX Pay. To check balance, use /wallet.",
        "topup_invalid": "Invalid top up amount.",
        "precheckout_currency": "Payment is accepted only in Telegram Stars.",
        "precheckout_expired": "Payment link is expired or already used.",
        "precheckout_amount": "Invoice amount does not match.",
    },
    "fr": {
        **BILLING_TEXT["fr"],
        "pay_button": "Payer Stars",
        "status_button": "Statut",
        "wallet_button": "Solde",
        "support_button": "Support",
        "language_button": "Langue",
        "mini_app": "Ouvrir CherryX",
        "payment_link_invalid": "Le lien de paiement a expiré ou n'est pas disponible.",
        "cancelled": "Annulé.",
        "pro_price": "L'accès CherryX coûte {stars} Stars pour {days} jours.",
        "wallet_error": "Impossible de vérifier le solde maintenant. Réessayez avec /wallet plus tard.",
        "wallet_linked": "Compte CherryX lié.\nSolde : {balance} CherryX.\nAccès : {access}.",
        "wallet_not_linked": "Telegram n'est pas encore lié à un compte CherryX.\nEn attente : {pending} CherryX.\n\nOuvrez CherryX Pay sur le site, copiez /link CODE et envoyez-le ici.",
        "not_active": "non actif",
        "link_missing": "Envoyez la commande avec le code de CherryX Pay : /link CODE",
        "link_failed": "Impossible de lier le compte. Générez un nouveau code dans CherryX Pay.",
        "link_not_found": "Code introuvable ou déjà utilisé. Générez un nouveau code dans CherryX Pay et envoyez /link CODE.",
        "link_success": "C'est fait, Telegram est lié au compte CherryX.\nSolde : {balance} CherryX.\nLes paiements Stars via le bot iront maintenant sur ce compte.",
        "pay_support": "Support des paiements CherryX via Telegram Stars.\n\nSi les Stars ont été débitées mais que l'accès ou le solde n'apparaît pas, envoyez une capture du paiement, votre Telegram ID depuis /id et l'heure approximative du paiement.\nPour lier un compte, utilisez /link CODE depuis CherryX Pay. Pour vérifier le solde, utilisez /wallet.",
        "topup_invalid": "Montant de recharge invalide.",
        "precheckout_currency": "Le paiement est accepté uniquement en Telegram Stars.",
        "precheckout_expired": "Le lien de paiement a expiré ou a déjà été utilisé.",
        "precheckout_amount": "Le montant de la facture ne correspond pas.",
    },
    "de": {
        **BILLING_TEXT["de"],
        "pay_button": "Stars zahlen",
        "status_button": "Status",
        "wallet_button": "Guthaben",
        "support_button": "Support",
        "language_button": "Sprache",
        "mini_app": "CherryX öffnen",
        "payment_link_invalid": "Der Zahlungslink ist abgelaufen oder nicht verfügbar.",
        "cancelled": "Abgebrochen.",
        "pro_price": "CherryX-Zugang kostet {stars} Stars für {days} Tage.",
        "wallet_error": "Guthaben konnte jetzt nicht geprüft werden. Versuchen Sie später /wallet.",
        "wallet_linked": "CherryX-Konto verknüpft.\nGuthaben: {balance} CherryX.\nZugang: {access}.",
        "wallet_not_linked": "Telegram ist noch nicht mit einem CherryX-Konto verknüpft.\nWartend: {pending} CherryX.\n\nÖffnen Sie CherryX Pay auf der Website, kopieren Sie /link CODE und senden Sie ihn hier.",
        "not_active": "nicht aktiv",
        "link_missing": "Senden Sie den Befehl mit dem Code aus CherryX Pay: /link CODE",
        "link_failed": "Konto konnte nicht verknüpft werden. Holen Sie einen neuen Code in CherryX Pay.",
        "link_not_found": "Code nicht gefunden oder bereits verwendet. Holen Sie einen neuen Code in CherryX Pay und senden Sie /link CODE.",
        "link_success": "Fertig, Telegram ist mit dem CherryX-Konto verknüpft.\nGuthaben: {balance} CherryX.\nStars-Zahlungen über den Bot gehen jetzt auf dieses Konto.",
        "pay_support": "CherryX-Zahlungssupport über Telegram Stars.\n\nWenn Stars abgebucht wurden, aber Zugang oder Guthaben nicht erschienen sind, senden Sie einen Zahlungs-Screenshot, Telegram ID aus /id und die ungefähre Zahlungszeit.\nZum Verknüpfen nutzen Sie /link CODE aus CherryX Pay. Zum Prüfen des Guthabens nutzen Sie /wallet.",
        "topup_invalid": "Ungültiger Aufladebetrag.",
        "precheckout_currency": "Zahlung wird nur in Telegram Stars akzeptiert.",
        "precheckout_expired": "Der Zahlungslink ist abgelaufen oder bereits verwendet.",
        "precheckout_amount": "Der Rechnungsbetrag stimmt nicht überein.",
    },
    "es": {
        **BILLING_TEXT["es"],
        "pay_button": "Pagar Stars",
        "status_button": "Estado",
        "wallet_button": "Saldo",
        "support_button": "Soporte",
        "language_button": "Idioma",
        "mini_app": "Abrir CherryX",
        "payment_link_invalid": "El enlace de pago expiró o no está disponible.",
        "cancelled": "Cancelado.",
        "pro_price": "El acceso CherryX cuesta {stars} Stars por {days} días.",
        "wallet_error": "No se pudo consultar el saldo ahora. Prueba /wallet más tarde.",
        "wallet_linked": "Cuenta CherryX vinculada.\nSaldo: {balance} CherryX.\nAcceso: {access}.",
        "wallet_not_linked": "Telegram aún no está vinculado a una cuenta CherryX.\nPendiente: {pending} CherryX.\n\nAbre CherryX Pay en el sitio, copia /link CODE y envíalo aquí.",
        "not_active": "no activo",
        "link_missing": "Envía el comando con el código de CherryX Pay: /link CODE",
        "link_failed": "No se pudo vincular la cuenta. Genera un código nuevo en CherryX Pay.",
        "link_not_found": "Código no encontrado o ya usado. Genera un código nuevo en CherryX Pay y envía /link CODE.",
        "link_success": "Listo, Telegram está vinculado a la cuenta CherryX.\nSaldo: {balance} CherryX.\nLos pagos Stars desde el bot irán ahora a esta cuenta.",
        "pay_support": "Soporte de pagos CherryX con Telegram Stars.\n\nSi se cobraron Stars pero no apareció el acceso o saldo, envía una captura del pago, Telegram ID de /id y la hora aproximada del pago.\nPara vincular una cuenta, usa /link CODE desde CherryX Pay. Para revisar saldo, usa /wallet.",
        "topup_invalid": "Importe de recarga inválido.",
        "precheckout_currency": "El pago solo se acepta en Telegram Stars.",
        "precheckout_expired": "El enlace de pago expiró o ya fue usado.",
        "precheckout_amount": "El importe de la factura no coincide.",
    },
    "it": {
        **BILLING_TEXT["it"],
        "pay_button": "Paga Stars",
        "status_button": "Stato",
        "wallet_button": "Saldo",
        "support_button": "Supporto",
        "language_button": "Lingua",
        "mini_app": "Apri CherryX",
        "payment_link_invalid": "Il link di pagamento è scaduto o non disponibile.",
        "cancelled": "Annullato.",
        "pro_price": "L'accesso CherryX costa {stars} Stars per {days} giorni.",
        "wallet_error": "Impossibile controllare il saldo ora. Prova /wallet più tardi.",
        "wallet_linked": "Account CherryX collegato.\nSaldo: {balance} CherryX.\nAccesso: {access}.",
        "wallet_not_linked": "Telegram non è ancora collegato a un account CherryX.\nIn attesa: {pending} CherryX.\n\nApri CherryX Pay sul sito, copia /link CODE e invialo qui.",
        "not_active": "non attivo",
        "link_missing": "Invia il comando con il codice da CherryX Pay: /link CODE",
        "link_failed": "Impossibile collegare l'account. Genera un nuovo codice in CherryX Pay.",
        "link_not_found": "Codice non trovato o già usato. Genera un nuovo codice in CherryX Pay e invia /link CODE.",
        "link_success": "Fatto, Telegram è collegato all'account CherryX.\nSaldo: {balance} CherryX.\nI pagamenti Stars tramite bot andranno ora su questo account.",
        "pay_support": "Supporto pagamenti CherryX tramite Telegram Stars.\n\nSe gli Stars sono stati addebitati ma accesso o saldo non sono apparsi, invia screenshot del pagamento, Telegram ID da /id e orario approssimativo del pagamento.\nPer collegare un account usa /link CODE da CherryX Pay. Per controllare il saldo usa /wallet.",
        "topup_invalid": "Importo di ricarica non valido.",
        "precheckout_currency": "Il pagamento è accettato solo in Telegram Stars.",
        "precheckout_expired": "Il link di pagamento è scaduto o già usato.",
        "precheckout_amount": "L'importo della fattura non corrisponde.",
    },
    "ka": {
        **BILLING_TEXT["ka"],
        "pay_button": "Stars გადახდა",
        "status_button": "სტატუსი",
        "wallet_button": "ბალანსი",
        "support_button": "მხარდაჭერა",
        "language_button": "ენა",
        "mini_app": "CherryX-ის გახსნა",
        "payment_link_invalid": "გადახდის ბმული ვადაგასულია ან მიუწვდომელია.",
        "cancelled": "გაუქმდა.",
        "pro_price": "CherryX წვდომა ღირს {stars} Stars {days} დღით.",
        "wallet_error": "ბალანსის შემოწმება ახლა ვერ მოხერხდა. სცადეთ /wallet მოგვიანებით.",
        "wallet_linked": "CherryX ანგარიში მიბმულია.\nბალანსი: {balance} CherryX.\nწვდომა: {access}.",
        "wallet_not_linked": "Telegram ჯერ არ არის მიბმული CherryX ანგარიშთან.\nმოლოდინშია: {pending} CherryX.\n\nგახსენით CherryX Pay საიტზე, დააკოპირეთ /link CODE და გამოგზავნეთ აქ.",
        "not_active": "არააქტიური",
        "link_missing": "გამოგზავნეთ ბრძანება CherryX Pay-ის კოდით: /link CODE",
        "link_failed": "ანგარიშის მიბმა ვერ მოხერხდა. მიიღეთ ახალი კოდი CherryX Pay-ში.",
        "link_not_found": "კოდი ვერ მოიძებნა ან უკვე გამოყენებულია. მიიღეთ ახალი კოდი CherryX Pay-ში და გამოგზავნეთ /link CODE.",
        "link_success": "მზადაა, Telegram მიბმულია CherryX ანგარიშთან.\nბალანსი: {balance} CherryX.\nStars გადახდები ბოტიდან ახლა ამ ანგარიშზე ჩაირიცხება.",
        "pay_support": "CherryX გადახდების მხარდაჭერა Telegram Stars-ით.\n\nთუ Stars ჩამოიჭრა, მაგრამ წვდომა ან ბალანსი არ გამოჩნდა, გამოგზავნეთ გადახდის სქრინი, Telegram ID /id-დან და გადახდის სავარაუდო დრო.\nანგარიშის მისაბმელად გამოიყენეთ /link CODE CherryX Pay-დან. ბალანსის შესამოწმებლად გამოიყენეთ /wallet.",
        "topup_invalid": "შევსების თანხა არასწორია.",
        "precheckout_currency": "გადახდა მიიღება მხოლოდ Telegram Stars-ით.",
        "precheckout_expired": "გადახდის ბმული ვადაგასულია ან უკვე გამოყენებულია.",
        "precheckout_amount": "ინვოისის თანხა არ ემთხვევა.",
    },
    "hy": {
        **BILLING_TEXT["hy"],
        "pay_button": "Վճարել Stars",
        "status_button": "Կարգավիճակ",
        "wallet_button": "Բալանս",
        "support_button": "Աջակցություն",
        "language_button": "Լեզու",
        "mini_app": "Բացել CherryX-ը",
        "payment_link_invalid": "Վճարման հղումը ժամկետանց է կամ անհասանելի։",
        "cancelled": "Չեղարկված է։",
        "pro_price": "CherryX հասանելիությունը արժե {stars} Stars {days} օրով։",
        "wallet_error": "Չհաջողվեց ստուգել բալանսը հիմա։ Փորձեք /wallet ավելի ուշ։",
        "wallet_linked": "CherryX հաշիվը կապված է։\nԲալանս՝ {balance} CherryX։\nՀասանելիություն՝ {access}։",
        "wallet_not_linked": "Telegram-ը դեռ կապված չէ CherryX հաշվի հետ։\nՍպասում է՝ {pending} CherryX։\n\nԲացեք CherryX Pay-ը կայքում, պատճենեք /link CODE և ուղարկեք այստեղ։",
        "not_active": "ակտիվ չէ",
        "link_missing": "Ուղարկեք հրամանը CherryX Pay-ի կոդով՝ /link CODE",
        "link_failed": "Չհաջողվեց կապել հաշիվը։ Ստացեք նոր կոդ CherryX Pay-ում։",
        "link_not_found": "Կոդը չի գտնվել կամ արդեն օգտագործվել է։ Ստացեք նոր կոդ CherryX Pay-ում և ուղարկեք /link CODE։",
        "link_success": "Պատրաստ է, Telegram-ը կապված է CherryX հաշվի հետ։\nԲալանս՝ {balance} CherryX։\nBot-ի Stars վճարումները այժմ կգնան այս հաշվին։",
        "pay_support": "CherryX վճարումների աջակցություն Telegram Stars-ով։\n\nԵթե Stars-ը գանձվել է, բայց հասանելիությունը կամ բալանսը չի հայտնվել, ուղարկեք վճարման սքրինը, Telegram ID-ն /id-ից և վճարման մոտավոր ժամը։\nՀաշիվ կապելու համար օգտագործեք /link CODE CherryX Pay-ից։ Բալանսը ստուգելու համար՝ /wallet։",
        "topup_invalid": "Համալրման գումարը սխալ է։",
        "precheckout_currency": "Վճարումն ընդունվում է միայն Telegram Stars-ով։",
        "precheckout_expired": "Վճարման հղումը ժամկետանց է կամ արդեն օգտագործվել է։",
        "precheckout_amount": "Ինվոյսի գումարը չի համընկնում։",
    },
})


BILLING_TEXT.update({
    "ru": {
        **BILLING_TEXT["ru"],
        "intro": "CherryX Pay бот\n\nЗдесь можно оплатить пакет, пополнить баланс и проверить аккаунт.\n\n/link CODE - привязать аккаунт сайта\n/status - статус доступа\n/wallet - баланс CherryX\n/paysupport - помощь с оплатой",
        "help": "Этот бот работает для оплат CherryX и мониторинга аккаунта.\n\n/subscribe - оплата через Telegram Stars\n/status - статус доступа\n/wallet - баланс и привязка\n/link CODE - привязать аккаунт сайта\n/paysupport - помощь с оплатой\n/id - Telegram ID",
        "only": "Бот принимает оплаты и показывает статус CherryX. Используйте /subscribe, /status, /wallet или /paysupport.",
        "choose": "Выберите пакет или пополнение баланса:",
        "topup": "Пополнить баланс",
        "enter_stars": "Введите сумму пополнения в Telegram Stars.\nМинимум: 1 Star. Максимум: 150000 Stars.\nНа баланс CherryX придет сумма по текущему курсу.",
        "invalid_stars": "Введите целое число Stars от 1 до 150000.",
        "stars_range": "Сумма должна быть от 1 до 150000 Telegram Stars.",
        "invoice": "{title}\n{description}\n\nК оплате: {stars} Telegram Stars.",
        "intent_error": "Оплата получена, но не смог применить ее к аккаунту. Напишите /paysupport.",
        "need_email": "Оплата получена.\nОтправьте email, и я создам CherryX аккаунт, применю пакет или баланс и пришлю данные для входа.",
        "applied": "Оплата прошла и применена.\n{title}\nCherryX: {cherryx}",
        "account_created": "CherryX аккаунт создан, оплата применена.\n\nЛогин: {email}\nПароль: {password}\nСсылка для входа: {login_url}\n\nПосле первого входа смените пароль.",
        "open_cherryx": "Открыть CherryX",
        "email_exists": "Такой email уже есть в CherryX.\nВойдите на сайте, откройте CherryX Pay, скопируйте /link CODE и отправьте сюда. Оплата будет ждать привязки.",
        "email_invalid": "Отправьте корректный email.",
    },
    "uk": {
        **BILLING_TEXT["uk"],
        "intro": "CherryX Pay бот\n\nТут можна оплатити пакет, поповнити баланс і перевірити акаунт.\n\n/link CODE - прив'язати акаунт сайту\n/status - статус доступу\n/wallet - баланс CherryX\n/paysupport - допомога з оплатою",
        "help": "Цей бот працює для оплат CherryX і моніторингу акаунта.\n\n/subscribe - оплата через Telegram Stars\n/status - статус доступу\n/wallet - баланс і прив'язка\n/link CODE - прив'язати акаунт сайту\n/paysupport - допомога з оплатою\n/id - Telegram ID",
        "only": "Бот приймає оплати і показує статус CherryX. Використовуйте /subscribe, /status, /wallet або /paysupport.",
        "choose": "Оберіть пакет або поповнення балансу:",
        "topup": "Поповнити баланс",
        "enter_stars": "Введіть суму поповнення в Telegram Stars.\nМінімум: 1 Star. Максимум: 150000 Stars.\nНа баланс CherryX прийде сума за поточним курсом.",
        "invalid_stars": "Введіть ціле число Stars від 1 до 150000.",
        "stars_range": "Сума має бути від 1 до 150000 Telegram Stars.",
        "invoice": "{title}\n{description}\n\nДо оплати: {stars} Telegram Stars.",
        "intent_error": "Оплату отримано, але не вдалося застосувати її до акаунта. Напишіть /paysupport.",
        "need_email": "Оплату отримано.\nНадішліть email, і я створю CherryX акаунт, застосую пакет або баланс і надішлю дані для входу.",
        "applied": "Оплату проведено і застосовано.\n{title}\nCherryX: {cherryx}",
        "account_created": "CherryX акаунт створено, оплату застосовано.\n\nЛогін: {email}\nПароль: {password}\nПосилання для входу: {login_url}\n\nПісля першого входу змініть пароль.",
        "open_cherryx": "Відкрити CherryX",
        "email_exists": "Такий email уже є в CherryX.\nУвійдіть на сайті, відкрийте CherryX Pay, скопіюйте /link CODE і надішліть сюди. Оплата чекатиме прив'язки.",
        "email_invalid": "Надішліть коректний email.",
    },
    "en": {
        **BILLING_TEXT["en"],
        "intro": "CherryX Pay bot\n\nPay for a package, top up balance, and monitor your account.\n\n/link CODE - link website account\n/status - access status\n/wallet - CherryX balance\n/paysupport - payment help",
        "help": "This bot is used for CherryX payments and account monitoring.\n\n/subscribe - pay with Telegram Stars\n/status - access status\n/wallet - CherryX balance and linked account\n/link CODE - link Telegram with the website account\n/paysupport - payment support\n/id - Telegram ID",
        "only": "This bot accepts payments and monitors CherryX access. Use /subscribe, /status, /wallet or /paysupport.",
        "choose": "Choose a package or top up balance:",
        "topup": "Top up balance",
        "enter_stars": "Enter the top up amount in Telegram Stars.\nMinimum: 1 Star. Maximum: 150000 Stars.\nCherryX will be credited by the current rate.",
        "invalid_stars": "Enter a whole Stars amount from 1 to 150000.",
        "stars_range": "Amount must be from 1 to 150000 Telegram Stars.",
        "invoice": "{title}\n{description}\n\nTo pay: {stars} Telegram Stars.",
        "intent_error": "Payment was received, but it could not be applied. Please contact /paysupport.",
        "need_email": "Payment received.\nSend your email and I will create your CherryX account, apply the package or balance, and send login details.",
        "applied": "Payment received and applied.\n{title}\nCherryX: {cherryx}",
        "account_created": "CherryX account created and payment applied.\n\nLogin: {email}\nPassword: {password}\nLogin URL: {login_url}\n\nChange the password after first login.",
        "open_cherryx": "Open CherryX",
        "email_exists": "This email already exists on CherryX.\nLog in on the website, open CherryX Pay, copy /link CODE and send it here. The paid intent will wait for linking.",
        "email_invalid": "Please send a valid email address.",
    },
    "fr": {
        **BILLING_TEXT["fr"],
        "intro": "Bot CherryX Pay\n\nPayez un forfait, rechargez le solde et vérifiez votre compte.\n\n/link CODE - lier le compte du site\n/status - statut d'accès\n/wallet - solde CherryX\n/paysupport - aide au paiement",
        "help": "Ce bot sert aux paiements CherryX et au suivi du compte.\n\n/subscribe - payer avec Telegram Stars\n/status - statut d'accès\n/wallet - solde et compte lié\n/link CODE - lier le compte du site\n/paysupport - support paiement\n/id - Telegram ID",
        "only": "Ce bot accepte les paiements et montre le statut CherryX. Utilisez /subscribe, /status, /wallet ou /paysupport.",
        "choose": "Choisissez un forfait ou rechargez le solde :",
        "topup": "Recharger le solde",
        "enter_stars": "Entrez le montant en Telegram Stars.\nMinimum : 1 Star. Maximum : 150000 Stars.\nCherryX sera crédité selon le taux actuel.",
        "invalid_stars": "Entrez un nombre entier de Stars entre 1 et 150000.",
        "stars_range": "Le montant doit être entre 1 et 150000 Telegram Stars.",
        "invoice": "{title}\n{description}\n\nÀ payer : {stars} Telegram Stars.",
        "intent_error": "Paiement reçu, mais impossible de l'appliquer. Contactez /paysupport.",
        "need_email": "Paiement reçu.\nEnvoyez votre email et je créerai votre compte CherryX, puis j'appliquerai le forfait ou le solde.",
        "applied": "Paiement reçu et appliqué.\n{title}\nCherryX : {cherryx}",
        "account_created": "Compte CherryX créé, paiement appliqué.\n\nLogin : {email}\nMot de passe : {password}\nURL de connexion : {login_url}\n\nChangez le mot de passe après la première connexion.",
        "open_cherryx": "Ouvrir CherryX",
        "email_exists": "Cet email existe déjà sur CherryX.\nConnectez-vous au site, ouvrez CherryX Pay, copiez /link CODE et envoyez-le ici. Le paiement attendra la liaison.",
        "email_invalid": "Envoyez une adresse email valide.",
    },
    "de": {
        **BILLING_TEXT["de"],
        "intro": "CherryX Pay Bot\n\nPaket bezahlen, Guthaben aufladen und Konto prüfen.\n\n/link CODE - Website-Konto verknüpfen\n/status - Zugriffsstatus\n/wallet - CherryX Guthaben\n/paysupport - Zahlungshilfe",
        "help": "Dieser Bot ist für CherryX-Zahlungen und Kontostatus.\n\n/subscribe - mit Telegram Stars zahlen\n/status - Zugriffsstatus\n/wallet - Guthaben und Verknüpfung\n/link CODE - Website-Konto verknüpfen\n/paysupport - Zahlungssupport\n/id - Telegram ID",
        "only": "Dieser Bot akzeptiert Zahlungen und zeigt den CherryX-Status. Nutzen Sie /subscribe, /status, /wallet oder /paysupport.",
        "choose": "Paket wählen oder Guthaben aufladen:",
        "topup": "Guthaben aufladen",
        "enter_stars": "Geben Sie den Betrag in Telegram Stars ein.\nMinimum: 1 Star. Maximum: 150000 Stars.\nCherryX wird zum aktuellen Kurs gutgeschrieben.",
        "invalid_stars": "Geben Sie eine ganze Stars-Zahl von 1 bis 150000 ein.",
        "stars_range": "Der Betrag muss zwischen 1 und 150000 Telegram Stars liegen.",
        "invoice": "{title}\n{description}\n\nZu zahlen: {stars} Telegram Stars.",
        "intent_error": "Zahlung erhalten, konnte aber nicht angewendet werden. Kontaktieren Sie /paysupport.",
        "need_email": "Zahlung erhalten.\nSenden Sie Ihre E-Mail, dann erstelle ich Ihr CherryX-Konto und wende Paket oder Guthaben an.",
        "applied": "Zahlung erhalten und angewendet.\n{title}\nCherryX: {cherryx}",
        "account_created": "CherryX-Konto erstellt, Zahlung angewendet.\n\nLogin: {email}\nPasswort: {password}\nLogin-URL: {login_url}\n\nÄndern Sie das Passwort nach dem ersten Login.",
        "open_cherryx": "CherryX öffnen",
        "email_exists": "Diese E-Mail existiert bereits auf CherryX.\nMelden Sie sich auf der Website an, öffnen Sie CherryX Pay, kopieren Sie /link CODE und senden Sie ihn hier.",
        "email_invalid": "Bitte senden Sie eine gültige E-Mail-Adresse.",
    },
    "es": {
        **BILLING_TEXT["es"],
        "intro": "Bot CherryX Pay\n\nPaga un paquete, recarga saldo y revisa tu cuenta.\n\n/link CODE - vincular cuenta web\n/status - estado de acceso\n/wallet - saldo CherryX\n/paysupport - ayuda con pagos",
        "help": "Este bot sirve para pagos CherryX y monitoreo de cuenta.\n\n/subscribe - pagar con Telegram Stars\n/status - estado de acceso\n/wallet - saldo y cuenta vinculada\n/link CODE - vincular cuenta web\n/paysupport - soporte de pagos\n/id - Telegram ID",
        "only": "Este bot acepta pagos y muestra el estado CherryX. Usa /subscribe, /status, /wallet o /paysupport.",
        "choose": "Elige un paquete o recarga saldo:",
        "topup": "Recargar saldo",
        "enter_stars": "Introduce el importe en Telegram Stars.\nMínimo: 1 Star. Máximo: 150000 Stars.\nCherryX se acreditará según el tipo actual.",
        "invalid_stars": "Introduce un número entero de Stars entre 1 y 150000.",
        "stars_range": "El importe debe estar entre 1 y 150000 Telegram Stars.",
        "invoice": "{title}\n{description}\n\nA pagar: {stars} Telegram Stars.",
        "intent_error": "Pago recibido, pero no se pudo aplicar. Contacta /paysupport.",
        "need_email": "Pago recibido.\nEnvía tu email y crearé tu cuenta CherryX, aplicando el paquete o saldo.",
        "applied": "Pago recibido y aplicado.\n{title}\nCherryX: {cherryx}",
        "account_created": "Cuenta CherryX creada, pago aplicado.\n\nLogin: {email}\nContraseña: {password}\nURL de acceso: {login_url}\n\nCambia la contraseña después del primer acceso.",
        "open_cherryx": "Abrir CherryX",
        "email_exists": "Este email ya existe en CherryX.\nInicia sesión en el sitio, abre CherryX Pay, copia /link CODE y envíalo aquí.",
        "email_invalid": "Envía un email válido.",
    },
    "it": {
        **BILLING_TEXT["it"],
        "intro": "Bot CherryX Pay\n\nPaga un pacchetto, ricarica il saldo e controlla l'account.\n\n/link CODE - collega account web\n/status - stato accesso\n/wallet - saldo CherryX\n/paysupport - supporto pagamenti",
        "help": "Questo bot serve per pagamenti CherryX e monitoraggio account.\n\n/subscribe - paga con Telegram Stars\n/status - stato accesso\n/wallet - saldo e account collegato\n/link CODE - collega account web\n/paysupport - supporto pagamenti\n/id - Telegram ID",
        "only": "Questo bot accetta pagamenti e mostra lo stato CherryX. Usa /subscribe, /status, /wallet o /paysupport.",
        "choose": "Scegli un pacchetto o ricarica il saldo:",
        "topup": "Ricarica saldo",
        "enter_stars": "Inserisci l'importo in Telegram Stars.\nMinimo: 1 Star. Massimo: 150000 Stars.\nCherryX verrà accreditato al tasso attuale.",
        "invalid_stars": "Inserisci un numero intero di Stars da 1 a 150000.",
        "stars_range": "L'importo deve essere tra 1 e 150000 Telegram Stars.",
        "invoice": "{title}\n{description}\n\nDa pagare: {stars} Telegram Stars.",
        "intent_error": "Pagamento ricevuto, ma non è stato possibile applicarlo. Contatta /paysupport.",
        "need_email": "Pagamento ricevuto.\nInvia la tua email e creerò l'account CherryX, applicando pacchetto o saldo.",
        "applied": "Pagamento ricevuto e applicato.\n{title}\nCherryX: {cherryx}",
        "account_created": "Account CherryX creato, pagamento applicato.\n\nLogin: {email}\nPassword: {password}\nURL login: {login_url}\n\nCambia la password dopo il primo accesso.",
        "open_cherryx": "Apri CherryX",
        "email_exists": "Questa email esiste già su CherryX.\nAccedi al sito, apri CherryX Pay, copia /link CODE e invialo qui.",
        "email_invalid": "Invia un indirizzo email valido.",
    },
    "ka": {
        **BILLING_TEXT["ka"],
        "intro": "CherryX Pay ბოტი\n\nაქ შეგიძლიათ პაკეტის გადახდა, ბალანსის შევსება და ანგარიშის შემოწმება.\n\n/link CODE - საიტის ანგარიშის მიბმა\n/status - წვდომის სტატუსი\n/wallet - CherryX ბალანსი\n/paysupport - გადახდის დახმარება",
        "help": "ეს ბოტი მუშაობს CherryX გადახდებისთვის და ანგარიშის მონიტორინგისთვის.\n\n/subscribe - გადახდა Telegram Stars-ით\n/status - წვდომის სტატუსი\n/wallet - ბალანსი და მიბმა\n/link CODE - საიტის ანგარიშის მიბმა\n/paysupport - გადახდის დახმარება\n/id - Telegram ID",
        "only": "ბოტი იღებს გადახდებს და აჩვენებს CherryX სტატუსს. გამოიყენეთ /subscribe, /status, /wallet ან /paysupport.",
        "choose": "აირჩიეთ პაკეტი ან ბალანსის შევსება:",
        "topup": "ბალანსის შევსება",
        "enter_stars": "შეიყვანეთ თანხა Telegram Stars-ში.\nმინიმუმი: 1 Star. მაქსიმუმი: 150000 Stars.\nCherryX ჩაირიცხება მიმდინარე კურსით.",
        "invalid_stars": "შეიყვანეთ მთელი რიცხვი 1-დან 150000 Stars-მდე.",
        "stars_range": "თანხა უნდა იყოს 1-დან 150000 Telegram Stars-მდე.",
        "invoice": "{title}\n{description}\n\nგადასახდელი: {stars} Telegram Stars.",
        "intent_error": "გადახდა მიღებულია, მაგრამ ანგარიშზე გამოყენება ვერ მოხერხდა. დაწერეთ /paysupport.",
        "need_email": "გადახდა მიღებულია.\nგამოგზავნეთ email და შევქმნი CherryX ანგარიშს, მივაბამ პაკეტს ან ბალანსს.",
        "applied": "გადახდა მიღებულია და გამოყენებულია.\n{title}\nCherryX: {cherryx}",
        "account_created": "CherryX ანგარიში შეიქმნა და გადახდა გამოყენებულია.\n\nLogin: {email}\nPassword: {password}\nLogin URL: {login_url}\n\nპირველი შესვლის შემდეგ შეცვალეთ პაროლი.",
        "open_cherryx": "CherryX-ის გახსნა",
        "email_exists": "ეს email უკვე არსებობს CherryX-ში.\nშედით საიტზე, გახსენით CherryX Pay, დააკოპირეთ /link CODE და გამოგზავნეთ აქ.",
        "email_invalid": "გთხოვთ, გამოგზავნოთ სწორი email.",
    },
    "hy": {
        **BILLING_TEXT["hy"],
        "intro": "CherryX Pay բոտ\n\nԱյստեղ կարող եք վճարել փաթեթի համար, համալրել բալանսը և ստուգել հաշիվը։\n\n/link CODE - կապել կայքի հաշիվը\n/status - հասանելիության կարգավիճակ\n/wallet - CherryX բալանս\n/paysupport - վճարման օգնություն",
        "help": "Այս բոտը CherryX վճարումների և հաշվի մոնիթորինգի համար է։\n\n/subscribe - վճարել Telegram Stars-ով\n/status - հասանելիության կարգավիճակ\n/wallet - բալանս և կապում\n/link CODE - կապել կայքի հաշիվը\n/paysupport - վճարման աջակցություն\n/id - Telegram ID",
        "only": "Բոտը ընդունում է վճարումներ և ցույց է տալիս CherryX կարգավիճակը։ Օգտագործեք /subscribe, /status, /wallet կամ /paysupport։",
        "choose": "Ընտրեք փաթեթ կամ բալանսի համալրում.",
        "topup": "Համալրել բալանսը",
        "enter_stars": "Մուտքագրեք համալրման գումարը Telegram Stars-ով։\nՆվազագույնը՝ 1 Star։ Առավելագույնը՝ 150000 Stars։\nCherryX-ը կավելացվի ընթացիկ փոխարժեքով։",
        "invalid_stars": "Մուտքագրեք ամբողջ թիվ 1-ից 150000 Stars միջակայքում։",
        "stars_range": "Գումարը պետք է լինի 1-ից 150000 Telegram Stars։",
        "invoice": "{title}\n{description}\n\nՎճարման ենթակա՝ {stars} Telegram Stars։",
        "intent_error": "Վճարումը ստացվել է, բայց չհաջողվեց կիրառել այն հաշվին։ Գրեք /paysupport։",
        "need_email": "Վճարումը ստացվել է։\nՈւղարկեք email-ը, և ես կստեղծեմ CherryX հաշիվ, կկիրառեմ փաթեթը կամ բալանսը։",
        "applied": "Վճարումը ստացվել և կիրառվել է։\n{title}\nCherryX: {cherryx}",
        "account_created": "CherryX հաշիվը ստեղծվել է, վճարումը կիրառվել է։\n\nLogin: {email}\nPassword: {password}\nLogin URL: {login_url}\n\nԱռաջին մուտքից հետո փոխեք գաղտնաբառը։",
        "open_cherryx": "Բացել CherryX-ը",
        "email_exists": "Այս email-ը արդեն կա CherryX-ում։\nՄուտք գործեք կայքում, բացեք CherryX Pay-ը, պատճենեք /link CODE և ուղարկեք այստեղ։",
        "email_invalid": "Խնդրում ենք ուղարկել ճիշտ email։",
    },
})


def billing_text(lang: str, key: str, **kwargs: object) -> str:
    template = BILLING_TEXT.get(lang, BILLING_TEXT["en"]).get(key, BILLING_TEXT["en"].get(key, key))
    return template.format(**kwargs)


def billing_intro_text(lang: str = "en") -> str:
    return billing_text(lang, "intro")


def billing_help_text(lang: str = "en") -> str:
    return billing_text(lang, "help")


def billing_only_text(lang: str = "en") -> str:
    return billing_text(lang, "only")


def billing_direct_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Start - 100 CherryX", callback_data="tgplan:free"),
            InlineKeyboardButton(text="Starter - 900", callback_data="tgplan:starter"),
        ],
        [
            InlineKeyboardButton(text="Creator Pro - 1900", callback_data="tgplan:pro"),
            InlineKeyboardButton(text="Studio - 4900", callback_data="tgplan:studio"),
        ],
        [
            InlineKeyboardButton(text=billing_text(lang, "topup"), callback_data="tgtopup:custom"),
        ],
    ])


def open_cherryx_keyboard(url: str, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=billing_text(lang, "open_cherryx"), url=url)]
    ])


async def send_intent_invoice(message: Message, bot: Bot, intent: dict[str, object]) -> None:
    await message.answer(
        billing_text(
            user_lang(message),
            "invoice",
            title=intent.get("title") or "CherryX",
            description=intent.get("description") or "CherryX payment",
            stars=intent.get("stars_amount") or 1,
        )
    )
    await bot(
        SendInvoice(
            chat_id=message.chat.id,
            title=str(intent.get("title") or "CherryX"),
            description=str(intent.get("description") or "CherryX payment"),
            payload=str(intent.get("payload") or ""),
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=str(intent.get("title") or "CherryX"), amount=int(intent.get("stars_amount") or 1))],
        )
    )


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
        f"{feature} РґРѕСЃС‚СѓРїРЅРѕ РїРѕСЃР»Рµ РѕРїР»Р°С‚С‹ Stars.\n\n"
        "Р•СЃР»Рё РІР°С€ Telegram ID РґРѕР±Р°РІР»РµРЅ РІ FREE_USER_IDS РІ .env, РґРѕСЃС‚СѓРї Р±СѓРґРµС‚ Р±РµСЃРїР»Р°С‚РЅС‹Рј Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё."
        + next_steps_text("РЅР°Р¶РјРё РѕРїР»Р°С‚Сѓ РЅРёР¶Рµ", "РёР»Рё РЅР°РїРёС€Рё /id Рё РґРѕР±Р°РІСЊ ID РІ FREE_USER_IDS", lang=lang),
        reply_markup=main_menu(lang),
    )
    return False


async def ensure_action_allowed(message: Message, user_id: int, action: str, detail: str = "") -> bool:
    paid_only_features = {
        "image": "РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РёР·РѕР±СЂР°Р¶РµРЅРёР№",
        "video": "РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РІРёРґРµРѕ",
        "resume": "PDF-СЂРµР·СЋРјРµ",
        "cover": "PNG-РѕР±Р»РѕР¶РєРё",
        "youtube": "YouTube-РјРѕРЅС‚Р°Р¶",
        "subtitles": "РђРІС‚РѕСЃСѓР±С‚РёС‚СЂС‹",
        "package": "РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё ZIP",
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
        "image": "РєРѕРЅРІРµСЂС‚Р°С†РёР№ РёР·РѕР±СЂР°Р¶РµРЅРёР№",
        "video": "РєРѕРЅРІРµСЂС‚Р°С†РёР№ РІРёРґРµРѕ",
        "resume": "PDF-СЂРµР·СЋРјРµ",
        "cover": "РѕР±Р»РѕР¶РµРє",
        "youtube": "YouTube-РјРѕРЅС‚Р°Р¶РµР№",
        "subtitles": "СЃСѓР±С‚РёС‚СЂРѕРІ",
        "package": "РїР°РєРµС‚РѕРІ РїСѓР±Р»РёРєР°С†РёРё",
    }
    feature = labels.get(action, "РѕР±СЂР°Р±РѕС‚РѕРє")
    limit_text = f"{used}/{limit}" if limit else "0"
    lines = [
        f"Free-Р»РёРјРёС‚ РЅР° СЃРµРіРѕРґРЅСЏ РёСЃС‡РµСЂРїР°РЅ: {limit_text} {feature}.",
        "Pro РѕС‚РєСЂС‹РІР°РµС‚ РїРѕР»РЅС‹Р№ РЅР°Р±РѕСЂ: YouTube, СЃСѓР±С‚РёС‚СЂС‹, РѕР±Р»РѕР¶РєРё, РїР°РєРµС‚С‹ РїСѓР±Р»РёРєР°С†РёРё Рё Р±РѕР»СЊС€Рµ РѕР±СЂР°Р±РѕС‚РѕРє.",
    ]
    if detail:
        lines.append(detail)
    lines.append(next_steps_text("РЅР°Р¶РјРё РѕРїР»Р°С‚Сѓ РЅРёР¶Рµ", "РёР»Рё РІРµСЂРЅРёСЃСЊ Р·Р°РІС‚СЂР° Рє Free-Р»РёРјРёС‚Сѓ"))
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
async def start(message: Message, bot: Bot) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    if billing_bot_mode():
        arg = (message.text or "").split(maxsplit=1)[1].strip() if len((message.text or "").split(maxsplit=1)) > 1 else ""
        if arg.startswith("pay_") and message.from_user:
            token = arg[4:]
            intent = await asyncio.to_thread(
                claim_payment_intent,
                token,
                message.from_user.id,
                message.from_user.username or "",
                message.from_user.first_name or "",
                getattr(message.from_user, "language_code", "") or "",
            )
            if not intent.get("ok"):
                await message.answer(billing_text(lang, "payment_link_invalid"), reply_markup=billing_direct_keyboard(lang))
                return
            await send_intent_invoice(message, bot, intent)
            return
        await message.answer(billing_intro_text(lang), reply_markup=persistent_menu_keyboard(lang))
        await message.answer(billing_text(lang, "choose"), reply_markup=billing_direct_keyboard(lang))
        return
    await message.answer(
        tr(
            lang,
            "start",
            shorts=settings.youtube_max_shorts,
            stars=settings.subscription_stars,
            days=settings.subscription_days,
        )
        + next_steps_text(
            "РѕС‚РїСЂР°РІСЊ РєР°СЂС‚РёРЅРєСѓ РёР»Рё РІРёРґРµРѕ РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†РёРё",
            "РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ Shorts РёР»Рё Preview",
            "РїРѕСЃР»Рµ СЂРµР·СѓР»СЊС‚Р°С‚Р° РЅР°Р¶РёРјР°Р№ Subtitles РёР»Рё Redo, РµСЃР»Рё РЅСѓР¶РЅРѕ РїСЂРѕРґРѕР»Р¶РёС‚СЊ РѕР±СЂР°Р±РѕС‚РєСѓ",
            lang=lang,
        ),
        reply_markup=persistent_menu_keyboard(lang),
    )
    await message.answer(tr(lang, "quick_actions"), reply_markup=main_menu(lang))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    if billing_bot_mode():
        await message.answer(billing_help_text(lang), reply_markup=main_menu(lang))
        return
    await message.answer(
        tr(lang, "help_menu")
        + next_steps_text(
            "РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†РёРё",
            "РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°",
            "РїРѕСЃР»Рµ РіРѕС‚РѕРІРѕРіРѕ MP4 РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ СЃСѓР±С‚РёС‚СЂС‹",
            lang=lang,
        ),
        reply_markup=help_navigation_keyboard(lang),
    )


@router.message(Command("id"))
async def id_command(message: Message) -> None:
    await ensure_user(message)
    if message.from_user:
        lang = user_lang(message)
        if billing_bot_mode():
            await message.answer(f"Telegram ID: {message.from_user.id}")
            return
        await message.answer(
            tr(lang, "id", user_id=message.from_user.id)
            + next_steps_text("РёСЃРїРѕР»СЊР·СѓР№ СЌС‚РѕС‚ ID РґР»СЏ СЃРїРёСЃРєР° Р±РµСЃРїР»Р°С‚РЅРѕРіРѕ РґРѕСЃС‚СѓРїР°", "РёР»Рё РѕС‚РїСЂР°РІСЊ С„Р°Р№Р»/СЃСЃС‹Р»РєСѓ РґР»СЏ РѕР±СЂР°Р±РѕС‚РєРё", lang=lang)
        )


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    await state.clear()
    if billing_bot_mode():
        await message.answer(billing_text(lang, "cancelled"), reply_markup=main_menu(lang))
        return
    await message.answer(
        tr(lang, "cancelled")
        + next_steps_text("РѕС‚РїСЂР°РІСЊ РЅРѕРІС‹Р№ С„Р°Р№Р»", "РёР»Рё РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°", lang=lang)
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
    if not billing_bot_mode() and message.from_user and is_free_user(message.from_user.id):
        await message.answer(
            tr(lang, "free_access")
            + next_steps_text("РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†РёРё", "РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°", lang=lang)
        )
        return
    await send_subscription_invoice(message, bot)


@router.message(Command("pro"))
async def pro_command(message: Message) -> None:
    await ensure_user(message)
    lang = user_lang(message)
    if billing_bot_mode():
        await message.answer(
            billing_text(lang, "pro_price", stars=settings.subscription_stars, days=settings.subscription_days),
            reply_markup=main_menu(lang),
        )
        return
    await message.answer(
        tr(lang, "help_pro", days=settings.subscription_days),
        reply_markup=help_navigation_keyboard(lang),
    )


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    await ensure_user(message)
    await send_status(message)


@router.message(Command("wallet"))
async def wallet_command(message: Message) -> None:
    await ensure_user(message)
    if not message.from_user:
        return
    lang = user_lang(message)
    try:
        wallet = await asyncio.to_thread(telegram_wallet, message.from_user.id)
    except Exception:
        logger.exception("Telegram wallet lookup failed for %s", message.from_user.id)
        await message.answer(billing_text(lang, "wallet_error"))
        return
    if wallet.get("linked"):
        active_until = wallet.get("active_until")
        until_text = active_until.strftime("%Y-%m-%d %H:%M UTC") if active_until else billing_text(lang, "not_active")
        await message.answer(
            billing_text(lang, "wallet_linked", balance=wallet.get("balance", 0), access=until_text),
            reply_markup=main_menu(lang),
        )
    else:
        pending = int(wallet.get("pending_cherryx") or 0)
        await message.answer(
            billing_text(lang, "wallet_not_linked", pending=pending),
            reply_markup=main_menu(lang),
        )

@router.message(Command("link"))
async def link_command(message: Message) -> None:
    await ensure_user(message)
    if not message.from_user:
        return
    lang = user_lang(message)
    token = (message.text or "").split(maxsplit=1)[1].strip() if len((message.text or "").split(maxsplit=1)) > 1 else ""
    if not token:
        await message.answer(billing_text(lang, "link_missing"))
        return
    try:
        result = await asyncio.to_thread(
            link_telegram_account,
            token,
            message.from_user.id,
            message.from_user.username or "",
            message.from_user.first_name or "",
        )
    except Exception:
        logger.exception("Telegram account link failed for %s", message.from_user.id)
        await message.answer(billing_text(lang, "link_failed"))
        return
    if not result.get("ok"):
        await message.answer(billing_text(lang, "link_not_found"))
        return
    await message.answer(
        billing_text(lang, "link_success", balance=result.get("balance", 0)),
        reply_markup=main_menu(lang),
    )

@router.message(Command("paysupport"))
async def pay_support_command(message: Message) -> None:
    await ensure_user(message)
    await message.answer(billing_text(user_lang(message), "pay_support"), reply_markup=main_menu(user_lang(message)))

@router.message(Command("admin_stats"))
async def admin_stats_command(message: Message) -> None:
    await ensure_user(message)
    if not is_admin_user(message.from_user.id if message.from_user else None):
        return
    stats = await db.bot_stats()
    await message.answer(
        "Bot stats\n"
        f"Users: {stats['users']}\n"
        f"Active local subscriptions: {stats['active']}\n"
        f"Stars payments: {stats['payments']}\n"
        f"Stars total: {stats['stars']}"
    )


@router.message(Command("broadcast"))
async def broadcast_command(message: Message, bot: Bot) -> None:
    await ensure_user(message)
    if not is_admin_user(message.from_user.id if message.from_user else None):
        return
    text = (message.text or "").split(maxsplit=1)[1].strip() if len((message.text or "").split(maxsplit=1)) > 1 else ""
    if not text:
        await message.answer("Usage: /broadcast message text")
        return
    user_ids = await db.all_user_ids()
    sent = 0
    failed = 0
    status = await message.answer(f"Broadcast started. Users: {len(user_ids)}")
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await safe_edit(status, f"Broadcast finished.\nSent: {sent}\nFailed: {failed}")


@router.message(Command("history"))
async def history_command(message: Message) -> None:
    await ensure_user(message)
    if billing_bot_mode():
        if not message.from_user:
            return
        payments = await db.recent_payments(message.from_user.id, 10)
        if not payments:
            await message.answer("No Stars payments yet.", reply_markup=main_menu(user_lang(message)))
            return
        lines = ["Recent Stars payments:"]
        for payment in payments:
            created = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(payment.created_at))
            lines.append(f"- {created}: {payment.total_amount} {payment.currency}")
        await message.answer("\n".join(lines))
        return
    await send_history(message)


@router.message(Command("resume"))
async def resume_command(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    if not message.from_user:
        return
    if not await ensure_pro_feature(message, message.from_user.id, "PDF-СЂРµР·СЋРјРµ"):
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
        "РЎСЃС‹Р»РєРё: LinkedIn, GitHub, Behance, РїРѕСЂС‚С„РѕР»РёРѕ, СЃР°Р№С‚ РёР»Рё Telegram-РєР°РЅР°Р». РњРѕР¶РЅРѕ РїСЂРѕРїСѓСЃС‚РёС‚СЊ.",
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
            await message.answer(f"Р¤РѕС‚Рѕ СЃР»РёС€РєРѕРј Р±РѕР»СЊС€РѕРµ. Р›РёРјРёС‚: {settings.max_image_mb} MB.")
            return
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id
        original_name = message.document.file_name or original_name
        if message.document.file_size and message.document.file_size > max_size_bytes("image"):
            await message.answer(f"РљР°СЂС‚РёРЅРєР° СЃР»РёС€РєРѕРј Р±РѕР»СЊС€Р°СЏ. Р›РёРјРёС‚: {settings.max_image_mb} MB.")
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
    "name": "РРјСЏ",
    "position": "Р”РѕР»Р¶РЅРѕСЃС‚СЊ",
    "contact": "РљРѕРЅС‚Р°РєС‚С‹",
    "links": "РЎСЃС‹Р»РєРё",
    "summary": "Рћ СЃРµР±Рµ",
    "experience": "РћРїС‹С‚",
    "education": "РћР±СЂР°Р·РѕРІР°РЅРёРµ",
    "skills": "РќР°РІС‹РєРё",
    "achievements": "Р”РѕСЃС‚РёР¶РµРЅРёСЏ",
    "additional": "Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ",
}


RESUME_FIELD_HINTS = {
    "name": "Р’РІРµРґРёС‚Рµ РёРјСЏ Рё С„Р°РјРёР»РёСЋ.",
    "position": "Р’РІРµРґРёС‚Рµ Р¶РµР»Р°РµРјСѓСЋ РґРѕР»Р¶РЅРѕСЃС‚СЊ РёР»Рё СЂРѕР»СЊ.",
    "contact": "Р’РІРµРґРёС‚Рµ РєРѕРЅС‚Р°РєС‚С‹: С‚РµР»РµС„РѕРЅ, email, Telegram, LinkedIn, РіРѕСЂРѕРґ.",
    "links": "Р’РІРµРґРёС‚Рµ СЃСЃС‹Р»РєРё: LinkedIn, GitHub, РїРѕСЂС‚С„РѕР»РёРѕ, СЃР°Р№С‚, Behance РёР»Рё Telegram-РєР°РЅР°Р». Р•СЃР»Рё СЃСЃС‹Р»РѕРє РЅРµС‚, РЅР°РїРёС€РёС‚Рµ В«РЅРµС‚В».",
    "summary": "Р’РІРµРґРёС‚Рµ РєРѕСЂРѕС‚РєРёР№ РїСЂРѕС„РµСЃСЃРёРѕРЅР°Р»СЊРЅС‹Р№ РїСЂРѕС„РёР»СЊ РЅР° 1-3 РїСЂРµРґР»РѕР¶РµРЅРёСЏ.",
    "experience": "Р’РІРµРґРёС‚Рµ РѕРїС‹С‚. РњРѕР¶РЅРѕ СЃ РїРµСЂРµРЅРѕСЃР°РјРё СЃС‚СЂРѕРє Рё СЃРїРёСЃРєР°РјРё С‡РµСЂРµР· РґРµС„РёСЃ.",
    "education": "Р’РІРµРґРёС‚Рµ РѕР±СЂР°Р·РѕРІР°РЅРёРµ, РєСѓСЂСЃС‹ РёР»Рё СЃРµСЂС‚РёС„РёРєР°С‚С‹.",
    "skills": "Р’РІРµРґРёС‚Рµ РЅР°РІС‹РєРё С‡РµСЂРµР· Р·Р°РїСЏС‚СѓСЋ.",
    "achievements": "Р’РІРµРґРёС‚Рµ РґРѕСЃС‚РёР¶РµРЅРёСЏ/РїСЂРѕРµРєС‚С‹ РёР»Рё РЅР°РїРёС€РёС‚Рµ В«РЅРµС‚В».",
    "additional": "Р’РІРµРґРёС‚Рµ СЏР·С‹РєРё, РёРЅСЃС‚СЂСѓРјРµРЅС‚С‹, РґРµС‚Р°Р»Рё РёР»Рё РЅР°РїРёС€РёС‚Рµ В«РЅРµС‚В».",
}


def resume_clip(value: str, limit: int = 260) -> str:
    return utils_resume_clip(value, limit)


def resume_review_text(data: dict) -> str:
    prepared = resume_section_data(data)
    rows = ["РџСЂРѕРІРµСЂСЊС‚Рµ СЂРµР·СЋРјРµ РїРµСЂРµРґ PDF:\n"]
    for key, label in RESUME_FIELD_LABELS.items():
        value = prepared.get(key) or "РЅРµ СѓРєР°Р·Р°РЅРѕ"
        rows.append(f"<b>{label}:</b> {escape(resume_clip(value), quote=False)}")
    rows.append(f"<b>Р¤РѕС‚Рѕ:</b> {'РґРѕР±Р°РІР»РµРЅРѕ' if data.get('photo_path') else 'Р±РµР· С„РѕС‚Рѕ'}")
    rows.append("\nРњРѕР¶РЅРѕ РѕС‚СЂРµРґР°РєС‚РёСЂРѕРІР°С‚СЊ Р»СЋР±РѕР№ Р±Р»РѕРє РёР»Рё СЃСЂР°Р·Сѓ РІС‹Р±СЂР°С‚СЊ С€Р°Р±Р»РѕРЅ.")
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
    await callback.answer("РЎС‚СЂСѓРєС‚СѓСЂСѓ РїСЂРёРІРµР» РІ РїРѕСЂСЏРґРѕРє")
    await show_resume_review(callback.message, state)


@router.callback_query(ResumeState.waiting_review, F.data == "resume_remove_photo")
async def resume_remove_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Р¤РѕС‚Рѕ СѓР±СЂР°РЅРѕ")
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
            f"Р РµРґР°РєС‚РёСЂСѓРµРј: {RESUME_FIELD_LABELS[field]}.\n"
            f"{RESUME_FIELD_HINTS[field]}\n\n"
            f"РЎРµР№С‡Р°СЃ:\n{current or 'РїСѓСЃС‚Рѕ'}"
        )


@router.message(ResumeState.waiting_edit_value)
async def resume_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("edit_field")
    if field not in RESUME_FIELD_LABELS:
        await show_resume_review(message, state)
        return
    await state.update_data(**{field: message.text or "", "edit_field": ""})
    await message.answer("РћР±РЅРѕРІРёР» Р±Р»РѕРє.")
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
            caption="РџСЂРёРјРµСЂРЅРѕ С‚Р°Рє РѕС‚Р»РёС‡Р°СЋС‚СЃСЏ С€Р°Р±Р»РѕРЅС‹ РїРѕ СЂР°СЃРїРѕР»РѕР¶РµРЅРёСЋ Р±Р»РѕРєРѕРІ. РќРёР¶Рµ РІС‹Р±РµСЂРёС‚Рµ РЅРѕРјРµСЂ.",
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
    await callback.answer("Р“РѕС‚РѕРІРѕ")
    await state.clear()
    if callback.message:
        await callback.message.answer("РћРє, РјР°СЃС‚РµСЂ СЂРµР·СЋРјРµ Р·Р°РєСЂС‹С‚. Р”Р»СЏ РЅРѕРІРѕРіРѕ СЂРµР·СЋРјРµ РёСЃРїРѕР»СЊР·СѓР№С‚Рµ /resume.")


@router.callback_query(ResumeState.waiting_template, F.data.startswith("template_"))
async def resume_template(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer("Р“РѕС‚РѕРІР»СЋ PDF...")
    template = callback.data.split("_")[1]
    data = await state.get_data()
    await state.update_data(last_template=template)
    pdf_path: Path | None = None
    try:
        pdf_path = await generate_resume_pdf(data, template)
        await bot.send_document(
            callback.from_user.id,
            FSInputFile(pdf_path),
            caption="Р’Р°С€Рµ СЂРµР·СЋРјРµ РіРѕС‚РѕРІРѕ. РњРѕР¶РЅРѕ СЃСЂР°Р·Сѓ СЃРѕР±СЂР°С‚СЊ РґСЂСѓРіРѕР№ С€Р°Р±Р»РѕРЅ РёР»Рё РѕС‚СЂРµРґР°РєС‚РёСЂРѕРІР°С‚СЊ РґР°РЅРЅС‹Рµ.",
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
            await callback.message.answer(f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ СЃРѕР±СЂР°С‚СЊ PDF-СЂРµР·СЋРјРµ: {exc}")
    finally:
        if pdf_path:
            pdf_path.unlink(missing_ok=True)


@router.message(StateFilter(None), F.text.in_({"РЎС‚Р°С‚СѓСЃ", "Status"}))
async def status_button(message: Message) -> None:
    await ensure_user(message)
    await send_status(message)


@router.message(StateFilter(None), F.text.in_({"РџРѕРјРѕС‰СЊ", "Help", "Р”РѕРїРѕРјРѕРіР°"}))
async def help_button(message: Message) -> None:
    await help_command(message)


@router.message(StateFilter(None), F.text.in_({"РСЃС‚РѕСЂРёСЏ", "History", "Р†СЃС‚РѕСЂС–СЏ"}))
async def history_button(message: Message) -> None:
    await history_command(message)


@router.message(StateFilter(None), F.text.in_({"РЇР·С‹Рє", "Language", "РњРѕРІР°"}))
async def language_button(message: Message) -> None:
    await language_command(message)


@router.message(StateFilter(None), F.text.in_({"Р РµР·СЋРјРµ", "Resume"}))
async def resume_button(message: Message, state: FSMContext) -> None:
    await resume_command(message, state)


@router.message(StateFilter(None), F.text.in_({"Shorts / Preview", "Shorts / Backstage"}))
async def youtube_hint_button(message: Message) -> None:
    await ensure_user(message)
    await message.answer(
        "РћС‚РїСЂР°РІСЊ СЃСЃС‹Р»РєСѓ YouTube, Рё СЏ РґР°Рј РєРЅРѕРїРєРё: Shorts, Preview РёР»Рё РѕР±Р»РѕР¶РєР° PNG.\n\n"
        "Shorts С‚РµРїРµСЂСЊ РІС‹Р±РёСЂР°СЋС‚СЃСЏ РїРѕ Р»РёС†Р°Рј, РґРІРёР¶РµРЅРёСЋ Рё СЃРјРµРЅР°Рј РєР°РґСЂР°. "
        "Preview СЃРѕР±РёСЂР°РµС‚ РѕРґРёРЅ С€РёСЂРѕРєРёР№ 16:9 СЂРѕР»РёРє СЃ Р»СѓС‡С€РёРјРё РјРѕРјРµРЅС‚Р°РјРё.",
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
                + next_steps_text("РѕС‚РїСЂР°РІСЊ С„Р°Р№Р»", "РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ", lang=lang)
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


@router.callback_query(F.data == "wallet")
async def wallet_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await ensure_callback_user(callback)
    if not callback.message or not callback.from_user:
        return
    lang = user_lang(callback)
    try:
        wallet = await asyncio.to_thread(telegram_wallet, callback.from_user.id)
    except Exception:
        logger.exception("Telegram wallet lookup failed for %s", callback.from_user.id)
        await callback.message.answer(billing_text(lang, "wallet_error"))
        return
    if wallet.get("linked"):
        active_until = wallet.get("active_until")
        until_text = active_until.strftime("%Y-%m-%d %H:%M UTC") if active_until else billing_text(lang, "not_active")
        await callback.message.answer(
            billing_text(lang, "wallet_linked", balance=wallet.get("balance", 0), access=until_text),
            reply_markup=main_menu(lang),
        )
    else:
        await callback.message.answer(
            billing_text(lang, "wallet_not_linked", pending=int(wallet.get("pending_cherryx") or 0)),
            reply_markup=main_menu(lang),
        )

@router.callback_query(F.data.startswith("help:"))
async def help_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await ensure_callback_user(callback)
    if not callback.message or not callback.data:
        return
    lang = user_lang(callback)
    if billing_bot_mode():
        await callback.message.answer(billing_help_text(lang), reply_markup=main_menu(lang))
        return
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


@router.callback_query(F.data.startswith("tgplan:"))
async def billing_plan_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await ensure_callback_user(callback)
    if not callback.message or not callback.from_user or not callback.data:
        return
    plan_code = callback.data.split(":", 1)[1]
    intent = await asyncio.to_thread(create_direct_payment_intent, "plan", plan_code, None, callback.from_user.id)
    await send_intent_invoice(callback.message, bot, intent)


@router.callback_query(F.data.startswith("tgtopup:"))
async def billing_topup_callback(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await callback.answer()
    await ensure_callback_user(callback)
    if not callback.message or not callback.from_user or not callback.data:
        return
    lang = user_lang(callback)
    if callback.data == "tgtopup:custom":
        await state.set_state(BillingAccountState.waiting_topup_stars)
        await callback.message.answer(billing_text(lang, "enter_stars"))
        return
    try:
        cherryx_amount = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.message.answer(billing_text(lang, "topup_invalid"))
        return
    intent = await asyncio.to_thread(create_direct_payment_intent, "topup", "", cherryx_amount, callback.from_user.id)
    await send_intent_invoice(callback.message, bot, intent)


@router.callback_query(F.data.startswith("lang:"))
async def set_language_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message or not callback.data:
        return
    await db.upsert_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    lang = callback.data.split(":", 1)[1]
    if lang not in BOT_LANGUAGE_CODES:
        await callback.message.answer(tr(user_lang(callback), "unknown_language"))
        return
    language_overrides[callback.from_user.id] = lang
    await db.set_language(callback.from_user.id, lang)
    labels = {
        "ru": "Русский",
        "uk": "Українська",
        "en": "English",
        "fr": "Français",
        "de": "Deutsch",
        "es": "Español",
        "ka": "ქართული",
        "hy": "Հայերեն",
        "it": "Italiano",
    }
    await callback.message.answer(
        tr(lang, "language_saved", language=labels[lang]),
        reply_markup=persistent_menu_keyboard(lang),
    )
    await callback.message.answer(tr(lang, "quick_actions"), reply_markup=main_menu(lang))


@router.callback_query(lambda callback: billing_bot_mode())
async def billing_mode_legacy_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await ensure_callback_user(callback)
    if callback.message:
        await callback.message.answer(billing_only_text(user_lang(callback)), reply_markup=main_menu(user_lang(callback)))


@router.callback_query(F.data == "video_help")
async def video_help(callback: CallbackQuery) -> None:
    await callback.answer()
    text = (
        "Р’РёРґРµРѕ-РєРѕРЅРІРµСЂС‚Р°С†РёСЏ Р°РєС‚РёРІРЅР°: MP4, WEBM, GIF.\n"
        "РџСЂРѕС†РµСЃСЃ: РїСЂРёРЅРёРјР°СЋ С„Р°Р№Р», РїСЂРѕРІРµСЂСЏСЋ РїР°СЂР°РјРµС‚СЂС‹, РєРѕРґРёСЂСѓСЋ РІС‹Р±СЂР°РЅРЅС‹Р№ С„РѕСЂРјР°С‚, РѕС‚РїСЂР°РІР»СЏСЋ СЂРµР·СѓР»СЊС‚Р°С‚."
        + next_steps_text("РѕС‚РїСЂР°РІСЊ РІРёРґРµРѕС„Р°Р№Р»", "РёР»Рё РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°", "РїРѕСЃР»Рµ MP4 РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ СЃСѓР±С‚РёС‚СЂС‹")
        if ffmpeg_available()
        else "РћР±СЂР°Р±РѕС‚С‡РёРє РІРёРґРµРѕ РЅРµРґРѕСЃС‚СѓРїРµРЅ." + next_steps_text("РѕР±РЅРѕРІРё Р·Р°РІРёСЃРёРјРѕСЃС‚Рё", "РїРµСЂРµР·Р°РїСѓСЃС‚Рё Р±РѕС‚Р°")
    )
    if callback.message:
        await callback.message.answer(text)


async def send_subscription_invoice(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id if message.from_user else message.chat.id
    payload = build_subscription_payload(user_id, settings.subscription_days, settings.subscription_stars)
    lang = user_lang(message)
    if billing_bot_mode():
        await message.answer(billing_text(lang, "choose"), reply_markup=billing_direct_keyboard(lang))
        return
    await message.answer(
        tr(lang, "pay_intro", stars=settings.subscription_stars, days=settings.subscription_days),
        reply_markup=help_navigation_keyboard(lang),
    )
    await message.answer(
        process_stage_text(
            "РџРѕРґРіРѕС‚РѕРІРєР° РґРѕСЃС‚СѓРїР°",
            ["РїСЂРѕРІРµСЂСЏСЋ Р·Р°РїСЂРѕСЃ", "С„РѕСЂРјРёСЂСѓСЋ СЃС‡РµС‚", "Р¶РґСѓ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ РѕРїР»Р°С‚С‹"],
            2,
            f"РџРµСЂРёРѕРґ: {settings.subscription_days} РґРЅРµР№",
            lang=lang,
        )
        + next_steps_text("РѕРїР»Р°С‚Рё СЃС‡РµС‚ РЅРёР¶Рµ", "РїРѕСЃР»Рµ РѕРїР»Р°С‚С‹ РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ", lang=lang)
    )
    await bot(
        SendInvoice(
            chat_id=message.chat.id,
            title="Image Converter Pro",
            description=f"Р”РѕСЃС‚СѓРї Рє РІРёРґРµРѕ, С„РѕС‚Рѕ, PDF-СЂРµР·СЋРјРµ, YouTube, СЃСѓР±С‚РёС‚СЂР°Рј Рё РѕР±Р»РѕР¶РєР°Рј РЅР° {settings.subscription_days} РґРЅРµР№.",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"{settings.subscription_days} РґРЅРµР№", amount=settings.subscription_stars)],
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
            + next_steps_text("РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†РёРё", "РёР»Рё РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°", lang=lang)
        )
        return
    sub = await db.get_subscription(current_user_id)
    if sub.is_active:
        payments = await db.recent_payments(current_user_id, 1)
        payment_note = ""
        if payments:
            paid = payments[0]
            paid_at = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(paid.created_at))
            payment_note = f"\nРџРѕСЃР»РµРґРЅСЏСЏ РѕРїР»Р°С‚Р°: {paid.total_amount} Stars, {paid_at}."
        await message.answer(
            tr(lang, "sub_active", date=sub.active_until_text)
            + "\n\nРџР»Р°РЅ: Pro\nР”РѕСЃС‚СѓРїРЅРѕ: YouTube, СЃСѓР±С‚РёС‚СЂС‹, РѕР±Р»РѕР¶РєРё, РїР°РєРµС‚С‹ РїСѓР±Р»РёРєР°С†РёРё, Р±РѕР»СЊС€Рµ РѕР±СЂР°Р±РѕС‚РѕРє."
            + payment_note
            + next_steps_text("РѕС‚РїСЂР°РІСЊ С„Р°Р№Р»", "РёР»Рё РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ", lang=lang)
        )
    else:
        await message.answer(
            tr(lang, "sub_inactive")
            + "\n\nРџР»Р°РЅ: Р±РµР· Р°РєС‚РёРІРЅРѕР№ РїРѕРґРїРёСЃРєРё\n"
            + "Р¤СѓРЅРєС†РёРё РІРёРґРµРѕ, С„РѕС‚Рѕ, PDF-СЂРµР·СЋРјРµ, YouTube, СЃСѓР±С‚РёС‚СЂС‹ Рё РѕР±Р»РѕР¶РєРё РґРѕСЃС‚СѓРїРЅС‹ РїРѕСЃР»Рµ РѕРїР»Р°С‚С‹ Stars.\n"
            + "РџРѕР»СЊР·РѕРІР°С‚РµР»Рё РёР· FREE_USER_IDS РІ .env РїРѕР»СѓС‡Р°СЋС‚ С‚РѕС‚ Р¶Рµ РґРѕСЃС‚СѓРї Р±РµСЃРїР»Р°С‚РЅРѕ."
            + next_steps_text("Р°РєС‚РёРІРёСЂСѓР№ РґРѕСЃС‚СѓРї РєРЅРѕРїРєРѕР№ РЅРёР¶Рµ", "РёР»Рё РЅР°РїРёС€Рё /id Рё РґРѕР±Р°РІСЊ ID РІ FREE_USER_IDS", lang=lang),
            reply_markup=main_menu(lang),
        )


async def free_usage_lines(user_id: int) -> list[str]:
    items = [
        ("image", "РёР·РѕР±СЂР°Р¶РµРЅРёСЏ"),
        ("video", "РІРёРґРµРѕ"),
        ("cover", "РѕР±Р»РѕР¶РєРё"),
        ("youtube", "YouTube"),
        ("subtitles", "СЃСѓР±С‚РёС‚СЂС‹"),
        ("package", "РїР°РєРµС‚С‹"),
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
            "РСЃС‚РѕСЂРёСЏ РїРѕРєР° РїСѓСЃС‚Р°СЏ."
            + next_steps_text("РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ", "РїРѕСЃР»Рµ РѕР±СЂР°Р±РѕС‚РєРё СЂРµР·СѓР»СЊС‚Р°С‚ РїРѕСЏРІРёС‚СЃСЏ Р·РґРµСЃСЊ")
        )
        return
    lines = ["РџРѕСЃР»РµРґРЅРёРµ РѕР±СЂР°Р±РѕС‚РєРё:"]
    for index, record in enumerate(records, start=1):
        created = time.strftime("%Y-%m-%d %H:%M", time.localtime(record.created_at))
        lines.append(
            f"{index}. {created} | {record.media_type} | {record.output_format.upper()} | "
            f"{human_size(record.output_size)}\n{record.output_name}"
        )
    await message.answer(
        "\n\n".join(lines)
        + next_steps_text("РѕС‚РїСЂР°РІСЊ РЅРѕРІС‹Р№ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ", "РґР»СЏ СЃРІРµР¶РёС… MP4 РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ СЃСѓР±С‚РёС‚СЂС‹ РєРЅРѕРїРєРѕР№ РїРѕРґ СЂРµР·СѓР»СЊС‚Р°С‚РѕРј")
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
    lang = user_lang(query)
    if query.currency != "XTR":
        await query.answer(ok=False, error_message=billing_text(lang, "precheckout_currency"))
        return
    if (query.invoice_payload or "").startswith("intent:"):
        intent = await asyncio.to_thread(get_payment_intent_by_payload, query.invoice_payload)
        if not intent.get("ok") or intent.get("status") != "pending":
            await query.answer(ok=False, error_message=billing_text(lang, "precheckout_expired"))
            return
        if int(intent.get("stars_amount") or 0) != query.total_amount:
            await query.answer(ok=False, error_message=billing_text(lang, "precheckout_amount"))
            return
        await query.answer(ok=True)
        return
    if query.total_amount != settings.subscription_stars:
        await query.answer(ok=False, error_message=billing_text(lang, "precheckout_amount"))
        return
    if not valid_subscription_payload(query.invoice_payload, query.from_user.id):
        await query.answer(ok=False, error_message=billing_text(lang, "precheckout_expired"))
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.successful_payment:
        return
    payment = message.successful_payment
    if (payment.invoice_payload or "").startswith("intent:"):
        result = await asyncio.to_thread(
            record_intent_payment,
            telegram_user_id=message.from_user.id,
            stars_amount=payment.total_amount,
            invoice_payload=payment.invoice_payload,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            provider_payment_charge_id=payment.provider_payment_charge_id or "",
            currency=payment.currency,
            telegram_username=message.from_user.username or "",
            telegram_first_name=message.from_user.first_name or "",
        )
        if not result.get("ok"):
            await message.answer(billing_text(user_lang(message), "intent_error"))
            return
        if result.get("needs_email"):
            await state.set_state(BillingAccountState.waiting_email)
            await message.answer(billing_text(user_lang(message), "need_email"))
            return
        await message.answer(
            billing_text(user_lang(message), "applied", title=result.get("title"), cherryx=result.get("cherryx_amount")),
            reply_markup=main_menu(user_lang(message)),
        )
        return
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
    account_note = ""
    try:
        account_result = await asyncio.to_thread(
            record_stars_payment,
            telegram_user_id=message.from_user.id,
            stars_amount=payment.total_amount,
            invoice_payload=payment.invoice_payload,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            provider_payment_charge_id=payment.provider_payment_charge_id or "",
            currency=payment.currency,
            telegram_username=message.from_user.username or "",
            telegram_first_name=message.from_user.first_name or "",
        )
        if account_result.get("linked"):
            account_note = (
                f"РќР° CherryX Р°РєРєР°СѓРЅС‚ Р·Р°С‡РёСЃР»РµРЅРѕ: {account_result.get('cherryx', 0)} CherryX.\n"
                f"Р‘Р°Р»Р°РЅСЃ: {account_result.get('balance', 0)} CherryX."
            )
        else:
            account_note = (
                f"РџР»Р°С‚С‘Р¶ СЃРѕС…СЂР°РЅС‘РЅ: {account_result.get('cherryx', 0)} CherryX Р¶РґСѓС‚ РїСЂРёРІСЏР·РєРё Р°РєРєР°СѓРЅС‚Р°.\n"
                "РћС‚РєСЂРѕР№ CherryX Pay РЅР° СЃР°Р№С‚Рµ Рё РѕС‚РїСЂР°РІСЊ СЃСЋРґР° РєРѕРјР°РЅРґСѓ /link РєРѕРґ."
            )
    except Exception:
        logger.exception("Failed to sync Telegram Stars payment with CherryX account for %s", message.from_user.id)
        account_note = "РџР»Р°С‚С‘Р¶ СЃРѕС…СЂР°РЅС‘РЅ РІ Р±РѕС‚Рµ. Р•СЃР»Рё Р±Р°Р»Р°РЅСЃ СЃР°Р№С‚Р° РЅРµ РѕР±РЅРѕРІРёР»СЃСЏ, РЅР°РїРёС€Рё /paysupport."
    await message.answer(
        "РћРїР»Р°С‚Р° РїСЂРѕС€Р»Р°.\n"
        f"РџРѕРґРїРёСЃРєР° Р°РєС‚РёРІРЅР° РґРѕ {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(active_until))}.\n"
        + next_steps_text("РѕС‚РїСЂР°РІСЊ РёР·РѕР±СЂР°Р¶РµРЅРёРµ РёР»Рё РІРёРґРµРѕ", "РёР»Рё РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РґР»СЏ РјРѕРЅС‚Р°Р¶Р°")
    )
    if account_note:
        await message.answer(account_note)


@router.message(BillingAccountState.waiting_topup_stars)
async def billing_topup_stars_amount(message: Message, bot: Bot, state: FSMContext) -> None:
    await ensure_user(message)
    if not message.from_user or not message.text:
        return
    raw_amount = message.text.strip().replace(" ", "")
    if not raw_amount.isdigit():
        await message.answer(billing_text(user_lang(message), "invalid_stars"))
        return
    stars_amount = int(raw_amount)
    if stars_amount < 1 or stars_amount > 150000:
        await message.answer(billing_text(user_lang(message), "stars_range"))
        return
    try:
        intent = await asyncio.to_thread(create_direct_topup_by_stars, stars_amount, message.from_user.id)
    except ValueError:
        await message.answer(billing_text(user_lang(message), "stars_range"))
        return
    await state.clear()
    await send_intent_invoice(message, bot, intent)


@router.message(BillingAccountState.waiting_email)
async def billing_account_email(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    if not message.from_user or not message.text:
        return
    email = message.text.strip()
    result = await asyncio.to_thread(
        create_account_for_paid_intent,
        message.from_user.id,
        email,
        message.from_user.username or "",
        message.from_user.first_name or "",
    )
    if result.get("ok"):
        await state.clear()
        login_url = str(result.get("magic_login_url") or result.get("login_url") or "")
        await message.answer(
            billing_text(
                user_lang(message),
                "account_created",
                email=result.get("email"),
                password=result.get("password"),
                login_url=login_url,
            ),
            reply_markup=open_cherryx_keyboard(login_url, user_lang(message)) if login_url else main_menu(user_lang(message)),
        )
        if login_url:
            await message.answer(billing_text(user_lang(message), "choose"), reply_markup=main_menu(user_lang(message)))
        return
    if result.get("reason") == "email_exists":
        await state.clear()
        await message.answer(billing_text(user_lang(message), "email_exists"))
        return
    await message.answer(billing_text(user_lang(message), "email_invalid"))


@router.message(StateFilter(None), F.text)
async def receive_text(message: Message, bot: Bot) -> None:
    await ensure_user(message)
    if not message.from_user:
        return
    if billing_bot_mode():
        text = (message.text or "").strip().lower()
        if text in {"pay", "pay stars", "stars"}:
            await send_subscription_invoice(message, bot)
            return
        if text == "status":
            await send_status(message)
            return
        if text == "wallet":
            await wallet_command(message)
            return
        if text in {"help", "support"}:
            await message.answer(billing_help_text(user_lang(message)), reply_markup=main_menu(user_lang(message)))
            return
        if text == "language":
            await language_command(message)
            return
        await message.answer(billing_only_text(user_lang(message)), reply_markup=main_menu(user_lang(message)))
        return

    url = extract_youtube_url(message.text)
    if not url:
        session = latest_video_session(message.from_user.id)
        prompt = normalize_cover_prompt_text(message.text)
        if session and prompt and len(prompt) >= 4:
            session.cover_title = prompt
            job_id = remember_cover_job(message.from_user.id, session.path, prompt, None)
            await message.answer(
                "РўРµРєСЃС‚ РґР»СЏ РѕР±Р»РѕР¶РєРё РїСЂРёРЅСЏС‚.\n"
                f"{cover_prompt_preview(prompt)}\n\n"
                "РўРµРїРµСЂСЊ РЅР°Р¶РјРё В«РЎРіРµРЅРµСЂРёСЂРѕРІР°С‚СЊ РѕР±Р»РѕР¶РєСѓ PNGВ» РёР»Рё В«Р•С‰Рµ 3 РІР°СЂРёР°РЅС‚Р°В», Рё СЏ РїРѕРґСЃС‚Р°РІР»СЋ СЌС‚РѕС‚ С‚РµРєСЃС‚ РІ РјР°РєРµС‚.",
                reply_markup=cover_tools_keyboard(job_id),
            )
        return

    lang = user_lang(message)
    source_label = video_source_label(url)
    if not await ensure_action_allowed(message, message.from_user.id, "youtube", f"{source_label}-РјРѕРЅС‚Р°Р¶ РІС…РѕРґРёС‚ РІ Pro-С„СѓРЅРєС†РёРё."):
        return

    job_id = uuid.uuid4().hex[:10]
    pending_youtube_jobs[job_id] = (message.from_user.id, url, lang, int(time.time()))
    await message.answer(
        f"{source_label}-СЃСЃС‹Р»РєР° РїСЂРёРЅСЏС‚Р°.\n\n"
        "Р’С‹Р±РµСЂРё СЂРµР¶РёРј:\n"
        "- РЎРєР°С‡Р°С‚СЊ MP4: СЃРєР°С‡Р°С‚СЊ РґРѕСЃС‚СѓРїРЅС‹Р№ С„Р°Р№Р» Рё РїСЂРё РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё РєРѕРЅРІРµСЂС‚РёСЂРѕРІР°С‚СЊ РІ MP4.\n"
        "- Shorts dynamic: РєРѕСЂРѕС‡Рµ, РїР»РѕС‚РЅРµРµ, Р±РѕР»СЊС€Рµ РѕРїРѕСЂС‹ РЅР° РїРёРєРё Р·РІСѓРєР° Рё СЃРјРµРЅС‹ РєР°РґСЂР°.\n"
        "- Shorts podcast: РґР»РёРЅРЅРµРµ, Р±РѕР»СЊС€Рµ РІРЅРёРјР°РЅРёСЏ Р»РёС†Р°Рј Рё РїР°СѓР·Р°Рј СЂРµС‡Рё.\n"
        "- Shorts calm: РјРµРЅСЊС€Рµ РєР»РёРїРѕРІ, СЃРїРѕРєРѕР№РЅРµРµ С‚РµРјРї.\n"
        "- Preview 30/60/90: РѕРґРёРЅ С€РёСЂРѕРєРёР№ 16:9 СЂРѕР»РёРє СЃ Р»СѓС‡С€РёРјРё РјРѕРјРµРЅС‚Р°РјРё Рё РјСЏРіРєРёРјРё РїРµСЂРµС…РѕРґР°РјРё.\n\n"
        f"- РћР±Р»РѕР¶РєР° PNG: Р°РЅР°Р»РёР· РІРёРґРµРѕ Рё СЏСЂРєР°СЏ 1280x720 РѕР±Р»РѕР¶РєР° РґР»СЏ {source_label}.\n\n"
        "РџРѕСЃР»Рµ РІС‹Р±РѕСЂР° Р±СѓРґСѓ РїРёСЃР°С‚СЊ СЌС‚Р°РїС‹. РќР° РґРѕР»РіРёС… РІРёРґРµРѕ СЃС‚Р°С‚СѓСЃ РѕР±РЅРѕРІР»СЏРµС‚СЃСЏ РїСЂРёРјРµСЂРЅРѕ СЂР°Р· РІ РјРёРЅСѓС‚Сѓ.",
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
        await callback.message.answer("Р­С‚Р° YouTube-Р·Р°РґР°С‡Р° СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРЅР°. РћС‚РїСЂР°РІСЊ СЃСЃС‹Р»РєСѓ РµС‰Рµ СЂР°Р·.")
        return
    user_id, url, lang, created_at = job
    source_label = video_source_label(url)
    if user_id != callback.from_user.id:
        await callback.message.answer(f"Р­С‚Р° РєРЅРѕРїРєР° РѕС‚ РґСЂСѓРіРѕР№ Р·Р°РґР°С‡Рё. РћС‚РїСЂР°РІСЊ СЃРІРѕСЋ {source_label}-СЃСЃС‹Р»РєСѓ.")
        return
    if mode == "cancel":
        await callback.message.answer(
            f"РћРє, {source_label}-Р·Р°РґР°С‡Р° РѕС‚РјРµРЅРµРЅР°."
            + next_steps_text("РѕС‚РїСЂР°РІСЊ РґСЂСѓРіСѓСЋ СЃСЃС‹Р»РєСѓ", "РёР»Рё РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РґР»СЏ РєРѕРЅРІРµСЂС‚Р°С†РёРё")
        )
        return
    if int(time.time()) - created_at > 900:
        await callback.message.answer(f"Р—Р°РґР°С‡Р° СѓСЃС‚Р°СЂРµР»Р°. РћС‚РїСЂР°РІСЊ {source_label}-СЃСЃС‹Р»РєСѓ РµС‰Рµ СЂР°Р·.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "youtube", f"{source_label}-РјРѕРЅС‚Р°Р¶ Рё РѕР±Р»РѕР¶РєРё РїРѕ СЃСЃС‹Р»РєРµ РІС…РѕРґСЏС‚ РІ Pro-С„СѓРЅРєС†РёРё."):
        return
    if mode == "download":
        if youtube_semaphore.locked():
            await callback.message.answer(f"РЎРµР№С‡Р°СЃ СѓР¶Рµ РёРґРµС‚ {source_label}-РѕР±СЂР°Р±РѕС‚РєР°. РџРѕСЃС‚Р°РІРёР» СЃРєР°С‡РёРІР°РЅРёРµ РІ РѕС‡РµСЂРµРґСЊ.")
        async with youtube_semaphore:
            await process_video_download_link(callback.message, bot, url, lang, user_id)
        return
    if mode == "cover":
        if youtube_semaphore.locked():
            await callback.message.answer(f"РЎРµР№С‡Р°СЃ СѓР¶Рµ РёРґРµС‚ {source_label}-РѕР±СЂР°Р±РѕС‚РєР°. РџРѕСЃС‚Р°РІРёР» РѕР±Р»РѕР¶РєСѓ РІ РѕС‡РµСЂРµРґСЊ.")
        async with youtube_semaphore:
            await process_youtube_cover_link(callback.message, bot, url, lang, user_id)
        return
    if youtube_semaphore.locked():
        await callback.message.answer(f"РЎРµР№С‡Р°СЃ СѓР¶Рµ РёРґРµС‚ {source_label}-РЅР°СЂРµР·РєР°. РџРѕСЃС‚Р°РІРёР» Р·Р°РґР°С‡Сѓ РІ РѕС‡РµСЂРµРґСЊ.")
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
        await callback.message.answer("Р­С‚Р° СЃСЃС‹Р»РєР° СѓР¶Рµ РЅРµ С…СЂР°РЅРёС‚СЃСЏ. РћС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РµС‰Рµ СЂР°Р·.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Р­С‚Р° РєРЅРѕРїРєР° РѕС‚ РґСЂСѓРіРѕР№ Р·Р°РґР°С‡Рё. РћС‚РїСЂР°РІСЊ СЃРІРѕСЋ YouTube-СЃСЃС‹Р»РєСѓ.")
        return
    if int(time.time()) - job.created_at > 86400:
        recent_youtube_jobs.pop(job_id, None)
        await callback.message.answer("Р—Р°РґР°С‡Р° СѓСЃС‚Р°СЂРµР»Р°. РћС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ РµС‰Рµ СЂР°Р·.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "youtube", "РџРѕРІС‚РѕСЂРЅР°СЏ YouTube-РѕР±СЂР°Р±РѕС‚РєР° РІС…РѕРґРёС‚ РІ Pro-С„СѓРЅРєС†РёРё."):
        return
    if youtube_semaphore.locked():
        await callback.message.answer("РЎРµР№С‡Р°СЃ СѓР¶Рµ РёРґРµС‚ РјРѕРЅС‚Р°Р¶. РџРѕСЃС‚Р°РІРёР» РїРµСЂРµРґРµР»РєСѓ РІ РѕС‡РµСЂРµРґСЊ.")
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
        await callback.message.answer("Р­С‚Рѕ РІРёРґРµРѕ СѓР¶Рµ РЅРµ С…СЂР°РЅРёС‚СЃСЏ РІ РѕС‡РµСЂРµРґРё СЃСѓР±С‚РёС‚СЂРѕРІ. РџРµСЂРµСЃРѕР±РµСЂРё СЂРѕР»РёРє РёР»Рё РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» Р·Р°РЅРѕРІРѕ.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Р­С‚Р° РєРЅРѕРїРєР° РѕС‚ РґСЂСѓРіРѕРіРѕ РІРёРґРµРѕ. РћС‚РїСЂР°РІСЊ СЃРІРѕРµ РІРёРґРµРѕ РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ.")
        return
    style = style if style in SUBTITLE_STYLE_LABELS else "pop"
    await callback.message.answer(
        f"РЎС‚РёР»СЊ СЃСѓР±С‚РёС‚СЂРѕРІ: {SUBTITLE_STYLE_LABELS[style]}.\nР’С‹Р±РµСЂРё СЏР·С‹Рє СЂРµС‡Рё РґР»СЏ СЂР°СЃРїРѕР·РЅР°РІР°РЅРёСЏ:",
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
        await callback.message.answer("Р­С‚Рѕ РІРёРґРµРѕ СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРЅРѕ РґР»СЏ СЃСѓР±С‚РёС‚СЂРѕРІ. РћС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ Р·Р°РЅРѕРІРѕ.")
        return
    preview_path: Path | None = None
    try:
        preview_path = await asyncio.to_thread(create_subtitle_style_preview_sheet, settings.output_dir)
        await callback.message.answer_photo(
            FSInputFile(preview_path),
            caption="РџСЂРёРјРµСЂС‹ СЃС‚РёР»РµР№ СЃСѓР±С‚РёС‚СЂРѕРІ. РџРѕСЃР»Рµ РїСЂРѕСЃРјРѕС‚СЂР° РІС‹Р±РµСЂРёС‚Рµ СЃС‚РёР»СЊ РєРЅРѕРїРєРѕР№ РЅРёР¶Рµ.",
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
        await callback.message.answer("Р­С‚Рѕ РІРёРґРµРѕ СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРЅРѕ РґР»СЏ СЃСѓР±С‚РёС‚СЂРѕРІ. РћС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ Р·Р°РЅРѕРІРѕ.")
        return
    await callback.message.answer("Р’С‹Р±РµСЂРё СЃС‚РёР»СЊ СЃСѓР±С‚РёС‚СЂРѕРІ:", reply_markup=subtitle_keyboard(job_id))


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
        await callback.message.answer("РќРµ РїРѕРЅСЏР» РІС‹Р±СЂР°РЅРЅС‹Р№ РІР°СЂРёР°РЅС‚ СЃСѓР±С‚РёС‚СЂРѕРІ. РќР°Р¶РјРё СЃС‚РёР»СЊ РµС‰Рµ СЂР°Р·.")
        return
    job = subtitle_jobs.get(job_id)
    if not job:
        await callback.message.answer("Р­С‚Рѕ РІРёРґРµРѕ СѓР¶Рµ РЅРµ С…СЂР°РЅРёС‚СЃСЏ РІ РѕС‡РµСЂРµРґРё СЃСѓР±С‚РёС‚СЂРѕРІ. РџРµСЂРµСЃРѕР±РµСЂРё СЂРѕР»РёРє РёР»Рё РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» Р·Р°РЅРѕРІРѕ.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Р­С‚Р° РєРЅРѕРїРєР° РѕС‚ РґСЂСѓРіРѕРіРѕ РІРёРґРµРѕ. РћС‚РїСЂР°РІСЊ СЃРІРѕРµ РІРёРґРµРѕ РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ.")
        return
    if not job.path.exists():
        subtitle_jobs.pop(job_id, None)
        await callback.message.answer("Р¤Р°Р№Р» СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РџРµСЂРµСЃРѕР±РµСЂРё СЂРѕР»РёРє, Рё СЏ СЃРЅРѕРІР° РґР°Рј РєРЅРѕРїРєСѓ СЃСѓР±С‚РёС‚СЂРѕРІ.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "subtitles", "РЎСѓР±С‚РёС‚СЂС‹ РІС…РѕРґСЏС‚ РІ Pro-С„СѓРЅРєС†РёРё."):
        return

    if subtitle_semaphore.locked():
        await callback.message.answer("РЎРµР№С‡Р°СЃ СѓР¶Рµ РґРµР»Р°СЋ СЃСѓР±С‚РёС‚СЂС‹. РџРѕСЃС‚Р°РІРёР» Р·Р°РґР°С‡Сѓ РІ РѕС‡РµСЂРµРґСЊ.")

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
        "stage": "РЎСѓР±С‚РёС‚СЂС‹: РїРѕРґРіРѕС‚РѕРІРєР°",
        "detail": job.path.name,
    }
    status = await message.answer(
        process_stage_text(
            "Р”РѕР±Р°РІР»РµРЅРёРµ СЃСѓР±С‚РёС‚СЂРѕРІ",
            SUBTITLE_STEPS,
            1,
            f"РЎС‚РёР»СЊ: {style_label}. РЇР·С‹Рє: {language_label}. Р‘РµСЂСѓ С‡РёСЃС‚С‹Р№ MP4 Р±РµР· РїРѕРІС‚РѕСЂРЅРѕРіРѕ РЅР°Р»РѕР¶РµРЅРёСЏ.",
        )
    )
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
        state["stage"] = "РЎСѓР±С‚РёС‚СЂС‹: СЂР°СЃРїРѕР·РЅР°СЋ СЂРµС‡СЊ Рё РІРµСЂСЃС‚Р°СЋ С‚РµРєСЃС‚"
        await safe_edit(
            status,
            process_stage_text("Р”РѕР±Р°РІР»РµРЅРёРµ СЃСѓР±С‚РёС‚СЂРѕРІ", SUBTITLE_STEPS, 2, "РР·РІР»РµРєР°СЋ Р·РІСѓРє Рё РёС‰Сѓ С„СЂР°Р·С‹"),
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
                "РќРµ РЅР°С€РµР» СЂРµС‡СЊ РґР»СЏ СЃСѓР±С‚РёС‚СЂРѕРІ."
                + next_steps_text("РїРѕРїСЂРѕР±СѓР№ РґСЂСѓРіРѕР№ С„СЂР°РіРјРµРЅС‚", "РёР»Рё РѕС‚РїСЂР°РІСЊ РІРёРґРµРѕ СЃ Р±РѕР»РµРµ С‡РёСЃС‚С‹Рј Р·РІСѓРєРѕРј"),
            )
            return
        state["stage"] = "РЎСѓР±С‚РёС‚СЂС‹: РІРµСЂСЃС‚Р°СЋ СЃС‚РёР»СЊ"
        await safe_edit(
            status,
            process_stage_text(
                "Р”РѕР±Р°РІР»РµРЅРёРµ СЃСѓР±С‚РёС‚СЂРѕРІ",
                SUBTITLE_STEPS,
                3,
                f"Р¤СЂР°Р· РЅР°Р№РґРµРЅРѕ: {len(cues)}. Р Р°СЃРєР»Р°РґС‹РІР°СЋ С‚РµРєСЃС‚ РїРѕ СЌРєСЂР°РЅСѓ.",
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
            process_stage_text("Р”РѕР±Р°РІР»РµРЅРёРµ СЃСѓР±С‚РёС‚СЂРѕРІ", SUBTITLE_STEPS, 4, "Р’С€РёРІР°СЋ РѕС„РѕСЂРјР»РµРЅРЅС‹Рµ СЃС‚СЂРѕРєРё РІ РІРёРґРµРѕ"),
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
        state["stage"] = "РЎСѓР±С‚РёС‚СЂС‹: РѕС‚РїСЂР°РІР»СЏСЋ РіРѕС‚РѕРІС‹Р№ MP4"
        state["detail"] = f"Р Р°Р·РјРµСЂ: {human_size(output.path.stat().st_size)}"
        await safe_edit(
            status,
            process_stage_text(
                "Р”РѕР±Р°РІР»РµРЅРёРµ СЃСѓР±С‚РёС‚СЂРѕРІ",
                SUBTITLE_STEPS,
                5,
                f"Р Р°Р·РјРµСЂ: {human_size(output.path.stat().st_size)}",
            ),
        )
        new_job_id = remember_subtitle_job(job.user_id, job.path, job.title)
        await message.answer_document(
            FSInputFile(output.path),
            caption=(
                "Р“РѕС‚РѕРІРѕ: РІРёРґРµРѕ СЃ РІС€РёС‚С‹РјРё СЃСѓР±С‚РёС‚СЂР°РјРё\n"
                f"РЎС‚РёР»СЊ: {style_label}\n"
                f"РЇР·С‹Рє: {language_label}\n"
                f"Р’РµСЃ: {human_size(output.path.stat().st_size)}\n"
                f"Р’СЂРµРјСЏ РѕР±СЂР°Р±РѕС‚РєРё: {format_duration(time.time() - started_at)}"
                + next_steps_text(
                    "СЃРєР°С‡Р°Р№ РІРµСЂСЃРёСЋ СЃ СЃСѓР±С‚РёС‚СЂР°РјРё",
                    "РјРѕР¶РЅРѕ РЅР°Р¶Р°С‚СЊ РґСЂСѓРіРѕР№ СЃС‚РёР»СЊ СЃСѓР±С‚РёС‚СЂРѕРІ",
                    "РјРѕР¶РЅРѕ РѕС‚РїСЂР°РІРёС‚СЊ СЃР»РµРґСѓСЋС‰РёР№ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ",
                )
            ),
            reply_markup=subtitle_keyboard(new_job_id),
        )
        await safe_edit(
            status,
            process_stage_text("Р”РѕР±Р°РІР»РµРЅРёРµ СЃСѓР±С‚РёС‚СЂРѕРІ", SUBTITLE_STEPS, 5, "Р¤Р°Р№Р» РѕС‚РїСЂР°РІР»РµРЅ", done=True)
            + next_steps_text("РїСЂРѕРІРµСЂСЊ С‡РёС‚Р°РµРјРѕСЃС‚СЊ", "РµСЃР»Рё СЃС‚РёР»СЊ РЅРµ РїРѕРґС…РѕРґРёС‚, РЅР°Р¶РјРё РґСЂСѓРіРѕР№ РІР°СЂРёР°РЅС‚"),
        )
    except SubtitleUnavailableError as exc:
        await safe_edit(
            status,
            str(exc) + next_steps_text("РѕР±РЅРѕРІРё Р·Р°РІРёСЃРёРјРѕСЃС‚Рё", "РїРµСЂРµР·Р°РїСѓСЃС‚Рё Р±РѕС‚Р°", "РЅР°Р¶РјРё РєРЅРѕРїРєСѓ СЃСѓР±С‚РёС‚СЂРѕРІ РµС‰Рµ СЂР°Р·"),
        )
    except Exception as exc:
        logger.exception("Subtitle job failed")
        await safe_edit(
            status,
            f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ СЃРґРµР»Р°С‚СЊ СЃСѓР±С‚РёС‚СЂС‹: {exc}"
            + next_steps_text("РїРѕРїСЂРѕР±СѓР№ РґСЂСѓРіРѕР№ СЃС‚РёР»СЊ", "РµСЃР»Рё РІ СЂРѕР»РёРєРµ РјР°Р»Рѕ СЂРµС‡Рё, РѕС‚РїСЂР°РІСЊ РґСЂСѓРіРѕР№ С„СЂР°РіРјРµРЅС‚"),
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
        await callback.message.answer("Р­С‚Рѕ РІРёРґРµРѕ СѓР¶Рµ РЅРµ С…СЂР°РЅРёС‚СЃСЏ РґР»СЏ РѕР±Р»РѕР¶РєРё. РћС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ Р·Р°РЅРѕРІРѕ.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Р­С‚Р° РєРЅРѕРїРєР° РѕС‚ РґСЂСѓРіРѕРіРѕ РІРёРґРµРѕ. РћС‚РїСЂР°РІСЊ СЃРІРѕРµ РІРёРґРµРѕ РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ.")
        return
    if not job.path.exists():
        cover_jobs.pop(job_id, None)
        await callback.message.answer("Р¤Р°Р№Р» СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РћС‚РїСЂР°РІСЊ РІРёРґРµРѕ Р·Р°РЅРѕРІРѕ.")
        return
    await state.set_state(CoverTextState.waiting_text)
    await state.update_data(cover_job_id=job_id)
    await callback.message.answer(
        "РќР°РїРёС€Рё С‚РµРєСЃС‚ РґР»СЏ РѕР±Р»РѕР¶РєРё РѕРґРЅРёРј СЃРѕРѕР±С‰РµРЅРёРµРј.\n\n"
        "1 СЃС‚СЂРѕРєР° вЂ” РєСЂСѓРїРЅС‹Р№ Р·Р°РіРѕР»РѕРІРѕРє.\n"
        "2 СЃС‚СЂРѕРєР° вЂ” РѕРїРёСЃР°РЅРёРµ/РєСЂСЋС‡РѕРє РїРѕРјРµР»СЊС‡Рµ.\n\n"
        "РџСЂРёРјРµСЂ:\n"
        "РљР°Рє РѕРЅ РїРѕРґРЅСЏР» РїСЂРѕРґР°Р¶Рё\n"
        "СЂР°Р·Р±РѕСЂ РіР»Р°РІРЅРѕРіРѕ РїСЂРёРµРјР°"
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
        await message.answer("Р’РёРґРµРѕ РґР»СЏ РѕР±Р»РѕР¶РєРё СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРЅРѕ. РћС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ Р·Р°РЅРѕРІРѕ.")
        return
    prompt = normalize_cover_prompt_text(message.text)
    if not prompt:
        await message.answer("РџСЂРёС€Р»Рё Р·Р°РіРѕР»РѕРІРѕРє Рё РѕРїРёСЃР°РЅРёРµ С‚РµРєСЃС‚РѕРј. РџРµСЂРІР°СЏ СЃС‚СЂРѕРєР° Р±СѓРґРµС‚ РіР»Р°РІРЅС‹Рј Р·Р°РіРѕР»РѕРІРєРѕРј.")
        return
    await state.clear()
    if not await ensure_action_allowed(message, message.from_user.id, "cover"):
        return
    if cover_semaphore.locked():
        await message.answer("РЎРµР№С‡Р°СЃ СѓР¶Рµ СЃРѕР±РёСЂР°СЋ РѕР±Р»РѕР¶РєСѓ. РџРѕСЃС‚Р°РІРёР» Р·Р°РґР°С‡Сѓ РІ РѕС‡РµСЂРµРґСЊ.")
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
    await callback.answer("Р“РѕС‚РѕРІР»СЋ РѕР±Р»РѕР¶РєСѓ...")
    if not callback.from_user or not callback.message or not callback.data:
        return
    session_id = callback.data.split(":", 1)[1]
    session = get_owned_session(session_id, callback.from_user.id)
    if not session:
        await callback.message.answer("Р­С‚РѕС‚ С„Р°Р№Р» СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РћС‚РїСЂР°РІСЊ РІРёРґРµРѕ Р·Р°РЅРѕРІРѕ.")
        return
    if session.kind != "video":
        await callback.message.answer("РћР±Р»РѕР¶РєСѓ РјРѕР¶РЅРѕ СЃРґРµР»Р°С‚СЊ С‚РѕР»СЊРєРѕ РґР»СЏ РІРёРґРµРѕ.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "cover"):
        return
    if cover_semaphore.locked():
        await callback.message.answer("РЎРµР№С‡Р°СЃ СѓР¶Рµ СЃРѕР±РёСЂР°СЋ РѕР±Р»РѕР¶РєСѓ. РџРѕСЃС‚Р°РІРёР» Р·Р°РґР°С‡Сѓ РІ РѕС‡РµСЂРµРґСЊ.")
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
    await callback.answer("Р“РѕС‚РѕРІР»СЋ РѕР±Р»РѕР¶РєСѓ...")
    if not callback.from_user or not callback.message or not callback.data:
        return
    job_id = callback.data.split(":", 1)[1]
    job = cover_jobs.get(job_id)
    if not job:
        await callback.message.answer("Р­С‚Рѕ РІРёРґРµРѕ СѓР¶Рµ РЅРµ С…СЂР°РЅРёС‚СЃСЏ РґР»СЏ РѕР±Р»РѕР¶РєРё. РћС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ Р·Р°РЅРѕРІРѕ.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Р­С‚Р° РєРЅРѕРїРєР° РѕС‚ РґСЂСѓРіРѕРіРѕ РІРёРґРµРѕ. РћС‚РїСЂР°РІСЊ СЃРІРѕРµ РІРёРґРµРѕ РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ.")
        return
    if not job.path.exists():
        cover_jobs.pop(job_id, None)
        await callback.message.answer("Р¤Р°Р№Р» СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РџРµСЂРµСЃРѕР±РµСЂРё СЂРѕР»РёРє РёР»Рё РѕС‚РїСЂР°РІСЊ РІРёРґРµРѕ Р·Р°РЅРѕРІРѕ.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "cover"):
        return
    if cover_semaphore.locked():
        await callback.message.answer("РЎРµР№С‡Р°СЃ СѓР¶Рµ СЃРѕР±РёСЂР°СЋ РѕР±Р»РѕР¶РєСѓ. РџРѕСЃС‚Р°РІРёР» Р·Р°РґР°С‡Сѓ РІ РѕС‡РµСЂРµРґСЊ.")
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
    await callback.answer("Р”РµР»Р°СЋ 3 РІР°СЂРёР°РЅС‚Р°...")
    if not callback.from_user or not callback.message or not callback.data:
        return
    job_id = callback.data.split(":", 1)[1]
    job = cover_jobs.get(job_id)
    if not job:
        await callback.message.answer("Р­С‚Рѕ РІРёРґРµРѕ СѓР¶Рµ РЅРµ С…СЂР°РЅРёС‚СЃСЏ РґР»СЏ РѕР±Р»РѕР¶РєРё. РћС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ Р·Р°РЅРѕРІРѕ.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Р­С‚Р° РєРЅРѕРїРєР° РѕС‚ РґСЂСѓРіРѕРіРѕ РІРёРґРµРѕ. РћС‚РїСЂР°РІСЊ СЃРІРѕРµ РІРёРґРµРѕ РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ.")
        return
    if not job.path.exists():
        cover_jobs.pop(job_id, None)
        await callback.message.answer("Р¤Р°Р№Р» СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РџРµСЂРµСЃРѕР±РµСЂРё СЂРѕР»РёРє РёР»Рё РѕС‚РїСЂР°РІСЊ РІРёРґРµРѕ Р·Р°РЅРѕРІРѕ.")
        return
    if not await ensure_pro_feature(callback.message, callback.from_user.id, "Р•С‰Рµ 3 РІР°СЂРёР°РЅС‚Р° РѕР±Р»РѕР¶РєРё"):
        return
    if cover_semaphore.locked():
        await callback.message.answer("РЎРµР№С‡Р°СЃ СѓР¶Рµ СЃРѕР±РёСЂР°СЋ РѕР±Р»РѕР¶РєРё. РџРѕСЃС‚Р°РІРёР» Р·Р°РґР°С‡Сѓ РІ РѕС‡РµСЂРµРґСЊ.")
    async with cover_semaphore:
        await process_cover_variants(callback.message, bot, job, 3)


@router.callback_query(F.data.startswith("package:"))
async def publication_package_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer("РЎРѕР±РёСЂР°СЋ РїР°РєРµС‚...")
    if not callback.from_user or not callback.message or not callback.data:
        return
    job_id = callback.data.split(":", 1)[1]
    job = cover_jobs.get(job_id)
    if not job:
        await callback.message.answer("Р­С‚Рѕ РІРёРґРµРѕ СѓР¶Рµ РЅРµ С…СЂР°РЅРёС‚СЃСЏ РґР»СЏ РїР°РєРµС‚Р°. РћС‚РїСЂР°РІСЊ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ Р·Р°РЅРѕРІРѕ.")
        return
    if job.user_id != callback.from_user.id:
        await callback.message.answer("Р­С‚Р° РєРЅРѕРїРєР° РѕС‚ РґСЂСѓРіРѕРіРѕ РІРёРґРµРѕ. РћС‚РїСЂР°РІСЊ СЃРІРѕРµ РІРёРґРµРѕ РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ.")
        return
    if not job.path.exists():
        cover_jobs.pop(job_id, None)
        await callback.message.answer("Р¤Р°Р№Р» СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РџРµСЂРµСЃРѕР±РµСЂРё СЂРѕР»РёРє РёР»Рё РѕС‚РїСЂР°РІСЊ РІРёРґРµРѕ Р·Р°РЅРѕРІРѕ.")
        return
    if not await ensure_action_allowed(callback.message, callback.from_user.id, "package", "РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё РІС…РѕРґРёС‚ РІ Pro-С„СѓРЅРєС†РёРё."):
        return
    if cover_semaphore.locked():
        await callback.message.answer("РЎРµР№С‡Р°СЃ СѓР¶Рµ СЃРѕР±РёСЂР°СЋ РїР°РєРµС‚. РџРѕСЃС‚Р°РІРёР» Р·Р°РґР°С‡Сѓ РІ РѕС‡РµСЂРµРґСЊ.")
    async with cover_semaphore:
        await process_publication_package(callback.message, bot, job)


async def process_cover_variants(message: Message, bot: Bot, job: CoverJob, count: int = 3) -> list[Path]:
    started_at = time.time()
    output_dir = settings.output_dir / str(job.user_id) / "cover_variants" / uuid.uuid4().hex[:10]
    status = await message.answer(process_stage_text("Р’Р°СЂРёР°РЅС‚С‹ РѕР±Р»РѕР¶РєРё", ["РіРѕС‚РѕРІР»СЋ РІРёРґРµРѕ", "РіРµРЅРµСЂРёСЂСѓСЋ РІР°СЂРёР°РЅС‚С‹", "СЃРѕР±РёСЂР°СЋ ZIP", "РѕС‚РїСЂР°РІР»СЏСЋ PNG"], 1, job.title))
    state: dict[str, object] = {"started_at": started_at, "stage": "РћР±Р»РѕР¶РєРё: РіРѕС‚РѕРІР»СЋ РІР°СЂРёР°РЅС‚С‹", "detail": job.title}
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    covers: list[Path] = []
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        for index in range(1, count + 1):
            state["stage"] = f"РћР±Р»РѕР¶РєРё: РІР°СЂРёР°РЅС‚ {index}/{count}"
            await safe_edit(
                status,
                process_stage_text("Р’Р°СЂРёР°РЅС‚С‹ РѕР±Р»РѕР¶РєРё", ["РіРѕС‚РѕРІР»СЋ РІРёРґРµРѕ", "РіРµРЅРµСЂРёСЂСѓСЋ РІР°СЂРёР°РЅС‚С‹", "СЃРѕР±РёСЂР°СЋ ZIP", "РѕС‚РїСЂР°РІР»СЏСЋ PNG"], 2, f"Р’Р°СЂРёР°РЅС‚ {index}/{count}"),
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
                caption=f"РћР±Р»РѕР¶РєР° {index}/{count}\nР’РµСЃ: {human_size(cover_path.stat().st_size)}",
            )
        zip_path = output_dir / "cover_variants.zip"
        await asyncio.to_thread(zip_files, covers, zip_path)
        await safe_edit(
            status,
            process_stage_text("Р’Р°СЂРёР°РЅС‚С‹ РѕР±Р»РѕР¶РєРё", ["РіРѕС‚РѕРІР»СЋ РІРёРґРµРѕ", "РіРµРЅРµСЂРёСЂСѓСЋ РІР°СЂРёР°РЅС‚С‹", "СЃРѕР±РёСЂР°СЋ ZIP", "РѕС‚РїСЂР°РІР»СЏСЋ PNG"], 4, "Р’Р°СЂРёР°РЅС‚С‹ РѕС‚РїСЂР°РІР»РµРЅС‹", done=True),
        )
        await message.answer_document(
            FSInputFile(zip_path),
            caption=(
                f"Р“РѕС‚РѕРІРѕ: {count} РІР°СЂРёР°РЅС‚Р° РѕР±Р»РѕР¶РєРё РѕРґРЅРёРј ZIP\n"
                f"Р’СЂРµРјСЏ: {format_duration(time.time() - started_at)}"
                + next_steps_text("РІС‹Р±РµСЂРё Р»СѓС‡С€РёР№ PNG", "РµСЃР»Рё РЅСѓР¶РµРЅ РїРѕР»РЅС‹Р№ РЅР°Р±РѕСЂ, РЅР°Р¶РјРё В«РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё ZIPВ»")
            ),
            reply_markup=cover_tools_keyboard(remember_cover_job(job.user_id, job.path, job.title, job.duration_seconds)),
        )
        return covers
    except Exception as exc:
        logger.exception("Cover variants failed")
        await safe_edit(status, f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ СЃРґРµР»Р°С‚СЊ РІР°СЂРёР°РЅС‚С‹ РѕР±Р»РѕР¶РєРё: {exc}")
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
    state: dict[str, object] = {"started_at": started_at, "stage": "РћР±Р»РѕР¶РєР° PNG: РїРѕРґРіРѕС‚РѕРІРєР°", "detail": source.name}
    status = await message.answer(process_stage_text("Р“РµРЅРµСЂР°С†РёСЏ РѕР±Р»РѕР¶РєРё PNG", COVER_STEPS, 1, source.name))
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        info = await asyncio.to_thread(inspect_video, source)
        duration = duration_seconds or info.duration_seconds or 0
        resolution = f"{info.width}x{info.height}" if info.width and info.height else "unknown"
        state["stage"] = "РћР±Р»РѕР¶РєР° PNG: РІС‹Р±РёСЂР°СЋ РєР°РґСЂ"
        state["detail"] = f"{title}\n{resolution}, {format_duration(duration)}"
        await safe_edit(
            status,
            process_stage_text(
                "Р“РµРЅРµСЂР°С†РёСЏ РѕР±Р»РѕР¶РєРё PNG",
                COVER_STEPS,
                2,
                f"Р’РёРґРµРѕ: {resolution}, РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(duration)}",
            ),
        )
        state["stage"] = "РћР±Р»РѕР¶РєР° PNG: РёС‰Сѓ С‚РµРјСѓ Рё РєР°СЂС‚РёРЅРєРё"
        await safe_edit(
            status,
            process_stage_text("Р“РµРЅРµСЂР°С†РёСЏ РѕР±Р»РѕР¶РєРё PNG", COVER_STEPS, 3, "РћРїСЂРµРґРµР»СЏСЋ С‚РµРјСѓ РїРѕ РЅР°Р·РІР°РЅРёСЋ Рё РёС‰Сѓ РїРѕРґС…РѕРґСЏС‰РёРµ РІРёР·СѓР°Р»СЊРЅС‹Рµ РІСЃС‚Р°РІРєРё"),
        )
        state["stage"] = "РћР±Р»РѕР¶РєР° PNG: СЃРѕР±РёСЂР°СЋ РјР°РєРµС‚"
        cover_path = await asyncio.to_thread(
            create_business_cover,
            source,
            output_dir,
            title,
            duration,
            settings.video_timeout_seconds,
            settings.face_detection_enabled,
        )
        state["stage"] = "РћР±Р»РѕР¶РєР° PNG: РѕС‚РїСЂР°РІР»СЏСЋ С„Р°Р№Р»"
        state["detail"] = f"Р Р°Р·РјРµСЂ: {human_size(cover_path.stat().st_size)}"
        await safe_edit(
            status,
            process_stage_text("Р“РµРЅРµСЂР°С†РёСЏ РѕР±Р»РѕР¶РєРё PNG", COVER_STEPS, 5, f"Р Р°Р·РјРµСЂ: {human_size(cover_path.stat().st_size)}"),
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
                "Р“РѕС‚РѕРІРѕ: PNG-РѕР±Р»РѕР¶РєР° РґР»СЏ РІРёРґРµРѕ\n"
                f"Р¤РѕСЂРјР°С‚: 1280x720 PNG\n"
                f"Р’РµСЃ: {human_size(cover_path.stat().st_size)}\n"
                f"Р’СЂРµРјСЏ РѕР±СЂР°Р±РѕС‚РєРё: {format_duration(time.time() - started_at)}"
                + next_steps_text("СЃРєР°С‡Р°Р№ PNG", "РЅР°Р¶РјРё В«Р•С‰Рµ 3 РІР°СЂРёР°РЅС‚Р°В», РµСЃР»Рё С…РѕС‡РµС€СЊ РІС‹Р±РѕСЂ", "РјРѕР¶РЅРѕ СЃРѕР±СЂР°С‚СЊ РїР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё ZIP")
            ),
            reply_markup=cover_tools_keyboard(tools_job_id),
        )
        await safe_edit(
            status,
            process_stage_text("Р“РµРЅРµСЂР°С†РёСЏ РѕР±Р»РѕР¶РєРё PNG", COVER_STEPS, 5, "Р¤Р°Р№Р» РѕС‚РїСЂР°РІР»РµРЅ", done=True)
            + next_steps_text("СЃРєР°С‡Р°Р№ PNG", "РґР»СЏ РґСЂСѓРіРѕРіРѕ РєР°РґСЂР° РЅР°Р¶РјРё РєРЅРѕРїРєСѓ РѕР±Р»РѕР¶РєРё РµС‰Рµ СЂР°Р·"),
        )
        return cover_path
    except Exception as exc:
        logger.exception("Cover job failed")
        await safe_edit(
            status,
            f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ СЃРґРµР»Р°С‚СЊ РѕР±Р»РѕР¶РєСѓ: {exc}"
            + next_steps_text("РїРѕРїСЂРѕР±СѓР№ РґСЂСѓРіРѕРµ РІРёРґРµРѕ", "РёР»Рё РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ Рё РІС‹Р±РµСЂРё РѕР±Р»РѕР¶РєСѓ"),
        )
        return None
    finally:
        heartbeat_task.cancel()


async def process_publication_package(message: Message, bot: Bot, job: CoverJob) -> Path | None:
    started_at = time.time()
    output_dir = settings.output_dir / str(job.user_id) / "publication_package" / uuid.uuid4().hex[:10]
    output_dir.mkdir(parents=True, exist_ok=True)
    status = await message.answer(process_stage_text("РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё", PUBLICATION_STEPS, 1, job.title))
    state: dict[str, object] = {"started_at": started_at, "stage": "РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё: РїРѕРґРіРѕС‚РѕРІРєР°", "detail": job.title}
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    package_files: list[Path] = []
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        info = await asyncio.to_thread(inspect_video, job.path)
        package_files.append(job.path)

        state["stage"] = "РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё: РѕР±Р»РѕР¶РєР°"
        await safe_edit(status, process_stage_text("РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё", PUBLICATION_STEPS, 2, "Р“РµРЅРµСЂРёСЂСѓСЋ PNG-РѕР±Р»РѕР¶РєСѓ"))
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

        state["stage"] = "РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё: СЃСѓР±С‚РёС‚СЂС‹"
        await safe_edit(status, process_stage_text("РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё", PUBLICATION_STEPS, 3, "РџСЂРѕР±СѓСЋ РґРѕР±Р°РІРёС‚СЊ Pop-СЃСѓР±С‚РёС‚СЂС‹"))
        subtitled_path: Path | None = None
        subtitle_note = "РЎСѓР±С‚РёС‚СЂС‹: СЂРµС‡СЊ РЅРµ РЅР°Р№РґРµРЅР° РёР»Рё СЂР°СЃРїРѕР·РЅР°РІР°РЅРёРµ РЅРµРґРѕСЃС‚СѓРїРЅРѕ."
        transcript_text = ""
        try:
            cues = await asyncio.to_thread(
                transcribe_subtitle_cues,
                job.path,
                settings.subtitle_model,
                settings.subtitle_language or None,
            )
            if cues:
                transcript_text = " ".join(cue.text for cue in cues[:24] if getattr(cue, "text", ""))
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
                subtitle_note = f"РЎСѓР±С‚РёС‚СЂС‹: РґРѕР±Р°РІР»РµРЅС‹, С„СЂР°Р· РЅР°Р№РґРµРЅРѕ: {len(cues)}."
        except Exception:
            logger.exception("Publication package subtitles failed")

        state["stage"] = "РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё: РѕРїРёСЃР°РЅРёРµ"
        await safe_edit(status, process_stage_text("РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё", PUBLICATION_STEPS, 4, "РџРёС€Сѓ РѕРїРёСЃР°РЅРёРµ Рё С…РµС€С‚РµРіРё"))
        description_path = output_dir / "description.txt"
        hashtags = publication_hashtags(job.title, transcript_text)
        description_path.write_text(
            publication_description(
                job.title,
                info.duration_seconds,
                hashtags,
                subtitle_note,
                transcript_text,
                settings.subtitle_language,
            ),
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

        state["stage"] = "РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё: ZIP"
        await safe_edit(status, process_stage_text("РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё", PUBLICATION_STEPS, 5, "РЈРїР°РєРѕРІС‹РІР°СЋ С„Р°Р№Р»С‹"))
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

        state["stage"] = "РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё: РѕС‚РїСЂР°РІР»СЏСЋ"
        await safe_edit(status, process_stage_text("РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё", PUBLICATION_STEPS, 6, f"Р Р°Р·РјРµСЂ ZIP: {human_size(zip_path.stat().st_size)}"))
        caption = (
            "Р“РѕС‚РѕРІРѕ: РїР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё ZIP\n"
            "Р’РЅСѓС‚СЂРё: РІРёРґРµРѕ, PNG-РѕР±Р»РѕР¶РєР°, РѕРїРёСЃР°РЅРёРµ, С…РµС€С‚РµРіРё"
            + (", РІРµСЂСЃРёСЏ СЃ СЃСѓР±С‚РёС‚СЂР°РјРё" if subtitled_path else "")
            + f"\nР’РµСЃ: {human_size(zip_path.stat().st_size)}\n"
            f"Р’СЂРµРјСЏ: {format_duration(time.time() - started_at)}"
        )
        if zip_path.stat().st_size <= TELEGRAM_SAFE_UPLOAD_BYTES:
            await message.answer_document(FSInputFile(zip_path), caption=caption)
        else:
            await message.answer(caption + "\nZIP Р±РѕР»СЊС€РѕР№ РґР»СЏ РѕС‚РїСЂР°РІРєРё РѕРґРЅРёРј С„Р°Р№Р»РѕРј, РѕС‚РїСЂР°РІР»СЏСЋ РєР»СЋС‡РµРІС‹Рµ С„Р°Р№Р»С‹ РѕС‚РґРµР»СЊРЅРѕ.")
            await message.answer_document(FSInputFile(cover_path), caption="PNG-РѕР±Р»РѕР¶РєР° РёР· РїР°РєРµС‚Р°")
            await message.answer_document(FSInputFile(description_path), caption="РћРїРёСЃР°РЅРёРµ Рё С…РµС€С‚РµРіРё")
            if subtitled_path:
                await message.answer_document(FSInputFile(subtitled_path), caption="Р’РёРґРµРѕ СЃ СЃСѓР±С‚РёС‚СЂР°РјРё")
        await safe_edit(
            status,
            process_stage_text("РџР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё", PUBLICATION_STEPS, 6, "РџР°РєРµС‚ РѕС‚РїСЂР°РІР»РµРЅ", done=True)
            + next_steps_text("СЃРєР°С‡Р°Р№ ZIP", "РІС‹Р±РµСЂРё РѕР±Р»РѕР¶РєСѓ РёР»Рё РѕС‚РїСЂР°РІСЊ РЅРѕРІС‹Р№ С„Р°Р№Р»"),
        )
        return zip_path
    except Exception as exc:
        logger.exception("Publication package failed")
        await safe_edit(
            status,
            f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ СЃРѕР±СЂР°С‚СЊ РїР°РєРµС‚ РїСѓР±Р»РёРєР°С†РёРё: {exc}"
            + next_steps_text("РїРѕРїСЂРѕР±СѓР№ РєРѕСЂРѕС‡Рµ РІРёРґРµРѕ", "РёР»Рё РѕС‚РґРµР»СЊРЅРѕ СЃРґРµР»Р°Р№ РѕР±Р»РѕР¶РєСѓ/СЃСѓР±С‚РёС‚СЂС‹"),
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
    state: dict[str, object] = {"started_at": started_at, "stage": f"{source_label}: С‡РёС‚Р°СЋ РІРёРґРµРѕ", "detail": ""}
    status = await message.answer(
        f"{source_label}-СЃСЃС‹Р»РєР° РїСЂРёРЅСЏС‚Р°.\n\n"
        "Р РµР¶РёРј: СЃРєР°С‡Р°С‚СЊ MP4\n"
        "РЇ СЃРєР°С‡Р°СЋ РґРѕСЃС‚СѓРїРЅС‹Р№ С„Р°Р№Р» Рё РїСЂРё РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё РєРѕРЅРІРµСЂС‚РёСЂСѓСЋ РµРіРѕ РІ MP4. РЈРґР°Р»РµРЅРёРµ watermark РЅРµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ."
    )
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        metadata = await asyncio.to_thread(get_youtube_metadata, url, settings.youtube_download_timeout_seconds)
        max_duration = settings.youtube_max_duration_minutes * 60
        if metadata.duration_seconds > max_duration:
            await safe_edit(
                status,
                f"Р’РёРґРµРѕ СЃР»РёС€РєРѕРј РґР»РёРЅРЅРѕРµ: {format_duration(metadata.duration_seconds)}.\n"
                f"Р›РёРјРёС‚ СЃРµР№С‡Р°СЃ: {settings.youtube_max_duration_minutes} РјРёРЅСѓС‚.",
            )
            return
        state["stage"] = f"{source_label}: СЃРєР°С‡РёРІР°СЋ С„Р°Р№Р»"
        state["detail"] = f"{metadata.title}\nР”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(metadata.duration_seconds)}"
        await safe_edit(
            status,
            f"РЎРєР°С‡РёРІР°СЋ {source_label}-РІРёРґРµРѕ.\n"
            f"РќР°Р·РІР°РЅРёРµ: {metadata.title}\n"
            f"Р”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(metadata.duration_seconds)}",
        )
        download = await asyncio.to_thread(download_youtube_video, url, source_dir, settings.youtube_download_timeout_seconds)
        source_size = download.path.stat().st_size
        result_path = download.path
        result_info = inspect_video(result_path)
        if result_path.suffix.lower() != ".mp4":
            state["stage"] = f"{source_label}: РєРѕРЅРІРµСЂС‚РёСЂСѓСЋ РІ MP4"
            await safe_edit(
                status,
                f"РСЃС‚РѕС‡РЅРёРє СЃРєР°С‡Р°Р»СЃСЏ РєР°Рє {result_path.suffix.lstrip('.').upper() or 'РІРёРґРµРѕ'}.\n"
                "РљРѕРЅРІРµСЂС‚РёСЂСѓСЋ РІ MP4, С‡С‚РѕР±С‹ Telegram РѕС‚РїСЂР°РІРёР» РёРјРµРЅРЅРѕ РІРёРґРµРѕС„Р°Р№Р».",
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
                f"Р¤Р°Р№Р» СЃРєР°С‡Р°РЅ, РЅРѕ РѕРЅ СЃР»РёС€РєРѕРј Р±РѕР»СЊС€РѕР№ РґР»СЏ РѕС‚РїСЂР°РІРєРё Р±РѕС‚РѕРј: {human_size(size)}.\n"
                "РњРѕР¶РЅРѕ РІС‹Р±СЂР°С‚СЊ Shorts РёР»Рё Preview, С‡С‚РѕР±С‹ РїРѕР»СѓС‡РёС‚СЊ РјРµРЅСЊС€РёР№ СЂРѕР»РёРє.",
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
                f"{source_label}: MP4 РіРѕС‚РѕРІ\n"
                f"Р¤Р°Р№Р»: {download.title}\n"
                f"Р”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(result_info.duration_seconds or download.duration_seconds)}\n"
                f"Р’РµСЃ: {human_size(size)}\n\n"
                "РЈРґР°Р»РµРЅРёРµ watermark РЅРµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ. РќРёР¶Рµ РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ СЃСѓР±С‚РёС‚СЂС‹ РёР»Рё СЃРґРµР»Р°С‚СЊ РѕР±Р»РѕР¶РєСѓ."
            ),
            reply_markup=media_tools_keyboard(subtitle_id, cover_id),
        )
        await safe_edit(status, f"Р“РѕС‚РѕРІРѕ: {source_label}-MP4 РѕС‚РїСЂР°РІР»РµРЅ.")
    except Exception as exc:
        logger.exception("%s source download failed", source_label)
        await safe_edit(
            status,
            f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ СЃРєР°С‡Р°С‚СЊ {source_label}-СЃСЃС‹Р»РєСѓ: {exc}\n"
            "Р•СЃР»Рё СЌС‚Рѕ РїСЂРёРІР°С‚РЅРѕРµ РІРёРґРµРѕ РёР»Рё РёСЃС‚РѕС‡РЅРёРє РѕРіСЂР°РЅРёС‡РёР» СЃРєР°С‡РёРІР°РЅРёРµ, РѕС‚РїСЂР°РІСЊ РІРёРґРµРѕ С„Р°Р№Р»РѕРј.",
        )
    finally:
        heartbeat_task.cancel()


async def process_youtube_cover_link(message: Message, bot: Bot, url: str, lang: str, user_id: int) -> None:
    started_at = time.time()
    source_label = video_source_label(url)
    job_id = uuid.uuid4().hex[:10]
    source_dir = settings.storage_dir / str(user_id) / "youtube_cover" / job_id
    output_dir = settings.output_dir / str(user_id) / "youtube_cover" / job_id
    state: dict[str, object] = {"started_at": started_at, "stage": f"РћР±Р»РѕР¶РєР° {source_label}: С‡РёС‚Р°СЋ РІРёРґРµРѕ", "detail": ""}
    status = await message.answer(
        f"РџСЂРёРЅСЏР» {source_label}-СЃСЃС‹Р»РєСѓ. РџРѕРґРіРѕС‚РѕРІР»СЋ PNG-РѕР±Р»РѕР¶РєСѓ РїРѕ РІРёРґРµРѕ.\n\n"
        "Р РµР¶РёРј: РѕР±Р»РѕР¶РєР° PNG\n"
        "Р­С‚Р°Рї 1/5: С‡РёС‚Р°СЋ РґР°РЅРЅС‹Рµ РІРёРґРµРѕ."
    )
    heartbeat_task = asyncio.create_task(heartbeat(status, state))
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        metadata = await asyncio.to_thread(get_youtube_metadata, url, settings.youtube_download_timeout_seconds)
        max_duration = settings.youtube_max_duration_minutes * 60
        if metadata.duration_seconds > max_duration:
            await safe_edit(
                status,
                f"Р’РёРґРµРѕ СЃР»РёС€РєРѕРј РґР»РёРЅРЅРѕРµ: {format_duration(metadata.duration_seconds)}.\n"
                f"Р›РёРјРёС‚ СЃРµР№С‡Р°СЃ: {settings.youtube_max_duration_minutes} РјРёРЅСѓС‚.",
            )
            return
        size_text = human_size(metadata.estimated_size_bytes) if metadata.estimated_size_bytes else "РЅРµ СѓРґР°Р»РѕСЃСЊ РѕС†РµРЅРёС‚СЊ Р·Р°СЂР°РЅРµРµ"
        state["stage"] = f"РћР±Р»РѕР¶РєР° {source_label}: СЃРєР°С‡РёРІР°СЋ РІРёРґРµРѕ"
        state["detail"] = f"{metadata.title}\nР”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(metadata.duration_seconds)}"
        await safe_edit(
            status,
            "Р РµР¶РёРј: РѕР±Р»РѕР¶РєР° PNG\n"
            "Р­С‚Р°Рї 2/5: СЃРєР°С‡РёРІР°СЋ РІРёРґРµРѕ.\n"
            f"РќР°Р·РІР°РЅРёРµ: {metadata.title}\n"
            f"Р”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(metadata.duration_seconds)}\n"
            f"РџСЂРёРјРµСЂРЅС‹Р№ СЂР°Р·РјРµСЂ: {size_text}",
        )
        download = await asyncio.to_thread(download_youtube_video, url, source_dir, settings.youtube_download_timeout_seconds)
        state["stage"] = "РћР±Р»РѕР¶РєР° YouTube: РІС‹Р±РёСЂР°СЋ РєР°РґСЂ"
        state["detail"] = f"РЎРєР°С‡Р°РЅРѕ: {human_size(download.path.stat().st_size)}"
        await safe_edit(
            status,
            "Р РµР¶РёРј: РѕР±Р»РѕР¶РєР° PNG\n"
            "Р­С‚Р°Рї 3/5: РІРёРґРµРѕ СЃРєР°С‡Р°РЅРѕ, РІС‹Р±РёСЂР°СЋ СЃРёР»СЊРЅС‹Р№ РєР°РґСЂ.\n"
            f"Р¤Р°Р№Р»: {download.title}\n"
            f"РЎРєР°С‡Р°РЅРѕ: {human_size(download.path.stat().st_size)}",
        )
        state["stage"] = "РћР±Р»РѕР¶РєР° YouTube: СЃРѕР±РёСЂР°СЋ PNG"
        await safe_edit(
            status,
            "Р РµР¶РёРј: РѕР±Р»РѕР¶РєР° PNG\n"
            "Р­С‚Р°Рї 4/5: РѕРїСЂРµРґРµР»СЏСЋ С‚РµРјСѓ, РёС‰Сѓ РІРёР·СѓР°Р»СЊРЅС‹Рµ РІСЃС‚Р°РІРєРё Рё СЃРѕР±РёСЂР°СЋ СЏСЂРєСѓСЋ 1280x720 PNG-РѕР±Р»РѕР¶РєСѓ.",
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
        state["stage"] = "РћР±Р»РѕР¶РєР° YouTube: РѕС‚РїСЂР°РІР»СЏСЋ PNG"
        state["detail"] = f"Р Р°Р·РјРµСЂ: {human_size(cover_path.stat().st_size)}"
        await safe_edit(
            status,
            "Р РµР¶РёРј: РѕР±Р»РѕР¶РєР° PNG\n"
            "Р­С‚Р°Рї 5/5: РѕС‚РїСЂР°РІР»СЏСЋ РіРѕС‚РѕРІС‹Р№ PNG.\n"
            f"Р Р°Р·РјРµСЂ: {human_size(cover_path.stat().st_size)}",
        )
        await message.answer_document(
            FSInputFile(cover_path),
            caption=(
                "Р“РѕС‚РѕРІРѕ: PNG-РѕР±Р»РѕР¶РєР° РїРѕ YouTube-СЃСЃС‹Р»РєРµ\n"
                f"РСЃС‚РѕС‡РЅРёРє: {download.title}\n"
                f"Р¤РѕСЂРјР°С‚: 1280x720 PNG\n"
                f"Р’РµСЃ: {human_size(cover_path.stat().st_size)}\n"
                f"Р’СЂРµРјСЏ РѕР±СЂР°Р±РѕС‚РєРё: {format_duration(time.time() - started_at)}"
                + next_steps_text("СЃРєР°С‡Р°Р№ PNG", "РјРѕР¶РЅРѕ СЃРЅРѕРІР° РѕС‚РїСЂР°РІРёС‚СЊ СЃСЃС‹Р»РєСѓ Рё РІС‹Р±СЂР°С‚СЊ РјРѕРЅС‚Р°Р¶ РёР»Рё Shorts")
            ),
            reply_markup=cover_tools_keyboard(cover_job_id),
        )
        await safe_edit(
            status,
            "Р“РѕС‚РѕРІРѕ. PNG-РѕР±Р»РѕР¶РєР° РѕС‚РїСЂР°РІР»РµРЅР°."
            + next_steps_text("СЃРєР°С‡Р°Р№ PNG", "РґР»СЏ РјРѕРЅС‚Р°Р¶Р° РѕС‚РїСЂР°РІСЊ СЃСЃС‹Р»РєСѓ РµС‰Рµ СЂР°Р· Рё РІС‹Р±РµСЂРё Shorts РёР»Рё Preview"),
        )
    except Exception as exc:
        logger.exception("YouTube cover job failed")
        await safe_edit(
            status,
            f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ СЃРґРµР»Р°С‚СЊ РѕР±Р»РѕР¶РєСѓ РїРѕ YouTube-СЃСЃС‹Р»РєРµ: {exc}"
            + next_steps_text("РїРѕРїСЂРѕР±СѓР№ РґСЂСѓРіСѓСЋ СЃСЃС‹Р»РєСѓ", "РёР»Рё РѕС‚РїСЂР°РІСЊ РІРёРґРµРѕ С„Р°Р№Р»РѕРј"),
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
    state: dict[str, object] = {"started_at": started_at, "stage": "Р­С‚Р°Рї 1/6: С‡РёС‚Р°СЋ РґР°РЅРЅС‹Рµ РІРёРґРµРѕ", "detail": ""}
    status = await message.answer(
        f"РџСЂРёРЅСЏР» {source_label}-СЃСЃС‹Р»РєСѓ. РЎРєР°С‡Р°СЋ РІРёРґРµРѕ Рё РѕР±СЂР°Р±РѕС‚Р°СЋ РІС‹Р±СЂР°РЅРЅС‹Р№ СЂРµР¶РёРј.\n\n"
        f"Р РµР¶РёРј: {mode_label}\n"
        "Р­С‚Р°Рї 1/6: С‡РёС‚Р°СЋ РґР°РЅРЅС‹Рµ РІРёРґРµРѕ.\n"
        "Р§С‚Рѕ РїСЂРѕРёСЃС…РѕРґРёС‚: РїРѕР»СѓС‡Р°СЋ РЅР°Р·РІР°РЅРёРµ, РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ Рё РїСЂРёРјРµСЂРЅС‹Р№ СЂР°Р·РјРµСЂ Р±РµР· СЃРєР°С‡РёРІР°РЅРёСЏ."
    )
    heartbeat_task = asyncio.create_task(heartbeat(status, state))

    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
        metadata = await asyncio.to_thread(get_youtube_metadata, url, settings.youtube_download_timeout_seconds)
        max_duration = settings.youtube_max_duration_minutes * 60
        if metadata.duration_seconds > max_duration:
            await safe_edit(
                status,
                f"Р’РёРґРµРѕ СЃР»РёС€РєРѕРј РґР»РёРЅРЅРѕРµ: {format_duration(metadata.duration_seconds)}.\n"
                f"Р›РёРјРёС‚ СЃРµР№С‡Р°СЃ: {settings.youtube_max_duration_minutes} РјРёРЅСѓС‚.",
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
                await safe_edit(status, "Р’РёРґРµРѕ СЃР»РёС€РєРѕРј РєРѕСЂРѕС‚РєРѕРµ РґР»СЏ Preview-РјРѕРЅС‚Р°Р¶Р°.")
                return
            plan_text = (
                f"РџР»Р°РЅ: РѕРґРёРЅ С€РёСЂРѕРєРёР№ СЂРѕР»РёРє 16:9 РґРѕ {output_length} СЃРµРє., "
                f"РјРѕРЅС‚Р°Р¶РЅС‹С… С„СЂР°РіРјРµРЅС‚РѕРІ: {planned_clips}, Р·Р°СЃС‚Р°РІРєР°: {profile.backstage_intro_seconds} СЃРµРє."
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
                await safe_edit(status, "Р’РёРґРµРѕ СЃР»РёС€РєРѕРј РєРѕСЂРѕС‚РєРѕРµ РґР»СЏ Shorts-РЅР°СЂРµР·РєРё.")
                return
            plan_text = f"РџР»Р°РЅ РєР»РёРїРѕРІ: {planned_clips} x {profile.short_seconds} СЃРµРє."
            cut_estimate = estimate_cut_time(
                metadata.duration_seconds,
                planned_clips,
                profile.short_seconds,
                settings.face_detection_enabled,
            )

        size_text = human_size(metadata.estimated_size_bytes) if metadata.estimated_size_bytes else "РЅРµ СѓРґР°Р»РѕСЃСЊ РѕС†РµРЅРёС‚СЊ Р·Р°СЂР°РЅРµРµ"
        state["stage"] = "Р­С‚Р°Рї 2/6: СЃРєР°С‡РёРІР°СЋ РІРёРґРµРѕ"
        state["detail"] = f"{metadata.title}\nР”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(metadata.duration_seconds)}"
        await safe_edit(
            status,
            f"Р РµР¶РёРј: {mode_label}\n"
            "Р­С‚Р°Рї 2/6: СЃРєР°С‡РёРІР°СЋ РІРёРґРµРѕ.\n"
            f"РќР°Р·РІР°РЅРёРµ: {metadata.title}\n"
            f"Р”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(metadata.duration_seconds)}\n"
            f"РџСЂРёРјРµСЂРЅС‹Р№ СЂР°Р·РјРµСЂ Р·Р°РіСЂСѓР·РєРё: {size_text}\n"
            f"РџСЂРёРјРµСЂРЅРѕРµ РІСЂРµРјСЏ Р·Р°РіСЂСѓР·РєРё: {estimate_download_time(metadata.estimated_size_bytes)}\n"
            f"{plan_text}\n"
            f"РћС†РµРЅРєР° РѕР±СЂР°Р±РѕС‚РєРё РїРѕСЃР»Рµ Р·Р°РіСЂСѓР·РєРё: {cut_estimate}\n\n"
            "РџРѕС‡РµРјСѓ РјРѕР¶РµС‚ Р±С‹С‚СЊ РґРѕР»РіРѕ: YouTube РѕС‚РґР°РµС‚ РґР»РёРЅРЅС‹Рµ РІРёРґРµРѕ РєСѓСЃРєР°РјРё, СЃРєРѕСЂРѕСЃС‚СЊ Р·Р°РІРёСЃРёС‚ РѕС‚ СЃРµС‚Рё Рё СЃР°РјРѕРіРѕ YouTube.",
        )

        download = await asyncio.to_thread(download_youtube_video, url, source_dir, settings.youtube_download_timeout_seconds)
        state["stage"] = "Р­С‚Р°Рї 3/6: РіРѕС‚РѕРІР»СЋ С‚РѕС‡РєРё РЅР°СЂРµР·РєРё"
        state["detail"] = f"РЎРєР°С‡Р°РЅРѕ: {human_size(download.path.stat().st_size)}"
        await safe_edit(
            status,
            f"Р РµР¶РёРј: {mode_label}\n"
            "Р­С‚Р°Рї 3/6: РІРёРґРµРѕ СЃРєР°С‡Р°РЅРѕ, РіРѕС‚РѕРІР»СЋ С‚РѕС‡РєРё РЅР°СЂРµР·РєРё.\n"
            f"Р¤Р°Р№Р»: {download.title}\n"
            f"РЎРєР°С‡Р°РЅРѕ: {human_size(download.path.stat().st_size)}\n"
            f"Р”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(download.duration_seconds)}\n"
            + (
                "Р”Р°Р»СЊС€Рµ СЃРѕР±РµСЂСѓ РѕРґРёРЅ С€РёСЂРѕРєРёР№ Preview-СЂРѕР»РёРє СЃРѕ Р·Р°СЃС‚Р°РІРєРѕР№."
                if profile.is_backstage
                else "Р”Р°Р»СЊС€Рµ РєР°Р¶РґС‹Р№ РіРѕС‚РѕРІС‹Р№ РєР»РёРї РѕС‚РїСЂР°РІР»СЋ СЃСЂР°Р·Сѓ, РЅРµ РґРѕР¶РёРґР°СЏСЃСЊ РІСЃРµР№ РїР°С‡РєРё."
            ),
        )

        if profile.is_backstage and settings.youtube_backstage_enabled:
            state["stage"] = "Р­С‚Р°Рї 4/6: СЃРѕР±РёСЂР°СЋ С€РёСЂРѕРєРёР№ Preview-РјРѕРЅС‚Р°Р¶"
            state["detail"] = "РС‰Сѓ РјРѕРјРµРЅС‚С‹, РґРµР»Р°СЋ Р·Р°СЃС‚Р°РІРєСѓ Рё СЃРєР»РµРёРІР°СЋ 16:9"
            await safe_edit(
                status,
                f"Р РµР¶РёРј: {mode_label}\n"
                "Р­С‚Р°Рї 4/6: СЃРѕР±РёСЂР°СЋ С€РёСЂРѕРєРёР№ Preview-РјРѕРЅС‚Р°Р¶.\n"
                "Р§С‚Рѕ РїСЂРѕРёСЃС…РѕРґРёС‚: Р°РЅР°Р»РёР·РёСЂСѓСЋ РґРІРёР¶РµРЅРёРµ, Р»РёС†Р°, СЃРјРµРЅС‹ РєР°РґСЂР°, РїР°СѓР·С‹ Рё РёРЅС‚РѕРЅР°С†РёРѕРЅРЅС‹Рµ РІСЃРїР»РµСЃРєРё, РґРµР»Р°СЋ Р·Р°СЃС‚Р°РІРєСѓ Рё СЃРєР»РµР№РєСѓ.\n"
                f"Р¤РѕСЂРјР°С‚: 16:9, РґРѕ {profile.backstage_output_seconds} СЃРµРє.\n"
                "Р­С‚Рѕ РјРѕР¶РµС‚ Р·Р°РЅСЏС‚СЊ РЅРµСЃРєРѕР»СЊРєРѕ РјРёРЅСѓС‚ РЅР° РґР»РёРЅРЅРѕРј РІРёРґРµРѕ.",
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
            state["stage"] = "Р­С‚Р°Рї 5/6: РѕС‚РїСЂР°РІР»СЏСЋ Preview-СЂРѕР»РёРє"
            state["detail"] = f"Р Р°Р·РјРµСЂ: {human_size(montage.path.stat().st_size)}"
            await safe_edit(
                status,
                f"Р РµР¶РёРј: {mode_label}\n"
                "Р­С‚Р°Рї 5/6: СЂРѕР»РёРє РіРѕС‚РѕРІ, РѕС‚РїСЂР°РІР»СЏСЋ С„Р°Р№Р».\n"
                f"Р Р°Р·РјРµСЂ: {human_size(montage.path.stat().st_size)}",
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
                    "Р“РѕС‚РѕРІРѕ: Preview-РјРѕРЅС‚Р°Р¶\n"
                    f"РСЃС‚РѕС‡РЅРёРє: {download.title}\n"
                    "Р¤РѕСЂРјР°С‚: С€РёСЂРѕРєРѕРµ РІРёРґРµРѕ 16:9, MP4\n"
                    f"Р”Р»РёРЅР°: РґРѕ {profile.backstage_output_seconds} СЃРµРє.\n"
                    f"Р’РµСЃ: {human_size(montage.path.stat().st_size)}\n"
                    f"РћР±С‰РµРµ РІСЂРµРјСЏ РѕР±СЂР°Р±РѕС‚РєРё: {format_duration(time.time() - started_at)}"
                    f"{AFTER_RESULT_HINT}"
                ),
                reply_markup=youtube_replay_keyboard(replay_id, mode, subtitle_id, cover_id),
            )
            if cover_path:
                await message.answer_document(FSInputFile(cover_path), caption="PNG-РѕР±Р»РѕР¶РєР° РґР»СЏ СЌС‚РѕРіРѕ РјРѕРЅС‚Р°Р¶Р°.")
            await safe_edit(
                status,
                "Р“РѕС‚РѕРІРѕ. Preview-СЂРѕР»РёРє РѕС‚РїСЂР°РІР»РµРЅ."
                + next_steps_text(
                    "СЃРєР°С‡Р°Р№ MP4",
                    "РЅР°Р¶РјРё Subtitles, РµСЃР»Рё РЅСѓР¶РЅС‹ СЃСѓР±С‚РёС‚СЂС‹",
                    "РЅР°Р¶РјРё Redo, РµСЃР»Рё С…РѕС‡РµС€СЊ РґСЂСѓРіРѕР№ С‚РµРјРї РјРѕРЅС‚Р°Р¶Р°",
                    "РѕС‚РїСЂР°РІСЊ СЃР»РµРґСѓСЋС‰РёР№ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ",
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
            profile.mode,
        )
        clips = []
        base_name = clean_base_name(download.title, "youtube_short")
        state["stage"] = "Р­С‚Р°Рї 4/6: С‡РёС‚Р°СЋ РїР°СЂР°РјРµС‚СЂС‹ РІРёРґРµРѕ"
        state["detail"] = "Р“РѕС‚РѕРІР»СЋ face-focus Рё РІРµСЂС‚РёРєР°Р»СЊРЅС‹Р№ crop"
        source_info = await asyncio.to_thread(inspect_video, download.path)

        for index, start_second in enumerate(starts, start=1):
            state["detail"] = f"РљР»РёРї {index}/{len(starts)}, СЃС‚Р°СЂС‚ {format_duration(start_second)}"
            await safe_edit(
                status,
                f"Р РµР¶РёРј: {mode_label}\n"
                "Р­С‚Р°Рї 4/6: СЂРµР¶Сѓ Shorts РїРѕ РѕРґРЅРѕРјСѓ.\n"
                f"РЎРµР№С‡Р°СЃ: РєР»РёРї {index}/{len(starts)}\n"
            f"РЎС‚Р°СЂС‚ С„СЂР°РіРјРµРЅС‚Р°: {format_duration(start_second)}\n"
            "Р§С‚Рѕ РїСЂРѕРёСЃС…РѕРґРёС‚: РІС‹Р±РёСЂР°СЋ РјРѕРјРµРЅС‚ РїРѕ Р»РёС†Р°Рј, РґРІРёР¶РµРЅРёСЋ, РїР°СѓР·Р°Рј Рё РёРЅС‚РѕРЅР°С†РёРё, РґРµР»Р°СЋ РІРµСЂС‚РёРєР°Р»СЊРЅС‹Р№ 1080x1920, РєРѕРґРёСЂСѓСЋ MP4.\n"
                "РљР°Рє С‚РѕР»СЊРєРѕ РєР»РёРї РіРѕС‚РѕРІ, СЃСЂР°Р·Сѓ РѕС‚РїСЂР°РІР»СЏСЋ РµРіРѕ СЃСЋРґР°.",
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
                    f"РЎС‚Р°СЂС‚: {format_duration(clip.start_seconds)}\n"
                    f"Р”Р»РёРЅР°: {format_duration(clip.duration_seconds)}\n"
                    f"Р’РµСЃ: {human_size(clip.path.stat().st_size)}\n\n"
                    f"Р“РѕС‚РѕРІРѕ {index}/{len(starts)}. РћСЃС‚Р°Р»РѕСЃСЊ: {len(starts) - index}."
                ),
                reply_markup=media_tools_keyboard(subtitle_id, cover_id),
            )

        if not clips:
            await safe_edit(status, "РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ СЃРґРµР»Р°С‚СЊ РєР»РёРїС‹: РІРёРґРµРѕ СЃР»РёС€РєРѕРј РєРѕСЂРѕС‚РєРѕРµ.")
            return

        state["stage"] = "Р­С‚Р°Рї 5/6: СѓРїР°РєРѕРІС‹РІР°СЋ ZIP"
        state["detail"] = f"РљР»РёРїРѕРІ: {len(clips)}"
        await safe_edit(
            status,
            f"Р РµР¶РёРј: {mode_label}\n"
            "Р­С‚Р°Рї 5/6: РєР»РёРїС‹ СѓР¶Рµ РѕС‚РїСЂР°РІР»РµРЅС‹, РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ СѓРїР°РєРѕРІС‹РІР°СЋ ZIP.\n"
            f"РљР»РёРїРѕРІ: {len(clips)}\n"
            f"РЎС‚Р°СЂС‚С‹: {describe_clips(clips)}\n"
            "ZIP РЅСѓР¶РµРЅ, С‡С‚РѕР±С‹ РІСЃРµ РєР»РёРїС‹ РјРѕР¶РЅРѕ Р±С‹Р»Рѕ СЃРєР°С‡Р°С‚СЊ РѕРґРЅРёРј С„Р°Р№Р»РѕРј.",
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
            f"Р“РѕС‚РѕРІРѕ: {len(clips)} Shorts\n"
            f"РСЃС‚РѕС‡РЅРёРє: {download.title}\n"
            f"РЎС‚Р°СЂС‚С‹ РєР»РёРїРѕРІ: {describe_clips(clips)}\n"
            f"Р’РµСЃ Р°СЂС…РёРІР°: {human_size(zip_path.stat().st_size)}\n"
            f"РћР±С‰РµРµ РІСЂРµРјСЏ РѕР±СЂР°Р±РѕС‚РєРё: {format_duration(time.time() - started_at)}"
            f"{AFTER_RESULT_HINT}"
        )
        state["stage"] = "Р­С‚Р°Рї 6/6: РѕС‚РїСЂР°РІР»СЏСЋ ZIP"
        state["detail"] = f"Р Р°Р·РјРµСЂ ZIP: {human_size(zip_path.stat().st_size)}"
        await safe_edit(
            status,
            f"Р РµР¶РёРј: {mode_label}\n"
            "Р­С‚Р°Рї 6/6: РѕС‚РїСЂР°РІР»СЏСЋ РѕР±С‰РёР№ ZIP-Р°СЂС…РёРІ.\n"
            f"Р Р°Р·РјРµСЂ ZIP: {human_size(zip_path.stat().st_size)}",
        )

        if zip_path.stat().st_size <= TELEGRAM_SAFE_UPLOAD_BYTES:
            await message.answer_document(FSInputFile(zip_path), caption=caption, reply_markup=youtube_replay_keyboard(replay_id, mode, cover_job_id=cover_id))
        else:
            await message.answer(caption + "\nZIP Р±РѕР»СЊС€РѕР№, РїРѕСЌС‚РѕРјСѓ РєР»РёРїС‹ СѓР¶Рµ РѕС‚РїСЂР°РІР»РµРЅС‹ РѕС‚РґРµР»СЊРЅРѕ РІС‹С€Рµ.", reply_markup=youtube_replay_keyboard(replay_id, mode, cover_job_id=cover_id))
        if cover_path:
            await message.answer_document(FSInputFile(cover_path), caption="PNG-РѕР±Р»РѕР¶РєР° РґР»СЏ Shorts-РїР°С‡РєРё.")
        await safe_edit(
            status,
            "Р“РѕС‚РѕРІРѕ. Р’СЃРµ РєР»РёРїС‹ РѕС‚РїСЂР°РІР»РµРЅС‹."
            + next_steps_text(
                "СЃРєР°С‡Р°Р№ РѕС‚РґРµР»СЊРЅС‹Рµ РєР»РёРїС‹ РёР»Рё РѕР±С‰РёР№ ZIP",
                "РЅР°Р¶РјРё Subtitles РЅР° РЅСѓР¶РЅРѕРј РєР»РёРїРµ",
                "РЅР°Р¶РјРё Redo, РµСЃР»Рё С…РѕС‡РµС€СЊ РґСЂСѓРіСѓСЋ РЅР°СЂРµР·РєСѓ",
                "РѕС‚РїСЂР°РІСЊ СЃР»РµРґСѓСЋС‰РёР№ С„Р°Р№Р» РёР»Рё СЃСЃС‹Р»РєСѓ",
            ),
        )
    except Exception as exc:
        logger.exception("YouTube shorts job failed")
        await safe_edit(status, f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ РѕР±СЂР°Р±РѕС‚Р°С‚СЊ YouTube-СЃСЃС‹Р»РєСѓ: {exc}")
    finally:
        heartbeat_task.cancel()


@router.message(F.photo | F.document | F.video)
async def receive_file(message: Message, bot: Bot) -> None:
    prune_sessions()
    await ensure_user(message)
    if not message.from_user:
        return
    if billing_bot_mode():
        await message.answer(billing_only_text(user_lang(message)), reply_markup=main_menu(user_lang(message)))
        return

    file_id, original_name, kind, file_size = extract_file_meta(message)
    if not file_id:
        return
    if not await ensure_paid_access(message, message.from_user.id, "РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РІРёРґРµРѕ" if kind == "video" else "РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РёР·РѕР±СЂР°Р¶РµРЅРёР№"):
        return

    if file_size and file_size > max_size_bytes(kind):
        await message.answer(
            f"Р¤Р°Р№Р» СЃР»РёС€РєРѕРј Р±РѕР»СЊС€РѕР№. Р›РёРјРёС‚ РґР»СЏ {'РІРёРґРµРѕ' if kind == 'video' else 'РёР·РѕР±СЂР°Р¶РµРЅРёР№'}: "
            f"{settings.max_video_mb if kind == 'video' else settings.max_image_mb} MB."
            + next_steps_text("СЃРѕР¶РјРё С„Р°Р№Р» РёР»Рё РѕС‚РїСЂР°РІСЊ Р±РѕР»РµРµ РєРѕСЂРѕС‚РєРёР№ С„СЂР°РіРјРµРЅС‚", "РјРѕР¶РЅРѕ РїРѕРїСЂРѕР±РѕРІР°С‚СЊ YouTube-СЃСЃС‹Р»РєСѓ РІРјРµСЃС‚Рѕ С„Р°Р№Р»Р°")
        )
        return

    status = await message.answer(
        process_stage_text("РџРѕРґРіРѕС‚РѕРІРєР° С„Р°Р№Р»Р°", FILE_PREP_STEPS, 1, f"Р¤Р°Р№Р»: {original_name}")
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
        process_stage_text("РџРѕРґРіРѕС‚РѕРІРєР° С„Р°Р№Р»Р°", FILE_PREP_STEPS, 2, f"Р—Р°РіСЂСѓР¶РµРЅРѕ: {human_size(source_path.stat().st_size)}"),
    )

    if source_path.stat().st_size > max_size_bytes(kind):
        source_path.unlink(missing_ok=True)
        await safe_edit(
            status,
            "Р¤Р°Р№Р» РѕРєР°Р·Р°Р»СЃСЏ Р±РѕР»СЊС€Рµ Р»РёРјРёС‚Р° РїРѕСЃР»Рµ Р·Р°РіСЂСѓР·РєРё."
            + next_steps_text("РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» РјРµРЅСЊС€Рµ", "РґР»СЏ РІРёРґРµРѕ РјРѕР¶РЅРѕ РїСЂРёСЃР»Р°С‚СЊ СЃСЃС‹Р»РєСѓ Рё РІС‹Р±СЂР°С‚СЊ СЂРµР¶РёРј РјРѕРЅС‚Р°Р¶Р°"),
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
    await safe_edit(status, process_stage_text("РџРѕРґРіРѕС‚РѕРІРєР° С„Р°Р№Р»Р°", FILE_PREP_STEPS, 3, "Р§РёС‚Р°СЋ РїР°СЂР°РјРµС‚СЂС‹ С„Р°Р№Р»Р°"))

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
                "РќРµ СЃРјРѕРі РѕС‚РєСЂС‹С‚СЊ С„Р°Р№Р» РєР°Рє РёР·РѕР±СЂР°Р¶РµРЅРёРµ."
                + next_steps_text("РѕС‚РїСЂР°РІСЊ PNG, JPG, WEBP, GIF, TIFF РёР»Рё BMP", "РёР»Рё РѕС‚РїСЂР°РІСЊ РІРёРґРµРѕ/YouTube-СЃСЃС‹Р»РєСѓ"),
            )
        else:
            await message.answer("РќРµ СЃРјРѕРі РѕС‚РєСЂС‹С‚СЊ С„Р°Р№Р» РєР°Рє РёР·РѕР±СЂР°Р¶РµРЅРёРµ." + next_steps_text("РѕС‚РїСЂР°РІСЊ РґСЂСѓРіРѕР№ С„Р°Р№Р»"))
        source_path.unlink(missing_ok=True)
        sessions.pop(session_id, None)
        return
    if status:
        await safe_edit(
            status,
            process_stage_text(
                "РџРѕРґРіРѕС‚РѕРІРєР° С„Р°Р№Р»Р°",
                FILE_PREP_STEPS,
                4,
                f"Р¤РѕСЂРјР°С‚: {info.format}, СЂР°Р·РјРµСЂ: {info.width}x{info.height}, РІРµСЃ: {human_size(info.size_bytes)}",
                done=True,
            ),
        )

    await message.answer(
        "РР·РѕР±СЂР°Р¶РµРЅРёРµ РїСЂРёРЅСЏС‚Рѕ.\n"
        f"Р¤РѕСЂРјР°С‚: {info.format}, СЂР°Р·РјРµСЂ: {info.width}x{info.height}, РєР°РґСЂРѕРІ: {info.frames}, РІРµСЃ: {human_size(info.size_bytes)}.\n"
        "Р’С‹Р±РµСЂРё С„РѕСЂРјР°С‚, РїРѕС‚РѕРј СЂРµР¶РёРј СЃР¶Р°С‚РёСЏ:"
        f"{NEXT_STEP_HINT}",
        reply_markup=formats_keyboard(session_id, available_image_formats(source_path), "image"),
    )


async def prepare_video_message(message: Message, session_id: str, source_path: Path, status: Message | None = None) -> None:
    if not ffmpeg_available():
        text = "Р’РёРґРµРѕ РїСЂРёРЅСЏС‚Рѕ, РЅРѕ РѕР±СЂР°Р±РѕС‚С‡РёРє РІРёРґРµРѕ РЅРµРґРѕСЃС‚СѓРїРµРЅ." + next_steps_text("РѕР±РЅРѕРІРё Р·Р°РІРёСЃРёРјРѕСЃС‚Рё", "РїРµСЂРµР·Р°РїСѓСЃС‚Рё Р±РѕС‚Р° Рё РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» Р·Р°РЅРѕРІРѕ")
        if status:
            await safe_edit(status, text)
        else:
            await message.answer(text)
        return
    try:
        info = await asyncio.to_thread(inspect_video, source_path)
        resolution = f"{info.width}x{info.height}" if info.width and info.height else "unknown"
        details = f"Р Р°Р·СЂРµС€РµРЅРёРµ: {resolution}, РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(info.duration_seconds)}, РІРµСЃ: {human_size(info.size_bytes)}.\n"
    except Exception:
        details = "РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕС‡РёС‚Р°С‚СЊ РјРµС‚Р°РґР°РЅРЅС‹Рµ, РЅРѕ РјРѕР¶РЅРѕ РїРѕРїСЂРѕР±РѕРІР°С‚СЊ РєРѕРЅРІРµСЂС‚Р°С†РёСЋ.\n"

    if status:
        await safe_edit(
            status,
            process_stage_text("РџРѕРґРіРѕС‚РѕРІРєР° С„Р°Р№Р»Р°", FILE_PREP_STEPS, 4, details.strip(), done=True),
        )

    session = sessions.get(session_id)
    if session and session.cover_title:
        cover_hint = "\nРўРµРєСЃС‚ РґР»СЏ РѕР±Р»РѕР¶РєРё СѓР¶Рµ РІР·СЏР» РёР· РїРѕРґРїРёСЃРё Рє РІРёРґРµРѕ.\n"
    else:
        cover_hint = "\nР”Р»СЏ РѕР±Р»РѕР¶РєРё РјРѕР¶РЅРѕ СЃР»РµРґСѓСЋС‰РёРј СЃРѕРѕР±С‰РµРЅРёРµРј РїСЂРёСЃР»Р°С‚СЊ РЅР°Р·РІР°РЅРёРµ Рё РѕРїРёСЃР°РЅРёРµ: РїРµСЂРІР°СЏ СЃС‚СЂРѕРєР° вЂ” Р·Р°РіРѕР»РѕРІРѕРє, РІС‚РѕСЂР°СЏ вЂ” РєСЂСЋС‡РѕРє.\n"

    await message.answer(
        "Р’РёРґРµРѕ РїСЂРёРЅСЏС‚Рѕ.\n" + details + cover_hint + "Р’С‹Р±РµСЂРё С„РѕСЂРјР°С‚:" + NEXT_STEP_HINT,
        reply_markup=formats_keyboard(session_id, VIDEO_FORMATS, "video"),
    )


@router.callback_query(F.data.startswith("rename:"))
async def rename_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    session_id = callback.data.split(":", 1)[1]
    session = get_owned_session(session_id, callback.from_user.id if callback.from_user else 0)
    if not session:
        if callback.message:
            await callback.message.answer("Р­С‚РѕС‚ С„Р°Р№Р» СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РћС‚РїСЂР°РІСЊ РµРіРѕ Р·Р°РЅРѕРІРѕ.")
        return
    await state.set_state(RenameState.waiting_name)
    await state.update_data(session_id=session_id)
    if callback.message:
        await callback.message.answer(
            "РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ: Р¶РґСѓ РЅРѕРІРѕРµ РёРјСЏ С„Р°Р№Р»Р° Р±РµР· СЂР°СЃС€РёСЂРµРЅРёСЏ."
            + next_steps_text("РЅР°РїРёС€Рё РЅРѕРІРѕРµ РёРјСЏ РѕРґРЅРёРј СЃРѕРѕР±С‰РµРЅРёРµРј", "РґР»СЏ РѕС‚РјРµРЅС‹ РЅР°РїРёС€Рё /cancel")
        )


@router.message(RenameState.waiting_name)
async def rename_finish(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("РќР°РїРёС€Рё РЅРѕРІРѕРµ РёРјСЏ С‚РµРєСЃС‚РѕРј." + next_steps_text("РёР»Рё РѕС‚РїСЂР°РІСЊ /cancel РґР»СЏ РѕС‚РјРµРЅС‹"))
        return
    if message.text.strip().lower() in {"/cancel", "cancel", "РѕС‚РјРµРЅР°", "СЃРєР°СЃСѓРІР°С‚Рё"}:
        await state.clear()
        await message.answer(
            "РћРє, РїРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РѕС‚РјРµРЅРµРЅРѕ."
            + next_steps_text("РІС‹Р±РµСЂРё С„РѕСЂРјР°С‚ РєРЅРѕРїРєРѕР№", "РёР»Рё РѕС‚РїСЂР°РІСЊ РЅРѕРІС‹Р№ С„Р°Р№Р»")
        )
        return

    data = await state.get_data()
    session_id = data.get("session_id")
    session = get_owned_session(session_id, message.from_user.id if message.from_user else 0)
    await state.clear()
    if not session:
        await message.answer("Р­С‚РѕС‚ С„Р°Р№Р» СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РћС‚РїСЂР°РІСЊ РµРіРѕ Р·Р°РЅРѕРІРѕ.")
        return
    session.base_name = clean_base_name(message.text or session.base_name)
    formats = VIDEO_FORMATS if session.kind == "video" else available_image_formats(session.path)
    await message.answer(
        f"РРјСЏ РѕР±РЅРѕРІР»РµРЅРѕ: {session.base_name}."
        + next_steps_text("РІС‹Р±РµСЂРё С„РѕСЂРјР°С‚ РєРЅРѕРїРєРѕР№ РЅРёР¶Рµ", "РёР»Рё РѕС‚РїСЂР°РІСЊ РЅРѕРІС‹Р№ С„Р°Р№Р»"),
        reply_markup=formats_keyboard(session_id, formats, session.kind),
    )


@router.callback_query(F.data.startswith("convert:"))
async def convert_callback(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer("РљРѕРЅРІРµСЂС‚РёСЂСѓСЋ...")
    if not callback.from_user or not callback.message:
        return
    parsed = parse_convert_callback_data(callback.data)
    if not parsed:
        await callback.message.answer("РќРµ РїРѕРЅСЏР» РїР°СЂР°РјРµС‚СЂС‹ РєРѕРЅРІРµСЂС‚Р°С†РёРё. Р’С‹Р±РµСЂРё С„РѕСЂРјР°С‚ РµС‰Рµ СЂР°Р·.")
        return
    session_id = parsed.session_id
    target_format = parsed.target_format
    image_mode = normalize_image_mode(parsed.image_mode)
    session = get_owned_session(session_id, callback.from_user.id)
    if not session:
        await callback.message.answer("Р­С‚РѕС‚ С„Р°Р№Р» СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РћС‚РїСЂР°РІСЊ РµРіРѕ Р·Р°РЅРѕРІРѕ.")
        return
    await bot.send_chat_action(callback.message.chat.id, ChatAction.UPLOAD_DOCUMENT)
    if session.kind == "video":
        if not await ensure_action_allowed(callback.message, callback.from_user.id, "video"):
            return
        await convert_video_callback(callback, session_id, session, target_format)
    else:
        if parsed.image_mode is None:
            await callback.message.answer(
                f"Р¤РѕСЂРјР°С‚: {target_format.upper()}.\nР’С‹Р±РµСЂРё СЂРµР¶РёРј СЃР¶Р°С‚РёСЏ:",
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
        process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ", IMAGE_CONVERT_STEPS, 1, f"Р¤РѕСЂРјР°С‚: {target_format.upper()}, СЂРµР¶РёРј: {mode_label}")
    )
    try:
        await safe_edit(status, process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ", IMAGE_CONVERT_STEPS, 1, "РџСЂРѕРІРµСЂСЏСЋ РёСЃС…РѕРґРЅС‹Р№ С„Р°Р№Р»"))
        source_info = await asyncio.to_thread(inspect_image, session.path)
        await safe_edit(status, process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ", IMAGE_CONVERT_STEPS, 2, "РњРµРЅСЏСЋ С„РѕСЂРјР°С‚ Рё СЃРѕС…СЂР°РЅСЏСЋ РєР°С‡РµСЃС‚РІРѕ"))
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
            f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ РєРѕРЅРІРµСЂС‚РёСЂРѕРІР°С‚СЊ РёР·РѕР±СЂР°Р¶РµРЅРёРµ: {exc}"
            + next_steps_text("РїРѕРїСЂРѕР±СѓР№ РґСЂСѓРіРѕР№ С„РѕСЂРјР°С‚", "РµСЃР»Рё С„Р°Р№Р» РїРѕРІСЂРµР¶РґРµРЅ, РѕС‚РїСЂР°РІСЊ РµРіРѕ Р·Р°РЅРѕРІРѕ"),
        )
        return

    await safe_edit(
        status,
        process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ", IMAGE_CONVERT_STEPS, 3, f"Р РµР·СѓР»СЊС‚Р°С‚: {output_path.name}"),
    )
    await db.add_conversion(callback.from_user.id, "image", session.original_name, output_path.name, target_format, source_info.size_bytes, output_info.size_bytes)
    await safe_edit(status, process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ", IMAGE_CONVERT_STEPS, 4, "РћС‚РїСЂР°РІР»СЏСЋ РіРѕС‚РѕРІС‹Р№ С„Р°Р№Р»"))
    await callback.message.answer_document(
        FSInputFile(output_path),
        caption=(
            f"{output_path.name}\n"
            f"{source_info.format} -> {output_info.format}\n"
            f"{output_info.width}x{output_info.height}, РєР°РґСЂРѕРІ: {output_info.frames}\n"
            f"Р РµР¶РёРј: {mode_label}\n"
            f"Р’РµСЃ: {human_size(source_info.size_bytes)} -> {human_size(output_info.size_bytes)}"
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
                "Р—Р°С‰РёС‚Р° РІРµСЃР°: РІС‹Р±СЂР°РЅРЅС‹Р№ С„РѕСЂРјР°С‚ РїРѕР»СѓС‡РёР»СЃСЏ С‚СЏР¶РµР»РµРµ РёСЃС…РѕРґРЅРёРєР°, РїРѕСЌС‚РѕРјСѓ РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ СЃРґРµР»Р°Р» Р»РµРіРєСѓСЋ WEBP-РІРµСЂСЃРёСЋ.\n"
                f"Р’РµСЃ: {human_size(source_info.size_bytes)} -> {human_size(safe_info.size_bytes)}"
            ),
            disable_content_type_detection=True,
        )
    await safe_edit(
        status,
        process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ", IMAGE_CONVERT_STEPS, 4, "Р¤Р°Р№Р» РѕС‚РїСЂР°РІР»РµРЅ", done=True)
        + next_steps_text("СЃРєР°С‡Р°Р№ СЂРµР·СѓР»СЊС‚Р°С‚", "РІС‹Р±РµСЂРё РґСЂСѓРіРѕР№ С„РѕСЂРјР°С‚ РёР»Рё РѕС‚РїСЂР°РІСЊ РЅРѕРІС‹Р№ С„Р°Р№Р»"),
    )


async def convert_video_callback(callback: CallbackQuery, session_id: str, session: FileSession, target_format: str) -> None:
    assert callback.message and callback.from_user
    if not ffmpeg_available():
        await callback.message.answer(
            "РћР±СЂР°Р±РѕС‚С‡РёРє РІРёРґРµРѕ РЅРµРґРѕСЃС‚СѓРїРµРЅ."
            + next_steps_text("РѕР±РЅРѕРІРё Р·Р°РІРёСЃРёРјРѕСЃС‚Рё", "РїРµСЂРµР·Р°РїСѓСЃС‚Рё Р±РѕС‚Р° Рё РѕС‚РїСЂР°РІСЊ РІРёРґРµРѕ Р·Р°РЅРѕРІРѕ")
        )
        return
    status = await callback.message.answer(
        process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РІРёРґРµРѕ", VIDEO_CONVERT_STEPS, 1, f"Р¤РѕСЂРјР°С‚: {target_format.upper()}")
    )
    try:
        await safe_edit(status, process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РІРёРґРµРѕ", VIDEO_CONVERT_STEPS, 2, "РљРѕРґРёСЂСѓСЋ РІРёРґРµРѕ Рё Р·РІСѓРє"))
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
            "Р’РёРґРµРѕ СЃР»РёС€РєРѕРј РґРѕР»РіРѕ РєРѕРЅРІРµСЂС‚РёСЂСѓРµС‚СЃСЏ."
            + next_steps_text("РїРѕРїСЂРѕР±СѓР№ С„Р°Р№Р» РєРѕСЂРѕС‡Рµ РёР»Рё Р»РµРіС‡Рµ", "РґР»СЏ РґР»РёРЅРЅС‹С… СЂРѕР»РёРєРѕРІ РѕС‚РїСЂР°РІСЊ YouTube-СЃСЃС‹Р»РєСѓ Рё РІС‹Р±РµСЂРё РјРѕРЅС‚Р°Р¶"),
        )
        return
    except Exception as exc:
        logger.exception("Video conversion failed")
        await safe_edit(
            status,
            f"РќРµ РїРѕР»СѓС‡РёР»РѕСЃСЊ РєРѕРЅРІРµСЂС‚РёСЂРѕРІР°С‚СЊ РІРёРґРµРѕ: {exc}"
            + next_steps_text("РїРѕРїСЂРѕР±СѓР№ РґСЂСѓРіРѕР№ С„РѕСЂРјР°С‚", "РµСЃР»Рё РІРёРґРµРѕ РїРѕРІСЂРµР¶РґРµРЅРѕ, РѕС‚РїСЂР°РІСЊ С„Р°Р№Р» Р·Р°РЅРѕРІРѕ"),
        )
        return

    await safe_edit(
        status,
        process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РІРёРґРµРѕ", VIDEO_CONVERT_STEPS, 3, f"Р РµР·СѓР»СЊС‚Р°С‚: {result.path.name}"),
    )
    await db.add_conversion(callback.from_user.id, "video", session.original_name, result.path.name, target_format, result.source.size_bytes, result.output.size_bytes)
    resolution = f"{result.output.width}x{result.output.height}" if result.output.width and result.output.height else "unknown"
    subtitle_id = remember_subtitle_job(callback.from_user.id, result.path, result.path.stem) if target_format == "mp4" else None
    cover_id = remember_cover_job(callback.from_user.id, result.path, result.path.stem, result.output.duration_seconds)
    await safe_edit(status, process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РІРёРґРµРѕ", VIDEO_CONVERT_STEPS, 4, "РћС‚РїСЂР°РІР»СЏСЋ РіРѕС‚РѕРІС‹Р№ С„Р°Р№Р»"))
    await callback.message.answer_document(
        FSInputFile(result.path),
        caption=(
            f"{result.path.name}\n"
            f"Р’РёРґРµРѕ -> {target_format.upper()}\n"
            f"Р Р°Р·СЂРµС€РµРЅРёРµ: {resolution}, РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: {format_duration(result.output.duration_seconds)}\n"
            f"Р’РµСЃ: {human_size(result.source.size_bytes)} -> {human_size(result.output.size_bytes)}"
            f"{AFTER_RESULT_HINT}"
        ),
        reply_markup=share_keyboard(session_id, result.path.name, subtitle_id, cover_id),
    )
    await safe_edit(
        status,
        process_stage_text("РљРѕРЅРІРµСЂС‚Р°С†РёСЏ РІРёРґРµРѕ", VIDEO_CONVERT_STEPS, 4, "Р¤Р°Р№Р» РѕС‚РїСЂР°РІР»РµРЅ", done=True)
        + next_steps_text(
            "СЃРєР°С‡Р°Р№ СЂРµР·СѓР»СЊС‚Р°С‚",
            "РґР»СЏ MP4 РЅР°Р¶РјРё Subtitles, РµСЃР»Рё РЅСѓР¶РЅС‹ СЃСѓР±С‚РёС‚СЂС‹",
            "РѕС‚РїСЂР°РІСЊ РЅРѕРІС‹Р№ С„Р°Р№Р» РёР»Рё YouTube-СЃСЃС‹Р»РєСѓ",
        ),
    )


async def cleanup_loop() -> None:
    while True:
        prune_sessions()
        await asyncio.sleep(settings.cleanup_interval_seconds)


async def heartbeat_loop() -> None:
    path = Path("data") / "bot_heartbeat.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            path.write_text(
                json.dumps(
                    {
                        "service": "telegram_bot",
                        "status": "ok",
                        "time": time.time(),
                        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to write bot heartbeat")
        await asyncio.sleep(30)


def normalize_resume_text(value: str | None) -> str:
    return utils_normalize_resume_text(value)


def resume_safe_text(value: str) -> str:
    return utils_resume_safe_text(value)


def resume_clean_text(value: str) -> str:
    return utils_repair_cyrillic_mojibake(str(value or ""))


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
    "1": {"name": "Classic", "label": "С‡РёСЃС‚С‹Р№ ATS", "accent": "#2563eb", "dark": "#111827", "muted": "#4b5563", "soft": "#eff6ff", "layout": "single"},
    "2": {"name": "Executive", "label": "СЃС‚СЂРѕРіРёР№ РїСЂРµРјРёСѓРј", "accent": "#0f766e", "dark": "#10201f", "muted": "#475569", "soft": "#ecfdf5", "layout": "band"},
    "3": {"name": "Creative", "label": "СЏСЂРєРёР№ РїСЂРѕС„РёР»СЊ", "accent": "#c026d3", "dark": "#2f1234", "muted": "#5b5061", "soft": "#fdf4ff", "layout": "two"},
    "4": {"name": "Modern", "label": "СЃРѕРІСЂРµРјРµРЅРЅС‹Р№ Р±Р»РѕРє", "accent": "#ea580c", "dark": "#1f2937", "muted": "#57534e", "soft": "#fff7ed", "layout": "cards"},
    "5": {"name": "Tech", "label": "IT Рё digital", "accent": "#0891b2", "dark": "#0f172a", "muted": "#475569", "soft": "#ecfeff", "layout": "two"},
    "6": {"name": "Minimal", "label": "РµРІСЂРѕРїРµР№СЃРєРёР№ СЃС‚РёР»СЊ", "accent": "#52525b", "dark": "#18181b", "muted": "#52525b", "soft": "#f4f4f5", "layout": "single"},
    "7": {"name": "Premium", "label": "СЃРёР»СЊРЅР°СЏ РєРѕР»РѕРЅРєР°", "accent": "#b45309", "dark": "#1c1917", "muted": "#57534e", "soft": "#fffbeb", "layout": "two"},
    "8": {"name": "Focus", "label": "Р°РєС†РµРЅС‚ РЅР° РѕРїС‹С‚", "accent": "#7c3aed", "dark": "#2e1065", "muted": "#5b5566", "soft": "#f5f3ff", "layout": "rail"},
    "9": {"name": "Nordic", "label": "СЃРїРѕРєРѕР№РЅС‹Р№ HR", "accent": "#0369a1", "dark": "#0c2538", "muted": "#475569", "soft": "#f0f9ff", "layout": "two"},
    "10": {"name": "Legal", "label": "РєРѕРЅСЃРµСЂРІР°С‚РёРІРЅС‹Р№", "accent": "#374151", "dark": "#111827", "muted": "#4b5563", "soft": "#f9fafb", "layout": "single"},
    "11": {"name": "Startup", "label": "СЌРЅРµСЂРіРёС‡РЅС‹Р№", "accent": "#16a34a", "dark": "#052e16", "muted": "#4b5563", "soft": "#f0fdf4", "layout": "cards"},
    "12": {"name": "Finance", "label": "РґРµР»РѕРІРѕР№", "accent": "#1d4ed8", "dark": "#172554", "muted": "#475569", "soft": "#eef2ff", "layout": "band"},
    "13": {"name": "Academic", "label": "РѕР±СЂР°Р·РѕРІР°РЅРёРµ", "accent": "#7f1d1d", "dark": "#1f1717", "muted": "#57534e", "soft": "#fef2f2", "layout": "photo_left"},
    "14": {"name": "Compact", "label": "РїР»РѕС‚РЅРѕ Рё СЏСЃРЅРѕ", "accent": "#0d9488", "dark": "#134e4a", "muted": "#475569", "soft": "#f0fdfa", "layout": "split"},
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
    draw.text((margin, 67), "РњРёРЅРё-РїСЂРёРјРµСЂ СЂР°СЃРїРѕР»РѕР¶РµРЅРёСЏ Р±Р»РѕРєРѕРІ, С„РѕС‚Рѕ, РєР°СЂС‚РѕС‡РµРє Рё РєРѕР»РѕРЅРѕРє РїРµСЂРµРґ РІС‹Р±РѕСЂРѕРј PDF", fill="#4b5563", font=fonts["subtitle"])
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
    draw.text((margin, 62), "Р’С‹Р±РµСЂРёС‚Рµ СЃС‚РёР»СЊ РєРЅРѕРїРєРѕР№ РЅРёР¶Рµ. Р­С‚Рѕ РїСЂРёРјРµСЂ С€СЂРёС„С‚Р°, С†РІРµС‚Р° Рё РїРѕРґР°С‡Рё.", fill="#cbd5e1", font=fonts["small"])
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
        sample = "BIG RESULT" if style in {"pop", "headline", "kinetic"} else "Р§РёСЃС‚С‹Р№ С‚РµРєСЃС‚"
        draw.text((x + 18, y + 58), sample, fill=primary, font=sample_font, stroke_width=2 if style in {"pop", "comic", "headline"} else 1, stroke_fill="#000000")
        draw.text((x + 18, y + 100), "РїСЂРёРјРµСЂ СЃС‚СЂРѕРєРё СЃСѓР±С‚РёС‚СЂРѕРІ", fill=accent, font=fonts["small"])
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
        prefix = "- " if line.startswith(("-", "вЂў", "•", "*")) else ""
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


def _clamp_resume_crop(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def manual_resume_square_crop(image: Image.Image, crop_data: str | dict | None) -> Image.Image | None:
    if not crop_data:
        return None
    try:
        crop = json.loads(crop_data) if isinstance(crop_data, str) else dict(crop_data)
        image = ImageOps.exif_transpose(image).convert("RGBA")
        width, height = image.size
        base_side = max(1, min(width, height))
        zoom = _clamp_resume_crop(float(crop.get("zoom") or 1), 1.0, 3.0)
        center_x = _clamp_resume_crop(float(crop.get("x") or 0.5), 0.0, 1.0) * width
        center_y = _clamp_resume_crop(float(crop.get("y") or 0.5), 0.0, 1.0) * height
        side = int(max(1, round(base_side / zoom)))
        left = int(round(center_x - side / 2))
        top = int(round(center_y - side / 2))
        left = max(0, min(left, width - side))
        top = max(0, min(top, height - side))
        return image.crop((left, top, left + side, top + side))
    except Exception:
        logger.exception("Could not apply manual resume photo crop")
        return None


def make_resume_avatar(photo_path: str | None, output_dir: Path, crop_data: str | dict | None = None) -> Path | None:
    if not photo_path:
        return None
    source = Path(photo_path)
    if not source.exists():
        return None
    try:
        with Image.open(source) as image:
            image = manual_resume_square_crop(image, crop_data) or face_aware_square_crop(image)
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
    canvas.drawRightString(width - doc.rightMargin, 8 * mm, resume_clean_text(f"Resume - {template['name']}"))
    canvas.restoreState()


def resume_section_data(data: dict) -> dict[str, str]:
    return utils_resume_section_data(data)


RESUME_PDF_NOISE_RE = re.compile(
    r"^(?:"
    r"focus:\s*structured communication,\s*ownership,\s*measurable delivery and clear business value\.?|"
    r"strengthened outcomes through clearer priorities,\s*practical execution and measurable improvements\.?|"
    r"local fallback used|"
    r"add real metrics where possible"
    r")$",
    flags=re.IGNORECASE,
)


def clean_resume_pdf_block(value: str, field: str = "") -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for raw in normalize_resume_text(value).splitlines():
        has_bullet = raw.lstrip().startswith(("-", "*", "вЂў", "•"))
        line = " ".join(raw.strip().strip(" -*\tвЂў•").split())
        if not line:
            continue
        line = re.sub(
            r"\bFocus:\s*structured communication,\s*ownership,\s*measurable delivery and clear business value\.?",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip(" -")
        if not line:
            continue
        if RESUME_PDF_NOISE_RE.match(line):
            continue
        if field in {"contact", "links"} and re.search(r"https?://(?:127\.0\.0\.1|localhost)(?::\d+)?(?:/|\b)", line, flags=re.IGNORECASE):
            continue
        key = re.sub(r"\s+", " ", line).casefold()
        if key in seen:
            continue
        seen.add(key)
        if has_bullet and field in {"experience", "achievements"}:
            lines.append(f"- {line}")
        else:
            lines.append(line)
    return "\n".join(lines)


def clean_resume_pdf_data(data: dict[str, str]) -> dict[str, str]:
    cleaned = dict(data)
    for field in (
        "name",
        "position",
        "contact",
        "links",
        "summary",
        "experience",
        "education",
        "skills",
        "achievements",
        "additional",
        "cover_letter",
    ):
        cleaned[field] = clean_resume_pdf_block(cleaned.get(field, ""), field)
    if cleaned.get("skills"):
        cleaned["skills"] = polish_resume_skills(cleaned["skills"])
    return cleaned


def select_resume_pdf_template(template: dict[str, str], prepared: dict[str, str]) -> dict[str, str]:
    selected = dict(template)
    verbose_layouts = {"band", "two", "split", "photo_left", "cards"}
    if selected.get("layout") in verbose_layouts and resume_content_score(prepared) > 980:
        selected["layout"] = "single"
        selected["name"] = f"{selected['name']} Clean"
    return selected


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
    if len(digits) >= 7 and (value.lstrip().startswith("+") or re.search(r"\b(phone|tel|С‚РµР»|РЅРѕРјРµСЂ|РјРѕР±)", lower)):
        return "phone", "TEL"
    if "behance.net" in lower:
        return "behance", "BE"
    if re.search(r"(https?://|www\.|[a-z0-9-]+\.[a-z]{2,})", lower):
        return "web", "WEB"
    return "contact", "ID"


def resume_pdf_labels(language: str) -> dict[str, str]:
    code = (language or "ru").lower()
    if code.startswith("uk"):
        labels = {
            "experience": "Р”РѕСЃРІС–Рґ СЂРѕР±РѕС‚Рё",
            "experience_short": "Р”РѕСЃРІС–Рґ",
            "education": "РћСЃРІС–С‚Р°",
            "skills": "РќР°РІРёС‡РєРё",
            "achievements": "Р”РѕСЃСЏРіРЅРµРЅРЅСЏ С‚Р° РїСЂРѕС”РєС‚Рё",
            "projects": "РџСЂРѕС”РєС‚Рё",
            "contacts": "РљРѕРЅС‚Р°РєС‚Рё С‚Р° РїРѕСЃРёР»Р°РЅРЅСЏ",
            "contacts_short": "РљРѕРЅС‚Р°РєС‚Рё",
            "additional": "Р”РѕРґР°С‚РєРѕРІРѕ",
            "cover_letter": "РЎСѓРїСЂРѕРІС–РґРЅРёР№ Р»РёСЃС‚",
            "more": "Р©Рµ",
        }
        return {key: resume_clean_text(value) for key, value in labels.items()}
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
            "cover_letter": "Cover letter",
            "more": "More",
        }
    labels = {
        "experience": "РћРїС‹С‚ СЂР°Р±РѕС‚С‹",
        "experience_short": "РћРїС‹С‚",
        "education": "РћР±СЂР°Р·РѕРІР°РЅРёРµ",
        "skills": "РќР°РІС‹РєРё",
        "achievements": "Р”РѕСЃС‚РёР¶РµРЅРёСЏ Рё РїСЂРѕРµРєС‚С‹",
        "projects": "РџСЂРѕРµРєС‚С‹",
        "contacts": "РљРѕРЅС‚Р°РєС‚С‹ Рё СЃСЃС‹Р»РєРё",
        "contacts_short": "РљРѕРЅС‚Р°РєС‚С‹",
        "additional": "Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ",
        "cover_letter": "РЎРѕРїСЂРѕРІРѕРґРёС‚РµР»СЊРЅРѕРµ РїРёСЃСЊРјРѕ",
        "more": "Р•С‰Рµ",
    }
    return {key: resume_clean_text(value) for key, value in labels.items()}


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
        Paragraph(resume_safe_text(data["name"] or "Р РµР·СЋРјРµ"), styles["ResumeName"]),
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
    add_resume_section(story, "РћРїС‹С‚ СЂР°Р±РѕС‚С‹", data["experience"], styles)
    add_resume_section(story, "РћР±СЂР°Р·РѕРІР°РЅРёРµ", data["education"], styles)
    add_resume_section(story, "РќР°РІС‹РєРё", data["skills"], styles)
    add_resume_contact_section(story, "РљРѕРЅС‚Р°РєС‚С‹ Рё СЃСЃС‹Р»РєРё", data, styles, template, content_width)
    add_resume_section(story, "Р”РѕСЃС‚РёР¶РµРЅРёСЏ Рё РїСЂРѕРµРєС‚С‹", data["achievements"], styles)
    add_resume_section(story, "Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ", data["additional"], styles)
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
        item = raw.strip(" вЂў•-*")
        if item:
            links.append(item)
    return "\n".join(links)


def resume_content_score(data: dict[str, str]) -> int:
    return sum(len(value or "") for value in data.values()) + len(resume_skill_tags(data.get("skills", ""))) * 18


def build_resume_highlight_strip(data: dict[str, str], styles: dict, template: dict[str, str], content_width: float) -> list:
    items = [
        ("Р¤РѕРєСѓСЃ", data.get("position") or "Р¦РµР»РµРІР°СЏ СЂРѕР»СЊ"),
        ("РџСЂРѕС„РёР»СЊ", data.get("summary") or data.get("experience") or "РљСЂР°С‚РєРёР№ РїСЂРѕС„РµСЃСЃРёРѕРЅР°Р»СЊРЅС‹Р№ РїСЂРѕС„РёР»СЊ"),
        ("РќР°РІС‹РєРё", ", ".join(resume_skill_tags(data.get("skills", ""), 4)) or "РљР»СЋС‡РµРІС‹Рµ РєРѕРјРїРµС‚РµРЅС†РёРё"),
    ]
    card_width = content_width / 3
    row = []
    for title, value in items:
        cell = [
            Paragraph(resume_safe_text(resume_clean_text(title).upper()), styles["ResumeMetricLabel"]),
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
    return [Paragraph("РљР»СЋС‡РµРІС‹Рµ РЅР°РІС‹РєРё", styles["ResumeSection"]), table, Spacer(1, 8)]


def build_resume_fill_panel(data: dict[str, str], styles: dict, template: dict[str, str], content_width: float) -> list:
    return []
    if resume_content_score(data) > 780:
        return []
    focus = data.get("position") or "С†РµР»РµРІРѕР№ СЂРѕР»Рё"
    skills = ", ".join(resume_skill_tags(data.get("skills", ""), 5)) or "РєР»СЋС‡РµРІС‹С… Р·Р°РґР°С‡"
    text = (
        f"Р“РѕС‚РѕРІ(Р°) Р·Р°РєСЂС‹РІР°С‚СЊ Р·Р°РґР°С‡Рё РЅР° РїРѕР·РёС†РёРё {focus}: СЂР°Р±РѕС‚Р°С‚СЊ СЃ РїСЂРёРѕСЂРёС‚РµС‚Р°РјРё, "
        f"Р±С‹СЃС‚СЂРѕ РїРѕРіСЂСѓР¶Р°С‚СЊСЃСЏ РІ РєРѕРЅС‚РµРєСЃС‚ Рё РїСЂРёРјРµРЅСЏС‚СЊ {skills} РґР»СЏ РёР·РјРµСЂРёРјРѕРіРѕ СЂРµР·СѓР»СЊС‚Р°С‚Р°."
    )
    table = Table(
        [[Paragraph("РџСЂРѕС„РµСЃСЃРёРѕРЅР°Р»СЊРЅС‹Р№ С„РѕРєСѓСЃ", styles["ResumeCardTitle"]), Paragraph(resume_safe_text(text), styles["ResumeCardBody"])]],
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
        prefix = "- " if line.startswith(("-", "вЂў", "•", "*")) else ""
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
        Paragraph(resume_safe_text(data["name"] or "Р РµР·СЋРјРµ"), styles["ResumeWhiteName"]),
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
        resume_card("РќР°РІС‹РєРё", data["skills"], styles, card_width, template),
        resume_card("РћР±СЂР°Р·РѕРІР°РЅРёРµ", data["education"], styles, card_width, template),
        resume_card("Р”РѕСЃС‚РёР¶РµРЅРёСЏ", data["achievements"], styles, card_width, template),
        resume_card("РЎСЃС‹Р»РєРё", resume_link_lines(data.get("links", "")), styles, card_width, template),
        resume_card("Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ", data["additional"], styles, card_width, template),
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
    add_resume_section(story, "РћРїС‹С‚ СЂР°Р±РѕС‚С‹", data["experience"], styles)
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
        Paragraph(resume_safe_text(data["name"] or "Р РµР·СЋРјРµ"), styles["ResumeName"]),
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
    left.append(Paragraph(resume_safe_text(data["name"] or "Р РµР·СЋРјРµ"), styles["ResumeWhiteName"]))
    if data["position"]:
        left.append(Paragraph(resume_safe_text(data["position"]), styles["ResumeWhiteRole"]))
    contact_block = resume_contact_flow(data, styles, template, left_width - 20, light=True, max_columns=1)
    if contact_block:
        left.append(Paragraph("РљРѕРЅС‚Р°РєС‚С‹", styles["ResumeSideTitle"]))
        left.extend(contact_block)
    for title, content in (("РќР°РІС‹РєРё", data["skills"]), ("Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ", data["additional"])):
        if content:
            left.append(Paragraph(title, styles["ResumeSideTitle"]))
            if title == "РќР°РІС‹РєРё":
                content = "\n".join(item.strip() for item in content.split(",") if item.strip())
            left.append(Paragraph(resume_safe_text(content), styles["ResumeSideBody"]))
    right: list = []
    if data["summary"]:
        right.append(Paragraph(resume_safe_text(data["summary"]), styles["ResumeSummary"]))
    right.append(Paragraph("РћСЃРЅРѕРІРЅРѕР№ РїСЂРѕС„РёР»СЊ", styles["ResumeSection"]))
    right.append(Paragraph("РћРїС‹С‚, РѕР±СЂР°Р·РѕРІР°РЅРёРµ Рё РїСЂРѕРµРєС‚С‹ РІС‹РЅРµСЃРµРЅС‹ РЅРёР¶Рµ РІ С€РёСЂРѕРєРёРµ СЃРµРєС†РёРё, С‡С‚РѕР±С‹ PDF Р°РєРєСѓСЂР°С‚РЅРѕ РїРµСЂРµРЅРѕСЃРёР»СЃСЏ РјРµР¶РґСѓ СЃС‚СЂР°РЅРёС†Р°РјРё.", styles["ResumeBody"]))
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
        [[Paragraph(resume_clean_text(title).upper(), styles["ResumeRailTitle"]), body]],
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
        side.append(Paragraph("РљРѕРЅС‚Р°РєС‚С‹", styles["ResumeSideTitle"]))
        side.extend(contact_block)
    if data["skills"]:
        side.append(Paragraph("РљР»СЋС‡РµРІС‹Рµ РЅР°РІС‹РєРё", styles["ResumeSideTitle"]))
        skills = "<br/>".join(escape(item.strip(), quote=False) for item in data["skills"].split(",") if item.strip())
        side.append(Paragraph(skills, styles["ResumeSideBody"]))
    if data["additional"]:
        side.append(Paragraph("Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ", styles["ResumeSideTitle"]))
        side.append(Paragraph(resume_safe_text(data["additional"]), styles["ResumeSideBody"]))
    return side


async def generate_resume_pdf(data: dict, template: str) -> Path:
    """Р“РµРЅРµСЂРёСЂСѓРµС‚ PDF СЂРµР·СЋРјРµ РЅР° РѕСЃРЅРѕРІРµ РґР°РЅРЅС‹С… Рё С€Р°Р±Р»РѕРЅР°."""
    filename = f"resume_{uuid.uuid4().hex}.pdf"
    filepath = settings.output_dir / filename
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    prepared = clean_resume_pdf_data(resume_section_data(data))
    selected = select_resume_pdf_template(RESUME_TEMPLATES.get(template, RESUME_TEMPLATES["1"]), prepared)
    labels = resume_pdf_labels(str(data.get("lang") or "ru"))
    avatar_path = make_resume_avatar(data.get("photo_path"), settings.output_dir, data.get("photo_crop"))
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

    if prepared.get("cover_letter"):
        story.extend([
            PageBreak(),
            Paragraph(resume_safe_text(labels["cover_letter"]), styles["ResumeSection"]),
            Spacer(1, 5),
            Paragraph(resume_safe_text(prepared["cover_letter"]), styles["ResumeBody"]),
        ])

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
            BotCommand(command="start", description="Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ"),
            BotCommand(command="subscribe", description="РџРѕРґРїРёСЃРєР° Р·Р° Stars"),
            BotCommand(command="pro", description="Р§С‚Рѕ РґР°РµС‚ Pro"),
            BotCommand(command="status", description="РЎС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїР°"),
            BotCommand(command="history", description="РСЃС‚РѕСЂРёСЏ РѕР±СЂР°Р±РѕС‚РѕРє"),
            BotCommand(command="resume", description="РЎРѕР·РґР°С‚СЊ PDF-СЂРµР·СЋРјРµ"),
            BotCommand(command="language", description="РЎРјРµРЅРёС‚СЊ СЏР·С‹Рє"),
            BotCommand(command="id", description="РњРѕР№ Telegram ID"),
            BotCommand(command="cancel", description="РћС‚РјРµРЅРёС‚СЊ С‚РµРєСѓС‰РµРµ РґРµР№СЃС‚РІРёРµ"),
            BotCommand(command="help", description="РљР°Рє РїРѕР»СЊР·РѕРІР°С‚СЊСЃСЏ"),
        ]
    )
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Main menu"),
            BotCommand(command="subscribe", description="Stars subscription"),
            BotCommand(command="pro", description="What Pro includes"),
            BotCommand(command="status", description="Access status"),
            BotCommand(command="wallet", description="CherryX balance"),
            BotCommand(command="link", description="Link CherryX account"),
            BotCommand(command="paysupport", description="Payment support"),
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
            BotCommand(command="start", description="Р“РѕР»РѕРІРЅРµ РјРµРЅСЋ"),
            BotCommand(command="subscribe", description="РџС–РґРїРёСЃРєР° Р·Р° Stars"),
            BotCommand(command="pro", description="Р©Рѕ РґР°С” Pro"),
            BotCommand(command="status", description="РЎС‚Р°С‚СѓСЃ РґРѕСЃС‚СѓРїСѓ"),
            BotCommand(command="history", description="Р†СЃС‚РѕСЂС–СЏ РѕР±СЂРѕР±РѕРє"),
            BotCommand(command="resume", description="РЎС‚РІРѕСЂРёС‚Рё PDF-СЂРµР·СЋРјРµ"),
            BotCommand(command="language", description="Р—РјС–РЅРёС‚Рё РјРѕРІСѓ"),
            BotCommand(command="id", description="РњС–Р№ Telegram ID"),
            BotCommand(command="cancel", description="РЎРєР°СЃСѓРІР°С‚Рё РґС–СЋ"),
            BotCommand(command="help", description="РЇРє РєРѕСЂРёСЃС‚СѓРІР°С‚РёСЃСЏ"),
        ],
        language_code="uk",
    )
    if billing_bot_mode():
        billing_commands = [
            BotCommand(command="start", description="Payment menu"),
            BotCommand(command="subscribe", description="Pay with Stars"),
            BotCommand(command="status", description="Access status"),
            BotCommand(command="wallet", description="CherryX wallet"),
            BotCommand(command="link", description="Link CherryX account"),
            BotCommand(command="paysupport", description="Payment support"),
            BotCommand(command="history", description="Payment history"),
            BotCommand(command="id", description="Telegram ID"),
            BotCommand(command="help", description="Help"),
        ]
        if admin_user_ids():
            billing_commands.extend([
                BotCommand(command="admin_stats", description="Admin stats"),
                BotCommand(command="broadcast", description="Admin broadcast"),
            ])
        await bot.set_my_commands(billing_commands)
        await bot.set_my_commands(billing_commands, language_code="en")

    if settings.mini_app_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Mini App", web_app=WebAppInfo(url=settings.mini_app_url)))

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    asyncio.create_task(cleanup_loop())
    asyncio.create_task(heartbeat_loop())
    logger.info("Bot started. Free users: %s. FFmpeg: %s", sorted(settings.free_user_ids), ffmpeg_available())
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


