from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
import asyncio
import json
import mimetypes
import shutil
import threading
import time
import uuid
import zipfile

from .bot_utils import publication_description, publication_hashtags, unique_archive_name
from .config import get_settings
from .image_tools import SUPPORTED_IMAGE_FORMATS, clean_base_name, convert_image, human_size
from .video_tools import VIDEO_FORMATS, convert_video, format_duration, inspect_video
from .youtube_tools import (
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
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("en", "English"),
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


_jobs: dict[str, WebJob] = {}
_lock = threading.RLock()
_executor = ThreadPoolExecutor(max_workers=max(2, settings.youtube_workers + settings.cover_workers + 1))


def start_conversion_job(
    source: Path,
    original_name: str,
    content_type: str,
    target_format: str,
    output_name: str,
    image_mode: str,
    owner_id: int | None = None,
    guest_key: str = "",
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
    )


def start_youtube_job(url: str, mode: str, owner_id: int | None = None, guest_key: str = "") -> dict:
    clean_url = _normalize_video_url(url)
    if mode == "download":
        return start_video_download_job(clean_url, owner_id, guest_key)
    if mode == "cover":
        return start_youtube_cover_job(clean_url, owner_id, guest_key)

    profile = youtube_render_profile(mode)
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

        plan_text = _youtube_plan_text(profile, metadata.duration_seconds)
        size_text = human_size(metadata.estimated_size_bytes) if metadata.estimated_size_bytes else "размер заранее не найден"
        _update_job(
            job,
            18,
            f"{metadata.title}. {format_duration(metadata.duration_seconds)}. "
            f"{size_text}. {plan_text}. Загрузка: {estimate_download_time(metadata.estimated_size_bytes)}",
        )
        download = download_youtube_video(clean_url, source_dir, settings.youtube_download_timeout_seconds)

        if profile.is_backstage:
            if not settings.youtube_backstage_enabled:
                raise RuntimeError("Preview-монтаж выключен в настройках")
            _update_job(job, 45, "Собираю широкий Preview-монтаж")
            montage = create_backstage_montage(
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
            _add_output(job, montage.path, "Preview MP4")
            _update_job(job, 78, "Генерирую PNG-обложку")
            cover = create_business_cover(
                montage.path,
                output_dir / "cover",
                download.title,
                montage.duration_seconds,
                settings.video_timeout_seconds,
                settings.face_detection_enabled,
            )
            _add_output(job, cover, "PNG-обложка")
            _update_job(job, 94, f"Preview готов: {human_size(montage.path.stat().st_size)}")
            return

        _update_job(job, 34, "Ищу сильные моменты для Shorts")
        starts = calculate_smart_clip_starts(
            download.path,
            download.duration_seconds,
            profile.max_shorts,
            profile.short_seconds,
            profile.sample_limit,
            settings.face_detection_enabled,
        )
        if not starts:
            raise ValueError("Не получилось подобрать фрагменты для Shorts")

        source_info = inspect_video(download.path)
        clips = []
        base_name = clean_base_name(download.title, "youtube_short")
        for index, start_second in enumerate(starts, start=1):
            progress = 38 + int((index - 1) / max(1, len(starts)) * 38)
            _update_job(job, progress, f"Режу клип {index}/{len(starts)}: старт {format_duration(start_second)}")
            clip = make_short_clip(
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
            _add_output(job, clip.path, f"Short {index}")

        _update_job(job, 82, "Собираю ZIP со всеми Shorts")
        zip_path = zip_clips(clips, output_dir / f"{base_name}_shorts.zip")
        _add_output(job, zip_path, f"ZIP: {len(clips)} Shorts")
        try:
            _update_job(job, 90, "Генерирую PNG-обложку")
            cover = create_business_cover(
                download.path,
                output_dir / "cover",
                download.title,
                download.duration_seconds,
                settings.video_timeout_seconds,
                settings.face_detection_enabled,
            )
            _add_output(job, cover, "PNG-обложка")
        except Exception:
            _update_job(job, 92, "Shorts готовы, обложку сделать не удалось")
        _update_job(job, 96, f"Готово: {describe_clips(clips)}")

    return _submit_job("youtube", youtube_render_profile(mode).label, worker, {"action": "youtube", "url": clean_url, "mode": mode}, owner_id, guest_key)


def start_video_download_job(url: str, owner_id: int | None = None, guest_key: str = "") -> dict:
    clean_url = _normalize_video_url(url)

    def worker(job: WebJob) -> None:
        source_dir = WEB_STORAGE_ROOT / job.id / "source_download"
        output_dir = WEB_OUTPUT_ROOT / job.id / "source_download"
        _update_job(job, 15, "Скачиваю исходное видео")
        download = download_youtube_video(clean_url, source_dir, settings.youtube_download_timeout_seconds)
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

    return _submit_job("download", "Скачать MP4", worker, {"action": "video_download", "url": clean_url}, owner_id, guest_key)


def start_youtube_cover_job(url: str, owner_id: int | None = None, guest_key: str = "") -> dict:
    clean_url = _normalize_video_url(url)

    def worker(job: WebJob) -> None:
        source_dir = WEB_STORAGE_ROOT / job.id / "youtube_cover"
        output_dir = WEB_OUTPUT_ROOT / job.id / "youtube_cover"
        _update_job(job, 15, "Скачиваю видео для обложки")
        download = download_youtube_video(clean_url, source_dir, settings.youtube_download_timeout_seconds)
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
        _update_job(job, 94, f"Готово: {download.title}")

    return _submit_job("youtube_cover", "YouTube PNG-обложка", worker, {"action": "youtube_cover", "url": clean_url}, owner_id, guest_key)


def start_cover_job(source: Path, original_name: str, title: str, variants: int, owner_id: int | None = None, guest_key: str = "") -> dict:
    variant_count = max(1, min(6, int(variants or 1)))
    clean_title = clean_base_name(title or original_name, "cover")

    def worker(job: WebJob) -> None:
        output_dir = WEB_OUTPUT_ROOT / job.id / "covers"
        _update_job(job, 12, "Читаю видео")
        info = inspect_video(source)
        covers: list[Path] = []
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
            )
            covers.append(cover)
            _add_output(job, cover, f"Обложка {index}")
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
        },
        owner_id,
        guest_key,
    )


