from __future__ import annotations

import audioop
from dataclasses import dataclass
import io
import json
from math import ceil, cos, pi, sin
import numpy as np
from pathlib import Path
import random
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import cv2
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from yt_dlp import YoutubeDL

from . import native_tools
from .image_tools import clean_base_name, human_size
from .video_tools import ffmpeg_path, format_duration, has_audio_stream, inspect_video


VIDEO_URL_RE = re.compile(
    r"(https?://(?:(?:www\.)?(?:youtube\.com/watch\?v=|youtube\.com/shorts/)|youtu\.be/|(?:[\w.-]+\.)?tiktok\.com/)[^\s]+)",
    re.IGNORECASE,
)

IMPACT_ICON_URLS = [
    ("collision", "https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/color/618x618/1F4A5.png"),
    ("zap", "https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/color/618x618/26A1.png"),
    ("fire", "https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/color/618x618/1F525.png"),
    ("rocket", "https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/color/618x618/1F680.png"),
]

VIDEO_QUALITY_PRESET = "medium"
SHORTS_VIDEO_CRF = "21"
PREVIEW_VIDEO_CRF = "21"
SUBTITLE_VIDEO_CRF = "20"
VIDEO_AUDIO_FILTER = "loudnorm=I=-16:LRA=11:TP=-1.5"
WHISPER_LANGUAGE_ALIASES = {
    "auto": None,
    "": None,
    "ua": "uk",
    "ukr": "uk",
    "rus": "ru",
    "eng": "en",
    "ger": "de",
    "deu": "de",
    "fre": "fr",
    "fra": "fr",
    "spa": "es",
    "geo": "ka",
    "kat": "ka",
    "arm": "hy",
    "hye": "hy",
    "pt-br": "pt",
    "pt_br": "pt",
    "zh-cn": "zh",
    "zh_cn": "zh",
    "zh-tw": "zh",
    "zh_tw": "zh",
}
WHISPER_LANGUAGE_CODES = {
    "af", "am", "ar", "as", "az", "ba", "be", "bg", "bn", "bo", "br", "bs", "ca", "cs", "cy", "da", "de",
    "el", "en", "es", "et", "eu", "fa", "fi", "fo", "fr", "gl", "gu", "ha", "haw", "he", "hi", "hr", "ht",
    "hu", "hy", "id", "is", "it", "ja", "jw", "ka", "kk", "km", "kn", "ko", "la", "lb", "ln", "lo", "lt",
    "lv", "mg", "mi", "mk", "ml", "mn", "mr", "ms", "mt", "my", "ne", "nl", "nn", "no", "oc", "pa", "pl",
    "ps", "pt", "ro", "ru", "sa", "sd", "si", "sk", "sl", "sn", "so", "sq", "sr", "su", "sv", "sw", "ta",
    "te", "tg", "th", "tk", "tl", "tr", "tt", "uk", "ur", "uz", "vi", "yi", "yo", "zh",
}
SUBTITLE_LANGUAGE_PROMPTS = {
    "ru": "Точная русская транскрипция с нормальной пунктуацией. Не переводить.",
    "uk": "Точна українська транскрипція з нормальною пунктуацією. Не перекладати.",
    "en": "Accurate English transcript with natural punctuation. Do not translate.",
    "fr": "Transcription française précise avec ponctuation naturelle. Ne pas traduire.",
    "de": "Genaue deutsche Transkription mit natürlicher Zeichensetzung. Nicht übersetzen.",
    "es": "Transcripción precisa en español con puntuación natural. No traducir.",
    "ka": "ზუსტი ქართული ტრანსკრიფცია ბუნებრივი პუნქტუაციით. არ თარგმნო.",
    "hy": "Ճշգրիտ հայերեն տառադարձում բնական կետադրությամբ։ Չթարգմանել։",
    "it": "Trascrizione italiana accurata con punteggiatura naturale. Non tradurre.",
}


@dataclass(frozen=True)
class YouTubeDownload:
    path: Path
    title: str
    video_id: str
    duration_seconds: float
    webpage_url: str


@dataclass(frozen=True)
class YouTubeMetadata:
    title: str
    video_id: str
    duration_seconds: float
    webpage_url: str
    estimated_size_bytes: int | None


@dataclass(frozen=True)
class ShortClip:
    path: Path
    start_seconds: int
    duration_seconds: int


@dataclass(frozen=True)
class FaceFocus:
    x: int
    y: int
    confidence: float


@dataclass(frozen=True)
class FaceTrackPoint:
    second: float
    x: int
    y: int
    width: int
    height: int
    confidence: float


@dataclass(frozen=True)
class CoverCopy:
    headline: str
    description: str


@dataclass(frozen=True)
class SubtitleCue:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SubtitleAssets:
    output: Path
    ass_path: Path
    cue_count: int
    duration_seconds: int


class SubtitleUnavailableError(RuntimeError):
    pass


def extract_youtube_url(text: str | None) -> str | None:
    if not text:
        return None
    match = VIDEO_URL_RE.search(text)
    return match.group(1) if match else None


