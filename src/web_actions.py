from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from pathlib import Path
import asyncio
import hashlib
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
import zipfile

from .bot_utils import publication_description, publication_hashtags, unique_archive_name
from . import native_tools, openai_ai
from .config import get_settings
from .image_tools import SUPPORTED_IMAGE_FORMATS, clean_base_name, convert_image, human_size
from .video_tools import VIDEO_FORMATS, convert_video, format_duration, inspect_video
from .youtube_tools import (
    create_backstage_montage,
    create_business_cover,
    create_premium_cover_from_image,
    create_subtitle_assets,
    describe_clips,
    download_youtube_video,
    estimate_cut_time,
    estimate_download_time,
    extract_youtube_url,
    get_youtube_metadata,
    make_short_clip,
    normalize_subtitle_language,
    planned_clip_count,
    rank_smart_clip_candidates,
    render_subtitle_assets,
    select_smart_clip_starts_from_candidates,
    shorts_mode_tuning,
    transcribe_subtitle_cues,
    video_source_label,
    YouTubeDownload,
    zip_clips,
)


settings = get_settings()

IMAGE_FORMAT_CHOICES = [(key, key.upper()) for key in SUPPORTED_IMAGE_FORMATS]
VIDEO_FORMAT_CHOICES = [(key, key.upper()) for key in VIDEO_FORMATS]
IMAGE_MODE_CHOICES = [
    ("light", "Легкий файл"),
    ("balanced", "Баланс"),
    ("quality", "Качество"),
]
YOUTUBE_MODE_CHOICES = [
    ("regular", "Shorts classic"),
    ("dynamic", "Shorts dynamic"),
    ("podcast", "Shorts podcast"),
    ("calm", "Shorts calm"),
    ("backstage30", "Preview 30s"),
    ("backstage60", "Preview 60s"),
    ("backstage90", "Preview 90s"),
    ("download", "Скачать MP4"),
    ("cover", "PNG-обложка"),
]
SUBTITLE_STYLE_CHOICES = [
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
SUBTITLE_LANGUAGE_CHOICES = [
    ("auto", "Auto"),
    ("en", "English"),
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("fr", "French"),
    ("de", "German"),
    ("es", "Spanish"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("pl", "Polish"),
    ("tr", "Turkish"),
    ("nl", "Dutch"),
    ("sv", "Swedish"),
    ("ar", "Arabic"),
    ("hi", "Hindi"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh", "Chinese"),
    ("ka", "Georgian"),
    ("hy", "Armenian"),
]
RESUME_TEMPLATE_CHOICES = [
    ("1", "Classic"),
    ("2", "Executive"),
    ("3", "Creative"),
    ("4", "Modern"),
    ("5", "Tech"),
    ("6", "Minimal"),
    ("7", "Premium"),
    ("8", "Focus"),
    ("9", "Nordic"),
    ("10", "Legal"),
    ("11", "Startup"),
    ("12", "Finance"),
    ("13", "Academic"),
    ("14", "Compact"),
]

VIDEO_SUFFIXES = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".mkv",
    ".avi",
    ".gif",
    ".wmv",
    ".flv",
}
WEB_OUTPUT_ROOT = settings.output_dir / "django"
WEB_STORAGE_ROOT = settings.storage_dir / "django"


@dataclass
class JobOutput:
    label: str
    path: Path
    media_type: str = "application/octet-stream"

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0


@dataclass
class WebJob:
    id: str
    kind: str
    title: str
    status: str = "queued"
    progress: int = 0
    message: str = "В очереди"
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    outputs: list[JobOutput] = field(default_factory=list)
    params: dict[str, object] = field(default_factory=dict)
    owner_id: int | None = None
    guest_key: str = ""
    runner: object | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class YouTubeProfile:
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
    strict_face: bool = False
    alignment_mode: str = "default"


@dataclass(frozen=True)
class YouTubeProcessingPlan:
    code: str
    label: str
    sample_limit: int
    face_detection: bool
    analysis_seconds: float
    render_workers: int
    focus_mode: str


_jobs: dict[str, WebJob] = {}
_pending_jobs: deque[tuple[WebJob, object]] = deque()
_running_job_ids: set[str] = set()
_running_by_account: dict[str, int] = defaultdict(int)
_deleted_job_ids: set[str] = set()
_lock = threading.RLock()
_executor = ThreadPoolExecutor(max_workers=max(1, settings.job_max_workers))
ACTIVE_JOB_STATUSES = {"queued", "running", "processing", "paused"}
INTERRUPTIBLE_JOB_STATUSES = {"queued", "running", "processing"}
INTERRUPT_REQUEST_STATUSES = {"cancelled", "paused"}
RECOVERABLE_JOB_STATUSES = {"paused", "failed"}


class JobCancelled(RuntimeError):
    pass


def is_openai_ready() -> bool:
    return openai_ai.is_openai_ready()


def native_status() -> dict[str, object]:
    helpers = {
        "audio_rms": native_tools.helper_available("audio_rms"),
        "media_analyzer": native_tools.helper_available("media_analyzer"),
        "cover_pick": native_tools.helper_available("cover_pick"),
        "face_track": native_tools.helper_available("face_track"),
    }
    enabled = any(helpers.values())
    return {
        "enabled": enabled,
        "label": "on" if enabled else "off",
        "message": "Native acceleration is available" if enabled else "Native acceleration unavailable, using Python/FFmpeg fallback",
        "helpers": helpers,
        "capabilities": native_tools.capabilities(),
    }


def queue_status(owner_id: int | None = None, guest_key: str = "") -> dict[str, object]:
    with _lock:
        jobs = list(_jobs.values())
        pending_total = len(_pending_jobs)
        running_total = len(_running_job_ids)
        if owner_id is not None or guest_key:
            account_jobs = [job for job in jobs if _access_matches(job.owner_id, job.guest_key, owner_id, guest_key)]
            pending_account = sum(1 for job in account_jobs if job.status == "queued")
            running_account = sum(1 for job in account_jobs if job.status == "running")
        else:
            pending_account = pending_total
            running_account = running_total
    return {
        "max_workers": max(1, int(getattr(settings, "job_max_workers", 1) or 1)),
        "account_concurrent_jobs": max(1, int(getattr(settings, "account_concurrent_jobs", 10) or 10)),
        "pending_jobs": pending_total,
        "running_jobs": running_total,
        "account_pending_jobs": pending_account,
        "account_running_jobs": running_account,
    }


def _normalize_requested_clip_count(value: int | str | None, default_count: int) -> int:
    try:
        requested = int(value or 0)
    except (TypeError, ValueError):
        requested = 0
    if requested <= 0:
        requested = 10
    upper = max(1, settings.youtube_max_shorts)
    return max(1, min(upper, requested or default_count))


def start_conversion_job(
    source: Path,
    original_name: str,
    content_type: str,
    target_format: str,
    output_name: str,
    image_mode: str,
    owner_id: int | None = None,
    guest_key: str = "",
    job_id: str | None = None,
    run_inline: bool = False,
) -> dict:
    target_format = target_format.lower().strip()
    if target_format not in SUPPORTED_IMAGE_FORMATS and target_format not in VIDEO_FORMATS:
        raise ValueError("Неподдерживаемый формат")

    def worker(job: WebJob) -> None:
        output_dir = WEB_OUTPUT_ROOT / job.id / "convert"
        output_base = clean_base_name(output_name or original_name)
        if target_format in VIDEO_FORMATS and _looks_like_video(source, content_type):
            _update_job(job, 18, "Читаю параметры видео")
            result = convert_video(source, output_dir, target_format, output_base, settings.video_timeout_seconds)
            _add_output(job, result.path, f"Видео {target_format.upper()}")
            _update_job(
                job,
                92,
                f"Готово: {result.output.width or '?'}x{result.output.height or '?'}, {human_size(result.output.size_bytes)}",
            )
            return

        _update_job(job, 22, "Конвертирую изображение")
        output, info = convert_image(source, output_dir, target_format, output_base, image_mode)
        _add_output(job, output, f"Изображение {target_format.upper()}")
        _update_job(job, 92, f"Готово: {info.width}x{info.height}, {human_size(info.size_bytes)}")

    return _submit_job(
        "convert",
        f"Конвертация {original_name}",
        worker,
        {
            "action": "convert",
            "source": str(source),
            "original_name": original_name,
            "content_type": content_type,
            "target_format": target_format,
            "output_name": output_name,
            "image_mode": image_mode,
        },
        owner_id,
        guest_key,
        job_id=job_id,
        run_inline=run_inline,
    )


def start_youtube_job(
    url: str,
    mode: str,
    owner_id: int | None = None,
    guest_key: str = "",
    ai_improve: bool = False,
    clip_count: int | None = None,
    processing_speed: str = "auto",
    job_id: str | None = None,
    run_inline: bool = False,
) -> dict:
    clean_url = _normalize_video_url(url)
    requested_processing_speed = _normalize_processing_speed(processing_speed)
    if mode == "download":
        return start_video_download_job(clean_url, owner_id, guest_key, job_id=job_id, run_inline=run_inline)
    if mode == "cover":
        return start_youtube_cover_job(clean_url, owner_id, guest_key, ai_cover=ai_improve, job_id=job_id, run_inline=run_inline)

    profile = youtube_render_profile(mode)
    requested_clip_count = _normalize_requested_clip_count(clip_count, profile.max_shorts)
    if requested_clip_count != profile.max_shorts:
        profile = replace(profile, max_shorts=requested_clip_count)
    source_label = video_source_label(clean_url)

    def worker(job: WebJob) -> None:
        source_dir = WEB_STORAGE_ROOT / job.id / "youtube"
        output_dir = WEB_OUTPUT_ROOT / job.id / "youtube"
        _update_job(job, 8, f"{source_label}: читаю метаданные")
        metadata = get_youtube_metadata(clean_url, settings.youtube_download_timeout_seconds)
        max_duration = settings.youtube_max_duration_minutes * 60
        if metadata.duration_seconds > max_duration:
            raise ValueError(
                f"Видео слишком длинное: {format_duration(metadata.duration_seconds)}. "
                f"Лимит: {settings.youtube_max_duration_minutes} мин."
            )

        initial_plan = _youtube_processing_plan(requested_processing_speed, profile, metadata.duration_seconds)
        plan_text = _youtube_plan_text(profile, metadata.duration_seconds)
        size_text = human_size(metadata.estimated_size_bytes) if metadata.estimated_size_bytes else "размер заранее не найден"
        _update_job(
            job,
            18,
            f"{metadata.title}. {format_duration(metadata.duration_seconds)}. "
            f"{size_text}. {plan_text}. Загрузка: {estimate_download_time(metadata.estimated_size_bytes)}",
        )
        _update_job(job, 19, f"Processing plan: {initial_plan.label}")
        download = _download_youtube_video_cached(clean_url, source_dir, settings.youtube_download_timeout_seconds, metadata.estimated_size_bytes, metadata)
        actual_duration = float(download.duration_seconds or metadata.duration_seconds or 0)
        if actual_duration <= 0:
            actual_duration = float(inspect_video(download.path).duration_seconds or 0)
        if actual_duration > max_duration:
            raise ValueError(
                f"Video is too long: {format_duration(actual_duration)}. "
                f"Limit: {settings.youtube_max_duration_minutes} min."
            )
        if metadata.duration_seconds <= 0 < actual_duration:
            _update_job(job, 24, f"Duration after download: {format_duration(actual_duration)}. {_youtube_plan_text(profile, actual_duration)}")

        if profile.is_backstage:
            processing_plan = _youtube_processing_plan(requested_processing_speed, profile, actual_duration)
            if not settings.youtube_backstage_enabled:
                raise RuntimeError("Preview-монтаж выключен в настройках")
            _update_job(job, 45, "Собираю широкий Preview-монтаж")
            montage = create_backstage_montage(
                download.path,
                output_dir,
                download.title,
                actual_duration,
                settings.video_timeout_seconds,
                profile.backstage_output_seconds,
                profile.backstage_segment_seconds,
                profile.backstage_intro_seconds,
                processing_plan.sample_limit,
                profile.min_gap_seconds,
                processing_plan.face_detection,
            )
            _add_output(job, montage.path, "Preview MP4")
            _update_job(job, 78, "Генерирую PNG-обложку")
            cover = create_business_cover(
                montage.path,
                output_dir / "cover",
                download.title,
                montage.duration_seconds,
                settings.video_timeout_seconds,
                processing_plan.face_detection,
            )
            _add_output(job, cover, "PNG-обложка")
            _update_job(job, 94, f"Preview готов: {human_size(montage.path.stat().st_size)}")
            return

        _update_job(job, 34, "Ищу сильные моменты для Shorts")
        processing_plan = _youtube_processing_plan(requested_processing_speed, profile, actual_duration)
        max_candidates = max(profile.max_shorts * 8, 24)
        cache_key = _youtube_analysis_cache_key(clean_url, profile.mode, actual_duration, profile.short_seconds, max_candidates, processing_plan)
        clip_candidates = _load_youtube_analysis_cache(cache_key)
        if clip_candidates:
            _update_job(job, 46, f"Moments from cache: {len(clip_candidates)}")
        else:
            last_analysis_progress = {"value": -1, "time": 0.0}

            def on_analysis_progress(done: int, total: int) -> None:
                total = max(1, int(total or 1))
                percent = max(0, min(100, int(done / total * 100)))
                progress = 34 + int(percent * 0.12)
                now = time.time()
                if progress <= last_analysis_progress["value"] and now - last_analysis_progress["time"] < 4:
                    return
                last_analysis_progress["value"] = progress
                last_analysis_progress["time"] = now
                _update_job(job, progress, f"Analyzing moments: {percent}% ({processing_plan.label})")

            _update_job(job, 34, f"Analyzing moments ({processing_plan.label})")
            clip_candidates = rank_smart_clip_candidates(
                download.path,
                actual_duration,
                max_candidates,
                profile.short_seconds,
                processing_plan.sample_limit,
                processing_plan.face_detection,
                profile.mode,
                progress_callback=on_analysis_progress,
                max_analysis_seconds=processing_plan.analysis_seconds,
                strict_focus=profile.strict_face,
            )
            _save_youtube_analysis_cache(cache_key, clip_candidates)
            _update_job(job, 46, f"Shorts candidates found: {len(clip_candidates)}")
        render_queue = select_smart_clip_starts_from_candidates(
            clip_candidates,
            actual_duration,
            profile.max_shorts * 2 if profile.strict_face else profile.max_shorts,
            profile.short_seconds,
            profile.strict_face,
            min_gap_seconds=profile.min_gap_seconds,
        )
        if profile.strict_face and not render_queue and clip_candidates:
            _update_job(job, 47, "No prevalidated face-safe candidates; probing render-time face tracks")
            render_queue = select_smart_clip_starts_from_candidates(
                clip_candidates,
                actual_duration,
                profile.max_shorts * 2,
                profile.short_seconds,
                profile.strict_face,
                min_gap_seconds=profile.min_gap_seconds,
                allow_strict_probe=True,
            )
        starts = render_queue[: profile.max_shorts]
        if not starts:
            raise ValueError("No face-safe moments found for Shorts. Try Smart/Pro, a clearer source video, or Preview mode.")

        if ai_improve and not profile.strict_face:
            starts = _ai_improve_clip_starts(job, download.title, actual_duration, clip_candidates or starts, profile.max_shorts)
        elif ai_improve and profile.strict_face:
            _update_job(job, 47, "AI improve skipped for strict face-safe Shorts selection")
        selected_starts = list(starts)
        candidate_by_start = {}
        for candidate in clip_candidates:
            try:
                candidate_by_start[int(candidate.get("start") or 0)] = dict(candidate)
            except (TypeError, ValueError):
                continue

        source_info = inspect_video(download.path)
        clips = []
        base_name = clean_base_name(download.title, "youtube_short")
        editor_source_path = _prepare_youtube_editor_source(download.path, output_dir, base_name)

        def render_short_with_retries(start_second: int, index: int):
            max_start = max(0, int(actual_duration) - max(1, profile.short_seconds))
            retry_offsets = [0, -2, 2, 4, -4] if profile.strict_face else [0]
            errors: list[str] = []
            tried: set[int] = set()
            for offset in retry_offsets:
                retry_start = max(0, min(max_start, int(start_second) + offset))
                if retry_start in tried:
                    continue
                tried.add(retry_start)
                try:
                    clip = make_short_clip(
                        download.path,
                        output_dir,
                        base_name,
                        actual_duration,
                        retry_start,
                        index,
                        profile.short_seconds,
                        settings.video_timeout_seconds,
                        processing_plan.focus_mode,
                        processing_plan.face_detection,
                        source_info.width,
                        source_info.height,
                        profile.strict_face,
                        profile.alignment_mode,
                    )
                    return clip, retry_start, errors
                except RuntimeError as exc:
                    errors.append(f"{format_duration(retry_start)}: {exc}")
                    if not profile.strict_face or "face" not in str(exc).lower():
                        raise
            raise RuntimeError("; ".join(errors) or "face-safe retry failed")

        if processing_plan.render_workers > 1 and len(starts) > 1:
            render_items = list(enumerate(starts, start=1))

            def render_clip(item: tuple[int, int]):
                index, start_second = item
                return index, make_short_clip(
                    download.path,
                    output_dir,
                    base_name,
                    actual_duration,
                    start_second,
                    index,
                    profile.short_seconds,
                    settings.video_timeout_seconds,
                    processing_plan.focus_mode,
                    processing_plan.face_detection,
                    source_info.width,
                    source_info.height,
                    profile.strict_face,
                    profile.alignment_mode,
                )

            rendered: dict[int, object] = {}
            _update_job(job, 50, f"Rendering Shorts in parallel: {len(render_items)}")
            with ThreadPoolExecutor(max_workers=processing_plan.render_workers) as render_pool:
                futures = {render_pool.submit(render_clip, item): item for item in render_items}
                for done_count, future in enumerate(as_completed(futures), start=1):
                    index, clip = future.result()
                    rendered[index] = clip
                    progress = 50 + int(done_count / max(1, len(render_items)) * 28)
                    _update_job(job, progress, f"Short {done_count}/{len(render_items)} rendered")
            for index in sorted(rendered):
                clip = rendered[index]
                clips.append(clip)
                try:
                    clip.path.with_suffix(".edit.json").write_text(
                        json.dumps(
                            {
                                "kind": "youtube_short_source",
                                "source_path": str(editor_source_path),
                                "fallback_source_path": str(download.path),
                                "source_title": download.title,
                                "source_url": clean_url,
                                "source_start": float(clip.start_seconds),
                                "clip_duration": float(clip.duration_seconds),
                                "source_width": source_info.width,
                                "source_height": source_info.height,
                                "mode": profile.mode,
                                "aspect": "9 / 16",
                                "selection": _clip_selection_report(candidate_by_start.get(int(clip.start_seconds), {}), profile.mode, processing_plan.label),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                _add_output(job, clip.path, f"Short {index}")
            starts = []
        sequential_starts = render_queue if profile.strict_face else starts
        for render_index, start_second in enumerate(sequential_starts, start=1):
            if profile.strict_face and len(clips) >= profile.max_shorts:
                break
            index = len(clips) + 1 if profile.strict_face else render_index
            progress = 38 + int((index - 1) / max(1, len(starts)) * 38)
            _update_job(job, progress, f"Режу клип {index}/{len(starts)}: старт {format_duration(start_second)}")
            try:
                clip, actual_start_second, retry_errors = render_short_with_retries(start_second, index)
            except RuntimeError as exc:
                if profile.strict_face and "face" in str(exc).lower():
                    _update_job(job, progress, f"Skipped weak face crop at {format_duration(start_second)}")
                    continue
                raise
            clips.append(clip)
            try:
                clip.path.with_suffix(".edit.json").write_text(
                    json.dumps(
                        {
                            "kind": "youtube_short_source",
                            "source_path": str(editor_source_path),
                            "fallback_source_path": str(download.path),
                            "source_title": download.title,
                            "source_url": clean_url,
                            "source_start": float(clip.start_seconds),
                            "clip_duration": float(clip.duration_seconds),
                            "source_width": source_info.width,
                            "source_height": source_info.height,
                            "mode": profile.mode,
                            "aspect": "9 / 16",
                            "selection": {
                                **_clip_selection_report(candidate_by_start.get(int(start_second), {}), profile.mode, processing_plan.label),
                                "requested_start": int(start_second),
                                "render_start": int(actual_start_second),
                                "retry_errors": retry_errors,
                            },
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
            _add_output(job, clip.path, f"Short {index}")

        if not clips:
            raise ValueError("No face-safe Shorts rendered. Try Smart/Pro, a clearer source video, or Preview mode.")

        _update_job(job, 82, "Собираю ZIP со всеми Shorts")
        zip_path = zip_clips(clips, output_dir / f"{base_name}_shorts.zip")
        _add_output(job, zip_path, f"ZIP: {len(clips)} Shorts")
        try:
            _update_job(job, 90, "Генерирую PNG-обложку")
            cover = create_business_cover(
                download.path,
                output_dir / "cover",
                download.title,
                actual_duration,
                timeout_seconds=settings.video_timeout_seconds,
                face_detection_enabled=processing_plan.face_detection,
                avoid_seconds=selected_starts,
            )
            _add_output(job, cover, "PNG-обложка")
        except Exception:
            _update_job(job, 92, "Shorts готовы, обложку сделать не удалось")
        _update_job(job, 96, f"Готово: {describe_clips(clips)}")

    return _submit_job(
        "youtube",
        youtube_render_profile(mode).label,
        worker,
        {
            "action": "youtube",
            "url": clean_url,
            "mode": mode,
            "ai_improve": bool(ai_improve),
            "clip_count": requested_clip_count,
            "processing_speed": requested_processing_speed,
        },
        owner_id,
        guest_key,
        job_id=job_id,
        run_inline=run_inline,
    )


def start_video_download_job(url: str, owner_id: int | None = None, guest_key: str = "", job_id: str | None = None, run_inline: bool = False) -> dict:
    clean_url = _normalize_video_url(url)

    def worker(job: WebJob) -> None:
        source_dir = WEB_STORAGE_ROOT / job.id / "source_download"
        output_dir = WEB_OUTPUT_ROOT / job.id / "source_download"
        _update_job(job, 15, "Скачиваю исходное видео")
        metadata = get_youtube_metadata(clean_url, settings.youtube_download_timeout_seconds)
        download = _download_youtube_video_cached(clean_url, source_dir, settings.youtube_download_timeout_seconds, metadata.estimated_size_bytes, metadata)
        output_path = download.path
        if output_path.suffix.lower() != ".mp4":
            _update_job(job, 65, "Конвертирую в MP4")
            output_path = convert_video(
                download.path,
                output_dir,
                "mp4",
                clean_base_name(download.title, "download"),
                settings.video_timeout_seconds,
            ).path
        _add_output(job, output_path, "MP4")
        _update_job(job, 94, f"Готово: {download.title}")

    return _submit_job("download", "Скачать MP4", worker, {"action": "video_download", "url": clean_url}, owner_id, guest_key, job_id=job_id, run_inline=run_inline)


def start_youtube_cover_job(url: str, owner_id: int | None = None, guest_key: str = "", ai_cover: bool = False, job_id: str | None = None, run_inline: bool = False) -> dict:
    clean_url = _normalize_video_url(url)

    def worker(job: WebJob) -> None:
        source_dir = WEB_STORAGE_ROOT / job.id / "youtube_cover"
        output_dir = WEB_OUTPUT_ROOT / job.id / "youtube_cover"
        _update_job(job, 15, "Скачиваю видео для обложки")
        metadata = get_youtube_metadata(clean_url, settings.youtube_download_timeout_seconds)
        download = _download_youtube_video_cached(clean_url, source_dir, settings.youtube_download_timeout_seconds, metadata.estimated_size_bytes, metadata)
        _update_job(job, 70, "Генерирую PNG-обложку")
        cover = create_business_cover(
            download.path,
            output_dir,
            download.title,
            download.duration_seconds,
            settings.video_timeout_seconds,
            settings.face_detection_enabled,
        )
        _add_output(job, cover, "PNG-обложка")
        if ai_cover:
            _maybe_add_ai_cover(job, cover, output_dir / "ai_cover", download.title)
        _update_job(job, 94, f"Готово: {download.title}")

    return _submit_job("youtube_cover", "YouTube PNG-обложка", worker, {"action": "youtube_cover", "url": clean_url, "ai_cover": bool(ai_cover)}, owner_id, guest_key, job_id=job_id, run_inline=run_inline)


def start_cover_job(source: Path, original_name: str, title: str, variants: int, owner_id: int | None = None, guest_key: str = "", ai_cover: bool = False, job_id: str | None = None, run_inline: bool = False) -> dict:
    variant_count = max(1, min(6, int(variants or 1)))
    clean_title = clean_base_name(title or original_name, "cover")

    def worker(job: WebJob) -> None:
        output_dir = WEB_OUTPUT_ROOT / job.id / "covers"
        _update_job(job, 12, "Читаю видео")
        info = inspect_video(source)
        covers: list[Path] = []
        used_cover_seconds: list[int] = []
        for index in range(1, variant_count + 1):
            progress = 18 + int((index - 1) / variant_count * 58)
            _update_job(job, progress, f"Генерирую обложку {index}/{variant_count}")
            cover = create_business_cover(
                source,
                output_dir / f"variant_{index}",
                clean_title,
                info.duration_seconds,
                settings.video_timeout_seconds,
                settings.face_detection_enabled,
                variant_index=index,
                variant_seed=abs(hash((job.id, clean_title, index))) % 1_000_000,
                avoid_seconds=used_cover_seconds,
            )
            try:
                meta_path = cover.with_suffix(".design.json")
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    used_cover_seconds.append(int(meta.get("start_seconds") or 0))
            except Exception:
                pass
            covers.append(cover)
            _add_output(job, cover, f"Обложка {index}")
        if ai_cover and covers:
            _maybe_add_ai_cover(job, covers[0], output_dir / "ai_cover", clean_title)
        if len(covers) > 1:
            _update_job(job, 86, "Собираю ZIP с вариантами")
            zip_path = output_dir / "cover_variants.zip"
            _zip_paths(covers, zip_path)
            _add_output(job, zip_path, "ZIP с обложками")
        _update_job(job, 94, f"Готово: {variant_count} вариант(ов)")

    return _submit_job(
        "cover",
        f"PNG-обложка: {clean_title}",
        worker,
        {
            "action": "cover",
            "source": str(source),
            "original_name": original_name,
            "title": title,
            "variants": variant_count,
            "ai_cover": bool(ai_cover),
        },
        owner_id,
        guest_key,
        job_id=job_id,
        run_inline=run_inline,
    )


def start_subtitle_job(source: Path, original_name: str, title: str, style: str, language: str, owner_id: int | None = None, guest_key: str = "", ai_transcription: bool = False, job_id: str | None = None, run_inline: bool = False) -> dict:
    subtitle_style = _normalize_choice(style, SUBTITLE_STYLE_CHOICES, "pop")
    subtitle_language = _normalize_language(language)
    clean_title = clean_base_name(title or original_name, "subtitled")

    def worker(job: WebJob) -> None:
        output_dir = WEB_OUTPUT_ROOT / job.id / "subtitles"
        _update_job(job, 15, "Распознаю речь")
        cues = _transcribe_with_optional_ai(job, source, subtitle_language, ai_transcription)
        if not cues:
            raise ValueError("Речь для субтитров не найдена")
        _update_job(job, 58, f"Фраз найдено: {len(cues)}. Верстаю субтитры")
        assets = create_subtitle_assets(source, output_dir, clean_title, cues, subtitle_style)
        _update_job(job, 78, "Вшиваю субтитры в видео")
        rendered = render_subtitle_assets(source, assets, settings.subtitle_timeout_seconds)
        _add_output(job, rendered.path, "Видео с субтитрами")
        _add_output(job, assets.ass_path, "ASS-субтитры")
        _update_job(job, 94, f"Готово: {len(cues)} фраз")

    return _submit_job(
        "subtitles",
        f"Субтитры: {clean_title}",
        worker,
        {
            "action": "subtitles",
            "source": str(source),
            "original_name": original_name,
            "title": title,
            "style": subtitle_style,
            "language": language,
            "ai_transcription": bool(ai_transcription),
        },
        owner_id,
        guest_key,
        job_id=job_id,
        run_inline=run_inline,
    )


def start_package_job(source: Path, original_name: str, title: str, style: str, language: str, owner_id: int | None = None, guest_key: str = "", ai_transcription: bool = False, ai_cover: bool = False, job_id: str | None = None, run_inline: bool = False) -> dict:
    subtitle_style = _normalize_choice(style, SUBTITLE_STYLE_CHOICES, "pop")
    subtitle_language = _normalize_language(language)
    clean_title = clean_base_name(title or original_name, "publication")

    def worker(job: WebJob) -> None:
        output_dir = WEB_OUTPUT_ROOT / job.id / "package"
        output_dir.mkdir(parents=True, exist_ok=True)
        package_files: list[Path] = [source]

        _update_job(job, 12, "Читаю видео")
        info = inspect_video(source)
        _update_job(job, 30, "Генерирую PNG-обложку")
        cover = create_business_cover(
            source,
            output_dir / "cover",
            clean_title,
            info.duration_seconds,
            settings.video_timeout_seconds,
            settings.face_detection_enabled,
        )
        package_files.append(cover)
        _add_output(job, cover, "PNG-обложка")
        if ai_cover:
            ai_cover_path = _maybe_add_ai_cover(job, cover, output_dir / "ai_cover", clean_title)
            if ai_cover_path:
                package_files.append(ai_cover_path)

        subtitle_note = "Субтитры не добавлены: речь не найдена или распознавание недоступно."
        transcript_text = ""
        try:
            _update_job(job, 50, "Пробую добавить субтитры")
            cues = _transcribe_with_optional_ai(job, source, subtitle_language, ai_transcription)
            if cues:
                transcript_text = " ".join(cue.text for cue in cues[:24] if getattr(cue, "text", ""))
                assets = create_subtitle_assets(source, output_dir / "subtitles", f"{clean_title}_package", cues, subtitle_style)
                rendered = render_subtitle_assets(source, assets, settings.subtitle_timeout_seconds)
                package_files.extend([rendered.path, assets.ass_path])
                _add_output(job, rendered.path, "Видео с субтитрами")
                subtitle_note = f"Субтитры добавлены, фраз найдено: {len(cues)}."
        except Exception:
            subtitle_note = "Субтитры не добавлены: распознавание завершилось ошибкой."

        _update_job(job, 74, "Пишу описание и manifest")
        hashtags = publication_hashtags(clean_title, transcript_text)
        description_path = output_dir / "description.txt"
        description_path.write_text(
            publication_description(clean_title, format_duration(info.duration_seconds), hashtags, subtitle_note, transcript_text, language),
            encoding="utf-8",
        )
        manifest_path = output_dir / "package_manifest.txt"
        manifest_path.write_text(
            "\n".join(
                [
                    "Publication package",
                    f"Title: {clean_title}",
                    f"Video: {source.name}",
                    f"Cover: {cover.name}",
                    f"Subtitles: {subtitle_note}",
                    f"Hashtags: {' '.join(hashtags)}",
                ]
            ),
            encoding="utf-8",
        )
        package_files.extend([description_path, manifest_path])
        _add_output(job, description_path, "Описание")

        _update_job(job, 88, "Собираю ZIP")
        zip_path = output_dir / f"{clean_title}_package.zip"
        _zip_paths(package_files, zip_path)
        _add_output(job, zip_path, "Пакет публикации ZIP")
        _update_job(job, 95, f"Готово: {human_size(zip_path.stat().st_size)}")

    return _submit_job(
        "package",
        f"Пакет публикации: {clean_title}",
        worker,
        {
            "action": "package",
            "source": str(source),
            "original_name": original_name,
            "title": title,
            "style": subtitle_style,
            "language": language,
            "ai_transcription": bool(ai_transcription),
            "ai_cover": bool(ai_cover),
        },
        owner_id,
        guest_key,
        job_id=job_id,
        run_inline=run_inline,
    )


def start_resume_job(data: dict[str, str], template: str, owner_id: int | None = None, guest_key: str = "", job_id: str | None = None, run_inline: bool = False) -> dict:
    resume_template = _normalize_choice(template, RESUME_TEMPLATE_CHOICES, "1")
    title = clean_base_name(data.get("name") or "resume", "resume")

    def worker(job: WebJob) -> None:
        _update_job(job, 20, "Готовлю данные резюме")
        from .bot import generate_resume_pdf

        _update_job(job, 62, "Собираю PDF")
        pdf_path = asyncio.run(generate_resume_pdf(data, resume_template))
        _add_output(job, pdf_path, "PDF-резюме")
        _update_job(job, 95, f"Готово: {pdf_path.name}")

    return _submit_job(
        "resume",
        f"PDF-резюме: {title}",
        worker,
        {
            "action": "resume",
            "data": data,
            "template": resume_template,
        },
        owner_id,
        guest_key,
        job_id=job_id,
        run_inline=run_inline,
    )


def _candidate_starts(candidates: list[dict[str, object]] | list[int]) -> list[int]:
    starts: list[int] = []
    for item in candidates:
        raw = item.get("start") if isinstance(item, dict) else item
        try:
            start = int(float(raw))
        except (TypeError, ValueError):
            continue
        if start not in starts:
            starts.append(start)
    return starts


def _ai_improve_clip_starts(job: WebJob, title: str, duration_seconds: float, local_candidates: list[dict[str, object]] | list[int], max_clips: int) -> list[int]:
    local_starts = _candidate_starts(local_candidates)
    if not openai_ai.is_openai_ready():
        _record_ai_meta(job, "clip_planner", {"status": "fallback", "reason": "OpenAI is not configured"})
        return sorted(local_starts[:max_clips])
    try:
        candidates = local_candidates
        if not candidates or not isinstance(candidates[0], dict):
            candidates = [{"start": int(start), "score": len(local_starts) - index} for index, start in enumerate(local_starts)]
        result = openai_ai.plan_clip_moments(title, duration_seconds, candidates, "")
        allowed = set(local_starts)
        selected: list[int] = []
        for raw_start in result.get("starts", []):
            try:
                start = int(raw_start)
            except (TypeError, ValueError):
                continue
            if start in allowed and start not in selected:
                selected.append(start)
        if not selected:
            _record_ai_meta(job, "clip_planner", {"status": "fallback", "reason": "OpenAI returned no usable starts", "model": result.get("model")})
            return sorted(local_starts[:max_clips])
        for start in local_starts:
            if len(selected) >= max_clips:
                break
            if start not in selected:
                selected.append(start)
        _record_ai_meta(
            job,
            "clip_planner",
            {
                "status": "used",
                "model": result.get("model"),
                "local_starts": local_starts,
                "selected_starts": selected[:max_clips],
                "reason": result.get("reason", ""),
            },
        )
        return sorted(selected[:max_clips])
    except Exception as exc:
        _record_ai_meta(job, "clip_planner", {"status": "fallback", "reason": str(exc)[:500]})
        return sorted(local_starts[:max_clips])


def _maybe_add_ai_cover(job: WebJob, reference_cover: Path, output_dir: Path, title: str, transcript_summary: str = "") -> Path | None:
    if not openai_ai.is_openai_ready():
        _record_ai_meta(job, "cover", {"status": "fallback", "reason": "OpenAI is not configured"})
        return None
    try:
        _update_job(job, min(98, max(job.progress, 82)), "Генерирую AI-обложку")
        copy = openai_ai.generate_cover_copy(title, transcript_summary)
        final_title = "\n".join(part for part in (copy.get("headline"), copy.get("description")) if part)
        frame_notes = (
            f"Use this local cover as the visual reference: {reference_cover.name}. "
            f"Final overlay copy will be: headline={copy.get('headline')!r}, description={copy.get('description')!r}, eyebrow={copy.get('eyebrow')!r}. "
            "Leave negative space for that copy."
        )
        prompt = openai_ai.generate_cover_prompt(title, transcript_summary, frame_notes)
        raw_output = output_dir / f"{clean_base_name(title, 'cover')}_ai_raw.png"
        final_output = output_dir / f"{clean_base_name(title, 'cover')}_ai_cover.png"
        openai_ai.generate_cover_image(reference_cover, title, prompt, raw_output)
        create_premium_cover_from_image(raw_output, final_output, final_title or title)
        _add_output(job, final_output, "AI PNG-cover")
        _record_ai_meta(
            job,
            "cover",
            {
                "status": "used",
                "model": settings.openai_text_model,
                "copy": copy,
                "prompt": prompt[:700],
                "path": str(final_output),
                "selected_outputs": [str(final_output)],
            },
        )
        return final_output
    except Exception as exc:
        _record_ai_meta(job, "cover", {"status": "fallback", "reason": str(exc)[:500]})
        return None


def _transcribe_with_optional_ai(job: WebJob, source: Path, language: str | None, ai_transcription: bool):
    if ai_transcription:
        if openai_ai.is_openai_ready():
            try:
                cues = openai_ai.transcribe_video_audio(source, language)
                if cues:
                    _record_ai_meta(job, "transcription", {"status": "used", "model": settings.openai_transcribe_model, "cue_count": len(cues)})
                    return cues
                _record_ai_meta(job, "transcription", {"status": "fallback", "reason": "OpenAI returned no cues"})
            except Exception as exc:
                _record_ai_meta(job, "transcription", {"status": "fallback", "reason": str(exc)[:500]})
        else:
            _record_ai_meta(job, "transcription", {"status": "fallback", "reason": "OpenAI is not configured"})
    cues = transcribe_subtitle_cues(source, settings.subtitle_model, language)
    if ai_transcription:
        _record_ai_meta(job, "transcription_fallback", {"status": "used", "model": f"faster-whisper:{settings.subtitle_model}", "cue_count": len(cues)})
    return cues


def _record_ai_meta(job: WebJob, key: str, value: dict[str, object]) -> None:
    value = dict(value)
    if value.get("status") == "fallback" and value.get("reason") and not value.get("fallback_reason"):
        value["fallback_reason"] = value.get("reason")
    value.setdefault("model", "")
    value.setdefault("selected_outputs", [])
    with _lock:
        current = job.params.get("ai")
        ai_meta = dict(current) if isinstance(current, dict) else {}
        ai_meta[key] = _json_safe(value)
        job.params["ai"] = ai_meta
        job.updated_at = time.time()
    _save_job_record(job)


def repeat_job(job_id: str, owner_id: int | None = None, guest_key: str = "") -> dict:
    params = _load_job_params(job_id, owner_id, guest_key)
    if not params:
        raise ValueError("У этой задачи нет сохраненных параметров для повтора")

    action = str(params.get("action") or "")
    if action == "convert":
        source = _existing_source(params.get("source"))
        return start_conversion_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            content_type=str(params.get("content_type") or ""),
            target_format=str(params.get("target_format") or "webp"),
            output_name=str(params.get("output_name") or source.stem),
            image_mode=str(params.get("image_mode") or "balanced"),
            owner_id=owner_id,
            guest_key=guest_key,
        )
    if action == "youtube":
        return start_youtube_job(
            str(params.get("url") or ""),
            str(params.get("mode") or "regular"),
            owner_id,
            guest_key,
            bool(params.get("ai_improve")),
            int(params.get("clip_count") or 10),
            str(params.get("processing_speed") or "auto"),
        )
    if action == "video_download":
        return start_video_download_job(str(params.get("url") or ""), owner_id, guest_key)
    if action == "youtube_cover":
        return start_youtube_cover_job(str(params.get("url") or ""), owner_id, guest_key, bool(params.get("ai_cover")))
    if action == "cover":
        source = _existing_source(params.get("source"))
        return start_cover_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            variants=int(params.get("variants") or 1),
            owner_id=owner_id,
            guest_key=guest_key,
            ai_cover=bool(params.get("ai_cover")),
        )
    if action == "subtitles":
        source = _existing_source(params.get("source"))
        return start_subtitle_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            style=str(params.get("style") or "pop"),
            language=str(params.get("language") or "auto"),
            owner_id=owner_id,
            guest_key=guest_key,
            ai_transcription=bool(params.get("ai_transcription")),
        )
    if action == "package":
        source = _existing_source(params.get("source"))
        return start_package_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            style=str(params.get("style") or "pop"),
            language=str(params.get("language") or "auto"),
            owner_id=owner_id,
            guest_key=guest_key,
            ai_transcription=bool(params.get("ai_transcription")),
            ai_cover=bool(params.get("ai_cover")),
        )
    if action == "resume":
        data = params.get("data")
        if not isinstance(data, dict):
            raise ValueError("Сохраненные данные резюме повреждены")
        photo_path = data.get("photo_path")
        if photo_path and not Path(str(photo_path)).exists():
            data = dict(data)
            data.pop("photo_path", None)
        return start_resume_job({str(key): str(value) for key, value in data.items()}, str(params.get("template") or "1"), owner_id, guest_key)
    raise ValueError("Этот тип задачи пока нельзя повторить")


def run_persisted_job(job_id: str) -> dict:
    models = _django_models()
    if not models:
        raise RuntimeError("Django models are not ready")
    JobRecord, _, _ = models
    _close_django_connections()
    record = JobRecord.objects.filter(job_id=job_id).first()
    if not record:
        raise ValueError("Task not found")
    params = _loads_record_params(record.params_json)
    if not params:
        raise ValueError("Task has no persisted params")
    owner_id = record.owner_id
    guest_key = record.guest_key

    action = str(params.get("action") or "")
    if action == "convert":
        source = _existing_source(params.get("source"))
        return start_conversion_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            content_type=str(params.get("content_type") or ""),
            target_format=str(params.get("target_format") or "webp"),
            output_name=str(params.get("output_name") or source.stem),
            image_mode=str(params.get("image_mode") or "balanced"),
            owner_id=owner_id,
            guest_key=guest_key,
            job_id=record.job_id,
            run_inline=True,
        )
    if action == "youtube":
        return start_youtube_job(
            str(params.get("url") or ""),
            str(params.get("mode") or "regular"),
            owner_id,
            guest_key,
            bool(params.get("ai_improve")),
            int(params.get("clip_count") or 10),
            str(params.get("processing_speed") or "auto"),
            job_id=record.job_id,
            run_inline=True,
        )
    if action == "video_download":
        return start_video_download_job(str(params.get("url") or ""), owner_id, guest_key, job_id=record.job_id, run_inline=True)
    if action == "youtube_cover":
        return start_youtube_cover_job(str(params.get("url") or ""), owner_id, guest_key, bool(params.get("ai_cover")), job_id=record.job_id, run_inline=True)
    if action == "cover":
        source = _existing_source(params.get("source"))
        return start_cover_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            variants=int(params.get("variants") or 1),
            owner_id=owner_id,
            guest_key=guest_key,
            ai_cover=bool(params.get("ai_cover")),
            job_id=record.job_id,
            run_inline=True,
        )
    if action == "subtitles":
        source = _existing_source(params.get("source"))
        return start_subtitle_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            style=str(params.get("style") or "pop"),
            language=str(params.get("language") or "auto"),
            owner_id=owner_id,
            guest_key=guest_key,
            ai_transcription=bool(params.get("ai_transcription")),
            job_id=record.job_id,
            run_inline=True,
        )
    if action == "package":
        source = _existing_source(params.get("source"))
        return start_package_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            style=str(params.get("style") or "pop"),
            language=str(params.get("language") or "auto"),
            owner_id=owner_id,
            guest_key=guest_key,
            ai_transcription=bool(params.get("ai_transcription")),
            ai_cover=bool(params.get("ai_cover")),
            job_id=record.job_id,
            run_inline=True,
        )
    if action == "resume":
        data = params.get("data")
        if not isinstance(data, dict):
            raise ValueError("Saved resume data is damaged")
        return start_resume_job({str(key): str(value) for key, value in data.items()}, str(params.get("template") or "1"), owner_id, guest_key, job_id=record.job_id, run_inline=True)
    raise ValueError("Unsupported persisted task action")