def start_subtitle_job(source: Path, original_name: str, title: str, style: str, language: str, owner_id: int | None = None, guest_key: str = "") -> dict:
    subtitle_style = _normalize_choice(style, SUBTITLE_STYLE_CHOICES, "pop")
    subtitle_language = _normalize_language(language)
    clean_title = clean_base_name(title or original_name, "subtitled")

    def worker(job: WebJob) -> None:
        output_dir = WEB_OUTPUT_ROOT / job.id / "subtitles"
        _update_job(job, 15, "Распознаю речь")
        cues = transcribe_subtitle_cues(source, settings.subtitle_model, subtitle_language)
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
        },
        owner_id,
        guest_key,
    )


def start_package_job(source: Path, original_name: str, title: str, style: str, language: str, owner_id: int | None = None, guest_key: str = "") -> dict:
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

        subtitle_note = "Субтитры не добавлены: речь не найдена или распознавание недоступно."
        try:
            _update_job(job, 50, "Пробую добавить субтитры")
            cues = transcribe_subtitle_cues(source, settings.subtitle_model, subtitle_language)
            if cues:
                assets = create_subtitle_assets(source, output_dir / "subtitles", f"{clean_title}_package", cues, subtitle_style)
                rendered = render_subtitle_assets(source, assets, settings.subtitle_timeout_seconds)
                package_files.extend([rendered.path, assets.ass_path])
                _add_output(job, rendered.path, "Видео с субтитрами")
                subtitle_note = f"Субтитры добавлены, фраз найдено: {len(cues)}."
        except Exception:
            subtitle_note = "Субтитры не добавлены: распознавание завершилось ошибкой."

        _update_job(job, 74, "Пишу описание и manifest")
        hashtags = publication_hashtags(clean_title)
        description_path = output_dir / "description.txt"
        description_path.write_text(
            publication_description(clean_title, format_duration(info.duration_seconds), hashtags, subtitle_note),
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
        },
        owner_id,
        guest_key,
    )


