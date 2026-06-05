from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
from typing import Any

from .video_tools import ffmpeg_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NATIVE_ROOT = PROJECT_ROOT / "native"
NATIVE_BIN = NATIVE_ROOT / "bin"
EXE_SUFFIX = ".exe" if os.name == "nt" else ""


def helper_path(name: str) -> Path:
    return NATIVE_BIN / f"{name}{EXE_SUFFIX}"


def capabilities() -> dict[str, object]:
    path = NATIVE_ROOT / "capabilities.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def helper_available(name: str) -> bool:
    return helper_path(name).exists()


def audio_rms_windows(
    source: Path,
    start_seconds: float,
    duration_seconds: float,
    window_seconds: float,
) -> list[tuple[float, int]]:
    helper = helper_path("audio_rms")
    if not helper.exists():
        return []
    sample_rate = 8000
    window_ms = max(1, int(round(window_seconds * 1000)))
    ffmpeg_process = None
    native_process = None
    try:
        ffmpeg_process = subprocess.Popen(
            audio_pcm_args(source, start_seconds, duration_seconds, sample_rate),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if not ffmpeg_process.stdout:
            return []
        native_process = subprocess.Popen(
            [str(helper), "--sample-rate", str(sample_rate), "--window-ms", str(window_ms)],
            stdin=ffmpeg_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        ffmpeg_process.stdout.close()
        output, _native_error = native_process.communicate(timeout=max(15, int(duration_seconds / 4) + 10))
        if ffmpeg_process.stderr:
            try:
                ffmpeg_process.stderr.read()
            except Exception:
                pass
        ffmpeg_return = ffmpeg_process.wait(timeout=5)
        if native_process.returncode != 0 or ffmpeg_return != 0:
            return []
        windows: list[tuple[float, int]] = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            try:
                index = int(parts[0])
                rms = int(parts[1])
            except ValueError:
                continue
            windows.append((start_seconds + index * window_seconds, rms))
        return windows
    except Exception:
        return []
    finally:
        _kill_process(native_process)
        _kill_process(ffmpeg_process)


def visual_moment_scores(
    source: Path,
    duration_seconds: int,
    step_seconds: int,
    timeout_seconds: int = 180,
) -> list[tuple[int, float]]:
    helper = helper_path("media_analyzer")
    if not helper.exists():
        return []
    width, height = 160, 90
    rows = _run_rawvideo_jsonl_helper(
        helper,
        source,
        width,
        height,
        fps_expr=f"1/{max(1, step_seconds)}",
        timeout_seconds=timeout_seconds,
    )
    scores: list[tuple[int, float]] = []
    for row in rows:
        try:
            index = int(row["index"])
            score = float(row["score"])
        except (KeyError, TypeError, ValueError):
            continue
        second = index * max(1, step_seconds)
        if 0 <= second < duration_seconds and score > 0:
            scores.append((second, score))
    return scores


def pick_cover_second(
    source: Path,
    duration_seconds: int,
    candidates: list[dict[str, object]],
    timeout_seconds: int = 120,
) -> int | None:
    helper = helper_path("cover_pick")
    if not helper.exists():
        return None
    starts = _candidate_seconds(candidates, duration_seconds)
    if not starts:
        return None
    # Keep the native path cheap: sample around candidate seconds at 1 fps by
    # trimming a compact window around the earliest/latest candidate.
    first = max(0, min(starts))
    last = min(max(0, duration_seconds - 1), max(starts) + 2)
    duration = max(1, last - first + 1)
    rows = _run_rawvideo_json_helper(
        helper,
        source,
        width=320,
        height=180,
        start_seconds=first,
        duration_seconds=duration,
        fps_expr="1",
        timeout_seconds=timeout_seconds,
    )
    if not rows:
        return None
    try:
        index = int(rows.get("index"))
    except (TypeError, ValueError):
        return None
    return max(0, min(duration_seconds - 1, first + index))


def face_track_points(
    _source: Path,
    _start_seconds: int,
    _clip_seconds: int,
    _timeout_seconds: int = 60,
) -> list[dict[str, object]]:
    if not capabilities().get("face_track") or not helper_available("face_track"):
        return []
    # Placeholder for future OpenCV-backed native face tracking. Returning an
    # empty list keeps the Python OpenCV fallback active and stable.
    return []


def audio_pcm_args(source: Path, start_seconds: float, duration_seconds: float, sample_rate: int) -> list[str]:
    return [
        ffmpeg_path(),
        "-v",
        "error",
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        f"{duration_seconds:.3f}",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-",
    ]


def _rawvideo_args(
    source: Path,
    width: int,
    height: int,
    fps_expr: str,
    start_seconds: int | None,
    duration_seconds: int | None,
) -> list[str]:
    args = [ffmpeg_path(), "-v", "error"]
    if start_seconds is not None:
        args.extend(["-ss", str(max(0, start_seconds))])
    if duration_seconds is not None:
        args.extend(["-t", str(max(1, duration_seconds))])
    args.extend(
        [
            "-i",
            str(source),
            "-vf",
            f"fps={fps_expr},scale={width}:{height}:flags=fast_bilinear",
            "-an",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    return args


def _run_rawvideo_jsonl_helper(
    helper: Path,
    source: Path,
    width: int,
    height: int,
    fps_expr: str,
    timeout_seconds: int,
) -> list[dict[str, object]]:
    output = _run_rawvideo_helper(helper, source, width, height, fps_expr, None, None, timeout_seconds)
    rows: list[dict[str, object]] = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _run_rawvideo_json_helper(
    helper: Path,
    source: Path,
    width: int,
    height: int,
    start_seconds: int,
    duration_seconds: int,
    fps_expr: str,
    timeout_seconds: int,
) -> dict[str, object]:
    output = _run_rawvideo_helper(helper, source, width, height, fps_expr, start_seconds, duration_seconds, timeout_seconds)
    try:
        data: Any = json.loads(output.strip())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _run_rawvideo_helper(
    helper: Path,
    source: Path,
    width: int,
    height: int,
    fps_expr: str,
    start_seconds: int | None,
    duration_seconds: int | None,
    timeout_seconds: int,
) -> str:
    ffmpeg_process = None
    native_process = None
    try:
        ffmpeg_process = subprocess.Popen(
            _rawvideo_args(source, width, height, fps_expr, start_seconds, duration_seconds),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if not ffmpeg_process.stdout:
            return ""
        native_process = subprocess.Popen(
            [str(helper), "--width", str(width), "--height", str(height)],
            stdin=ffmpeg_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        ffmpeg_process.stdout.close()
        output, _native_error = native_process.communicate(timeout=timeout_seconds)
        if ffmpeg_process.stderr:
            try:
                ffmpeg_process.stderr.read()
            except Exception:
                pass
        ffmpeg_return = ffmpeg_process.wait(timeout=5)
        if native_process.returncode != 0 or ffmpeg_return != 0:
            return ""
        return output
    except Exception:
        return ""
    finally:
        _kill_process(native_process)
        _kill_process(ffmpeg_process)


def _candidate_seconds(candidates: list[dict[str, object]], duration_seconds: int) -> list[int]:
    starts: list[int] = []
    for item in candidates[:12]:
        try:
            start = int(float(item.get("peak_second") or item.get("start")))
        except (AttributeError, TypeError, ValueError):
            continue
        start = max(0, min(max(0, duration_seconds - 1), start))
        if start not in starts:
            starts.append(start)
    return starts


def _kill_process(process: subprocess.Popen | None) -> None:
    if process and process.poll() is None:
        try:
            process.kill()
        except Exception:
            pass