def cancel_job(job_id: str, owner_id: int | None = None, guest_key: str = "") -> dict:
    with _lock:
        active_job = _jobs.get(job_id)
        if active_job and not _access_matches(active_job.owner_id, active_job.guest_key, owner_id, guest_key):
            raise ValueError("Task not found")
        if active_job:
            if active_job.status in INTERRUPTIBLE_JOB_STATUSES or active_job.status == "paused":
                active_job.status = "cancelled"
                active_job.progress = 100
                active_job.message = "Cancelled"
                active_job.error = ""
                active_job.updated_at = time.time()
                remaining = [(job, worker) for job, worker in _pending_jobs if job.id != job_id]
                _pending_jobs.clear()
                _pending_jobs.extend(remaining)
                _save_job_record(active_job)
            return _serialize_job(active_job)

    models = _django_models()
    if not models:
        raise ValueError("Task not found")
    JobRecord, _, JobEventRecord = models
    try:
        _close_django_connections()
        record = _owned_records(JobRecord, owner_id, guest_key).prefetch_related("outputs").filter(job_id=job_id).first()
        if not record:
            raise ValueError("Task not found")
        if record.status in (INTERRUPTIBLE_JOB_STATUSES | {"paused"}):
            record.status = "cancelled"
            record.progress = 100
            record.message = "Cancelled"
            record.error = ""
            record.save(update_fields=["status", "progress", "message", "error", "updated_at"])
            JobEventRecord.objects.create(job=record, status="cancelled", progress=100, message="Cancelled")
        return _serialize_job_record(record)
    except (RuntimeError, ValueError):
        raise
    except Exception as exc:
        raise RuntimeError(str(exc) or "Could not cancel task") from exc


