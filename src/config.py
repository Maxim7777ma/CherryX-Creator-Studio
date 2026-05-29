from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import os


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    subscription_stars: int
    subscription_days: int
    database_path: Path
    storage_dir: Path
    output_dir: Path
    mini_app_url: str
    web_host: str
    web_port: int
    allow_web_without_telegram: bool
    free_user_ids: set[int]
    max_image_mb: int
    max_video_mb: int
    video_timeout_seconds: int
    session_ttl_minutes: int
    cleanup_interval_seconds: int
    youtube_max_duration_minutes: int
    youtube_max_shorts: int
    youtube_short_seconds: int
    youtube_download_timeout_seconds: int
    youtube_workers: int
    shorts_focus_mode: str
    face_detection_enabled: bool
    youtube_backstage_enabled: bool
    backstage_sample_limit: int
    backstage_min_gap_seconds: int
    backstage_output_seconds: int
    backstage_segment_seconds: int
    backstage_intro_seconds: int
    subtitle_model: str
    subtitle_language: str
    subtitle_timeout_seconds: int
    subtitle_workers: int
    cover_workers: int
    free_daily_image_conversions: int
    free_daily_video_conversions: int
    free_daily_cover_generations: int
    free_daily_youtube_jobs: int
    free_daily_subtitle_jobs: int
    free_daily_package_jobs: int


def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing in .env")

    return Settings(
        bot_token=token,
        subscription_stars=parse_env_int("SUBSCRIPTION_STARS", 100, min_value=1),
        subscription_days=parse_env_int("SUBSCRIPTION_DAYS", 30, min_value=1),
        database_path=Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3")),
        storage_dir=Path(os.getenv("STORAGE_DIR", "data/files")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "data/output")),
        mini_app_url=os.getenv("MINI_APP_URL", "").strip(),
        web_host=os.getenv("WEB_HOST", "127.0.0.1"),
        web_port=parse_env_int("WEB_PORT", 8000, min_value=1),
        allow_web_without_telegram=os.getenv("ALLOW_WEB_WITHOUT_TELEGRAM", "false").lower()
        in {"1", "true", "yes", "on"},
        free_user_ids=parse_id_set(os.getenv("FREE_USER_IDS", "")),
        max_image_mb=parse_env_int("MAX_IMAGE_MB", 25, min_value=1),
        max_video_mb=parse_env_int("MAX_VIDEO_MB", 80, min_value=1),
        video_timeout_seconds=parse_env_int("VIDEO_TIMEOUT_SECONDS", 180, min_value=1),
        session_ttl_minutes=parse_env_int("SESSION_TTL_MINUTES", 60, min_value=1),
        cleanup_interval_seconds=parse_env_int("CLEANUP_INTERVAL_SECONDS", 600, min_value=1),
        youtube_max_duration_minutes=parse_env_int("YOUTUBE_MAX_DURATION_MINUTES", 360, min_value=1),
        youtube_max_shorts=parse_env_int("YOUTUBE_MAX_SHORTS", 15, min_value=1),
        youtube_short_seconds=parse_env_int("YOUTUBE_SHORT_SECONDS", 45, min_value=1),
        youtube_download_timeout_seconds=parse_env_int("YOUTUBE_DOWNLOAD_TIMEOUT_SECONDS", 3600, min_value=1),
        youtube_workers=parse_env_int("YOUTUBE_WORKERS", 1, min_value=1),
        shorts_focus_mode=os.getenv("SHORTS_FOCUS_MODE", "face").strip().lower(),
        face_detection_enabled=os.getenv("FACE_DETECTION_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        youtube_backstage_enabled=os.getenv("YOUTUBE_BACKSTAGE_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        backstage_sample_limit=parse_env_int("BACKSTAGE_SAMPLE_LIMIT", 420, min_value=1),
        backstage_min_gap_seconds=parse_env_int("BACKSTAGE_MIN_GAP_SECONDS", 90, min_value=1),
        backstage_output_seconds=parse_env_int("BACKSTAGE_OUTPUT_SECONDS", 30, min_value=1),
        backstage_segment_seconds=parse_env_int("BACKSTAGE_SEGMENT_SECONDS", 4, min_value=1),
        backstage_intro_seconds=parse_env_int("BACKSTAGE_INTRO_SECONDS", 3, min_value=0),
        subtitle_model=os.getenv("SUBTITLE_MODEL", "small").strip(),
        subtitle_language=os.getenv("SUBTITLE_LANGUAGE", "").strip(),
        subtitle_timeout_seconds=parse_env_int("SUBTITLE_TIMEOUT_SECONDS", 900, min_value=1),
        subtitle_workers=parse_env_int("SUBTITLE_WORKERS", 1, min_value=1),
        cover_workers=parse_env_int("COVER_WORKERS", 2, min_value=1),
        free_daily_image_conversions=parse_env_int("FREE_DAILY_IMAGE_CONVERSIONS", 3, min_value=0),
        free_daily_video_conversions=parse_env_int("FREE_DAILY_VIDEO_CONVERSIONS", 1, min_value=0),
        free_daily_cover_generations=parse_env_int("FREE_DAILY_COVER_GENERATIONS", 1, min_value=0),
        free_daily_youtube_jobs=parse_env_int("FREE_DAILY_YOUTUBE_JOBS", 0, min_value=0),
        free_daily_subtitle_jobs=parse_env_int("FREE_DAILY_SUBTITLE_JOBS", 0, min_value=0),
        free_daily_package_jobs=parse_env_int("FREE_DAILY_PACKAGE_JOBS", 0, min_value=0),
    )


def parse_id_set(value: str) -> set[int]:
    ids: set[int] = set()
    for chunk in value.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError:
            continue
    return ids


def parse_env_int(name: str, default: int, min_value: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            value = default
    if min_value is not None:
        return max(min_value, value)
    return value
