from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess

import imageio_ffmpeg

from .image_tools import clean_base_name


VIDEO_FORMATS = ["mp4", "webm", "gif"]
VIDEO_SCALE_EVEN_FILTER = "scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos,setsar=1"
VIDEO_AUDIO_FILTER = "loudnorm=I=-16:LRA=11:TP=-1.5"


@dataclass(frozen=True)
class VideoInfo:
    width: int | None
    height: int | None
    duration_seconds: float | None
    size_bytes: int


@dataclass(frozen=True)
class VideoResult:
    path: Path
    source: VideoInfo
    output: VideoInfo


def ffmpeg_path() -> str:
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg_available() -> bool:
    try:
        return bool(ffmpeg_path())
    except Exception:
        return False


def inspect_video(path: Path) -> VideoInfo:
    completed = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    width, height = _parse_resolution(output)
    duration = _parse_duration(output)
    return VideoInfo(width=width, height=height, duration_seconds=duration, size_bytes=path.stat().st_size)


def convert_video(
    source: Path,
    output_dir: Path,
    target_format: str,
    output_base_name: str,
    timeout_seconds: int = 180,
) -> VideoResult:
    target_format = target_format.lower()
    if target_format not in VIDEO_FORMATS:
        raise ValueError("Unsupported video format")

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{clean_base_name(output_base_name)}.{target_format}"
    source_info = inspect_video(source)
    audio_args = ["-af", VIDEO_AUDIO_FILTER] if _has_audio_stream(source) else []

    if target_format == "mp4":
        args = [
            ffmpeg_path(),
            "-y",
            "-i",
            str(source),
            "-vf",
            VIDEO_SCALE_EVEN_FILTER,
            *audio_args,
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "21",
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
    elif target_format == "webm":
        args = [
            ffmpeg_path(),
            "-y",
            "-i",
            str(source),
            "-vf",
            VIDEO_SCALE_EVEN_FILTER,
            *audio_args,
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libvpx-vp9",
            "-deadline",
            "good",
            "-cpu-used",
            "4",
            "-crf",
            "32",
            "-b:v",
            "0",
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(output),
        ]
    else:
        args = [
            ffmpeg_path(),
            "-y",
            "-i",
            str(source),
            "-vf",
            "fps=15,scale='min(720,iw)':-2:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a",
            "-loop",
            "0",
            str(output),
        ]

    completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout_seconds)
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1:] or ["FFmpeg conversion failed"]
        raise RuntimeError(detail[0])

    return VideoResult(path=output, source=source_info, output=inspect_video(output))


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _parse_duration(output: str) -> float | None:
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _parse_resolution(output: str) -> tuple[int | None, int | None]:
    match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", output)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _has_audio_stream(path: Path) -> bool:
    try:
        completed = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return False
    return "Audio:" in f"{completed.stdout}\n{completed.stderr}"


def has_audio_stream(path: Path) -> bool:
    return _has_audio_stream(path)