def pause_job(job_id: str, owner_id: int | None = None, guest_key: str = "") -> dict:
    with _lock:
        active_job = _jobs.get(job_id)
        if active_job and not _access_matches(active_job.owner_id, active_job.guest_key, owner_id, guest_key):
            raise ValueError("Task not found")
        if active_job:
            if active_job.status in INTERRUPTIBLE_JOB_STATUSES:
                active_job.status = "paused"
                active_job.progress = max(0, min(99, int(active_job.progress or 0)))
                active_job.message = "Paused"
                active_job.error = ""
                active_job.updated_at = time.time()
                remaining = [(job, worker) for job, worker in _pending_jobs if job.id != job_id]
                _pending_jobs.clear()
                _pending_jobs.extend(remaining)
                _save_job_record(active_job)
            return _serialize_job(active_job)

    models = _django_models()
    if not models:
        raise ValueError("Task not found")
    JobRecord, _, JobEventRecord = models
    try:
        _close_django_connections()
        record = _owned_records(JobRecord, owner_id, guest_key).prefetch_related("outputs").filter(job_id=job_id).first()
        if not record:
            raise ValueError("Task not found")
        if record.status in INTERRUPTIBLE_JOB_STATUSES:
            record.status = "paused"
            record.progress = max(0, min(99, int(record.progress or 0)))
            record.message = "Paused"
            record.error = ""
            record.save(update_fields=["status", "progress", "message", "error", "updated_at"])
            JobEventRecord.objects.create(job=record, status="paused", progress=record.progress, message="Paused")
        return _serialize_job_record(record)
    except (RuntimeError, ValueError):
        raise
    except Exception as exc:
        raise RuntimeError(str(exc) or "Could not pause task") from exc