def start_resume_job(data: dict[str, str], template: str, owner_id: int | None = None, guest_key: str = "") -> dict:
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
    )


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
        return start_youtube_job(str(params.get("url") or ""), str(params.get("mode") or "regular"), owner_id, guest_key)
    if action == "video_download":
        return start_video_download_job(str(params.get("url") or ""), owner_id, guest_key)
    if action == "youtube_cover":
        return start_youtube_cover_job(str(params.get("url") or ""), owner_id, guest_key)
    if action == "cover":
        source = _existing_source(params.get("source"))
        return start_cover_job(
            source=source,
            original_name=str(params.get("original_name") or source.name),
            title=str(params.get("title") or ""),
            variants=int(params.get("variants") or 1),
            owner_id=owner_id,
            guest_key=guest_key,
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

    JobRecord, _, _ = models
    try:
        _close_django_connections()
        records = list(_owned_records(JobRecord, owner_id, guest_key).prefetch_related("outputs"))
        output_count = 0
        total_size = 0
        for record in records:
            for output in record.outputs.all():
                output_count += 1
                total_size += int(output.size or 0)
        return _stats_payload(records, output_count, total_size)
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
        if active_job and active_job.status in {"queued", "running"}:
            raise RuntimeError("Active tasks can be deleted only after completion")
        if active_job:
            output_paths = [output.path for output in active_job.outputs]
            params = dict(active_job.params)
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
        queryset = JobRecord.objects.filter(status__in=["queued", "running"])
        if active_ids:
            queryset = queryset.exclude(job_id__in=active_ids)
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
        )
    if mode == "podcast":
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
        )
    if mode == "calm":
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
        )
    if mode.startswith("backstage"):
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
        )
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
    )


def _submit_job(
    kind: str,
    title: str,
    worker,
    params: dict[str, object] | None = None,
    owner_id: int | None = None,
    guest_key: str = "",
) -> dict:
    job = WebJob(
        id=uuid.uuid4().hex[:12],
        kind=kind,
        title=title,
        params=params or {},
        owner_id=owner_id,
        guest_key="" if owner_id is not None else guest_key,
    )
    with _lock:
        _jobs[job.id] = job
        snapshot = _serialize_job(job)
    _create_job_record(job)
    _executor.submit(_run_job, job, worker)
    return snapshot


def _run_job(job: WebJob, worker) -> None:
    _close_django_connections()
    _update_status(job, "running", 2, "Стартую задачу")
    try:
        worker(job)
        _update_status(job, "completed", 100, "Готово")
    except Exception as exc:
        _update_error(job, exc)
    finally:
        _close_django_connections()


def _update_job(job: WebJob, progress: int, message: str) -> None:
    with _lock:
        job.progress = max(0, min(99, int(progress)))
        job.message = message
        job.updated_at = time.time()
    _save_job_record(job)


def _update_status(job: WebJob, status: str, progress: int, message: str) -> None:
    with _lock:
        job.status = status
        job.progress = max(0, min(100, int(progress)))
        job.message = message
        job.updated_at = time.time()
    _save_job_record(job)


def _update_error(job: WebJob, exc: Exception) -> None:
    with _lock:
        job.status = "failed"
        job.progress = 100
        job.error = str(exc) or exc.__class__.__name__
        job.message = "Ошибка"
        job.updated_at = time.time()
    _save_job_record(job)


def _add_output(job: WebJob, path: Path, label: str) -> None:
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
    models = _django_models()
    if not models:
        return
    JobRecord, _, _ = models
    try:
        _close_django_connections()
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
            },
        )
        _record_job_event(job, job.message)
    except Exception:
        return


def _save_job_record(job: WebJob) -> None:
    models = _django_models()
    if not models:
        return
    JobRecord, _, _ = models
    try:
        from django.utils import timezone

        _close_django_connections()
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
                "updated_at": timezone.now(),
            },
        )
        _record_job_event(job, job.error or job.message)
    except Exception:
        return


def _create_output_record(job: WebJob, output: JobOutput) -> None:
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
            return
        JobOutputRecord.objects.create(
            job=job_record,
            label=output.label,
            path=path_text,
            media_type=output.media_type,
            size=output.size,
        )
        _record_job_event(job, f"Файл готов: {output.label}")
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
        "outputs": outputs,
    }


def _estimate_job_eta(created_at: float, progress: int, status: str) -> tuple[int | None, str]:
    if status not in {"queued", "running"}:
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
        "active_jobs": sum(1 for status in statuses if status in {"queued", "running"}),
        "completed_jobs": sum(1 for status in statuses if status == "completed"),
        "failed_jobs": sum(1 for status in statuses if status == "failed"),
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
    value = (value or "auto").strip().lower()
    return value if value in {"ru", "uk", "en"} else None


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