def video_source_label(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if "tiktok.com" in host:
        return "TikTok"
    if "youtu" in host or "youtube.com" in host:
        return "YouTube"
    return "Video"


def get_youtube_metadata(url: str, timeout_seconds: int) -> YouTubeMetadata:
    ydl_opts = _youtube_options(Path("."), timeout_seconds)
    ydl_opts.update({"skip_download": True})
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise RuntimeError("Could not read video metadata")

    return YouTubeMetadata(
        title=info.get("title") or "youtube_video",
        video_id=info.get("id") or "youtube",
        duration_seconds=float(info.get("duration") or 0),
        webpage_url=info.get("webpage_url") or url,
        estimated_size_bytes=_estimate_download_size(info),
    )


def download_youtube_video(url: str, output_dir: Path, timeout_seconds: int, estimated_size_bytes: int | None = None) -> YouTubeDownload:
    output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_download_space(output_dir, estimated_size_bytes)
    ydl_opts = _youtube_options(output_dir, timeout_seconds)
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        _cleanup_partial_downloads(output_dir)
        message = str(exc)
        if "No space left on device" in message or "not enough space" in message.lower():
            raise RuntimeError(_storage_error_message(output_dir, estimated_size_bytes)) from exc
        raise

    if not info:
        raise RuntimeError("Не удалось получить данные видео")

    path = _resolve_downloaded_path(info, output_dir)
    duration = float(info.get("duration") or 0)
    if duration <= 0:
        try:
            duration = float(inspect_video(path).duration_seconds or 0)
        except Exception:
            duration = 0
    return YouTubeDownload(
        path=path,
        title=info.get("title") or "youtube_video",
        video_id=info.get("id") or path.stem,
        duration_seconds=duration,
        webpage_url=info.get("webpage_url") or url,
    )


def estimate_download_time(size_bytes: int | None) -> str:
    if not size_bytes:
        return "unknown, depends on YouTube speed"
    slow_seconds = size_bytes / (1.5 * 1024 * 1024)
    fast_seconds = size_bytes / (6 * 1024 * 1024)
    return f"{format_duration(fast_seconds)} - {format_duration(slow_seconds)}"


def estimate_cut_time(duration_seconds: float, clip_count: int, clip_seconds: int, face_focus: bool) -> str:
    total_clip_seconds = min(duration_seconds, clip_count * clip_seconds)
    multiplier = 1.8 if face_focus else 1.2
    estimate = max(20, int(total_clip_seconds * multiplier))
    return f"about {format_duration(estimate)}"


def _ensure_download_space(output_dir: Path, estimated_size_bytes: int | None) -> None:
    if not estimated_size_bytes:
        return
    disk_path = output_dir if output_dir.exists() else output_dir.parent
    free_bytes = shutil.disk_usage(disk_path).free
    # yt-dlp often keeps video, audio and merged output at the same time.
    required = max(900 * 1024 * 1024, int(estimated_size_bytes * 2.35))
    if free_bytes < required:
        raise RuntimeError(_storage_error_message(output_dir, estimated_size_bytes, free_bytes, required))


def _cleanup_partial_downloads(output_dir: Path) -> None:
    for pattern in ("*.part", "*.temp.*", "*.ytdl", "*.frag"):
        for path in output_dir.glob(pattern):
            try:
                path.unlink()
            except OSError:
                continue


def _storage_error_message(
    output_dir: Path,
    estimated_size_bytes: int | None = None,
    free_bytes: int | None = None,
    required_bytes: int | None = None,
) -> str:
    disk_path = output_dir if output_dir.exists() else output_dir.parent
    free = shutil.disk_usage(disk_path).free if free_bytes is None else free_bytes
    required = required_bytes or (int(estimated_size_bytes * 2.35) if estimated_size_bytes else 900 * 1024 * 1024)
    return (
        "Недостаточно места на диске для YouTube-задачи. "
        f"Свободно: {human_size(free)}, нужно примерно: {human_size(required)}. "
        "Освободите место или перенесите STORAGE_DIR на диск с большим объёмом."
    )


def planned_clip_count(duration_seconds: float, max_clips: int, clip_seconds: int) -> int:
    return len(calculate_clip_starts(duration_seconds, max_clips, clip_seconds))


def calculate_smart_clip_starts(
    source: Path,
    duration_seconds: float,
    max_clips: int,
    clip_seconds: int,
    sample_limit: int = 360,
    face_detection_enabled: bool = True,
) -> list[int]:
    ranked_starts = rank_smart_clip_candidates(
        source,
        duration_seconds,
        max(max_clips * 5, max_clips),
        clip_seconds,
        sample_limit,
        face_detection_enabled,
    )
    if not ranked_starts:
        return calculate_clip_starts(duration_seconds, max_clips, clip_seconds)
    min_gap = max(int(clip_seconds * 0.82), min(clip_seconds + 12, 65))
    selected = _select_diverse_ranked_starts(
        [(int(item["start"]), float(item["score"])) for item in ranked_starts],
        max_clips,
        min_gap,
        int(duration_seconds),
        clip_seconds,
    )
    base_starts = calculate_clip_starts(duration_seconds, max_clips, clip_seconds)
    if len(selected) < max_clips:
        for start in base_starts:
            if all(abs(start - existing) >= clip_seconds // 2 for existing in selected):
                selected.append(start)
            if len(selected) >= max_clips:
                break
    return sorted(selected[:max_clips])


def rank_smart_clip_candidates(
    source: Path,
    duration_seconds: float,
    max_candidates: int,
    clip_seconds: int,
    sample_limit: int = 360,
    face_detection_enabled: bool = True,
) -> list[dict[str, object]]:
    duration = int(duration_seconds)
    if duration < 10:
        return []

    base_starts = calculate_clip_starts(duration_seconds, max_candidates, clip_seconds)
    if duration <= max_candidates * clip_seconds:
        return [{"start": start, "score": round(1000.0 - index, 3), "source": "sequential"} for index, start in enumerate(base_starts)]

    sample_limit = max(120, min(1200, sample_limit))
    step = max(2, int(duration / sample_limit))
    scores = _score_video_moments(source, duration, step, face_detection_enabled)
    ranked_starts = _rank_clip_windows(scores, duration, clip_seconds, step, lead_seconds=max(2, clip_seconds // 5))
    candidates = _clip_candidate_dicts(ranked_starts, scores, duration, clip_seconds, step)

    seen = {int(item["start"]) for item in candidates}
    for index, start in enumerate(base_starts):
        if start in seen:
            continue
        candidates.append({"start": start, "score": round(max(1.0, 35.0 - index), 3), "source": "fallback"})
        seen.add(start)

    return candidates[: max(1, max_candidates)]


def make_shorts(
    source: Path,
    output_dir: Path,
    title: str,
    duration_seconds: float,
    max_clips: int,
    clip_seconds: int,
    timeout_seconds: int,
    focus_mode: str = "face",
    face_detection_enabled: bool = True,
) -> list[ShortClip]:
    output_dir.mkdir(parents=True, exist_ok=True)
    starts = calculate_smart_clip_starts(source, duration_seconds, max_clips, clip_seconds, face_detection_enabled=face_detection_enabled)
    if not starts:
        raise RuntimeError("Видео слишком короткое для нарезки")

    base = clean_base_name(title, "youtube_short")
    source_info = inspect_video(source)
    clips: list[ShortClip] = []
    for index, start in enumerate(starts, start=1):
        clips.append(
            make_short_clip(
                source,
                output_dir,
                base,
                duration_seconds,
                start,
                index,
                clip_seconds,
                timeout_seconds,
                focus_mode,
                face_detection_enabled,
                source_info.width,
                source_info.height,
            )
        )
    return clips


def make_short_clip(
    source: Path,
    output_dir: Path,
    base_name: str,
    duration_seconds: float,
    start_seconds: int,
    index: int,
    clip_seconds: int,
    timeout_seconds: int,
    focus_mode: str = "face",
    face_detection_enabled: bool = True,
    source_width: int | None = None,
    source_height: int | None = None,
) -> ShortClip:
    output_dir.mkdir(parents=True, exist_ok=True)
    if source_width is None or source_height is None:
        source_info = inspect_video(source)
        source_width = source_info.width
        source_height = source_info.height

    start_seconds, current_duration = align_clip_window_to_audio(source, start_seconds, clip_seconds, duration_seconds)
    output = output_dir / f"{clean_base_name(base_name, 'youtube_short')}_short_{index:02d}.mp4"
    vf = build_vertical_filter(
        source,
        start_seconds,
        current_duration,
        source_width,
        source_height,
        focus_mode,
        face_detection_enabled,
    )
    args = [
        ffmpeg_path(),
        "-y",
        "-ss",
        str(start_seconds),
        "-t",
        str(current_duration),
        "-i",
        str(source),
        "-vf",
        vf,
        *(["-af", VIDEO_AUDIO_FILTER] if has_audio_stream(source) else []),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        VIDEO_QUALITY_PRESET,
        "-crf",
        SHORTS_VIDEO_CRF,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output),
    ]
    completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout_seconds)
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1:] or ["FFmpeg shorts conversion failed"]
        raise RuntimeError(detail[0])
    return ShortClip(path=output, start_seconds=start_seconds, duration_seconds=current_duration)


def align_clip_start_to_audio(
    source: Path,
    start_seconds: int,
    clip_seconds: int,
    duration_seconds: float,
) -> int:
    if start_seconds <= 0:
        return 0
    phrase_start = _find_phrase_start_near(source, start_seconds, before_seconds=5.5, after_seconds=1.8)
    if phrase_start is not None:
        aligned = clamp(int(round(phrase_start)), 0, max(0, int(duration_seconds) - max(1, clip_seconds)))
        if abs(aligned - start_seconds) <= 6:
            return aligned
    pause = _find_nearby_audio_pause(source, start_seconds, before_seconds=3.5, after_seconds=1.5)
    if pause is None:
        return start_seconds
    aligned = clamp(int(round(pause)), 0, max(0, int(duration_seconds) - max(1, clip_seconds)))
    if abs(aligned - start_seconds) > 5:
        return start_seconds
    return aligned


def align_clip_window_to_audio(
    source: Path,
    start_seconds: int,
    clip_seconds: int,
    duration_seconds: float,
    min_duration: int | None = None,
    max_extension_seconds: int = 3,
) -> tuple[int, int]:
    aligned_start = align_clip_start_to_audio(source, start_seconds, clip_seconds, duration_seconds)
    remaining = max(1, int(duration_seconds - aligned_start))
    current_duration = min(clip_seconds, remaining)
    if remaining <= current_duration:
        return aligned_start, current_duration

    min_duration = min_duration or max(8, min(clip_seconds, clip_seconds - 4))
    preferred_end = aligned_start + current_duration
    end_pause = _find_nearby_audio_pause(source, preferred_end, before_seconds=2.5, after_seconds=3.0)
    if end_pause is not None:
        candidate_duration = int(round(end_pause - aligned_start))
        max_duration = min(remaining, clip_seconds + max_extension_seconds)
        if min_duration <= candidate_duration <= max_duration:
            current_duration = candidate_duration
    return aligned_start, max(1, min(current_duration, remaining))


def create_backstage_montage(
    source: Path,
    output_dir: Path,
    title: str,
    duration_seconds: float,
    timeout_seconds: int,
    output_seconds: int = 30,
    segment_seconds: int = 4,
    intro_seconds: int = 3,
    sample_limit: int = 420,
    min_gap_seconds: int = 90,
    face_detection_enabled: bool = True,
) -> ShortClip:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_seconds = max(12, min(90, output_seconds))
    intro_seconds = max(0, min(5, intro_seconds))
    segment_seconds = max(2, min(8, segment_seconds))
    available_seconds = max(6, output_seconds - intro_seconds)
    segment_count = max(1, available_seconds // segment_seconds)
    starts = calculate_backstage_clip_starts(
        source,
        duration_seconds,
        segment_count,
        segment_seconds,
        sample_limit,
        min_gap_seconds,
        face_detection_enabled,
    )
    if not starts:
        starts = calculate_clip_starts(duration_seconds, segment_count, segment_seconds)
    if not starts:
        raise RuntimeError("Видео слишком короткое для Preview-монтажа")

    base = clean_base_name(title, "preview")
    pieces: list[Path] = []
    if intro_seconds:
        intro_image = output_dir / f"{base}_intro.png"
        intro_video = output_dir / f"{base}_intro.mp4"
        _create_intro_image(intro_image, title, output_seconds)
        _render_intro_video(intro_image, intro_video, intro_seconds, timeout_seconds)
        pieces.append(intro_video)

    aligned_starts: list[int] = []
    for index, start in enumerate(starts, start=1):
        aligned_start, aligned_duration = align_clip_window_to_audio(
            source,
            start,
            segment_seconds,
            duration_seconds,
            min_duration=max(2, segment_seconds - 1),
            max_extension_seconds=2,
        )
        aligned_starts.append(aligned_start)
        piece = output_dir / f"{base}_part_{index:02d}.mp4"
        _render_wide_segment(source, piece, aligned_start, aligned_duration, timeout_seconds)
        pieces.append(piece)

    output = output_dir / f"{base}_preview.mp4"
    _concat_videos(pieces, output, timeout_seconds)
    return ShortClip(path=output, start_seconds=aligned_starts[0] if aligned_starts else starts[0], duration_seconds=min(output_seconds, int(duration_seconds)))


def _create_intro_image(path: Path, title: str, output_seconds: int) -> None:
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), (12, 14, 18))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        shade = int(18 + 38 * (y / height))
        draw.line([(0, y), (width, y)], fill=(shade, 22, 32 + shade // 3))
    title_font = _load_font(54)
    label_font = _load_font(28)
    draw.text((72, 72), "PREVIEW CUT", fill=(255, 214, 94), font=label_font)
    wrapped = _wrap_text(clean_base_name(title, "YouTube video"), 28)
    y = 170
    for line in wrapped[:5]:
        draw.text((72, y), line, fill=(245, 247, 250), font=title_font)
        y += 66
    draw.text((72, 620), f"Auto-picked moments | wide format | {output_seconds} sec", fill=(185, 192, 204), font=label_font)
    image.save(path)


def create_cover_image(
    source: Path,
    output: Path,
    title: str,
    start_seconds: int,
    vertical: bool = False,
    timeout_seconds: int = 60,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_path = output.with_suffix(".frame.jpg")
    args = [
        ffmpeg_path(),
        "-y",
        "-ss",
        str(max(0, start_seconds)),
        "-i",
        str(source),
        "-vframes",
        "1",
        "-q:v",
        "3",
        str(frame_path),
    ]
    _run_ffmpeg(args, timeout_seconds)

    target_size = (1080, 1920) if vertical else (1280, 720)
    image = Image.open(frame_path).convert("RGB")
    image.thumbnail(target_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", target_size, (12, 14, 18))
    x = (target_size[0] - image.width) // 2
    y = (target_size[1] - image.height) // 2
    canvas.paste(image, (x, y))

    draw = ImageDraw.Draw(canvas, "RGBA")
    overlay_height = int(target_size[1] * 0.34)
    draw.rectangle((0, target_size[1] - overlay_height, target_size[0], target_size[1]), fill=(0, 0, 0, 150))
    label_font = _load_font(34 if not vertical else 42)
    title_font = _load_font(58 if not vertical else 70)
    margin = 72 if not vertical else 62
    draw.text((margin, target_size[1] - overlay_height + 34), "AUTO CUT", fill=(255, 214, 94, 255), font=label_font)
    y_text = target_size[1] - overlay_height + 88
    for line in _wrap_text(clean_base_name(title, "YouTube video"), 26 if not vertical else 18)[:3]:
        draw.text((margin, y_text), line, fill=(255, 255, 255, 255), font=title_font)
        y_text += 70 if not vertical else 86
    canvas.save(output, quality=92)
    frame_path.unlink(missing_ok=True)
    return output


def create_business_cover(
    source: Path,
    output_dir: Path,
    title: str,
    duration_seconds: float | None = None,
    timeout_seconds: int = 120,
    face_detection_enabled: bool = True,
    variant_index: int = 1,
    variant_seed: int | None = None,
    avoid_seconds: list[int] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    info = inspect_video(source)
    duration = int(duration_seconds or info.duration_seconds or 0)
    candidates = rank_smart_clip_candidates(
        source,
        duration,
        max_candidates=18,
        clip_seconds=5,
        sample_limit=420,
        face_detection_enabled=face_detection_enabled,
    )
    start_seconds = _select_cover_start(source, duration, candidates, face_detection_enabled, avoid_seconds or [])
    face = detect_face_focus(source, start_seconds, 4) if face_detection_enabled else None

    base = clean_base_name(title, "video")
    suffix = "" if variant_index <= 1 else f"_v{variant_index}"
    output = output_dir / f"{base}{suffix}_business_cover.png"
    frame_path = output.with_suffix(".frame.jpg")
    args = [
        ffmpeg_path(),
        "-y",
        "-ss",
        str(max(0, start_seconds)),
        "-i",
        str(source),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(frame_path),
    ]
    _run_ffmpeg(args, timeout_seconds)

    frame = Image.open(frame_path).convert("RGB")
    target_size = (1280, 720)
    focus = (face.x, face.y) if face else None
    canvas, focus_point = _resize_cover_background(frame, target_size, focus)
    canvas = _cinematic_cover_grade(canvas)
    editable_background = canvas.copy()
    topic_assets = _load_cover_topic_assets(title, output_dir / "_topic_assets")
    impact_asset = _load_cover_impact_asset(output_dir / "_impact_assets")
    _draw_business_cover(canvas, title, focus_point, topic_assets, impact_asset, variant_seed, variant_index)
    canvas.save(output, format="PNG", optimize=True)
    background_path = output.with_suffix(".background.jpg")
    editable_background.save(background_path, format="JPEG", quality=92, optimize=True)
    _write_cover_design_metadata(output, background_path, title, focus_point, variant_index, variant_seed, start_seconds)
    frame_path.unlink(missing_ok=True)
    return output


def _select_cover_start(
    source: Path,
    duration_seconds: int,
    candidates: list[dict[str, object]],
    face_detection_enabled: bool,
    avoid_seconds: list[int] | None = None,
) -> int:
    avoid = {int(value) for value in (avoid_seconds or [])}
    min_gap = max(6, min(28, int(duration_seconds * 0.045)))

    def too_close(second: int) -> bool:
        return any(abs(second - used) < min_gap for used in avoid)

    native_start = native_tools.pick_cover_second(source, duration_seconds, candidates)
    if native_start is not None and not too_close(native_start):
        return native_start

    fallback = clamp(duration_seconds // 3, 0, max(0, duration_seconds - 1))
    starts: list[int] = []
    for item in candidates[:10]:
        try:
            start = int(float(item.get("peak_second") or item.get("start")))
        except (AttributeError, TypeError, ValueError):
            continue
        start = clamp(start, 0, max(0, duration_seconds - 1))
        if start not in starts and not too_close(start):
            starts.append(start)
    if fallback not in starts:
        starts.append(fallback)
    if not starts:
        return fallback

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return starts[0]
    frontal = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    profile = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml"))
    detectors = [detector for detector in (frontal, profile) if not detector.empty()]
    best: tuple[float, int] | None = None
    try:
        for index, start in enumerate(starts):
            for offset in (0.0, 0.75, 1.5):
                second = clamp(int(round(start + offset)), 0, max(0, duration_seconds - 1))
                capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
                ok, frame = capture.read()
                if not ok:
                    continue
                score = _cover_frame_score(frame, detectors if face_detection_enabled else [])
                score += max(0.0, 9.0 - index)
                if best is None or score > best[0]:
                    best = (score, second)
    finally:
        capture.release()
    return best[1] if best else starts[0]


def _cover_frame_score(frame: np.ndarray, detectors: list[cv2.CascadeClassifier]) -> float:
    small = cv2.resize(frame, (320, 180))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    saturation = float(hsv[:, :, 1].mean())
    exposure = max(0.0, 1.0 - abs(brightness - 122.0) / 122.0) * 18.0
    face_score = 0.0
    if detectors:
        faces = _detect_frame_faces(frame, detectors)
        if faces:
            frame_area = max(1, frame.shape[0] * frame.shape[1])
            largest = max((w * h for _x, _y, w, h in faces), default=0)
            face_score = min(44.0, 12.0 * len(faces) + largest / frame_area * 190.0)
    return (
        min(24.0, contrast / 3.8)
        + min(20.0, saturation / 8.5)
        + min(18.0, sharpness / 140.0)
        + exposure
        + face_score
    )


def create_premium_cover_from_image(source: Path, output: Path, title: str) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(source).convert("RGB")
    focus = _detect_image_face_focus(image)
    canvas, focus_point = _resize_cover_background(image, (1280, 720), focus)
    canvas = _cinematic_cover_grade(canvas)
    _draw_business_cover(canvas, title, focus_point, [], None)
    canvas.save(output, format="PNG", optimize=True)
    return output


def _write_cover_design_metadata(
    output: Path,
    background_path: Path,
    title: str,
    focus_point: tuple[int, int] | None,
    variant_index: int,
    variant_seed: int | None,
    start_seconds: int,
) -> None:
    cover_copy = _cover_copy(title)
    headline = _cover_title_text(cover_copy.headline)
    description = _cover_description_text(cover_copy.description)
    seed = int(variant_seed if variant_seed is not None else abs(hash((title, variant_index, start_seconds))) % 1_000_000)
    profile = _cover_variant_profile(headline, focus_point, variant_index, seed)
    metadata = {
        "version": 2,
        "kind": "cover_design",
        "title": title,
        "canvas": {"width": 1280, "height": 720},
        "background_path": str(background_path),
        "source_output": str(output),
        "variant_index": int(variant_index),
        "variant_seed": seed,
        "start_seconds": int(start_seconds),
        "text_left": bool(profile["text_left"]),
        "focus_point": {"x": focus_point[0], "y": focus_point[1]} if focus_point else None,
        "style": {
            "layout": profile["layout"],
            "mood": profile["mood"],
            "badge": profile["badge"],
            "text_left": bool(profile["text_left"]),
        },
        "copy": {
            "eyebrow": profile["eyebrow"],
            "headline": headline,
            "description": description,
        },
        "palette": {
            "accent": _hex_color(profile["accent"]),
            "accent2": _hex_color(profile["accent2"]),
            "dark": profile["dark"],
            "paper": profile["paper"],
        },
        "layout": {
            "panel_x": profile["panel_x"],
            "headline_y": profile["headline_y"],
            "max_text_width": profile["max_text_width"],
            "badge_x": profile["badge_x"],
            "badge_y": profile["badge_y"],
            "hook_x": profile["hook_x"],
            "hook_y": profile["hook_y"],
        },
    }
    try:
        output.with_suffix(".design.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


def _hex_color(color: tuple[int, int, int, int] | tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(int(color[0]) & 255, int(color[1]) & 255, int(color[2]) & 255)


def _cover_variant_profile(title: str, focus_point: tuple[int, int] | None, variant_index: int, variant_seed: int | None = None) -> dict[str, object]:
    seed = int(variant_seed if variant_seed is not None else abs(hash((title, variant_index))) % 1_000_000)
    rng = random.Random(seed + variant_index * 7919)
    layouts = ("split", "poster", "broadcast", "impact")
    moods = ("premium", "neon", "urgent", "clean")
    layout = layouts[(variant_index - 1) % len(layouts)]
    mood = moods[(seed + variant_index) % len(moods)]
    text_left = not focus_point or focus_point[0] > 1280 * 0.54
    if layout in {"poster", "impact"} and variant_index % 2 == 0:
        text_left = not text_left
    if layout == "broadcast":
        text_left = variant_index % 2 == 1

    accent = _premium_cover_accent(f"{title}:{seed}:{mood}")
    accent2 = _premium_cover_secondary_accent(f"{title}:{seed}:{layout}")
    if mood == "neon":
        accent = rng.choice([(48, 226, 255, 255), (134, 239, 172, 255), (244, 114, 182, 255)])
        accent2 = rng.choice([(255, 218, 58, 255), (167, 139, 250, 255), (251, 113, 133, 255)])
    elif mood == "urgent":
        accent = (255, 66, 92, 255)
        accent2 = (255, 226, 96, 255)
    elif mood == "clean":
        accent = (255, 255, 255, 255)
        accent2 = _premium_cover_secondary_accent(f"{title}:{seed}")

    if layout == "poster":
        max_text_width = 650
        panel_x = 62 if text_left else 552
        headline_y = 132
    elif layout == "broadcast":
        max_text_width = 560
        panel_x = 62 if text_left else 660
        headline_y = 138
    elif layout == "impact":
        max_text_width = 610
        panel_x = 70 if text_left else 604
        headline_y = 126
    else:
        max_text_width = 590 if text_left else 560
        panel_x = 66 if text_left else 676
        headline_y = 146

    badge_x = panel_x
    badge_y = 46 if layout != "impact" else 38
    hook_text = _premium_cover_hook(title, mood)
    hook_width = min(500, len(hook_text) * 15 + 86)
    hook_x = 62 if text_left else 1280 - hook_width - 62
    hook_y = 620 if layout != "poster" else 604
    return {
        "layout": layout,
        "mood": mood,
        "text_left": text_left,
        "panel_x": panel_x,
        "headline_y": headline_y,
        "max_text_width": max_text_width,
        "badge_x": badge_x,
        "badge_y": badge_y,
        "hook_x": hook_x,
        "hook_y": hook_y,
        "badge": hook_text,
        "eyebrow": _premium_cover_eyebrow(title),
        "accent": accent,
        "accent2": accent2,
        "dark": "#05070c" if mood != "clean" else "#0f172a",
        "paper": "#f8fafc" if mood == "clean" else "#ffffff",
    }


def _detect_image_face_focus(image: Image.Image) -> tuple[int, int] | None:
    try:
        frame = np.array(image.convert("RGB"))
        frontal = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
        profile = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml"))
        detectors = [detector for detector in (frontal, profile) if not detector.empty()]
        faces = _detect_frame_faces(frame, detectors)
        if not faces:
            return None
        x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
        return int(x + w / 2), int(y + h / 2)
    except Exception:
        return None


def _cinematic_cover_grade(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    arr = np.asarray(rgb).astype(np.float32)
    arr = (arr - 128.0) * 1.10 + 128.0
    arr[:, :, 0] *= 1.03
    arr[:, :, 1] *= 1.01
    arr[:, :, 2] *= 0.96
    arr = np.clip(arr, 0, 255).astype("uint8")
    graded = Image.fromarray(arr, "RGB")
    graded = ImageOps.autocontrast(graded, cutoff=1)
    graded = graded.filter(ImageFilter.UnsharpMask(radius=1.5, percent=145, threshold=4))
    return graded


def add_subtitles_to_video(
    source: Path,
    output_dir: Path,
    base_name: str,
    timeout_seconds: int = 900,
    model_size: str = "small",
    language: str | None = None,
    style: str = "pop",
) -> ShortClip:
    assets = prepare_subtitle_assets(source, output_dir, base_name, model_size, language, style)
    return render_subtitle_assets(source, assets, timeout_seconds)


def prepare_subtitle_assets(
    source: Path,
    output_dir: Path,
    base_name: str,
    model_size: str = "small",
    language: str | None = None,
    style: str = "pop",
) -> SubtitleAssets:
    output_dir.mkdir(parents=True, exist_ok=True)
    cues = transcribe_subtitle_cues(source, model_size=model_size, language=language)
    if not cues:
        raise RuntimeError("Не удалось распознать речь для субтитров")
    return create_subtitle_assets(source, output_dir, base_name, cues, style)


def create_subtitle_assets(
    source: Path,
    output_dir: Path,
    base_name: str,
    cues: list[SubtitleCue],
    style: str = "pop",
) -> SubtitleAssets:
    output_dir.mkdir(parents=True, exist_ok=True)
    info = inspect_video(source)
    safe_style = clean_base_name(style, "pop")
    output = output_dir / f"{clean_base_name(base_name, 'subtitled')}_subtitled_{safe_style}.mp4"
    ass_path = output.with_suffix(".ass")
    _write_ass_subtitles(ass_path, cues, info.width or 1080, info.height or 1920, style)
    return SubtitleAssets(
        output=output,
        ass_path=ass_path,
        cue_count=len(cues),
        duration_seconds=int(info.duration_seconds or 0),
    )


def render_subtitle_assets(source: Path, assets: SubtitleAssets, timeout_seconds: int = 900) -> ShortClip:
    _burn_ass_subtitles(source, assets.ass_path, assets.output, timeout_seconds)
    return ShortClip(path=assets.output, start_seconds=0, duration_seconds=assets.duration_seconds)


def normalize_subtitle_language(value: str | None) -> str | None:
    language = (value or "").strip().lower().replace("_", "-")
    language = WHISPER_LANGUAGE_ALIASES.get(language, language)
    if not language:
        return None
    return language if language in WHISPER_LANGUAGE_CODES else None


def transcribe_subtitle_cues(source: Path, model_size: str = "small", language: str | None = None) -> list[SubtitleCue]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SubtitleUnavailableError(
            "Для автосубтитров нужен локальный faster-whisper. Обнови зависимости: pip install -r requirements.txt"
        ) from exc

    normalized_language = normalize_subtitle_language(language)
    prompt = SUBTITLE_LANGUAGE_PROMPTS.get(normalized_language or "", "")
    model = WhisperModel(model_size or "small", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(source),
        language=normalized_language,
        initial_prompt=prompt or None,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 420, "speech_pad_ms": 280},
        word_timestamps=True,
        beam_size=7,
        best_of=5,
        patience=1.05,
        temperature=(0.0, 0.2, 0.4),
        condition_on_previous_text=False,
        compression_ratio_threshold=2.35,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.55,
    )

    cues: list[SubtitleCue] = []
    for segment in segments:
        words = getattr(segment, "words", None) or []
        if words:
            cues.extend(_word_cues(words))
        else:
            text = _normalize_caption_text(getattr(segment, "text", ""))
            start = float(getattr(segment, "start", 0.0) or 0.0)
            end = float(getattr(segment, "end", start + 1.0) or start + 1.0)
            if text and end > start:
                cues.extend(_split_segment_text_into_cues(start, end, text))
    return _polish_subtitle_cues(_merge_short_cues(cues))


def _word_cues(words) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    current: list[tuple[float, float, str]] = []
    current_chars = 0
    max_chars = 36
    max_duration = 2.8

    for word in words:
        raw = _normalize_caption_text(getattr(word, "word", ""))
        start = float(getattr(word, "start", 0.0) or 0.0)
        end = float(getattr(word, "end", start + 0.25) or start + 0.25)
        if not raw:
            continue
        gap = start - current[-1][1] if current else 0
        duration = end - current[0][0] if current else 0
        hard_break = bool(current and re.search(r"[.!?…]$", current[-1][2]) and current_chars >= 18)
        if current and (current_chars + len(raw) > max_chars or duration > max_duration or gap > 0.55 or hard_break):
            cues.append(_cue_from_words(current))
            current = []
            current_chars = 0
        current.append((start, end, raw))
        current_chars += len(raw) + 1

    if current:
        cues.append(_cue_from_words(current))
    return cues


def _cue_from_words(words: list[tuple[float, float, str]]) -> SubtitleCue:
    start = words[0][0]
    end = max(words[-1][1], start + 0.65)
    text = " ".join(word for _start, _end, word in words)
    return SubtitleCue(start=max(0.0, start), end=end, text=_normalize_caption_text(text))


def _split_segment_text_into_cues(start: float, end: float, text: str) -> list[SubtitleCue]:
    text = _normalize_caption_text(text)
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", text) if part.strip()]
    if len(parts) <= 1 and len(text) <= 42:
        return [SubtitleCue(start=max(0.0, start), end=max(end, start + 0.65), text=text)]
    if len(parts) <= 1:
        parts = _split_long_caption_text(text, 36)
    duration = max(0.65, end - start)
    total_chars = max(1, sum(len(part) for part in parts))
    cues: list[SubtitleCue] = []
    cursor = start
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            part_end = end
        else:
            part_duration = max(0.65, duration * (len(part) / total_chars))
            part_end = min(end, cursor + part_duration)
        cues.append(SubtitleCue(start=max(0.0, cursor), end=max(part_end, cursor + 0.65), text=_normalize_caption_text(part)))
        cursor = part_end
    return cues


def _split_long_caption_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    parts: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = word
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts or [text]


def _merge_short_cues(cues: list[SubtitleCue]) -> list[SubtitleCue]:
    merged: list[SubtitleCue] = []
    for cue in cues:
        if not cue.text:
            continue
        combined_text = f"{merged[-1].text} {cue.text}".strip() if merged else cue.text
        if merged and cue.end - cue.start < 0.55 and cue.end - merged[-1].start < 3.0 and len(combined_text) <= 42:
            previous = merged.pop()
            merged.append(SubtitleCue(previous.start, cue.end, combined_text))
        else:
            merged.append(cue)
    return merged


def _polish_subtitle_cues(cues: list[SubtitleCue]) -> list[SubtitleCue]:
    polished: list[SubtitleCue] = []
    previous_text = ""
    for cue in cues:
        text = _normalize_caption_text(cue.text)
        if not text or _is_low_value_caption(text):
            continue
        if previous_text and text.lower() == previous_text.lower() and cue.start - polished[-1].end < 0.35:
            continue
        start = max(0.0, cue.start)
        end = max(cue.end, start + 0.65)
        if polished and start < polished[-1].end:
            start = polished[-1].end + 0.02
            end = max(end, start + 0.55)
        polished.append(SubtitleCue(start=round(start, 3), end=round(end, 3), text=text))
        previous_text = text
    return polished


def _is_low_value_caption(text: str) -> bool:
    normalized = text.strip().lower()
    normalized = re.sub(r"[\[\](){}]", "", normalized).strip()
    low_value = {
        "music", "музыка", "музика", "applause", "аплодисменты", "оплески",
        "thank you for watching", "thanks for watching", "subscribe", "подписывайтесь",
    }
    return normalized in low_value


def _write_ass_subtitles(path: Path, cues: list[SubtitleCue], width: int, height: int, style: str) -> None:
    style = _normalize_subtitle_style(style)
    vertical = height > width
    font_size = _subtitle_font_size(width, height, vertical, style)
    margin_v = _subtitle_margin_v(height, vertical, style)
    outline = max(2, int(font_size * (0.09 if style in {"neon", "candy", "comic", "kinetic", "bounce", "headline", "mono"} else 0.075)))
    if style == "minimal":
        outline = max(1, int(font_size * 0.045))
    shadow = max(1, int(font_size * (0.055 if style in {"neon", "candy", "comic", "luxury", "soft"} else 0.035)))
    primary, secondary, outline_color, shadow_color = _subtitle_style_colors(style)
    font_name = _subtitle_font_name(style)
    alignment = 2

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},{font_size},{primary},{secondary},{outline_color},{shadow_color},"
        f"{_subtitle_bold(style)},{_subtitle_italic(style)},0,0,100,100,{_subtitle_spacing(style)},0,1,{outline},{shadow},{alignment},70,70,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    lines = header[:]
    for index, cue in enumerate(cues):
        text = _format_ass_caption(cue.text, vertical, style)
        if not text:
            continue
        text = _subtitle_motion_tags(index, cue, width, height, vertical, style) + text
        lines.append(f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},Default,,0,0,0,,{text}")
    path.write_text("\n".join(lines), encoding="utf-8")


def _burn_ass_subtitles(source: Path, ass_path: Path, output: Path, timeout_seconds: int) -> None:
    vf = f"ass='{_escape_filter_path(ass_path)}'"
    audio_args = ["-af", VIDEO_AUDIO_FILTER] if has_audio_stream(source) else []
    args = [
        ffmpeg_path(),
        "-y",
        "-i",
        str(source),
        "-vf",
        vf,
        *audio_args,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        VIDEO_QUALITY_PRESET,
        "-crf",
        SUBTITLE_VIDEO_CRF,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output),
    ]
    _run_ffmpeg(args, timeout_seconds)


def _subtitle_font_size(width: int, height: int, vertical: bool, style: str) -> int:
    style = _normalize_subtitle_style(style)
    loud = {"pop", "neon", "candy", "comic", "kinetic", "bounce", "headline", "mono"}
    if vertical:
        base = int(height * (0.048 if style in loud else 0.038))
    else:
        base = int(height * (0.068 if style in loud else 0.052))
    if style == "minimal":
        base = int(base * 0.82)
    if style in {"comic", "bounce", "headline"}:
        base = int(base * 1.06)
    if style in {"editorial", "luxury", "typewriter"}:
        base = int(base * 0.92)
    return max(28, min(92, base))


def _subtitle_margin_v(height: int, vertical: bool, style: str) -> int:
    style = _normalize_subtitle_style(style)
    if vertical:
        ratio = 0.145 if style in {"pop", "neon", "candy", "comic", "kinetic", "bounce", "headline", "mono"} else 0.11
    else:
        ratio = 0.09 if style in {"pop", "neon", "candy", "comic", "kinetic", "bounce", "headline", "mono"} else 0.065
    return max(26, int(height * ratio))


def _format_ass_caption(text: str, vertical: bool, style: str) -> str:
    style = _normalize_subtitle_style(style)
    text = _normalize_caption_text(text)
    if not text:
        return ""
    if style in {"pop", "neon", "candy", "comic", "kinetic", "bounce", "headline", "mono"}:
        text = _highlight_caption_words(text.upper(), style)
    else:
        text = _ass_escape_text(text)
    max_chars = 18 if vertical else 34
    if style == "minimal":
        max_chars += 8
    if style in {"kinetic", "bounce"}:
        max_chars -= 2
    if style in {"typewriter", "editorial", "luxury", "soft"}:
        max_chars += 4
    return r"\N".join(_caption_lines(text, max_chars))


def _caption_lines(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        plain_word = re.sub(r"\{[^}]*\}", "", word)
        plain_current = re.sub(r"\{[^}]*\}", "", current)
        candidate_len = len(f"{plain_current} {plain_word}".strip())
        if current and candidate_len > max_chars and len(lines) < 1:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    if len(lines) > 2:
        return [lines[0], " ".join(lines[1:])]
    return lines


def _highlight_caption_words(text: str, style: str) -> str:
    style = _normalize_subtitle_style(style)
    words = text.split()
    candidates = [
        index
        for index, word in enumerate(words)
        if len(re.sub(r"[^A-ZА-ЯЁІЇЄҐ0-9]", "", word, flags=re.IGNORECASE)) >= 6
    ][:2]
    palette = _subtitle_word_palette(style)
    output: list[str] = []
    for index, word in enumerate(words):
        escaped = _ass_escape_text(word)
        if index in candidates:
            color = palette[index % len(palette)]
            output.append(r"{\c" + color + r"}" + escaped + r"{\c&H00FFFFFF&}")
        else:
            output.append(escaped)
    return " ".join(output)


def _normalize_subtitle_style(style: str) -> str:
    style = (style or "pop").strip().lower()
    return style if style in {
        "pop", "clean", "minimal", "neon", "candy", "comic", "kinetic", "bounce",
        "editorial", "typewriter", "headline", "luxury", "mono", "soft",
    } else "pop"


def _subtitle_font_name(style: str) -> str:
    style = _normalize_subtitle_style(style)
    return {
        "comic": "Arial Rounded MT Bold",
        "typewriter": "Consolas",
        "mono": "Consolas",
        "headline": "Arial Black",
        "luxury": "Georgia",
        "editorial": "Georgia",
        "soft": "Trebuchet MS",
        "minimal": "Segoe UI",
        "clean": "Segoe UI",
    }.get(style, "Segoe UI Semibold")


def _subtitle_bold(style: str) -> int:
    return 0 if _normalize_subtitle_style(style) in {"minimal", "typewriter", "luxury", "editorial"} else -1


def _subtitle_italic(style: str) -> int:
    return -1 if _normalize_subtitle_style(style) in {"luxury", "editorial"} else 0


def _subtitle_spacing(style: str) -> int:
    return 2 if _normalize_subtitle_style(style) in {"headline", "mono"} else 0


def _subtitle_style_colors(style: str) -> tuple[str, str, str, str]:
    style = _normalize_subtitle_style(style)
    if style == "neon":
        return "&H00FFFFFF", "&H0000D7FF", "&H008C19FF", "&HAA001028"
    if style == "candy":
        return "&H00FFFFFF", "&H00FF76D8", "&H00672C92", "&HAA170A26"
    if style == "comic":
        return "&H00FFFFFF", "&H0000E7FF", "&H00000000", "&HAA2B2200"
    if style == "kinetic":
        return "&H00FFFFFF", "&H0000D1FF", "&H00000000", "&HAA000000"
    if style == "bounce":
        return "&H00FFFFFF", "&H0000F2FF", "&H003B1688", "&HAA000000"
    if style == "minimal":
        return "&H00FFFFFF", "&H00D0D0D0", "&H00303030", "&H77000000"
    if style == "clean":
        return "&H00FFFFFF", "&H00E8E8E8", "&H00000000", "&H99000000"
    if style == "editorial":
        return "&H00F8FAFC", "&H00CBD5E1", "&H00301E12", "&H88000000"
    if style == "typewriter":
        return "&H00FDECC8", "&H0000B4FF", "&H00302010", "&H88000000"
    if style == "headline":
        return "&H00FFFFFF", "&H003737FF", "&H00000000", "&HAA000000"
    if style == "luxury":
        return "&H00F4E7C1", "&H0027AFD4", "&H00130F08", "&HAA000000"
    if style == "mono":
        return "&H00D5FBE5", "&H004ADE80", "&H00070D09", "&HAA000000"
    if style == "soft":
        return "&H00FFFFFF", "&H00F3BF93", "&H00433217", "&H88000000"
    return "&H00FFFFFF", "&H0066D1FF", "&H00000000", "&HAA000000"


def _subtitle_word_palette(style: str) -> list[str]:
    style = _normalize_subtitle_style(style)
    palettes = {
        "pop": [r"&H0066D1FF&", r"&H0000E6FF&"],
        "neon": [r"&H0000F0FF&", r"&H00FF42E6&", r"&H006DFF7A&"],
        "candy": [r"&H00FF76D8&", r"&H0000E7FF&", r"&H00A6FF5E&"],
        "comic": [r"&H0000E7FF&", r"&H004B8CFF&", r"&H00FF78EA&"],
        "kinetic": [r"&H0000D1FF&", r"&H00FF6FD8&", r"&H006BFF81&"],
        "bounce": [r"&H0000F2FF&", r"&H00FF78EA&", r"&H008AFF6B&"],
        "headline": [r"&H003737FF&", r"&H0000E7FF&"],
        "mono": [r"&H004ADE80&", r"&H00D5FBE5&"],
    }
    return palettes.get(style, palettes["pop"])


def _subtitle_motion_tags(
    index: int,
    cue: SubtitleCue,
    width: int,
    height: int,
    vertical: bool,
    style: str,
) -> str:
    style = _normalize_subtitle_style(style)
    if style in {"pop", "clean", "minimal", "editorial", "typewriter", "luxury", "soft"}:
        return ""
    duration = max(0.4, cue.end - cue.start)
    y = int(height * (0.78 if vertical else 0.84))
    if style == "kinetic":
        swing = max(16, int(width * 0.018))
        x1 = width // 2 + (-swing if index % 2 == 0 else swing)
        x2 = width // 2 + (swing if index % 2 == 0 else -swing)
        return rf"{{\an2\move({x1},{y},{x2},{y},0,{int(duration * 1000)})\fad(80,120)\t(0,160,\fscx108\fscy108)\t(160,320,\fscx100\fscy100)}}"
    if style == "bounce":
        y1 = y + max(18, int(height * 0.025))
        return rf"{{\an2\move({width // 2},{y1},{width // 2},{y},0,220)\fad(60,100)\t(0,180,\fscx116\fscy116)\t(180,360,\fscx100\fscy100)}}"
    if style == "neon":
        return r"{\an2\fad(90,120)\t(0,220,\fscx106\fscy106)\t(220,420,\fscx100\fscy100)}"
    if style == "candy":
        x = width // 2 + (-max(10, width // 90) if index % 2 else max(10, width // 90))
        return rf"{{\an2\pos({x},{y})\fad(80,110)\t(0,180,\frz{-2 if index % 2 else 2})\t(180,360,\frz0)}}"
    if style == "comic":
        return r"{\an2\fad(60,90)\t(0,130,\fscx120\fscy120)\t(130,300,\fscx100\fscy100)}"
    return ""


def _normalize_caption_text(text: str) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    value = value.replace(" ,", ",").replace(" .", ".").replace(" !", "!").replace(" ?", "?")
    value = re.sub(r"\s+([,.;:!?…])", r"\1", value)
    value = re.sub(r"([,.;:!?…])([^\s,.;:!?…])", r"\1 \2", value)
    value = re.sub(r"\.{2,}", "…", value)
    value = re.sub(r"([!?]){3,}", r"\1", value)
    value = re.sub(r"\b(\w{2,})\s+\1\b", r"\1", value, flags=re.IGNORECASE)
    if value:
        value = value[0].upper() + value[1:]
    return value.strip()


def _ass_escape_text(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", "")
        .replace("}", "")
        .replace("\n", r"\N")
    )


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds >= 100:
        secs += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _escape_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return value.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _load_font(size: int) -> ImageFont.ImageFont:
    for name in _font_candidates("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(str(name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _font_candidates(*names: str) -> list[str | Path]:
    candidates: list[str | Path] = list(names)
    windows_fonts = Path("C:/Windows/Fonts")
    for name in names:
        candidates.append(windows_fonts / name)
    return candidates


def _wrap_text(text: str, line_length: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > line_length and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [text]


def _resize_cover_background(
    image: Image.Image,
    target_size: tuple[int, int],
    focus: tuple[int, int] | None,
) -> tuple[Image.Image, tuple[int, int] | None]:
    target_width, target_height = target_size
    scale = max(target_width / image.width, target_height / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    if focus:
        focus_x = int(focus[0] * scale)
        focus_y = int(focus[1] * scale)
        left = clamp(focus_x - int(target_width * 0.72), 0, max(0, resized.width - target_width))
        top = clamp(focus_y - int(target_height * 0.45), 0, max(0, resized.height - target_height))
    else:
        left = max(0, (resized.width - target_width) // 2)
        top = max(0, (resized.height - target_height) // 2)
        focus_x = left + int(target_width * 0.76)
        focus_y = top + int(target_height * 0.42)
    crop = resized.crop((left, top, left + target_width, top + target_height))
    return crop, (focus_x - left, focus_y - top) if focus else None


def _load_cover_topic_assets(title: str, cache_dir: Path) -> list[Image.Image]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    assets: list[Image.Image] = []
    for query in _cover_topic_queries(title):
        for item in _search_commons_images(query, limit=5):
            image = _download_cover_asset(item["url"])
            if image is None:
                continue
            assets.append(_make_cover_sticker(image))
            if len(assets) >= 2:
                return assets
    return assets or _fallback_cover_topic_assets(title)


def _cover_topic_queries(title: str) -> list[str]:
    words = _cover_topic_words(title)
    joined = " ".join(words[:5])
    rules = [
        (("бизнес", "бізнес", "деньг", "грош", "финанс", "фінанс", "инвест", "інвест", "заработ", "зароб", "money", "business", "finance", "bank"), "business money finance"),
        (("крипт", "crypto", "bitcoin", "битко", "бітко", "blockchain"), "cryptocurrency bitcoin finance"),
        (("кроссов", "крассов", "кросів", "sneaker", "shoe", "обув", "взут"), "sneakers shoes"),
        (("авто", "машин", "car", "cars", "tesla", "bmw", "mercedes"), "sports car automobile"),
        (("игр", "ігр", "game", "gaming", "minecraft", "roblox", "fortnite"), "gaming computer controller"),
        (("еда", "їжа", "food", "ресторан", "кухн", "burger", "pizza"), "food restaurant meal"),
        (("спорт", "sport", "fitness", "трен", "зал", "gym", "boxing", "football"), "sport fitness training"),
        (("путеш", "подорож", "travel", "туризм", "город", "місто", "city"), "travel city landmark"),
        (("музык", "музик", "music", "song", "artist", "concert"), "music concert microphone"),
        (("тех", "tech", "телефон", "phone", "iphone", "android", "ноут", "laptop"), "technology smartphone laptop"),
        (("дом", "house", "real", "estate", "недвиж", "нерух"), "real estate house"),
        (("мода", "fashion", "style", "стиль", "beauty", "красот"), "fashion style"),
    ]
    scored: list[tuple[int, str]] = []
    haystack = " ".join(words).lower()
    for terms, query in rules:
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, query))
    queries = [query for _score, query in sorted(scored, reverse=True)]
    if joined:
        queries.append(joined)
    queries.append("business success money")

    unique: list[str] = []
    for query in queries:
        if query and query not in unique:
            unique.append(query)
    return unique[:4]


def _cover_topic_words(title: str) -> list[str]:
    stop_words = {
        "the", "and", "for", "with", "from", "this", "that", "video", "shorts", "youtube",
        "что", "как", "это", "для", "или", "при", "про", "без", "все", "всё", "его", "она", "они",
        "цей", "для", "або", "про", "без", "відео", "как", "що", "це",
    }
    cleaned = re.sub(r"https?://\S+", " ", title or "")
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ0-9]{3,}", cleaned)
        if word.lower() not in stop_words
    ]
    return words[:10]


def _search_commons_images(query: str, limit: int = 5) -> list[dict[str, str]]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "iiurlwidth": "900",
        "format": "json",
        "origin": "*",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "cherryx-cover-bot/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []

    results: list[dict[str, str]] = []
    pages = (payload.get("query") or {}).get("pages") or {}
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        mime = str(info.get("mime") or "")
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        if int(info.get("width") or 0) < 180 or int(info.get("height") or 0) < 180:
            continue
        metadata = info.get("extmetadata") or {}
        if not _commons_license_allowed(metadata):
            continue
        asset_url = info.get("thumburl") or info.get("url")
        if asset_url:
            results.append({"url": asset_url, "title": str(page.get("title") or query)})
    return results


def _commons_license_allowed(metadata: dict) -> bool:
    license_name = str((metadata.get("LicenseShortName") or {}).get("value") or "").lower()
    license_code = str((metadata.get("License") or {}).get("value") or "").lower()
    attribution = str((metadata.get("AttributionRequired") or {}).get("value") or "").lower()
    copyrighted = str((metadata.get("Copyrighted") or {}).get("value") or "").lower()
    if "public domain" in license_name or "cc0" in license_name or license_code in {"pd", "cc0"}:
        return True
    return copyrighted == "false" and attribution == "false"


def _download_cover_asset(url: str) -> Image.Image | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "cherryx-cover-bot/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            content = response.read(5 * 1024 * 1024)
        return ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert("RGB")
    except Exception:
        return None


def _download_rgba_asset(url: str) -> Image.Image | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "cherryx-cover-bot/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            content = response.read(3 * 1024 * 1024)
        return Image.open(io.BytesIO(content)).convert("RGBA")
    except Exception:
        return None


def _load_cover_impact_asset(cache_dir: Path) -> Image.Image:
    cache_dir.mkdir(parents=True, exist_ok=True)
    rng = random.SystemRandom()
    choices = list(IMPACT_ICON_URLS)
    rng.shuffle(choices)
    for name, url in choices:
        cached = cache_dir / f"{name}.png"
        image: Image.Image | None = None
        try:
            if cached.exists():
                image = Image.open(cached).convert("RGBA")
        except Exception:
            image = None
        if image is None:
            image = _download_rgba_asset(url)
            if image is not None:
                try:
                    image.save(cached)
                except Exception:
                    pass
        if image is not None:
            return _make_cover_impact_sticker(image, rng.choice(["BAM!", "WOW!", "HOT!", "BOOM!"]))
    return _draw_fallback_impact_sticker(rng.choice(["BAM!", "WOW!", "BOOM!"]))


def _make_cover_impact_sticker(icon: Image.Image, label: str) -> Image.Image:
    canvas = Image.new("RGBA", (320, 278), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    _draw_starburst(draw, (160, 128), 128, 74, 13, (255, 222, 48, 255), (240, 36, 54, 255))
    icon = icon.copy()
    icon.thumbnail((158, 158), Image.Resampling.LANCZOS)
    canvas.paste(icon, ((320 - icon.width) // 2, 42), icon)

    label_font = _load_cover_font(48)
    label_w = _text_width(label_font, label)
    label_box = (max(18, 160 - label_w // 2 - 28), 196, min(302, 160 + label_w // 2 + 28), 256)
    draw.rounded_rectangle(label_box, radius=18, fill=(8, 10, 14, 245), outline=(255, 255, 255, 245), width=5)
    draw.text((160 - label_w // 2, 199), label, fill=(255, 255, 255, 255), font=label_font)
    return _add_sticker_outline(canvas)


def _draw_fallback_impact_sticker(label: str) -> Image.Image:
    canvas = Image.new("RGBA", (320, 278), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    _draw_starburst(draw, (160, 132), 132, 62, 14, (255, 219, 40, 255), (238, 34, 58, 255))
    font = _load_cover_font(58)
    width = _text_width(font, label)
    draw.text((160 - width // 2, 102), label, fill=(255, 255, 255, 255), font=font, stroke_width=7, stroke_fill=(8, 10, 14, 255))
    return _add_sticker_outline(canvas)


def _draw_starburst(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    outer_radius: int,
    inner_radius: int,
    points: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
) -> None:
    cx, cy = center
    polygon: list[tuple[int, int]] = []
    for index in range(points * 2):
        radius = outer_radius if index % 2 == 0 else inner_radius
        angle = -pi / 2 + index * pi / points
        polygon.append((int(cx + cos(angle) * radius), int(cy + sin(angle) * radius)))
    draw.polygon(polygon, fill=fill, outline=outline)
    draw.line(polygon + [polygon[0]], fill=outline, width=8, joint="curve")


def _make_cover_sticker(image: Image.Image) -> Image.Image:
    image = image.copy()
    image.thumbnail((360, 280), Image.Resampling.LANCZOS)
    cutout = _subject_cutout_rgba(image)
    return _add_sticker_outline(cutout)


def _subject_cutout_rgba(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    mask = _grabcut_subject_mask(rgb)
    if mask is None:
        mask = _soft_rounded_mask(rgb.size)
    rgba = rgb.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def _grabcut_subject_mask(image: Image.Image) -> Image.Image | None:
    width, height = image.size
    if width < 90 or height < 90:
        return None
    try:
        array = np.array(image)
        mask = np.zeros(array.shape[:2], np.uint8)
        rect = (
            max(1, int(width * 0.07)),
            max(1, int(height * 0.07)),
            max(2, int(width * 0.86)),
            max(2, int(height * 0.86)),
        )
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        cv2.grabCut(array, mask, rect, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
        subject = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
        coverage = float(subject.mean()) / 255.0
        if coverage < 0.10 or coverage > 0.92:
            return None
        kernel = np.ones((5, 5), np.uint8)
        subject = cv2.morphologyEx(subject, cv2.MORPH_CLOSE, kernel, iterations=1)
        subject = cv2.medianBlur(subject, 5)
        return Image.fromarray(subject, "L").filter(ImageFilter.GaussianBlur(0.8))
    except Exception:
        return None


def _soft_rounded_mask(size: tuple[int, int]) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    radius = max(24, min(width, height) // 6)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(0.4))


def _add_sticker_outline(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    outline_alpha = alpha.filter(ImageFilter.MaxFilter(19))
    pad = 28
    canvas = Image.new("RGBA", (image.width + pad * 2, image.height + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 150))
    shadow_alpha = outline_alpha.filter(ImageFilter.GaussianBlur(9))
    canvas.paste(shadow, (pad + 10, pad + 12), shadow_alpha)
    outline = Image.new("RGBA", image.size, (255, 255, 255, 245))
    canvas.paste(outline, (pad, pad), outline_alpha)
    canvas.paste(image, (pad, pad), alpha)
    return canvas


def _fallback_cover_topic_assets(title: str) -> list[Image.Image]:
    kind = _fallback_topic_kind(title)
    return [_draw_fallback_topic_sticker(kind)]


def _fallback_topic_kind(title: str) -> str:
    words = " ".join(_cover_topic_words(title))
    checks = [
        ("money", ("бизнес", "бізнес", "деньг", "грош", "финанс", "інвест", "заработ", "зароб", "money", "business", "finance")),
        ("crypto", ("крипт", "crypto", "bitcoin", "битко", "бітко")),
        ("shoe", ("кроссов", "крассов", "кросів", "sneaker", "shoe", "обув", "взут")),
        ("car", ("авто", "машин", "car", "tesla", "bmw")),
        ("game", ("игр", "ігр", "game", "gaming", "minecraft", "roblox")),
        ("food", ("еда", "їжа", "food", "ресторан", "burger", "pizza")),
        ("sport", ("спорт", "sport", "fitness", "gym", "boxing", "football")),
        ("travel", ("путеш", "подорож", "travel", "туризм", "city")),
        ("music", ("музык", "музик", "music", "song", "concert")),
        ("tech", ("тех", "tech", "телефон", "phone", "iphone", "laptop")),
        ("house", ("дом", "house", "real", "estate", "недвиж", "нерух")),
    ]
    for kind, terms in checks:
        if any(term in words for term in terms):
            return kind
    return "money"


def _draw_fallback_topic_sticker(kind: str) -> Image.Image:
    image = Image.new("RGBA", (320, 240), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    accent = (255, 218, 58, 255)
    accent2 = (44, 221, 255, 255)
    red = (238, 36, 56, 255)
    black = (8, 10, 14, 255)

    if kind == "shoe":
        draw.polygon([(55, 140), (118, 92), (174, 122), (252, 128), (284, 162), (268, 186), (90, 186), (54, 166)], fill=accent2)
        draw.line([(105, 126), (138, 148), (172, 134), (204, 150)], fill=black, width=8)
        draw.rounded_rectangle((74, 176, 280, 205), radius=14, fill=black)
    elif kind == "car":
        draw.rounded_rectangle((54, 112, 282, 176), radius=24, fill=red)
        draw.polygon([(96, 112), (132, 70), (220, 70), (252, 112)], fill=accent2)
        draw.ellipse((78, 158, 128, 208), fill=black)
        draw.ellipse((214, 158, 264, 208), fill=black)
    elif kind == "game":
        draw.rounded_rectangle((56, 88, 284, 184), radius=40, fill=black)
        draw.ellipse((92, 122, 126, 156), fill=accent2)
        draw.rectangle((106, 104, 112, 174), fill=accent2)
        draw.rectangle((76, 136, 142, 142), fill=accent2)
        for x, y in [(218, 118), (246, 142), (218, 166), (190, 142)]:
            draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=accent)
    elif kind == "food":
        draw.ellipse((60, 82, 286, 190), fill=accent)
        draw.rectangle((58, 128, 288, 164), fill=red)
        draw.rounded_rectangle((72, 154, 274, 196), radius=20, fill=black)
        for x in range(100, 240, 34):
            draw.ellipse((x, 100, x + 12, 112), fill=black)
    elif kind == "sport":
        draw.ellipse((78, 48, 246, 216), fill=accent2, outline=black, width=10)
        draw.arc((92, 62, 232, 202), 70, 290, fill=black, width=7)
        draw.arc((92, 62, 232, 202), -110, 110, fill=black, width=7)
        draw.line((162, 52, 162, 212), fill=black, width=7)
    elif kind == "travel":
        draw.polygon([(156, 42), (238, 198), (156, 170), (76, 198)], fill=accent2)
        draw.polygon([(156, 42), (174, 166), (156, 170), (138, 166)], fill=black)
        draw.ellipse((120, 108, 194, 182), outline=red, width=10)
    elif kind == "music":
        draw.ellipse((82, 152, 142, 212), fill=red)
        draw.rectangle((128, 58, 146, 178), fill=black)
        draw.rectangle((144, 58, 240, 78), fill=black)
        draw.ellipse((216, 128, 276, 188), fill=accent)
        draw.rectangle((238, 72, 256, 152), fill=black)
    elif kind == "tech":
        draw.rounded_rectangle((92, 42, 230, 214), radius=22, fill=black)
        draw.rounded_rectangle((108, 62, 214, 184), radius=8, fill=accent2)
        draw.ellipse((146, 190, 176, 220), fill=accent)
    elif kind == "house":
        draw.polygon([(52, 130), (160, 44), (270, 130)], fill=red)
        draw.rounded_rectangle((82, 124, 240, 214), radius=8, fill=accent)
        draw.rectangle((142, 156, 182, 214), fill=black)
    elif kind == "crypto":
        draw.ellipse((72, 42, 248, 218), fill=accent, outline=black, width=12)
        font = _load_cover_font(112)
        draw.text((116, 74), "B", fill=black, font=font, stroke_width=2, stroke_fill=black)
        draw.line((108, 66, 108, 196), fill=black, width=7)
        draw.line((210, 66, 210, 196), fill=black, width=7)
    else:
        draw.rounded_rectangle((46, 82, 144, 190), radius=12, fill=accent)
        draw.rounded_rectangle((136, 58, 236, 190), radius=12, fill=accent2)
        draw.rounded_rectangle((226, 108, 292, 190), radius=12, fill=red)
        draw.ellipse((70, 36, 242, 208), outline=black, width=12)
        draw.text((125, 74), "$", fill=black, font=_load_cover_font(98))
    return _add_sticker_outline(image)


def _draw_business_cover(
    canvas: Image.Image,
    title: str,
    focus_point: tuple[int, int] | None,
    topic_assets: list[Image.Image] | None = None,
    impact_asset: Image.Image | None = None,
    variant_seed: int | None = None,
    variant_index: int = 1,
) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    width, height = canvas.size
    rng = random.SystemRandom()
    templates = ["classic", "split", "money", "premium", "neon"]
    template = rng.choice(templates)
    palette = rng.choice(
        [
            {"accent": (255, 218, 58, 255), "accent2": (35, 214, 255, 255), "danger": (235, 21, 38, 255), "dark": (8, 9, 12, 225)},
            {"accent": (57, 255, 136, 255), "accent2": (255, 230, 65, 255), "danger": (255, 64, 64, 255), "dark": (4, 18, 15, 230)},
            {"accent": (255, 122, 40, 255), "accent2": (255, 230, 72, 255), "danger": (206, 24, 38, 255), "dark": (22, 12, 7, 230)},
            {"accent": (255, 84, 208, 255), "accent2": (74, 221, 255, 255), "danger": (255, 35, 70, 255), "dark": (12, 8, 24, 230)},
        ]
    )
    accent = palette["accent"]
    accent2 = palette["accent2"]
    danger = palette["danger"]
    dark = palette["dark"]

    shadow = canvas.filter(ImageFilter.GaussianBlur(radius=10))
    canvas.paste(Image.blend(canvas, shadow, 0.16))
    text_left = not focus_point or focus_point[0] > width * 0.52
    panel_x = 52 if text_left else 610
    max_text_width = 620 if text_left else 600
    cover_copy = _cover_copy(title)
    title_text = _cover_title_text(cover_copy.headline)
    description_text = _cover_description_text(cover_copy.description)

    label_font = _load_cover_font(34)
    title_font, lines = _fit_cover_title(title_text, max_text_width, 3)
    small_font = _load_cover_font(28)
    micro_font = _load_cover_font(22)
    description_font = _load_cover_font(30)

    if template == "classic":
        _draw_cover_fade(draw, width, height, text_left, dark)
        draw.rectangle((0, 0, width, height), outline=accent, width=10)
        draw.rounded_rectangle((panel_x, 48, panel_x + 348, 105), radius=12, fill=accent)
        draw.text((panel_x + 22, 57), "BUSINESS CUT", fill=(16, 17, 20, 255), font=label_font)
        badge_box = (panel_x + 4, 592, panel_x + 470, 650)
        badge_text = rng.choice(["STRONG MOMENT", "BIG MOVE", "WATCH THIS"])
        draw.rounded_rectangle(badge_box, radius=10, fill=danger)
        draw.text((badge_box[0] + 24, badge_box[1] + 12), badge_text, fill=(255, 255, 255, 255), font=small_font)
    elif template == "split":
        _draw_cover_fade(draw, width, height, text_left, dark)
        stripe = [(0, 0), (width, 0), (width, 60), (0, 155)] if text_left else [(0, 0), (width, 0), (width, 155), (0, 60)]
        draw.polygon(stripe, fill=accent)
        draw.polygon([(0, height), (width, height), (width, height - 52), (0, height - 140)], fill=danger)
        draw.rounded_rectangle((panel_x, 42, panel_x + 330, 96), radius=8, fill=(0, 0, 0, 235), outline=accent, width=3)
        draw.text((panel_x + 20, 50), "THE MOMENT", fill=accent, font=label_font)
    elif template == "money":
        _draw_cover_fade(draw, width, height, text_left, dark)
        for index in range(7):
            bar_w = 38
            bar_h = rng.randint(60, 210)
            x = (760 if text_left else 60) + index * 56
            draw.rounded_rectangle((x, height - 85 - bar_h, x + bar_w, height - 85), radius=8, fill=(*accent2[:3], 150))
        draw.ellipse((width - 260, 38, width - 70, 228) if text_left else (70, 38, 260, 228), fill=accent, outline=(0, 0, 0, 255), width=8)
        circle_x = width - 207 if text_left else 123
        draw.text((circle_x, 82), "$", fill=(10, 12, 14, 255), font=_load_cover_font(98))
        draw.rounded_rectangle((panel_x, 50, panel_x + 315, 104), radius=8, fill=danger)
        draw.text((panel_x + 20, 58), "MONEY MOVE", fill=(255, 255, 255, 255), font=label_font)
    elif template == "premium":
        draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 72))
        panel = (38, 36, 710, 666) if text_left else (570, 36, 1242, 666)
        draw.rounded_rectangle(panel, radius=20, fill=(0, 0, 0, 178), outline=accent, width=4)
        draw.line((panel[0] + 28, 118, panel[2] - 28, 118), fill=accent2, width=5)
        draw.text((panel_x, 64), "PREMIUM STORY", fill=accent, font=label_font)
        draw.text((panel_x, 610), "SELECTED FRAME  /  1280x720", fill=(235, 238, 242, 230), font=micro_font)
    else:
        draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 46))
        _draw_cover_fade(draw, width, height, text_left, (0, 0, 0, 210))
        for offset in range(0, width, 170):
            draw.line((offset, 0, offset + 130, height), fill=(*accent2[:3], 95), width=7)
        draw.rectangle((0, 0, width, height), outline=accent2, width=8)
        draw.rectangle((18, 18, width - 18, height - 18), outline=accent, width=4)
        draw.rounded_rectangle((panel_x, 48, panel_x + 300, 104), radius=28, fill=(0, 0, 0, 210), outline=accent2, width=3)
        draw.text((panel_x + 24, 57), "VIRAL FRAME", fill=accent2, font=label_font)

    y = 148 if template != "premium" else 170
    title_line_height = max(78, int(getattr(title_font, "size", 88)) + 7)
    for index, line in enumerate(lines):
        fill = (255, 255, 255, 255) if index % 2 == 0 else accent
        draw.text((panel_x, y), line, fill=fill, font=title_font, stroke_width=7, stroke_fill=(0, 0, 0, 255))
        y += title_line_height

    if description_text:
        description_lines = _wrap_cover_text(description_text.upper(), description_font, max_width=max_text_width, max_lines=2)
        if description_lines and y < 542:
            desc_y = y + 8
            line_height = 38
            box_height = len(description_lines) * line_height + 22
            draw.rounded_rectangle(
                (panel_x - 10, desc_y - 8, panel_x + max_text_width + 18, desc_y + box_height),
                radius=12,
                fill=(0, 0, 0, 118),
                outline=(*accent2[:3], 130),
                width=2,
            )
            for line in description_lines:
                draw.text((panel_x + 4, desc_y), line, fill=(238, 242, 246, 245), font=description_font, stroke_width=3, stroke_fill=(0, 0, 0, 220))
                desc_y += line_height

    _paste_cover_topic_assets(canvas, topic_assets or [], text_left, rng)
    point = focus_point or (int(width * 0.76), int(height * 0.42))
    _draw_cover_focus_marker(canvas, draw, width, height, point, focus_point is not None, text_left, accent, danger, impact_asset)


def _paste_cover_topic_assets(
    canvas: Image.Image,
    assets: list[Image.Image],
    text_left: bool,
    rng: random.SystemRandom,
) -> None:
    if not assets:
        return
    width, _height = canvas.size
    positions = [(930, 422), (1070, 184)] if text_left else [(260, 430), (390, 190)]
    sizes = [(330, 260), (230, 190)]
    for index, asset in enumerate(assets[:2]):
        sticker = asset.copy()
        sticker.thumbnail(sizes[index], Image.Resampling.LANCZOS)
        center_x, center_y = positions[index]
        center_x += rng.randint(-38, 38)
        center_y += rng.randint(-26, 26)
        x = max(20, min(width - sticker.width - 20, center_x - sticker.width // 2))
        y = max(35, min(650 - sticker.height, center_y - sticker.height // 2))
        canvas.paste(sticker, (x, y), sticker)


def _draw_cover_fade(draw: ImageDraw.ImageDraw, width: int, height: int, text_left: bool, color: tuple[int, int, int, int]) -> None:
    fade_width = int(width * 0.62)
    if text_left:
        for x in range(fade_width):
            alpha = int(color[3] * (1 - x / fade_width))
            draw.line([(x, 0), (x, height)], fill=(*color[:3], alpha))
    else:
        for offset in range(fade_width):
            x = width - 1 - offset
            alpha = int(color[3] * (1 - offset / fade_width))
            draw.line([(x, 0), (x, height)], fill=(*color[:3], alpha))


def _draw_cover_focus_marker(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    point: tuple[int, int],
    has_focus: bool,
    text_left: bool,
    accent: tuple[int, int, int, int],
    danger: tuple[int, int, int, int],
    impact_asset: Image.Image | None,
) -> None:
    x, y = point
    if has_focus:
        radius = 76
        segment = 44
        marker = (*accent[:3], 235)
        shadow = (0, 0, 0, 210)
        corners = [
            ((x - radius, y - radius), (x - radius + segment, y - radius), (x - radius, y - radius + segment)),
            ((x + radius, y - radius), (x + radius - segment, y - radius), (x + radius, y - radius + segment)),
            ((x - radius, y + radius), (x - radius + segment, y + radius), (x - radius, y + radius - segment)),
            ((x + radius, y + radius), (x + radius - segment, y + radius), (x + radius, y + radius - segment)),
        ]
        for corner, horizontal, vertical in corners:
            draw.line((corner, horizontal), fill=shadow, width=15)
            draw.line((corner, vertical), fill=shadow, width=15)
            draw.line((corner, horizontal), fill=marker, width=9)
            draw.line((corner, vertical), fill=marker, width=9)

    anchor_x = int(width * (0.84 if text_left else 0.18))
    anchor_y = max(145, min(height - 155, y - 32))
    target_x = max(110, min(width - 110, x))
    target_y = max(110, min(height - 110, y))
    for offset, color, line_width in [(-28, accent, 7), (0, danger, 12), (28, accent, 7)]:
        start = (anchor_x - (82 if text_left else -82), anchor_y + offset)
        end = (target_x - (34 if text_left else -34), target_y + offset // 3)
        draw.line((start, end), fill=(*color[:3], 195), width=line_width)

    sticker = (impact_asset or _draw_fallback_impact_sticker("BAM!")).copy()
    sticker.thumbnail((245, 210), Image.Resampling.LANCZOS)
    if text_left:
        min_x = int(width * 0.60)
        x0 = max(min_x, min(width - sticker.width - 26, anchor_x - sticker.width // 2))
    else:
        max_x = int(width * 0.42)
        x0 = max(26, min(max_x - sticker.width, anchor_x - sticker.width // 2))
    y0 = max(42, min(height - sticker.height - 42, anchor_y - sticker.height // 2))
    canvas.paste(sticker, (x0, y0), sticker)


def _draw_business_cover(
    canvas: Image.Image,
    title: str,
    focus_point: tuple[int, int] | None,
    topic_assets: list[Image.Image] | None = None,
    impact_asset: Image.Image | None = None,
    variant_seed: int | None = None,
    variant_index: int = 1,
) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    width, height = canvas.size
    seed_title = f"{title}:{variant_seed}:{variant_index}"
    profile = _cover_variant_profile(title, focus_point, variant_index, variant_seed)
    accent = profile["accent"]
    accent2 = profile["accent2"]
    layout = str(profile["layout"])
    mood = str(profile["mood"])
    warm = (255, 226, 96, 255)

    cinematic = canvas.filter(ImageFilter.GaussianBlur(radius=12))
    canvas.paste(Image.blend(canvas, cinematic, 0.05))
    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vignette_draw = ImageDraw.Draw(vignette, "RGBA")
    for step in range(42):
        alpha = min(148, int(7 + step * 3.4))
        inset_x = step * 12
        inset_y = step * 7
        vignette_draw.rounded_rectangle(
            (inset_x, inset_y, width - inset_x, height - inset_y),
            radius=18,
            outline=(0, 0, 0, alpha),
            width=18,
        )
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), vignette).convert(canvas.mode))

    text_left = bool(profile["text_left"])
    panel_x = int(profile["panel_x"])
    max_text_width = int(profile["max_text_width"])
    cover_copy = _cover_copy(title)
    title_text = _cover_title_text(cover_copy.headline)
    description_text = _cover_description_text(cover_copy.description)

    fade_alpha = 210 if mood == "clean" else 226
    _draw_cover_fade(draw, width, height, text_left, (0, 0, 0, fade_alpha))
    draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 14 if mood == "clean" else 24))
    _draw_cover_light_sweep(canvas, text_left, accent2)
    _draw_cover_variant_frame(draw, width, height, text_left, accent, accent2, layout)
    if layout in {"split", "broadcast"} and variant_index % 2:
        draw.line((0, height - 30, width, height - 30), fill=(*accent2[:3], 72), width=4)
        draw.line((0, height - 16, width, height - 16), fill=(*accent[:3], 160), width=3)
    elif layout in {"split", "broadcast"}:
        draw.line((0, 28, width, 28), fill=(*accent2[:3], 82), width=4)
        draw.line((0, 44, width, 44), fill=(*accent[:3], 145), width=3)
    elif layout == "impact":
        _draw_cover_impact_burst(draw, width, height, text_left, accent, accent2)

    label_font = _load_cover_font(22)
    eyebrow = str(profile["eyebrow"])
    eyebrow_w = min(max_text_width, _text_width(label_font, eyebrow) + 34)
    badge_y = int(profile["badge_y"])
    draw.rounded_rectangle((panel_x, badge_y, panel_x + eyebrow_w, badge_y + 38), radius=7, fill=(*accent[:3], 235))
    draw.text((panel_x + 17, badge_y + 8), eyebrow, fill=(8, 10, 14, 255), font=label_font)

    title_font, lines = _fit_cover_title(title_text, max_text_width, 3)
    y = int(profile["headline_y"])
    title_line_height = max(54, int(getattr(title_font, "size", 58)) + 7)
    title_box_height = len(lines) * title_line_height + 20
    draw.rounded_rectangle(
        (panel_x - 18, y - 14, panel_x + max_text_width + 20, y + title_box_height),
        radius=10,
        fill=(0, 0, 0, 72),
    )
    for index, line in enumerate(lines):
        fill = (255, 255, 255, 255) if index != 1 else accent
        _draw_cover_text_shadow(draw, (panel_x, y), line, title_font)
        draw.text((panel_x, y), line, fill=fill, font=title_font, stroke_width=4, stroke_fill=(0, 0, 0, 238))
        y += title_line_height

    if description_text:
        description_font = _load_cover_font(23)
        description_lines = _wrap_cover_text(description_text.upper(), description_font, max_width=max_text_width, max_lines=2)
        if description_lines and y < 542:
            desc_y = y + 12
            line_height = 30
            box_height = len(description_lines) * line_height + 18
            draw.rounded_rectangle(
                (panel_x - 8, desc_y - 7, panel_x + max_text_width + 12, desc_y + box_height),
                radius=7,
                fill=(0, 0, 0, 132),
                outline=(*accent[:3], 68),
                width=1,
            )
            for line in description_lines:
                draw.text((panel_x + 3, desc_y), line, fill=(238, 242, 246, 238), font=description_font, stroke_width=2, stroke_fill=(0, 0, 0, 210))
                desc_y += line_height

    _draw_premium_hook_badge(draw, width, height, text_left, accent, warm, title_text, str(profile["badge"]), int(profile["hook_x"]), int(profile["hook_y"]))
    if topic_assets and not focus_point:
        _paste_cover_topic_assets(canvas, topic_assets[:1], text_left, random.SystemRandom())


def _draw_cover_light_sweep(canvas: Image.Image, text_left: bool, accent: tuple[int, int, int, int]) -> None:
    width, height = canvas.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    if text_left:
        polygon = [(width * 0.52, 0), (width, 0), (width * 0.82, height), (width * 0.38, height)]
    else:
        polygon = [(0, 0), (width * 0.46, 0), (width * 0.62, height), (0, height)]
    draw.polygon([(int(x), int(y)) for x, y in polygon], fill=(*accent[:3], 32))
    glow = overlay.filter(ImageFilter.GaussianBlur(radius=38))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB"))


def _draw_cover_variant_frame(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    text_left: bool,
    accent: tuple[int, int, int, int],
    accent2: tuple[int, int, int, int],
    layout: str,
) -> None:
    if layout == "poster":
        draw.rounded_rectangle((18, 18, width - 18, height - 18), radius=4, outline=(*accent[:3], 190), width=4)
        draw.rectangle((34, 34, width - 34, height - 34), outline=(*accent2[:3], 70), width=1)
        return
    if layout == "broadcast":
        draw.rounded_rectangle((13, 13, width - 13, height - 13), radius=14, outline=(*accent[:3], 165), width=3)
        x = int(width * (0.57 if text_left else 0.43))
        draw.line((x, 0, x + (-88 if text_left else 88), height), fill=(*accent2[:3], 58), width=4)
        return
    if layout == "impact":
        draw.rounded_rectangle((12, 12, width - 12, height - 12), radius=18, outline=(*accent[:3], 205), width=5)
        draw.rounded_rectangle((32, 32, width - 32, height - 32), radius=14, outline=(*accent2[:3], 82), width=2)
        return
    draw.rounded_rectangle((13, 13, width - 13, height - 13), radius=14, outline=(*accent[:3], 190), width=3)


def _draw_cover_impact_burst(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    text_left: bool,
    accent: tuple[int, int, int, int],
    accent2: tuple[int, int, int, int],
) -> None:
    cx = int(width * (0.78 if text_left else 0.22))
    cy = int(height * 0.33)
    for index in range(18):
        angle = (index / 18.0) * pi * 2
        inner = 92 + (index % 3) * 16
        outer = 290 + (index % 4) * 22
        x1 = int(cx + cos(angle) * inner)
        y1 = int(cy + sin(angle) * inner)
        x2 = int(cx + cos(angle) * outer)
        y2 = int(cy + sin(angle) * outer)
        color = accent if index % 2 else accent2
        draw.line((x1, y1, x2, y2), fill=(*color[:3], 48), width=3)


def _premium_cover_accent(title: str) -> tuple[int, int, int, int]:
    text = (title or "").lower()
    if any(word in text for word in ("крипт", "crypto", "bitcoin", "битко")):
        return (255, 184, 45, 255)
    if any(word in text for word in ("подкаст", "story", "истор", "интерв")):
        return (66, 245, 142, 255)
    if any(word in text for word in ("драма", "шок", "лома", "разоблач", "секрет")):
        return (255, 66, 92, 255)
    return (255, 218, 58, 255)


def _premium_cover_secondary_accent(title: str) -> tuple[int, int, int, int]:
    accent = _premium_cover_accent(title)
    if accent[:3] == (255, 66, 92):
        return (255, 226, 96, 255)
    if accent[:3] == (66, 245, 142):
        return (76, 210, 255, 255)
    return (48, 226, 255, 255)


def _premium_cover_eyebrow(title: str) -> str:
    text = (title or "").lower()
    if any(word in text for word in ("подкаст", "podcast", "интерв")):
        return "PODCAST"
    if any(word in text for word in ("истор", "story")):
        return "REAL STORY"
    if any(word in text for word in ("секрет", "разбор", "ошиб", "лома")):
        return "MUST WATCH"
    return "TOP MOMENT"


def _premium_cover_hook(title: str, mood: str = "premium") -> str:
    text = (title or "").lower()
    cyrillic = re.search(r"[А-Яа-яЁёІіЇїЄєҐґ]", title or "")
    if any(word in text for word in ("secret", "секрет", "ошиб", "mistake", "разбор")):
        return "НЕ ПОВТОРЯЙ ЭТО" if cyrillic else "DON'T MISS THIS"
    if any(word in text for word in ("money", "crypto", "bitcoin", "деньги", "бизнес")):
        return "ГДЕ ДЕНЬГИ?" if cyrillic else "MONEY ANGLE"
    if mood == "urgent":
        return "СМОТРИ СЕЙЧАС" if cyrillic else "WATCH NOW"
    if mood == "clean":
        return "ГЛАВНАЯ МЫСЛЬ" if cyrillic else "KEY TAKEAWAY"
    return "СМОТРИ ДО КОНЦА" if cyrillic else "WATCH TO THE END"


def _draw_cover_text_shadow(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont) -> None:
    x, y = xy
    for offset, alpha in ((6, 82), (3, 132), (2, 178)):
        draw.text((x + offset, y + offset), text, fill=(0, 0, 0, alpha), font=font, stroke_width=4, stroke_fill=(0, 0, 0, alpha))


def _draw_premium_hook_badge(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    text_left: bool,
    accent: tuple[int, int, int, int],
    warm: tuple[int, int, int, int],
    title: str,
    text: str | None = None,
    x: int | None = None,
    y: int | None = None,
) -> None:
    font = _load_cover_font(24)
    text = text or ("СМОТРИ ДО КОНЦА" if re.search(r"[А-Яа-яЁёІіЇїЄєҐґ]", title or "") else "WATCH TO THE END")
    text = text or "WATCH TO THE END"
    text_w = _text_width(font, text)
    x = int(x if x is not None else (56 if text_left else width - text_w - 106))
    y = int(y if y is not None else height - 96)
    draw.rounded_rectangle((x, y, x + text_w + 42, y + 48), radius=7, fill=(0, 0, 0, 178), outline=(*accent[:3], 170), width=1)
    draw.rectangle((x, y, x + 10, y + 48), fill=warm)
    draw.text((x + 24, y + 11), text, fill=(255, 255, 255, 245), font=font)


def _draw_subtle_face_focus(draw: ImageDraw.ImageDraw, point: tuple[int, int], accent: tuple[int, int, int, int]) -> None:
    x, y = point
    radius = 82
    segment = 36
    for corner, horizontal, vertical in [
        ((x - radius, y - radius), (x - radius + segment, y - radius), (x - radius, y - radius + segment)),
        ((x + radius, y - radius), (x + radius - segment, y - radius), (x + radius, y - radius + segment)),
        ((x - radius, y + radius), (x - radius + segment, y + radius), (x - radius, y + radius - segment)),
        ((x + radius, y + radius), (x + radius - segment, y + radius), (x + radius, y + radius - segment)),
    ]:
        draw.line((corner, horizontal), fill=(0, 0, 0, 165), width=10)
        draw.line((corner, vertical), fill=(0, 0, 0, 165), width=10)
        draw.line((corner, horizontal), fill=(*accent[:3], 205), width=5)
        draw.line((corner, vertical), fill=(*accent[:3], 205), width=5)


def _load_cover_font(size: int) -> ImageFont.ImageFont:
    for name in _font_candidates("arialbd.ttf", "segoeuib.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(str(name), size)
        except OSError:
            continue
    return _load_font(size)


def _cover_copy(raw: str) -> CoverCopy:
    value = re.sub(r"https?://\S+", " ", raw or "")
    value = value.replace("\r", "\n")
    lines = [_strip_cover_copy_prefix(line) for line in value.splitlines()]
    lines = [re.sub(r"\s+", " ", line).strip(" -:;") for line in lines if line.strip()]
    if not lines:
        return CoverCopy("NEW VIDEO", "")
    headline = lines[0]
    description = " ".join(lines[1:]).strip()
    if not description and ":" in headline:
        head, _, tail = headline.partition(":")
        if len(head.strip()) >= 10 and len(tail.strip()) >= 6:
            headline = head.strip()
            description = tail.strip()
    if not description and len(headline) > 58:
        original = headline
        head, _, tail = original[:58].rpartition(" ")
        headline = head or headline[:58]
        description = " ".join(part for part in (tail, original[58:]) if part).strip()
    return CoverCopy(headline=headline, description=description)


def _strip_cover_copy_prefix(line: str) -> str:
    return re.sub(
        r"^\s*(title|headline|name|название|заголовок|описание|опис|назва|заголовок|опис)\s*[:=-]\s*",
        "",
        line.strip(),
        flags=re.IGNORECASE,
    )


def _cover_title_text(title: str) -> str:
    value = re.sub(r"\s+", " ", title or "").strip()
    value = re.sub(r"[|#]+", " ", value).strip()
    if len(value) > 60:
        value = value[:60].rsplit(" ", 1)[0] or value[:60]
    return value.upper() or "NEW VIDEO"


def _cover_description_text(description: str) -> str:
    value = re.sub(r"\s+", " ", description or "").strip()
    value = re.sub(r"[#|]+", " ", value).strip()
    if len(value) > 92:
        value = value[:92].rsplit(" ", 1)[0] or value[:92]
    return value


def _fit_cover_title(text: str, max_width: int, max_lines: int) -> tuple[ImageFont.ImageFont, list[str]]:
    fallback_lines: list[str] = []
    fallback_font = _load_cover_font(42)
    for size in (68, 62, 56, 50, 46, 42):
        font = _load_cover_font(size)
        lines = _wrap_cover_text(text, font, max_width=max_width, max_lines=max_lines)
        fallback_font, fallback_lines = font, lines
        total_height = len(lines) * (size + 7)
        if len(lines) <= max_lines and total_height <= 224 and all(_text_width(font, line) <= max_width for line in lines):
            return font, lines
    return fallback_font, fallback_lines or [text[:18]]


def _wrap_cover_text(text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and _text_width(font, candidate) > max_width:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
        else:
            current = candidate
    remaining = " ".join(words[len(" ".join(lines + ([current] if current else [])).split()):])
    if remaining and len(lines) >= max_lines - 1:
        current = f"{current} {remaining}".strip()
    if current:
        while _text_width(font, current) > max_width and len(current) > 12:
            current = current.rsplit(" ", 1)[0] if " " in current else current[:-1]
        lines.append(current)
    return lines[:max_lines] or [text[:18]]


def _text_width(font: ImageFont.ImageFont, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _render_intro_video(image: Path, output: Path, duration: int, timeout_seconds: int) -> None:
    fade_out_start = max(0.0, duration - 0.35)
    args = [
        ffmpeg_path(),
        "-y",
        "-loop",
        "1",
        "-i",
        str(image),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t",
        str(duration),
        "-vf",
        f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out_start:.2f}:d=0.35,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        VIDEO_QUALITY_PRESET,
        "-crf",
        PREVIEW_VIDEO_CRF,
        "-r",
        "30",
        "-c:a",
        "aac",
        "-shortest",
        str(output),
    ]
    _run_ffmpeg(args, timeout_seconds)


def _render_wide_segment(source: Path, output: Path, start: int, duration: int, timeout_seconds: int) -> None:
    vf = _wide_preview_filter(duration)
    af = f"afade=t=in:st=0:d=0.12,afade=t=out:st={max(0.2, duration - 0.22)}:d=0.22,{VIDEO_AUDIO_FILTER}"
    args = [
        ffmpeg_path(),
        "-y",
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-i",
        str(source),
        "-filter_complex",
        vf,
        "-af",
        af,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        VIDEO_QUALITY_PRESET,
        "-crf",
        PREVIEW_VIDEO_CRF,
        "-r",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output),
    ]
    try:
        _run_ffmpeg(args, timeout_seconds)
    except RuntimeError:
        no_audio_args = [
            ffmpeg_path(),
            "-y",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-i",
            str(source),
            "-f",
            "lavfi",
            "-t",
            str(duration),
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-filter_complex",
            vf,
            "-map",
            "[vout]",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            VIDEO_QUALITY_PRESET,
            "-crf",
            PREVIEW_VIDEO_CRF,
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
        _run_ffmpeg(no_audio_args, timeout_seconds)


def _wide_preview_filter(duration: int) -> str:
    fade_out_start = max(0.2, duration - 0.22)
    return (
        "[0:v]scale=1280:720:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=1280:720,gblur=sigma=18,eq=brightness=-0.08:saturation=0.85[bg];"
        "[0:v]scale=1280:720:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        "fade=t=in:st=0:d=0.18,"
        f"fade=t=out:st={fade_out_start}:d=0.22,"
        "format=yuv420p[vout]"
    )


def _concat_videos(parts: list[Path], output: Path, timeout_seconds: int) -> None:
    if len(parts) > 1:
        try:
            _concat_videos_with_transitions(parts, output, timeout_seconds)
            return
        except RuntimeError:
            pass

    list_path = output.with_suffix(".txt")
    list_path.write_text(
        "\n".join(f"file '{part.resolve().as_posix()}'" for part in parts),
        encoding="utf-8",
    )
    args = [
        ffmpeg_path(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output),
    ]
    try:
        _run_ffmpeg(args, timeout_seconds)
    finally:
        list_path.unlink(missing_ok=True)


def _concat_videos_with_transitions(parts: list[Path], output: Path, timeout_seconds: int) -> None:
    transition = 0.28
    durations = [max(transition + 0.1, inspect_video(part).duration_seconds or 0) for part in parts]
    args = [ffmpeg_path(), "-y"]
    for part in parts:
        args.extend(["-i", str(part)])

    filters: list[str] = []
    for index in range(len(parts)):
        filters.append(f"[{index}:v]setpts=PTS-STARTPTS,format=yuv420p[v{index}]")
        filters.append(f"[{index}:a]asetpts=PTS-STARTPTS,aresample=48000[a{index}]")

    video_label = "v0"
    audio_label = "a0"
    elapsed = durations[0]
    for index in range(1, len(parts)):
        next_video = f"vx{index}"
        next_audio = f"ax{index}"
        offset = max(0.1, elapsed - transition)
        filters.append(
            f"[{video_label}][v{index}]xfade=transition=fade:duration={transition}:offset={offset:.3f}[{next_video}]"
        )
        filters.append(f"[{audio_label}][a{index}]acrossfade=d={transition}:c1=tri:c2=tri[{next_audio}]")
        video_label = next_video
        audio_label = next_audio
        elapsed += durations[index] - transition

    args.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{video_label}]",
            "-map",
            f"[{audio_label}]",
            "-c:v",
            "libx264",
            "-preset",
            VIDEO_QUALITY_PRESET,
            "-crf",
            PREVIEW_VIDEO_CRF,
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run_ffmpeg(args, timeout_seconds)


def _run_ffmpeg(args: list[str], timeout_seconds: int) -> None:
    completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout_seconds)
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1:] or ["FFmpeg failed"]
        raise RuntimeError(detail[0])


def _youtube_options(output_dir: Path, timeout_seconds: int) -> dict:
    return {
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "format": "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/bv*[height<=1080]+ba/b[ext=mp4][height<=1080]/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_path(),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": timeout_seconds,
        "retries": 3,
        "fragment_retries": 3,
    }


def _estimate_download_size(info: dict) -> int | None:
    direct = info.get("filesize") or info.get("filesize_approx")
    if direct:
        return int(direct)

    formats = info.get("formats") or []
    best_video = 0
    best_audio = 0
    for item in formats:
        size = item.get("filesize") or item.get("filesize_approx") or 0
        if not size:
            continue
        height = item.get("height") or 0
        vcodec = item.get("vcodec")
        acodec = item.get("acodec")
        if vcodec and vcodec != "none" and height <= 1080:
            best_video = max(best_video, int(size))
        if acodec and acodec != "none" and (not vcodec or vcodec == "none"):
            best_audio = max(best_audio, int(size))
    total = best_video + best_audio
    return total or None


def build_vertical_filter(
    source: Path,
    start_seconds: int,
    clip_seconds: int,
    width: int | None,
    height: int | None,
    focus_mode: str,
    face_detection_enabled: bool,
) -> str:
    if not width or not height:
        return "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1"

    face_track: list[FaceTrackPoint] = []
    if focus_mode == "face" and face_detection_enabled:
        face_track = detect_face_track(source, start_seconds, clip_seconds)

    if not face_track:
        return "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1"

    target_ratio = 9 / 16
    source_ratio = width / height
    if source_ratio > target_ratio:
        crop_h = height
        crop_w = int(height * target_ratio)
        crop_x_expr = _ffmpeg_dynamic_crop_expr(_face_safe_crop_positions(face_track, crop_w, width, axis="x"), width - crop_w)
        return f"crop={crop_w}:{crop_h}:x='{crop_x_expr}':y=0,scale=1080:1920:flags=lanczos,setsar=1"
    else:
        crop_w = width
        crop_h = int(width / target_ratio)
        crop_y_expr = _ffmpeg_dynamic_crop_expr(_face_safe_crop_positions(face_track, crop_h, height, axis="y"), height - crop_h)
        return f"crop={crop_w}:{crop_h}:x=0:y='{crop_y_expr}',scale=1080:1920:flags=lanczos,setsar=1"

    return "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1"


def detect_face_center(source: Path, start_seconds: int, clip_seconds: int = 10) -> tuple[int, int] | None:
    focus = detect_face_focus(source, start_seconds, clip_seconds)
    if not focus:
        return None
    return focus.x, focus.y


def detect_face_focus(source: Path, start_seconds: int, clip_seconds: int = 10) -> FaceFocus | None:
    track = detect_face_track(source, start_seconds, clip_seconds)
    if not track:
        return None
    weighted_x = sum(point.x * point.confidence for point in track)
    weighted_y = sum(point.y * point.confidence for point in track)
    total_weight = sum(point.confidence for point in track)
    if total_weight <= 0:
        return None
    confidence = min(1.0, len(track) / max(1, len(_focus_sample_offsets(max(1, clip_seconds)))) + total_weight / max(1, len(track)) * 0.18)
    if confidence < 0.28:
        return None
    return FaceFocus(int(weighted_x / total_weight), int(weighted_y / total_weight), confidence)


def detect_face_track(source: Path, start_seconds: int, clip_seconds: int = 10) -> list[FaceTrackPoint]:
    native_points = native_tools.face_track_points(source, start_seconds, clip_seconds)
    if native_points:
        points: list[FaceTrackPoint] = []
        for item in native_points:
            try:
                points.append(
                    FaceTrackPoint(
                        second=float(item.get("second", 0)),
                        x=int(item["x"]),
                        y=int(item["y"]),
                        width=int(item.get("width", 1)),
                        height=int(item.get("height", 1)),
                        confidence=float(item.get("confidence", 0.5)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if points:
            return points

    frontal = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    profile = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml"))
    detectors = [detector for detector in (frontal, profile) if not detector.empty()]
    if not detectors:
        return []

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return []
    try:
        offsets = _focus_sample_offsets(max(1, clip_seconds))
        candidates: list[FaceTrackPoint] = []
        for offset in offsets:
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0, start_seconds + offset) * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            faces = _detect_frame_faces(frame, detectors)
            if not faces:
                continue
            x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
            face_area = w * h
            frame_area = max(1, frame.shape[0] * frame.shape[1])
            if face_area / frame_area < 0.002:
                continue
            candidates.append(
                FaceTrackPoint(
                    second=float(offset),
                    x=int(x + w / 2),
                    y=int(y + h / 2),
                    width=int(w),
                    height=int(h),
                    confidence=min(1.0, max(0.08, face_area / frame_area * 18.0)),
                )
            )
        if not candidates:
            return []
        return _smooth_face_track(_keep_face_track_cluster(candidates))
    finally:
        capture.release()
    return []


def _detect_frame_faces(
    frame: np.ndarray,
    detectors: list[cv2.CascadeClassifier],
) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces: list[tuple[int, int, int, int]] = []
    for detector in detectors:
        faces.extend(tuple(map(int, face)) for face in detector.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(42, 42)))
        flipped = cv2.flip(gray, 1)
        frame_width = gray.shape[1]
        for fx, fy, fw, fh in detector.detectMultiScale(flipped, scaleFactor=1.08, minNeighbors=4, minSize=(42, 42)):
            faces.append((int(frame_width - fx - fw), int(fy), int(fw), int(fh)))
    return faces


def _keep_face_track_cluster(points: list[FaceTrackPoint]) -> list[FaceTrackPoint]:
    if len(points) <= 2:
        return points
    xs = sorted(point.x for point in points)
    ys = sorted(point.y for point in points)
    median_x = xs[len(xs) // 2]
    median_y = ys[len(ys) // 2]
    distances = [
        (abs(point.x - median_x) + abs(point.y - median_y), point)
        for point in points
    ]
    distances.sort(key=lambda item: item[0])
    keep_count = max(2, int(round(len(points) * 0.82)))
    return sorted((point for _distance, point in distances[:keep_count]), key=lambda point: point.second)


def _smooth_face_track(points: list[FaceTrackPoint]) -> list[FaceTrackPoint]:
    if len(points) < 3:
        return points
    smoothed: list[FaceTrackPoint] = []
    for index, point in enumerate(points):
        neighbors = points[max(0, index - 1) : min(len(points), index + 2)]
        total = sum(item.confidence for item in neighbors) or 1.0
        smoothed.append(
            FaceTrackPoint(
                second=point.second,
                x=int(sum(item.x * item.confidence for item in neighbors) / total),
                y=int(sum(item.y * item.confidence for item in neighbors) / total),
                width=int(sum(item.width * item.confidence for item in neighbors) / total),
                height=int(sum(item.height * item.confidence for item in neighbors) / total),
                confidence=point.confidence,
            )
        )
    return smoothed


def _face_safe_crop_positions(points: list[FaceTrackPoint], crop_size: int, source_size: int, axis: str) -> list[tuple[float, int]]:
    max_offset = max(0, source_size - crop_size)
    positions: list[tuple[float, int]] = []
    for point in points:
        center = point.x if axis == "x" else point.y
        face_size = point.width if axis == "x" else point.height
        face_start = center - face_size / 2
        face_end = center + face_size / 2
        if axis == "x":
            padding = max(18, int(face_size * 0.62), int(crop_size * 0.08))
            desired = center - crop_size * 0.50
        else:
            padding = max(22, int(face_size * 0.72), int(crop_size * 0.10))
            desired = center - crop_size * 0.42
        lower = face_end + padding - crop_size
        upper = face_start - padding
        if lower <= upper:
            offset = min(max(desired, lower), upper)
        else:
            offset = center - crop_size * (0.50 if axis == "x" else 0.42)
        positions.append((point.second, clamp(int(round(offset)), 0, max_offset)))
    if not positions:
        return []
    return _limit_crop_motion(positions, max_step=max(24, crop_size // 22))


def _limit_crop_motion(positions: list[tuple[float, int]], max_step: int) -> list[tuple[float, int]]:
    limited: list[tuple[float, int]] = []
    previous: int | None = None
    for second, offset in positions:
        if previous is not None:
            offset = clamp(offset, previous - max_step, previous + max_step)
        limited.append((second, offset))
        previous = offset
    return limited


def _ffmpeg_dynamic_crop_expr(positions: list[tuple[float, int]], max_offset: int) -> str:
    if not positions:
        return "0"
    positions = [(max(0.0, float(second)), clamp(int(offset), 0, max_offset)) for second, offset in positions]
    if len(positions) == 1:
        return str(positions[0][1])

    expression = str(positions[-1][1])
    for (start_t, start_x), (end_t, end_x) in reversed(list(zip(positions, positions[1:]))):
        if end_t <= start_t:
            value = str(end_x)
        else:
            progress = f"((t-{start_t:.3f})/{(end_t - start_t):.3f})"
            value = f"({start_x}+({end_x - start_x})*{progress})"
        expression = f"if(lt(t\\,{end_t:.3f})\\,{value}\\,{expression})"
    return expression


def _keep_face_cluster(candidates: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    if len(candidates) <= 2:
        return candidates
    xs = sorted(x for x, _y, _weight in candidates)
    ys = sorted(y for _x, y, _weight in candidates)
    median_x = xs[len(xs) // 2]
    median_y = ys[len(ys) // 2]
    distances = [
        (abs(x - median_x) + abs(y - median_y), (x, y, weight))
        for x, y, weight in candidates
    ]
    distances.sort(key=lambda item: item[0])
    keep_count = max(2, int(round(len(candidates) * 0.75)))
    return [item for _distance, item in distances[:keep_count]]


def _focus_sample_offsets(clip_seconds: int) -> list[int]:
    if clip_seconds <= 8:
        return [0, max(0, clip_seconds // 2)]
    count = min(7, max(3, clip_seconds // 8))
    if count == 1:
        return [0]
    return sorted({int(round(i * (clip_seconds - 1) / (count - 1))) for i in range(count)})


def calculate_backstage_clip_starts(
    source: Path,
    duration_seconds: float,
    max_clips: int,
    clip_seconds: int,
    sample_limit: int = 420,
    min_gap_seconds: int = 90,
    face_detection_enabled: bool = True,
) -> list[int]:
    duration = int(duration_seconds)
    if duration < 10:
        return []
    base_starts = calculate_clip_starts(duration_seconds, max_clips, clip_seconds)
    if duration <= max_clips * clip_seconds:
        return base_starts

    sample_limit = max(60, min(1200, sample_limit))
    step = max(5, int(duration / sample_limit))
    min_gap = max(clip_seconds, min_gap_seconds)
    scores = _score_video_moments(source, duration, step, face_detection_enabled)
    ranked_starts = _rank_clip_windows(scores, duration, clip_seconds, step, lead_seconds=max(1, clip_seconds // 3))
    selected = _select_diverse_ranked_starts(ranked_starts, max_clips, min_gap, duration, clip_seconds)

    if len(selected) < max_clips:
        for start in base_starts:
            if all(abs(start - existing) >= clip_seconds for existing in selected):
                selected.append(start)
            if len(selected) >= max_clips:
                break

    return sorted(selected[:max_clips])


def _score_video_moments(
    source: Path,
    duration_seconds: int,
    step_seconds: int,
    face_detection_enabled: bool,
) -> list[tuple[int, float]]:
    native_visual = native_tools.visual_moment_scores(source, duration_seconds, step_seconds)
    if native_visual:
        if face_detection_enabled:
            native_visual = _add_python_face_scores(source, native_visual)
        audio_scores = _score_audio_moments(source, duration_seconds, step_seconds)
        return _smooth_scores(_combine_moment_scores(_smooth_scores(native_visual, step_seconds), audio_scores), step_seconds)

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return []

    frontal = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    profile = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml"))
    detectors = [detector for detector in (frontal, profile) if not detector.empty()]
    previous_small = None
    previous_hist = None
    previous_motion_score = 0.0
    scores: list[tuple[int, float]] = []
    try:
        for second in range(0, max(1, duration_seconds - 2), step_seconds):
            capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            small = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            motion_score = 0.0
            if previous_small is not None:
                diff = cv2.absdiff(gray, previous_small)
                motion_score = float(diff.mean())
            previous_small = gray
            motion_rise_score = min(10.0, max(0.0, motion_score - previous_motion_score) * 0.9)
            previous_motion_score = motion_score
            hist = cv2.calcHist([small], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist, hist)
            scene_score = 0.0
            if previous_hist is not None:
                scene_score = min(22.0, max(0.0, cv2.compareHist(previous_hist, hist, cv2.HISTCMP_BHATTACHARYYA)) * 36.0)
            previous_hist = hist
            sharpness_score = min(12.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 90.0)
            visual_interest_score = _visual_frame_interest_score(small, gray)

            face_score = 0.0
            if face_detection_enabled and detectors:
                full_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                full_gray = cv2.equalizeHist(full_gray)
                faces: list[tuple[int, int, int, int]] = []
                for detector in detectors:
                    faces.extend(detector.detectMultiScale(full_gray, scaleFactor=1.08, minNeighbors=4, minSize=(42, 42)))
                    flipped = cv2.flip(full_gray, 1)
                    frame_width = full_gray.shape[1]
                    for fx, fy, fw, fh in detector.detectMultiScale(
                        flipped, scaleFactor=1.08, minNeighbors=4, minSize=(42, 42)
                    ):
                        faces.append((frame_width - fx - fw, fy, fw, fh))
                if len(faces):
                    largest = max((w * h for _x, _y, w, h in faces), default=0)
                    face_score = min(58.0, 14.0 * len(faces) + largest / max(1, frame.shape[0] * frame.shape[1]) * 150.0)

            # Prefer moments with visible people and some visual change, but avoid pure random noise dominating.
            score = (
                min(32.0, motion_score)
                + motion_rise_score
                + scene_score
                + sharpness_score
                + visual_interest_score
                + face_score
            )
            if score > 0:
                scores.append((second, score))
    finally:
        capture.release()
    visual_scores = _smooth_scores(scores, step_seconds)
    audio_scores = _score_audio_moments(source, duration_seconds, step_seconds)
    return _smooth_scores(_combine_moment_scores(visual_scores, audio_scores), step_seconds)


def _add_python_face_scores(source: Path, visual_scores: list[tuple[int, float]]) -> list[tuple[int, float]]:
    if not visual_scores:
        return visual_scores
    frontal = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    profile = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml"))
    detectors = [detector for detector in (frontal, profile) if not detector.empty()]
    if not detectors:
        return visual_scores

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return visual_scores
    boosted: list[tuple[int, float]] = []
    try:
        for second, score in visual_scores:
            capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
            ok, frame = capture.read()
            if not ok:
                boosted.append((second, score))
                continue
            faces = _detect_frame_faces(frame, detectors)
            face_score = 0.0
            if faces:
                largest = max((w * h for _x, _y, w, h in faces), default=0)
                face_score = min(58.0, 14.0 * len(faces) + largest / max(1, frame.shape[0] * frame.shape[1]) * 150.0)
            boosted.append((second, score + face_score))
    finally:
        capture.release()
    return boosted


def _combine_moment_scores(
    visual_scores: list[tuple[int, float]],
    audio_scores: list[tuple[int, float]],
) -> list[tuple[int, float]]:
    combined: dict[int, float] = {}
    for second, score in visual_scores:
        combined[second] = combined.get(second, 0.0) + score
    for second, score in audio_scores:
        combined[second] = combined.get(second, 0.0) + score * 0.85
    return sorted((second, score) for second, score in combined.items() if score > 0)


def _rank_clip_windows(
    scores: list[tuple[int, float]],
    duration_seconds: int,
    clip_seconds: int,
    step_seconds: int,
    lead_seconds: int,
) -> list[tuple[int, float]]:
    if not scores:
        return []

    max_start = max(0, duration_seconds - clip_seconds)
    step_seconds = max(1, step_seconds)
    clip_seconds = max(1, clip_seconds)
    lead_seconds = max(0, min(clip_seconds // 2, lead_seconds))

    by_second = {int(second): max(0.0, float(score)) for second, score in scores if score > 0}
    peak_candidates = _local_peak_seconds(scores, step_seconds)
    candidate_starts = {
        clamp(second - lead_seconds, 0, max_start)
        for second in peak_candidates
    }
    candidate_starts.update(
        clamp(second - lead_seconds, 0, max_start)
        for second, _score in sorted(scores, key=lambda item: item[1], reverse=True)[: max(8, len(scores) // 3)]
    )

    ranked: list[tuple[int, float]] = []
    for start in sorted(candidate_starts):
        window_values = [
            score
            for second, score in by_second.items()
            if start <= second < start + clip_seconds
        ]
        if not window_values:
            continue
        total = sum(window_values)
        peak = max(window_values)
        average = total / len(window_values)
        ordered_values = sorted(window_values)
        upper_mid = ordered_values[int((len(ordered_values) - 1) * 0.65)]
        strong_threshold = max(average * 1.08, peak * 0.48)
        strong_ratio = sum(1 for score in window_values if score >= strong_threshold) / max(1, len(window_values))
        coverage = len(window_values) / max(1, min(clip_seconds, duration_seconds) / step_seconds)
        center = start + clip_seconds / 2
        center_bonus = 1.0 - min(1.0, abs(max(by_second, key=lambda sec: by_second[sec] if start <= sec < start + clip_seconds else -1) - center) / max(1.0, clip_seconds / 2))
        edge_penalty = _timeline_edge_penalty(start, duration_seconds, clip_seconds)
        isolated_peak_penalty = 0.72 if peak > max(1.0, upper_mid) * 2.8 and strong_ratio < 0.34 else 1.0
        sustained_bonus = 1.0 + min(0.34, strong_ratio * 0.42)
        score = (
            total * 0.78
            + peak * 0.34
            + average * 0.75
            + upper_mid * 0.42
            + coverage * 24.0
            + center_bonus * 7.0
        ) * edge_penalty * isolated_peak_penalty * sustained_bonus
        ranked.append((start, score))

    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def _clip_candidate_dicts(
    ranked_starts: list[tuple[int, float]],
    scores: list[tuple[int, float]],
    duration_seconds: int,
    clip_seconds: int,
    step_seconds: int,
) -> list[dict[str, object]]:
    if not ranked_starts:
        return []
    by_second = {int(second): max(0.0, float(score)) for second, score in scores if score > 0}
    max_score = max((score for _start, score in ranked_starts), default=1.0) or 1.0
    candidates: list[dict[str, object]] = []
    for start, raw_score in ranked_starts:
        window_values = [
            score
            for second, score in by_second.items()
            if start <= second < start + clip_seconds
        ]
        if not window_values:
            continue
        peak_second = max(
            (second for second in by_second if start <= second < start + clip_seconds),
            key=lambda second: by_second[second],
            default=start,
        )
        candidates.append(
            {
                "start": int(start),
                "score": round(float(raw_score) / max_score * 100.0, 3),
                "peak_second": int(peak_second),
                "peak_score": round(max(window_values), 3),
                "avg_score": round(sum(window_values) / len(window_values), 3),
                "coverage": round(len(window_values) / max(1, min(clip_seconds, duration_seconds) / max(1, step_seconds)), 3),
                "position": round((start + clip_seconds / 2) / max(1, duration_seconds), 3),
                "source": "local",
            }
        )
    return candidates


def _select_diverse_ranked_starts(
    ranked_starts: list[tuple[int, float]],
    max_clips: int,
    min_gap_seconds: int,
    duration_seconds: int,
    clip_seconds: int,
) -> list[int]:
    if max_clips <= 0 or not ranked_starts:
        return []

    bucket_count = max(3, min(8, max_clips + 2))
    selected: list[int] = []
    bucket_hits: dict[int, int] = {}
    candidates = [(int(start), max(0.0, float(score))) for start, score in ranked_starts if score > 0]

    while len(selected) < max_clips:
        best: tuple[int, float] | None = None
        for start, score in candidates:
            if start in selected:
                continue
            nearest_gap = min((abs(start - existing) for existing in selected), default=10**9)
            if nearest_gap < min_gap_seconds:
                continue
            center = start + clip_seconds / 2
            bucket = min(bucket_count - 1, max(0, int(center / max(1, duration_seconds) * bucket_count)))
            bucket_penalty = 0.72 ** bucket_hits.get(bucket, 0)
            proximity_penalty = 0.82 if nearest_gap < min_gap_seconds * 1.8 else 1.0
            edge_penalty = _timeline_edge_penalty(start, duration_seconds, clip_seconds)
            adjusted = score * bucket_penalty * proximity_penalty * edge_penalty
            if best is None or adjusted > best[1]:
                best = (start, adjusted)
        if best is None:
            break
        selected.append(best[0])
        center = best[0] + clip_seconds / 2
        bucket = min(bucket_count - 1, max(0, int(center / max(1, duration_seconds) * bucket_count)))
        bucket_hits[bucket] = bucket_hits.get(bucket, 0) + 1
    return selected


def _timeline_edge_penalty(start: int, duration_seconds: int, clip_seconds: int) -> float:
    if duration_seconds <= clip_seconds * 2:
        return 1.0

    center = start + clip_seconds / 2
    intro_zone = min(max(12.0, duration_seconds * 0.035), 45.0)
    outro_zone = min(max(12.0, duration_seconds * 0.035), 50.0)
    if center < intro_zone:
        return 0.76 + 0.20 * (center / max(1.0, intro_zone))
    outro_start = duration_seconds - outro_zone
    if center > outro_start:
        return 0.76 + 0.20 * ((duration_seconds - center) / max(1.0, outro_zone))
    return 1.0


def _visual_frame_interest_score(small_frame: np.ndarray, gray: np.ndarray) -> float:
    brightness = float(gray.mean())
    contrast = float(gray.std())
    hsv = cv2.cvtColor(small_frame, cv2.COLOR_BGR2HSV)
    saturation = float(hsv[:, :, 1].mean())

    exposure_balance = max(0.0, 1.0 - abs(brightness - 118.0) / 118.0)
    contrast_score = min(10.0, contrast / 6.0)
    saturation_score = min(8.0, saturation / 22.0)
    exposure_score = exposure_balance * 6.0
    dull_penalty = 5.0 if contrast < 9.0 and saturation < 18.0 else 0.0
    blown_penalty = 4.0 if brightness < 18.0 or brightness > 238.0 else 0.0
    return max(0.0, contrast_score + saturation_score + exposure_score - dull_penalty - blown_penalty)


def _local_peak_seconds(scores: list[tuple[int, float]], step_seconds: int) -> list[int]:
    if not scores:
        return []
    ordered = sorted((int(second), float(score)) for second, score in scores)
    by_second = dict(ordered)
    peaks: list[tuple[int, float]] = []
    for second, score in ordered:
        prev_score = by_second.get(second - step_seconds, -1.0)
        next_score = by_second.get(second + step_seconds, -1.0)
        if score >= prev_score and score >= next_score:
            peaks.append((second, score))
    if not peaks:
        peaks = ordered
    return [second for second, _score in sorted(peaks, key=lambda item: item[1], reverse=True)]


def _score_audio_moments(source: Path, duration_seconds: int, step_seconds: int) -> list[tuple[int, float]]:
    window_seconds = 0.5 if duration_seconds <= 3600 else 1.0
    windows = _read_audio_rms_windows(source, 0, max(1, duration_seconds), window_seconds=window_seconds)
    if not windows:
        return []

    rms_values = sorted(rms for _second, rms in windows)
    if not rms_values:
        return []
    median = rms_values[len(rms_values) // 2]
    high = rms_values[int(len(rms_values) * 0.78)]
    low = rms_values[int(len(rms_values) * 0.28)]
    speech_threshold = max(95, min(max(median * 0.72, low * 1.25), 420))
    accent_threshold = max(high, median * 1.35, speech_threshold * 1.55)

    scores: list[tuple[int, float]] = []
    by_index = {round(second / window_seconds): rms for second, rms in windows}
    max_index = max(by_index) if by_index else 0
    for second in range(0, max(1, duration_seconds - 1), max(1, step_seconds)):
        center_index = round(second / window_seconds)
        before = [by_index.get(index, 0) for index in range(max(0, center_index - 5), center_index)]
        current = [by_index.get(index, 0) for index in range(center_index, min(max_index + 1, center_index + 7))]
        after = [by_index.get(index, 0) for index in range(center_index + 7, min(max_index + 1, center_index + 13))]
        if not current:
            continue
        peak = max(current)
        avg = sum(current) / len(current)
        active_ratio = sum(1 for value in current if value >= speech_threshold) / len(current)
        before_min = min(before) if before else median
        before_avg = sum(before) / len(before) if before else median
        after_min = min(after) if after else median

        loudness_score = min(28.0, avg / max(1.0, median) * 8.0)
        accent_score = min(28.0, max(0.0, peak - before_avg) / max(1.0, median) * 10.0)
        phrase_start_bonus = 20.0 if before_min <= speech_threshold * 0.72 and peak >= accent_threshold * 0.82 else 0.0
        active_score = active_ratio * 16.0
        ending_pause_bonus = 7.0 if after_min <= speech_threshold * 0.75 else 0.0
        silence_penalty = 26.0 if active_ratio < 0.25 and peak < accent_threshold else 0.0
        score = max(0.0, loudness_score + accent_score + phrase_start_bonus + active_score + ending_pause_bonus - silence_penalty)
        if score:
            scores.append((second, score))
    return scores


def _find_nearby_audio_pause(
    source: Path,
    target_second: int,
    before_seconds: float,
    after_seconds: float,
) -> float | None:
    start = max(0.0, target_second - before_seconds)
    duration = max(0.5, before_seconds + after_seconds)
    windows = _read_audio_rms_windows(source, start, duration, window_seconds=0.25)
    if not windows:
        return None

    rms_values = sorted(rms for _second, rms in windows)
    median = rms_values[len(rms_values) // 2]
    if median <= 0:
        return None

    best_second, best_rms = min(
        windows,
        key=lambda item: (item[1] / median) * 0.72 + (abs(item[0] - target_second) / duration) * 0.28,
    )
    if best_rms > max(150, median * 0.82):
        return None
    return best_second


def _find_phrase_start_near(
    source: Path,
    target_second: int,
    before_seconds: float,
    after_seconds: float,
) -> float | None:
    start = max(0.0, target_second - before_seconds)
    duration = max(1.0, before_seconds + after_seconds)
    windows = _read_audio_rms_windows(source, start, duration, window_seconds=0.25)
    if len(windows) < 4:
        return None

    rms_values = sorted(rms for _second, rms in windows)
    median = rms_values[len(rms_values) // 2]
    if median <= 0:
        return None
    low_threshold = max(70, min(220, median * 0.62))
    speech_threshold = max(110, median * 0.86)
    candidates: list[tuple[float, float]] = []

    for index, (second, rms) in enumerate(windows[:-2]):
        if second > target_second + after_seconds:
            break
        if rms > low_threshold:
            continue
        follow = windows[index + 1 : min(len(windows), index + 8)]
        onset = next((item for item in follow if item[1] >= speech_threshold), None)
        if not onset:
            continue
        candidate_second = max(0.0, onset[0] - 0.18)
        if candidate_second > target_second + after_seconds:
            continue
        rise = onset[1] / max(1.0, rms)
        distance = abs(candidate_second - target_second)
        score = distance * 1.0 - min(3.0, rise) * 0.45
        candidates.append((score, candidate_second))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _read_audio_rms_windows(
    source: Path,
    start_seconds: float,
    duration_seconds: float,
    window_seconds: float,
) -> list[tuple[float, int]]:
    native_windows = native_tools.audio_rms_windows(source, start_seconds, duration_seconds, window_seconds)
    if native_windows:
        return native_windows
    return _read_audio_rms_windows_python(source, start_seconds, duration_seconds, window_seconds)


def _read_audio_rms_windows_python(
    source: Path,
    start_seconds: float,
    duration_seconds: float,
    window_seconds: float,
) -> list[tuple[float, int]]:
    sample_rate = 8000
    samples_per_window = max(1, int(sample_rate * window_seconds))
    chunk_size = samples_per_window * 2
    try:
        process = subprocess.Popen(native_tools.audio_pcm_args(source, start_seconds, duration_seconds, sample_rate), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception:
        return []
    if not process.stdout:
        process.kill()
        return []

    windows: list[tuple[float, int]] = []
    try:
        index = 0
        while True:
            raw = process.stdout.read(chunk_size)
            if len(raw) < chunk_size // 2:
                break
            windows.append((start_seconds + index * window_seconds, audioop.rms(raw, 2)))
            index += 1
    except Exception:
        return windows
    finally:
        if process.poll() is None:
            process.kill()
        try:
            process.stderr.read()
        except Exception:
            pass
    return windows


def _smooth_scores(scores: list[tuple[int, float]], step_seconds: int) -> list[tuple[int, float]]:
    if len(scores) < 3:
        return scores
    by_second = dict(scores)
    smoothed: list[tuple[int, float]] = []
    for second, score in scores:
        prev_score = by_second.get(second - step_seconds, score)
        next_score = by_second.get(second + step_seconds, score)
        smoothed.append((second, score * 0.6 + prev_score * 0.2 + next_score * 0.2))
    return smoothed


def clamp(value: int, minimum: int, maximum: int) -> int:
    if maximum < minimum:
        return minimum
    return max(minimum, min(value, maximum))


def calculate_clip_starts(duration_seconds: float, max_clips: int, clip_seconds: int) -> list[int]:
    duration = int(duration_seconds)
    if duration < 10:
        return []
    max_clips = max(1, max_clips)
    clip_seconds = max(10, min(60, clip_seconds))
    sequential_count = min(max_clips, ceil(duration / clip_seconds))

    if duration <= max_clips * clip_seconds:
        return [i * clip_seconds for i in range(sequential_count) if i * clip_seconds < duration - 5]

    last_start = max(0, duration - clip_seconds)
    if max_clips == 1:
        return [0]
    step = last_start / (max_clips - 1)
    return sorted({int(round(i * step)) for i in range(max_clips)})


def zip_clips(clips: list[ShortClip], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for clip in clips:
            archive.write(clip.path, clip.path.name)
    return output_path


def describe_clips(clips: list[ShortClip]) -> str:
    parts = []
    for index, clip in enumerate(clips, start=1):
        parts.append(f"{index:02d}: {format_duration(clip.start_seconds)}")
    return ", ".join(parts)


def _resolve_downloaded_path(info: dict, output_dir: Path) -> Path:
    requested = info.get("requested_downloads") or []
    for item in requested:
        filepath = item.get("filepath")
        if filepath and Path(filepath).exists():
            return Path(filepath)

    filename = info.get("_filename")
    if filename and Path(filename).exists():
        return Path(filename)

    video_id = info.get("id")
    if video_id:
        candidates = sorted(output_dir.glob(f"{video_id}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            return candidates[0]

    candidates = sorted(output_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    raise RuntimeError("Скачанный файл не найден")