def resume_job(job_id: str, owner_id: int | None = None, guest_key: str = "") -> dict:
    with _lock:
        active_job = _jobs.get(job_id)
        if active_job and not _access_matches(active_job.owner_id, active_job.guest_key, owner_id, guest_key):
            raise ValueError("Task not found")
        if active_job:
            if active_job.status in RECOVERABLE_JOB_STATUSES:
                active_job.status = "queued"
                active_job.progress = 0
                active_job.message = "Queued"
                active_job.error = ""
                active_job.outputs.clear()
                active_job.updated_at = time.time()
                if active_job.runner and not any(job.id == job_id for job, _worker in _pending_jobs):
                    _pending_jobs.append((active_job, active_job.runner))
                    _save_job_record(active_job)
                    _schedule_jobs()
                    return _serialize_job(active_job)
                _save_job_record(active_job)
            return _serialize_job(active_job)

    models = _django_models()
    if not models:
        raise ValueError("Task not found")
    JobRecord, _, JobEventRecord = models
    try:
        _close_django_connections()
        record = _owned_records(JobRecord, owner_id, guest_key).prefetch_related("outputs").filter(job_id=job_id).first()
        if not record:
            raise ValueError("Task not found")
        if record.status not in RECOVERABLE_JOB_STATUSES:
            return _serialize_job_record(record)
        params = _loads_record_params(record.params_json)
        if not params:
            raise ValueError("Task has no saved parameters to continue")
        record.status = "queued"
        record.progress = 0
        record.message = "Queued"
        record.error = ""
        record.output_count = 0
        record.total_output_size = 0
        record.primary_output_type = ""
        record.outputs.all().delete()
        record.save(update_fields=["status", "progress", "message", "error", "output_count", "total_output_size", "primary_output_type", "updated_at"])
        JobEventRecord.objects.create(job=record, status="queued", progress=0, message="Queued")
        return _rerun_persisted_job(record)
    except (RuntimeError, ValueError):
        raise
    except Exception as exc:
        raise RuntimeError(str(exc) or "Could not resume task") from exc


def _rerun_persisted_job(record) -> dict:
    if getattr(settings, "persistent_job_queue", False):
        return _serialize_job_record(record)

    params = _loads_record_params(record.params_json)
    if not params:
        raise ValueError("Task has no saved parameters to continue")

    with _lock:
        _jobs.pop(record.job_id, None)
        remaining = [(job, worker) for job, worker in _pending_jobs if job.id != record.job_id]
        _pending_jobs.clear()
        _pending_jobs.extend(remaining)

    owner_id = record.owner_id
    guest_key = record.guest_key
    job_id = record.job_id
    action = str(params.get("action") or "")

    if action == "convert":
        source = _existing_source(params.get("source"))
        return start_conversion_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            content_type=str(params.get("content_type") or ""),
            target_format=str(params.get("target_format") or "webp"),
            output_name=str(params.get("output_name") or source.stem),
            image_mode=str(params.get("image_mode") or "balanced"),
            owner_id=owner_id,
            guest_key=guest_key,
            job_id=job_id,
        )
    if action == "youtube":
        return start_youtube_job(
            str(params.get("url") or ""),
            str(params.get("mode") or "regular"),
            owner_id,
            guest_key,
            bool(params.get("ai_improve")),
            int(params.get("clip_count") or 10),
            str(params.get("processing_speed") or "auto"),
            job_id=job_id,
        )
    if action == "video_download":
        return start_video_download_job(str(params.get("url") or ""), owner_id, guest_key, job_id=job_id)
    if action == "youtube_cover":
        return start_youtube_cover_job(str(params.get("url") or ""), owner_id, guest_key, bool(params.get("ai_cover")), job_id=job_id)
    if action == "cover":
        source = _existing_source(params.get("source"))
        return start_cover_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            variants=int(params.get("variants") or 1),
            owner_id=owner_id,
            guest_key=guest_key,
            ai_cover=bool(params.get("ai_cover")),
            job_id=job_id,
        )
    if action == "subtitles":
        source = _existing_source(params.get("source"))
        return start_subtitle_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            style=str(params.get("style") or "pop"),
            language=str(params.get("language") or "auto"),
            owner_id=owner_id,
            guest_key=guest_key,
            ai_transcription=bool(params.get("ai_transcription")),
            job_id=job_id,
        )
    if action == "package":
        source = _existing_source(params.get("source"))
        return start_package_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            style=str(params.get("style") or "pop"),
            language=str(params.get("language") or "auto"),
            owner_id=owner_id,
            guest_key=guest_key,
            ai_transcription=bool(params.get("ai_transcription")),
            ai_cover=bool(params.get("ai_cover")),
            job_id=job_id,
        )
    if action == "resume":
        data = params.get("data")
        if not isinstance(data, dict):
            raise ValueError("Saved resume data is damaged")
        return start_resume_job(
            {str(key): str(value) for key, value in data.items()},
            str(params.get("template") or "1"),
            owner_id,
            guest_key,
            job_id=job_id,
        )
    raise ValueError("Unsupported persisted task action")


def get_job(job_id: str, owner_id: int | None = None, guest_key: str = "") -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        if job and _access_matches(job.owner_id, job.guest_key, owner_id, guest_key):
            return _serialize_job(job)
    return _load_job_record(job_id, owner_id, guest_key)


def get_output(job_id: str, index: int, owner_id: int | None = None, guest_key: str = "") -> JobOutput | None:
    with _lock:
        job = _jobs.get(job_id)
        if job and _access_matches(job.owner_id, job.guest_key, owner_id, guest_key):
            if index < 0 or index >= len(job.outputs):
                return None
            output = job.outputs[index]
            if not output.path.exists():
                return None
            return output
    output = _load_output_record(job_id, index, owner_id, guest_key)
    if not output:
        return None
    if not output.path.exists():
        return None
    return output


def get_recent_jobs(limit: int = 20, owner_id: int | None = None, guest_key: str = "") -> list[dict]:
    mark_interrupted_jobs()
    models = _django_models()
    if not models:
        with _lock:
            jobs = [job for job in _jobs.values() if _access_matches(job.owner_id, job.guest_key, owner_id, guest_key)]
            return [_serialize_job(job) for job in sorted(jobs, key=lambda item: item.created_at, reverse=True)[:limit]]
    JobRecord, _, _ = models
    try:
        records = _owned_records(JobRecord, owner_id, guest_key).prefetch_related("outputs").order_by("-created_at")[:limit]
        return [_serialize_job_record(record) for record in records]
    except Exception:
        return []


def get_account_stats(owner_id: int | None = None, guest_key: str = "") -> dict[str, object]:
    models = _django_models()
    if not models:
        with _lock:
            jobs = [job for job in _jobs.values() if _access_matches(job.owner_id, job.guest_key, owner_id, guest_key)]
            outputs = [output for job in jobs for output in job.outputs]
        total_size = sum(output.size for output in outputs)
        return _stats_payload(jobs, len(outputs), total_size)

    JobRecord, JobOutputRecord, _ = models
    try:
        _close_django_connections()
        from django.db.models import Count, Q, Sum

        queryset = _owned_records(JobRecord, owner_id, guest_key).order_by()
        job_stats = queryset.aggregate(
            total_jobs=Count("id"),
            active_jobs=Count("id", filter=Q(status__in=ACTIVE_JOB_STATUSES)),
            completed_jobs=Count("id", filter=Q(status="completed")),
            failed_jobs=Count("id", filter=Q(status__in=["failed", "cancelled"])),
        )
        output_stats = JobOutputRecord.objects.filter(job__in=queryset).aggregate(
            output_count=Count("id"),
            total_output_size=Sum("size"),
        )
        total_size = int(output_stats.get("total_output_size") or 0)
        return {
            "total_jobs": int(job_stats.get("total_jobs") or 0),
            "active_jobs": int(job_stats.get("active_jobs") or 0),
            "completed_jobs": int(job_stats.get("completed_jobs") or 0),
            "failed_jobs": int(job_stats.get("failed_jobs") or 0),
            "output_count": int(output_stats.get("output_count") or 0),
            "total_output_size": total_size,
            "total_output_size_text": human_size(total_size),
        }
    except Exception:
        return _stats_payload([], 0, 0)


def get_job_events(job_id: str, owner_id: int | None = None, guest_key: str = "") -> list[dict]:
    models = _django_models()
    if not models:
        return []
    JobRecord, _, _ = models
    try:
        _close_django_connections()
        record = _owned_records(JobRecord, owner_id, guest_key).prefetch_related("events").get(job_id=job_id)
        return [
            {
                "status": event.status,
                "progress": event.progress,
                "message": _display_text(event.message),
                "created_at": int(event.created_at.timestamp()),
                "created_at_text": event.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for event in record.events.all()
        ]
    except Exception:
        return []


def delete_job_history(job_id: str, owner_id: int | None = None, guest_key: str = "") -> bool:
    with _lock:
        active_job = _jobs.get(job_id)
        if active_job and not _access_matches(active_job.owner_id, active_job.guest_key, owner_id, guest_key):
            return False
        if active_job and active_job.status in {"queued", "running"}:
            raise RuntimeError("Активную задачу нельзя удалить из истории до завершения")
        _jobs.pop(job_id, None)

    models = _django_models()
    if not models:
        return True
    JobRecord, _, _ = models
    try:
        _close_django_connections()
        deleted, _ = _owned_records(JobRecord, owner_id, guest_key).filter(job_id=job_id).delete()
        return deleted > 0
    except Exception:
        return False


def delete_job_and_media(job_id: str, owner_id: int | None = None, guest_key: str = "") -> bool:
    output_paths: list[Path] = []
    params: dict[str, object] = {}
    with _lock:
        active_job = _jobs.get(job_id)
        if active_job and not _access_matches(active_job.owner_id, active_job.guest_key, owner_id, guest_key):
            return False
        if active_job:
            if active_job.status in ACTIVE_JOB_STATUSES:
                active_job.status = "cancelled"
                active_job.progress = 100
                active_job.message = "Cancelled"
                active_job.error = ""
                active_job.updated_at = time.time()
                remaining = [(job, worker) for job, worker in _pending_jobs if job.id != job_id]
                _pending_jobs.clear()
                _pending_jobs.extend(remaining)
                _save_job_record(active_job)
            output_paths = [output.path for output in active_job.outputs]
            params = dict(active_job.params)
        _deleted_job_ids.add(job_id)
        _jobs.pop(job_id, None)

    models = _django_models()
    if not models:
        _delete_job_media(job_id, output_paths, params)
        return True
    JobRecord, _, _ = models
    try:
        _close_django_connections()
        record = _owned_records(JobRecord, owner_id, guest_key).prefetch_related("outputs").filter(job_id=job_id).first()
        if record:
            output_paths = output_paths or [Path(output.path) for output in record.outputs.all()]
            if not params and record.params_json:
                try:
                    loaded = json.loads(record.params_json)
                    params = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    params = {}
        deleted, _ = _owned_records(JobRecord, owner_id, guest_key).filter(job_id=job_id).delete()
        if deleted:
            _delete_job_media(job_id, output_paths, params)
        return deleted > 0
    except Exception:
        return False


def zip_job_outputs(job_id: str, owner_id: int | None = None, guest_key: str = "") -> Path:
    outputs = _job_output_paths(job_id, owner_id, guest_key)
    existing = [path for path in outputs if path.exists()]
    if not existing:
        raise FileNotFoundError("У задачи нет доступных файлов результата")
    output_dir = WEB_OUTPUT_ROOT / job_id / "downloads"
    return _zip_paths(existing, output_dir / f"{job_id}_outputs.zip")


def transfer_guest_jobs_to_user(guest_key: str, owner_id: int) -> int:
    if not guest_key or not owner_id:
        return 0
    moved = 0
    with _lock:
        for job in _jobs.values():
            if job.owner_id is None and job.guest_key == guest_key:
                job.owner_id = owner_id
                job.guest_key = ""
                job.updated_at = time.time()
                moved += 1

    models = _django_models()
    if not models:
        return moved
    JobRecord, _, _ = models
    try:
        from django.utils import timezone

        _close_django_connections()
        db_moved = JobRecord.objects.filter(owner__isnull=True, guest_key=guest_key).update(
            owner_id=owner_id,
            guest_key="",
            updated_at=timezone.now(),
        )
        return max(moved, db_moved)
    except Exception:
        return moved


def mark_interrupted_jobs() -> None:
    if getattr(settings, "persistent_job_queue", False):
        return
    models = _django_models()
    if not models:
        return
    JobRecord, _, _ = models
    try:
        from django.db import close_old_connections
        from django.utils import timezone

        close_old_connections()
        with _lock:
            active_ids = list(_jobs.keys())
        queryset = JobRecord.objects.filter(status__in=["queued", "running", "processing"])
        if active_ids:
            queryset = queryset.exclude(job_id__in=active_ids)
        for record in queryset:
            record.status = "paused"
            record.progress = max(0, min(99, int(record.progress or 0)))
            record.message = "Interrupted. Press Continue to restore the task."
            record.error = ""
            record.updated_at = timezone.now()
            record.save(update_fields=["status", "progress", "message", "error", "updated_at"])
        return
        queryset.update(
            status="failed",
            progress=100,
            message="Задача прервана",
            error="Сервер был перезапущен до завершения задачи.",
            updated_at=timezone.now(),
        )
    except Exception:
        return


def youtube_render_profile(mode: str) -> YouTubeProfile:
    mode = (mode or "regular").lower()
    if mode == "backstage":
        mode = "backstage30"

    base_short_seconds = max(10, settings.youtube_short_seconds)
    if mode == "dynamic":
        tuning = shorts_mode_tuning(mode)
        return YouTubeProfile(
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
            strict_face=tuning.strict_focus,
            alignment_mode=tuning.alignment_mode,
        )
    if mode == "podcast":
        tuning = shorts_mode_tuning(mode)
        return YouTubeProfile(
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
            strict_face=tuning.strict_focus,
            alignment_mode=tuning.alignment_mode,
        )
    if mode == "calm":
        tuning = shorts_mode_tuning(mode)
        return YouTubeProfile(
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
            strict_face=tuning.strict_focus,
            alignment_mode=tuning.alignment_mode,
        )
    if mode.startswith("backstage"):
        tuning = shorts_mode_tuning(mode)
        seconds = {"backstage30": 30, "backstage60": 60, "backstage90": 90}.get(mode, settings.backstage_output_seconds)
        return YouTubeProfile(
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
            strict_face=tuning.strict_focus,
            alignment_mode=tuning.alignment_mode,
        )
    tuning = shorts_mode_tuning("regular")
    return YouTubeProfile(
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
        strict_face=tuning.strict_focus,
        alignment_mode=tuning.alignment_mode,
    )


def _normalize_processing_speed(value: str | None) -> str:
    normalized = (value or "auto").strip().lower()
    return normalized if normalized in {"auto", "fast", "smart", "pro"} else "auto"


def _youtube_processing_plan(speed: str, profile: YouTubeProfile, duration_seconds: float) -> YouTubeProcessingPlan:
    duration = max(1, int(duration_seconds or 0))
    requested = _normalize_processing_speed(speed)
    if requested == "auto":
        requested = "smart" if profile.strict_face else "fast" if duration >= 45 * 60 else "smart"

    cpu_count = max(1, os.cpu_count() or 1)
    max_render_workers = max(1, min(2, cpu_count // 2 or 1))
    base_sample_limit = max(80, int(profile.sample_limit or settings.backstage_sample_limit or 360))

    if requested == "fast":
        strict_face_detection = bool(profile.strict_face and settings.face_detection_enabled)
        return YouTubeProcessingPlan(
            code="fast",
            label="Fast face" if strict_face_detection else "Fast",
            sample_limit=max(80, min(180, int(base_sample_limit * 0.55))),
            face_detection=strict_face_detection,
            analysis_seconds=45.0,
            render_workers=1 if strict_face_detection else max_render_workers,
            focus_mode=settings.shorts_focus_mode if strict_face_detection else "center",
        )
    if requested == "pro":
        return YouTubeProcessingPlan(
            code="pro",
            label="Pro",
            sample_limit=max(160, min(520, int(base_sample_limit * 1.18))),
            face_detection=bool(settings.face_detection_enabled),
            analysis_seconds=150.0,
            render_workers=1 if bool(settings.face_detection_enabled or profile.strict_face) else max_render_workers,
            focus_mode=settings.shorts_focus_mode,
        )
    return YouTubeProcessingPlan(
        code="smart",
        label="Smart",
        sample_limit=max(100, min(300, int(base_sample_limit * 0.78))),
        face_detection=bool(settings.face_detection_enabled and (duration < 90 * 60 or profile.strict_face)),
        analysis_seconds=80.0,
        render_workers=1 if bool(profile.strict_face and settings.face_detection_enabled) else max_render_workers,
        focus_mode=settings.shorts_focus_mode,
    )


def _youtube_analysis_cache_key(
    url: str,
    mode: str,
    duration_seconds: float,
    clip_seconds: int,
    max_candidates: int,
    plan: YouTubeProcessingPlan,
) -> str:
    payload = {
        "schema": "youtube-analysis-v4-focus-passport",
        "url": url,
        "mode": mode,
        "duration": int(duration_seconds or 0),
        "clip_seconds": int(clip_seconds),
        "max_candidates": int(max_candidates),
        "speed": plan.code,
        "sample_limit": int(plan.sample_limit),
        "face_detection": bool(plan.face_detection),
        "strict_face": bool(youtube_render_profile(mode).strict_face),
        "alignment_mode": youtube_render_profile(mode).alignment_mode,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _clip_selection_report(candidate: dict[str, object], mode: str, processing_label: str) -> dict[str, object]:
    fields = (
        "score",
        "peak_second",
        "peak_score",
        "avg_score",
        "coverage",
        "position",
        "face_coverage",
        "face_confidence",
        "crop_safety",
        "center_safety",
        "size_safety",
        "speech_activity_score",
        "face_liveliness_score",
        "speaker_lock_score",
        "empty_frame_risk",
        "focus_score",
        "focus_source",
        "motion_focus_available",
        "strict_focus_ok",
        "source",
    )
    report = {key: candidate.get(key) for key in fields if key in candidate}
    report["mode"] = mode
    report["processing"] = processing_label
    return report


def _youtube_analysis_cache_path(cache_key: str) -> Path:
    return WEB_STORAGE_ROOT / "_cache" / "youtube_analysis" / f"{cache_key}.json"


def _load_youtube_analysis_cache(cache_key: str) -> list[dict[str, object]]:
    path = _youtube_analysis_cache_path(cache_key)
    try:
        if not path.exists() or time.time() - path.stat().st_mtime > 14 * 24 * 60 * 60:
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    return candidates if isinstance(candidates, list) else []


def _save_youtube_analysis_cache(cache_key: str, candidates: list[dict[str, object]]) -> None:
    if not candidates:
        return
    path = _youtube_analysis_cache_path(cache_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "created_at": time.time(), "candidates": candidates}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def _youtube_source_cache_key(url: str) -> str:
    return hashlib.sha256(f"youtube-source-v2-720|{url.strip()}".encode("utf-8")).hexdigest()[:32]


def _youtube_source_cache_dir(cache_key: str) -> Path:
    return WEB_STORAGE_ROOT / "_cache" / "youtube_sources" / cache_key


def _download_youtube_video_cached(
    url: str,
    output_dir: Path,
    timeout_seconds: int,
    estimated_size_bytes: int | None,
    metadata,
) -> YouTubeDownload:
    cache_dir = _youtube_source_cache_dir(_youtube_source_cache_key(url))
    cache_meta_path = cache_dir / "source.json"
    try:
        cached_files = [path for path in cache_dir.iterdir() if path.is_file() and path.name != cache_meta_path.name and path.stat().st_size > 0]
    except Exception:
        cached_files = []
    if cached_files:
        cached_source = max(cached_files, key=lambda item: item.stat().st_size)
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / cached_source.name
        try:
            if not target.exists() or target.stat().st_size != cached_source.stat().st_size:
                target.unlink(missing_ok=True)
                try:
                    os.link(cached_source, target)
                except Exception:
                    shutil.copy2(cached_source, target)
            return YouTubeDownload(
                path=target,
                title=str(getattr(metadata, "title", "") or target.stem),
                video_id=str(getattr(metadata, "video_id", "") or ""),
                duration_seconds=float(getattr(metadata, "duration_seconds", 0) or 0),
                webpage_url=str(getattr(metadata, "webpage_url", "") or url),
            )
        except Exception:
            pass

    download = download_youtube_video(url, output_dir, timeout_seconds, estimated_size_bytes)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_target = cache_dir / download.path.name
        if not cached_target.exists() or cached_target.stat().st_size != download.path.stat().st_size:
            cached_target.unlink(missing_ok=True)
            try:
                os.link(download.path, cached_target)
            except Exception:
                shutil.copy2(download.path, cached_target)
        cache_meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "title": download.title,
                    "video_id": download.video_id,
                    "duration_seconds": download.duration_seconds,
                    "webpage_url": download.webpage_url,
                    "path": cached_target.name,
                    "created_at": time.time(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return download


def _submit_job(
    kind: str,
    title: str,
    worker,
    params: dict[str, object] | None = None,
    owner_id: int | None = None,
    guest_key: str = "",
    *,
    job_id: str | None = None,
    run_inline: bool = False,
) -> dict:
    job = WebJob(
        id=job_id or uuid.uuid4().hex[:12],
        kind=kind,
        title=title,
        params=params or {},
        owner_id=owner_id,
        guest_key="" if owner_id is not None else guest_key,
        runner=worker,
    )
    with _lock:
        _deleted_job_ids.discard(job.id)
    if run_inline:
        with _lock:
            _jobs[job.id] = job
        _create_job_record(job)
        _run_job(job, worker)
        return _serialize_job(job)
    if getattr(settings, "persistent_job_queue", False):
        _create_job_record(job)
        return _serialize_job(job)
    with _lock:
        _jobs[job.id] = job
        _pending_jobs.append((job, worker))
        snapshot = _serialize_job(job)
    _create_job_record(job)
    _schedule_jobs()
    return snapshot


def _schedule_jobs() -> None:
    submissions: list[tuple[WebJob, object]] = []
    with _lock:
        max_workers = max(1, int(getattr(settings, "job_max_workers", 1) or 1))
        per_account = max(1, int(getattr(settings, "account_concurrent_jobs", 10) or 10))
        blocked_rotations = 0
        while _pending_jobs and len(_running_job_ids) < max_workers and blocked_rotations < len(_pending_jobs):
            job, worker = _pending_jobs.popleft()
            if job.status != "queued":
                blocked_rotations = 0
                continue
            account_key = _job_account_key(job)
            if _running_by_account.get(account_key, 0) >= per_account:
                _pending_jobs.append((job, worker))
                blocked_rotations += 1
                continue
            _running_job_ids.add(job.id)
            _running_by_account[account_key] = _running_by_account.get(account_key, 0) + 1
            submissions.append((job, worker))
            blocked_rotations = 0
    for job, worker in submissions:
        try:
            _executor.submit(_run_job, job, worker)
        except Exception as exc:
            _release_job_slot(job)
            _update_error(job, exc)


def _run_job(job: WebJob, worker) -> None:
    _close_django_connections()
    _update_status(job, "running", 2, "Стартую задачу")
    try:
        worker(job)
        interrupt_status = _job_interrupt_status(job)
        if interrupt_status:
            _finish_interrupted_job(job, interrupt_status)
        else:
            _update_status(job, "completed", 100, "Готово")
    except JobCancelled as exc:
        interrupted = str(exc) if str(exc) in INTERRUPT_REQUEST_STATUSES else _job_interrupt_status(job) or "cancelled"
        _finish_interrupted_job(job, interrupted)
    except Exception as exc:
        _update_error(job, exc)
    finally:
        _release_job_slot(job)
        _close_django_connections()
        _schedule_jobs()


def _release_job_slot(job: WebJob) -> None:
    with _lock:
        _running_job_ids.discard(job.id)
        account_key = _job_account_key(job)
        current = max(0, _running_by_account.get(account_key, 0) - 1)
        if current:
            _running_by_account[account_key] = current
        else:
            _running_by_account.pop(account_key, None)


def _job_account_key(job: WebJob) -> str:
    if job.owner_id is not None:
        return f"user:{job.owner_id}"
    return f"guest:{job.guest_key or 'anonymous'}"


def _job_interrupt_status(job: WebJob) -> str:
    with _lock:
        if job.status in INTERRUPT_REQUEST_STATUSES:
            return job.status
    models = _django_models()
    if not models:
        return ""
    JobRecord, _, _ = models
    try:
        _close_django_connections()
        record = JobRecord.objects.filter(job_id=job.id, status__in=INTERRUPT_REQUEST_STATUSES).only("status").first()
        return str(record.status) if record else ""
    except Exception:
        return ""


def _job_cancel_requested(job: WebJob) -> bool:
    return bool(_job_interrupt_status(job))


def _finish_interrupted_job(job: WebJob, status: str) -> None:
    if status == "paused":
        _update_status(job, "paused", max(0, min(99, int(job.progress or 0))), "Paused")
    else:
        _update_status(job, "cancelled", 100, "Cancelled")


def _update_job(job: WebJob, progress: int, message: str) -> None:
    interrupt_status = _job_interrupt_status(job)
    if interrupt_status:
        raise JobCancelled(interrupt_status)
    with _lock:
        job.progress = max(0, min(99, int(progress)))
        job.message = message
        job.updated_at = time.time()
    _save_job_record(job)


def _update_status(job: WebJob, status: str, progress: int, message: str) -> None:
    interrupt_status = _job_interrupt_status(job)
    if status in {"running", "completed"} and interrupt_status:
        status = interrupt_status
        progress = 100 if interrupt_status == "cancelled" else max(0, min(99, int(job.progress or progress or 0)))
        message = "Cancelled" if interrupt_status == "cancelled" else "Paused"
    with _lock:
        job.status = status
        job.progress = max(0, min(100, int(progress)))
        job.message = message
        job.updated_at = time.time()
    _save_job_record(job)


def _update_error(job: WebJob, exc: Exception) -> None:
    interrupt_status = _job_interrupt_status(job)
    if interrupt_status:
        _finish_interrupted_job(job, interrupt_status)
        return
    with _lock:
        job.status = "failed"
        job.progress = 100
        job.error = str(exc) or exc.__class__.__name__
        job.message = "Ошибка"
        job.updated_at = time.time()
    _save_job_record(job)


def _add_output(job: WebJob, path: Path, label: str) -> None:
    interrupt_status = _job_interrupt_status(job)
    if interrupt_status:
        raise JobCancelled(interrupt_status)
    media_type = _media_type_for_path(path)
    output = JobOutput(label=label, path=path, media_type=media_type)
    with _lock:
        job.outputs.append(output)
        job.updated_at = time.time()
    _create_output_record(job, output)
    _save_job_record(job)


def _serialize_job(job: WebJob | None) -> dict:
    if not job:
        return {}
    eta_seconds, eta_text = _estimate_job_eta(job.created_at, job.progress, job.status)
    output_count, total_output_size, primary_output_type = _job_output_summary(job.outputs)
    return {
        "id": job.id,
        "kind": job.kind,
        "title": _display_text(job.title),
        "status": job.status,
        "progress": job.progress,
        "eta_seconds": eta_seconds,
        "eta_text": eta_text,
        "message": _display_text(job.message),
        "error": _display_text(job.error),
        "created_at": int(job.created_at),
        "updated_at": int(job.updated_at),
        "repeatable": bool(job.params),
        "owner_id": job.owner_id,
        "guest_key": job.guest_key,
        "output_count": output_count,
        "total_output_size": total_output_size,
        "primary_output_type": primary_output_type,
        "ai": _ai_meta_payload(job.params),
        "outputs": [
            {
                "index": index,
                "label": _display_text(output.label),
                "name": output.name,
                "size": output.size,
                "size_text": human_size(output.size),
                "media_type": output.media_type,
                "exists": output.path.exists(),
            }
            for index, output in enumerate(job.outputs)
        ],
    }


def _django_models():
    try:
        from django.apps import apps

        if not apps.ready:
            return None
        from studio.models import JobEventRecord, JobOutputRecord, JobRecord

        return JobRecord, JobOutputRecord, JobEventRecord
    except Exception:
        return None


def _close_django_connections() -> None:
    try:
        from django.db import close_old_connections

        close_old_connections()
    except Exception:
        return


def _params_to_json(params: dict[str, object]) -> str:
    if not params:
        return ""
    try:
        return json.dumps(params, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(_json_safe(params), ensure_ascii=False)


def _json_safe(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _load_job_params(job_id: str, owner_id: int | None = None, guest_key: str = "") -> dict[str, object]:
    with _lock:
        job = _jobs.get(job_id)
        if job and job.params and _access_matches(job.owner_id, job.guest_key, owner_id, guest_key):
            return dict(job.params)

    models = _django_models()
    if not models:
        return {}
    JobRecord, _, _ = models
    try:
        _close_django_connections()
        raw = _owned_records(JobRecord, owner_id, guest_key).only("params_json").get(job_id=job_id).params_json
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _existing_source(value: object) -> Path:
    path = Path(str(value or ""))
    if not path.exists():
        raise FileNotFoundError("Исходный файл для повтора больше не найден")
    return path


def _create_job_record(job: WebJob) -> None:
    with _lock:
        if job.id in _deleted_job_ids:
            return
    models = _django_models()
    if not models:
        return
    JobRecord, _, _ = models
    try:
        _close_django_connections()
        output_count, total_output_size, primary_output_type = _job_output_summary(job.outputs)
        JobRecord.objects.get_or_create(
            job_id=job.id,
            defaults={
                "kind": job.kind,
                "title": job.title,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "error": job.error,
                "params_json": _params_to_json(job.params),
                "owner_id": job.owner_id,
                "guest_key": job.guest_key,
                "output_count": output_count,
                "total_output_size": total_output_size,
                "primary_output_type": primary_output_type,
            },
        )
        _record_job_event(job, job.message)
    except Exception:
        return


def _save_job_record(job: WebJob) -> None:
    with _lock:
        if job.id in _deleted_job_ids:
            return
    models = _django_models()
    if not models:
        return
    JobRecord, _, _ = models
    try:
        from django.utils import timezone

        _close_django_connections()
        output_count, total_output_size, primary_output_type = _job_output_summary(job.outputs)
        JobRecord.objects.update_or_create(
            job_id=job.id,
            defaults={
                "kind": job.kind,
                "title": job.title,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "error": job.error,
                "params_json": _params_to_json(job.params),
                "owner_id": job.owner_id,
                "guest_key": job.guest_key,
                "output_count": output_count,
                "total_output_size": total_output_size,
                "primary_output_type": primary_output_type,
                "updated_at": timezone.now(),
            },
        )
        _record_job_event(job, job.error or job.message)
    except Exception:
        return


def _create_output_record(job: WebJob, output: JobOutput) -> None:
    with _lock:
        if job.id in _deleted_job_ids:
            return
    models = _django_models()
    if not models:
        return
    JobRecord, JobOutputRecord, _ = models
    try:
        _close_django_connections()
        job_record, _ = JobRecord.objects.get_or_create(
            job_id=job.id,
            defaults={
                "kind": job.kind,
                "title": job.title,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "error": job.error,
                "params_json": _params_to_json(job.params),
                "owner_id": job.owner_id,
                "guest_key": job.guest_key,
            },
        )
        path_text = str(output.path)
        existing = JobOutputRecord.objects.filter(job=job_record, path=path_text, label=output.label).first()
        if existing:
            existing.media_type = output.media_type
            existing.size = output.size
            existing.save(update_fields=["media_type", "size"])
            _refresh_job_record_outputs(job_record)
            return
        JobOutputRecord.objects.create(
            job=job_record,
            label=output.label,
            path=path_text,
            media_type=output.media_type,
            size=output.size,
        )
        _refresh_job_record_outputs(job_record)
        _record_job_event(job, f"Файл готов: {output.label}")
    except Exception:
        return


def _job_output_summary(outputs: list[JobOutput]) -> tuple[int, int, str]:
    count = len(outputs)
    total_size = sum(int(output.size or 0) for output in outputs)
    primary_type = ""
    if outputs:
        primary_type = str(outputs[0].media_type or "").split("/", 1)[0][:32]
    return count, total_size, primary_type


def _refresh_job_record_outputs(job_record) -> None:
    try:
        from django.db.models import Count, Sum

        stats = job_record.outputs.aggregate(output_count=Count("id"), total_output_size=Sum("size"))
        first = job_record.outputs.order_by("id").first()
        job_record.output_count = int(stats.get("output_count") or 0)
        job_record.total_output_size = int(stats.get("total_output_size") or 0)
        job_record.primary_output_type = str(getattr(first, "media_type", "") or "").split("/", 1)[0][:32] if first else ""
        job_record.save(update_fields=["output_count", "total_output_size", "primary_output_type", "updated_at"])
    except Exception:
        return


def _record_job_event(job: WebJob, message: str) -> None:
    models = _django_models()
    if not models:
        return
    JobRecord, _, JobEventRecord = models
    try:
        _close_django_connections()
        job_record = JobRecord.objects.get(job_id=job.id)
        last_event = JobEventRecord.objects.filter(job=job_record).order_by("-id").first()
        if (
            last_event
            and last_event.status == job.status
            and last_event.progress == job.progress
            and last_event.message == message
        ):
            return
        JobEventRecord.objects.create(
            job=job_record,
            status=job.status,
            progress=job.progress,
            message=message,
        )
    except Exception:
        return


def _load_job_record(job_id: str, owner_id: int | None = None, guest_key: str = "") -> dict | None:
    models = _django_models()
    if not models:
        return None
    JobRecord, _, _ = models
    try:
        _close_django_connections()
        record = _owned_records(JobRecord, owner_id, guest_key).prefetch_related("outputs").get(job_id=job_id)
        return _serialize_job_record(record)
    except Exception:
        return None


def _load_output_record(job_id: str, index: int, owner_id: int | None = None, guest_key: str = "") -> JobOutput | None:
    models = _django_models()
    if not models:
        return None
    JobRecord, _, _ = models
    try:
        _close_django_connections()
        record = _owned_records(JobRecord, owner_id, guest_key).prefetch_related("outputs").get(job_id=job_id)
        output_record = list(record.outputs.all())[index]
        return JobOutput(
            label=output_record.label,
            path=Path(output_record.path),
            media_type=_media_type_for_path(Path(output_record.path), output_record.media_type),
        )
    except Exception:
        return None


def _job_output_paths(job_id: str, owner_id: int | None = None, guest_key: str = "") -> list[Path]:
    with _lock:
        job = _jobs.get(job_id)
        if job and _access_matches(job.owner_id, job.guest_key, owner_id, guest_key):
            return [output.path for output in job.outputs]

    models = _django_models()
    if not models:
        return []
    JobRecord, _, _ = models
    try:
        _close_django_connections()
        record = _owned_records(JobRecord, owner_id, guest_key).prefetch_related("outputs").get(job_id=job_id)
        return [Path(output.path) for output in record.outputs.all()]
    except Exception:
        return []


def _serialize_job_record(record) -> dict:
    outputs = []
    for index, output in enumerate(record.outputs.all()):
        path = Path(output.path)
        size = output.size
        if path.exists():
            try:
                size = path.stat().st_size
            except OSError:
                pass
        outputs.append(
            {
                "index": index,
                "label": _display_text(output.label),
                "name": path.name,
                "size": size,
                "size_text": human_size(size),
                "media_type": _media_type_for_path(path, output.media_type),
                "exists": path.exists(),
            }
        )
    eta_seconds, eta_text = _estimate_job_eta(record.created_at.timestamp(), record.progress, record.status)
    params = _loads_record_params(record.params_json)
    return {
        "id": record.job_id,
        "kind": record.kind,
        "title": _display_text(record.title),
        "status": record.status,
        "progress": record.progress,
        "eta_seconds": eta_seconds,
        "eta_text": eta_text,
        "message": _display_text(record.message),
        "error": _display_text(record.error),
        "created_at": int(record.created_at.timestamp()),
        "updated_at": int(record.updated_at.timestamp()),
        "repeatable": bool(record.params_json),
        "owner_id": record.owner_id,
        "guest_key": record.guest_key,
        "output_count": int(getattr(record, "output_count", 0) or len(outputs)),
        "total_output_size": int(getattr(record, "total_output_size", 0) or sum(int(output.get("size") or 0) for output in outputs)),
        "primary_output_type": getattr(record, "primary_output_type", "") or "",
        "ai": _ai_meta_payload(params),
        "outputs": outputs,
    }


def _loads_record_params(raw: str) -> dict[str, object]:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _ai_meta_payload(params: dict[str, object]) -> dict[str, object]:
    ai = params.get("ai") if isinstance(params, dict) else None
    return ai if isinstance(ai, dict) else {}


def _estimate_job_eta(created_at: float, progress: int, status: str) -> tuple[int | None, str]:
    if status not in {"queued", "running", "processing"}:
        return None, ""
    safe_progress = max(0, min(99, int(progress or 0)))
    if safe_progress < 4:
        return None, "estimating"
    elapsed = max(1.0, time.time() - float(created_at or time.time()))
    total = elapsed / (safe_progress / 100)
    remaining = max(1, int(total - elapsed))
    return remaining, f"about {_format_eta_duration(remaining)}"


def _format_eta_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _display_text(value: str) -> str:
    if not value:
        return value
    value = re.sub(r"\x1b\[[0-9;]*m", "", str(value))
    try:
        repaired = value.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if repaired else value


def _looks_like_video(path: Path, content_type: str) -> bool:
    return (content_type or "").startswith("video/") or path.suffix.lower() in VIDEO_SUFFIXES


def _access_matches(job_owner_id: int | None, job_guest_key: str, owner_id: int | None, guest_key: str = "") -> bool:
    if owner_id is not None:
        return job_owner_id == owner_id
    if guest_key:
        return job_owner_id is None and job_guest_key == guest_key
    return job_owner_id is None and not job_guest_key


def _owned_records(JobRecord, owner_id: int | None, guest_key: str = ""):
    queryset = JobRecord.objects.all()
    if owner_id is not None:
        return queryset.filter(owner_id=owner_id)
    if guest_key:
        return queryset.filter(owner__isnull=True, guest_key=guest_key)
    return queryset.filter(owner__isnull=True, guest_key="")


def _media_type_for_path(path: Path, stored: str | None = None) -> str:
    if stored and stored != "application/octet-stream":
        return stored
    mapped = {
        ".webp": "image/webp",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".ass": "text/plain",
        ".srt": "text/plain",
        ".json": "application/json",
        ".zip": "application/zip",
    }.get(path.suffix.lower())
    return mapped or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _delete_job_media(job_id: str, output_paths: list[Path], params: dict[str, object]) -> None:
    _remove_tree_inside(WEB_OUTPUT_ROOT / job_id, WEB_OUTPUT_ROOT.parent)
    _remove_tree_inside(WEB_STORAGE_ROOT / job_id, settings.storage_dir)

    for path in output_paths:
        _remove_file_inside(path, WEB_OUTPUT_ROOT.parent)

    for key in ("source", "photo_path"):
        value = params.get(key)
        if value:
            _remove_file_inside(Path(str(value)), settings.storage_dir)


def _remove_tree_inside(path: Path, root: Path) -> None:
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        if not _path_inside(resolved, root_resolved) or not resolved.exists():
            return
        shutil.rmtree(resolved, ignore_errors=True)
    except Exception:
        return


def _remove_file_inside(path: Path, root: Path) -> None:
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        if not _path_inside(resolved, root_resolved) or not resolved.exists() or not resolved.is_file():
            return
        resolved.unlink(missing_ok=True)
        _remove_empty_parents(resolved.parent, root_resolved)
    except Exception:
        return


def _remove_empty_parents(path: Path, root: Path) -> None:
    current = path
    while _path_inside(current, root) and current != root:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _stats_payload(jobs: list, output_count: int, total_size: int) -> dict[str, object]:
    statuses = [getattr(job, "status", "") for job in jobs]
    return {
        "total_jobs": len(jobs),
        "active_jobs": sum(1 for status in statuses if status in ACTIVE_JOB_STATUSES),
        "completed_jobs": sum(1 for status in statuses if status == "completed"),
        "failed_jobs": sum(1 for status in statuses if status in {"failed", "cancelled"}),
        "output_count": output_count,
        "total_output_size": total_size,
        "total_output_size_text": human_size(total_size),
    }


def _normalize_video_url(value: str) -> str:
    url = extract_youtube_url(value) or (value or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Нужна ссылка на YouTube, YouTube Shorts или TikTok")
    return url


def _normalize_choice(value: str, choices: list[tuple[str, str]], default: str) -> str:
    allowed = {key for key, _ in choices}
    value = (value or default).strip().lower()
    return value if value in allowed else default


def _normalize_language(value: str) -> str | None:
    normalized = normalize_subtitle_language(value)
    allowed = {key for key, _label in SUBTITLE_LANGUAGE_CHOICES if key != "auto"}
    return normalized if normalized in allowed else None


def _youtube_plan_text(profile: YouTubeProfile, duration_seconds: float) -> str:
    if profile.is_backstage:
        clips = max(1, (max(6, profile.backstage_output_seconds - profile.backstage_intro_seconds)) // max(1, profile.backstage_segment_seconds))
        return (
            f"Preview до {min(profile.backstage_output_seconds, int(duration_seconds))} сек., "
            f"фрагментов: {clips}. Обработка: "
            f"{estimate_cut_time(duration_seconds, clips, profile.backstage_segment_seconds, settings.face_detection_enabled)}"
        )
    clips = planned_clip_count(duration_seconds, profile.max_shorts, profile.short_seconds)
    return (
        f"{clips} Shorts по {profile.short_seconds} сек. Обработка: "
        f"{estimate_cut_time(duration_seconds, clips, profile.short_seconds, settings.face_detection_enabled)}"
    )


def _prepare_youtube_editor_source(source: Path, output_dir: Path, base_name: str) -> Path:
    target_dir = output_dir / "editor_source"
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()[:16] or ".mp4"
    target = target_dir / f"{clean_base_name(base_name, 'youtube_source')}_wide_source{suffix}"
    if target.exists() and target.stat().st_size == source.stat().st_size:
        return target
    target.unlink(missing_ok=True)
    try:
        os.link(source, target)
    except Exception:
        shutil.copy2(source, target)
    return target


def _zip_paths(paths: list[Path], output: Path) -> Path:
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
