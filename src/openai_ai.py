from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
import re
from typing import Any

from .config import get_settings
from .youtube_tools import SubtitleCue


class OpenAIUnavailableError(RuntimeError):
    pass


def is_openai_ready() -> bool:
    settings = get_settings()
    return bool(settings.openai_enabled and settings.openai_api_key)


def plan_clip_moments(
    title: str,
    duration: float,
    local_scores: list[dict[str, object]] | list[int],
    transcript: str = "",
) -> dict[str, object]:
    if not is_openai_ready():
        raise OpenAIUnavailableError("OpenAI is not configured")

    candidates = _normalize_candidates(local_scores, duration)
    if not candidates:
        return {"starts": [], "model": get_settings().openai_text_model, "reason": "no candidates"}

    prompt = {
        "task": "Choose the best short-form clip start times from the provided candidates.",
        "rules": [
            "Return JSON only.",
            "Use only candidate start values.",
            "Prefer moments likely to work as TikTok/YouTube Shorts hooks.",
            "Prefer a clear phrase start, visible reaction, reveal, conflict, surprise, answer, or strong visual change.",
            "Avoid dead air, slow setup, title cards, generic intros, outros, and near-duplicate moments.",
            "Keep the selected list diverse across the full video.",
            "Do not invent timestamps. Pick only from candidates.",
        ],
        "title": title[:240],
        "duration_seconds": int(duration or 0),
        "candidates": candidates,
        "transcript_snippet": transcript[:6000],
    }
    response_text = _responses_text(
        "You are a concise viral video editor. Return compact valid JSON.",
        json.dumps(prompt, ensure_ascii=False),
    )
    data = _loads_json_object(response_text)
    allowed = {int(item["start"]) for item in candidates if "start" in item}
    starts = []
    for value in data.get("starts", []):
        try:
            start = int(float(value))
        except (TypeError, ValueError):
            continue
        if start in allowed and start not in starts:
            starts.append(start)
    return {
        "starts": starts,
        "reason": str(data.get("reason") or "")[:500],
        "model": get_settings().openai_text_model,
    }


def generate_cover_prompt(title: str, transcript_summary: str = "", frame_notes: str = "") -> str:
    if not is_openai_ready():
        raise OpenAIUnavailableError("OpenAI is not configured")

    payload = {
        "task": "Write one image-generation prompt for a premium YouTube thumbnail background.",
        "title": title[:180],
        "transcript_summary": transcript_summary[:1600],
        "frame_notes": frame_notes[:800],
        "requirements": [
            "Create a premium cinematic 16:9 YouTube thumbnail background, not the final text layout.",
            "Keep the main person or subject sharp, expressive, close, and dominant.",
            "Use dramatic directional lighting, clean contrast, tasteful color grading, realistic depth, and editorial composition.",
            "Leave a clear dark negative-space area on one side for huge headline text.",
            "Do not draw any text, words, letters, subtitles, watermarks, UI, logos, emoji, stickers, arrows, dollar icons, or comic bursts.",
            "Avoid clutter, cheap clip-art aesthetics, plastic skin, distorted faces, and extra fingers.",
        ],
    }
    response_text = _responses_text(
        "You write art-direction prompts for premium creator thumbnails. Return only the prompt text.",
        json.dumps(payload, ensure_ascii=False),
    )
    return response_text.strip()[:1400]


def generate_cover_copy(title: str, transcript_summary: str = "") -> dict[str, str]:
    if not is_openai_ready():
        raise OpenAIUnavailableError("OpenAI is not configured")

    payload = {
        "task": "Write high-click YouTube thumbnail copy for the final local text overlay.",
        "title": title[:220],
        "transcript_summary": transcript_summary[:1800],
        "rules": [
            "Return compact JSON only.",
            "Keep the same language as the source title.",
            "headline: 2 to 5 punchy words, no hashtags, no quotes, no emoji.",
            "description: optional 3 to 8 words that adds curiosity, not a full sentence.",
            "eyebrow: 1 to 3 words, category/urgency label.",
            "Avoid clickbait that promises facts not present in the title.",
        ],
        "schema": {"headline": "string", "description": "string", "eyebrow": "string"},
    }
    response_text = _responses_text(
        "You are a senior YouTube thumbnail editor. Return only valid JSON.",
        json.dumps(payload, ensure_ascii=False),
    )
    data = _loads_json_object(response_text)
    headline = _clean_cover_text(data.get("headline"), 54)
    description = _clean_cover_text(data.get("description"), 92)
    eyebrow = _clean_cover_text(data.get("eyebrow"), 24)
    return {
        "headline": headline or _clean_cover_text(title, 54) or "NEW VIDEO",
        "description": description,
        "eyebrow": eyebrow,
    }


def generate_cover_image(frame_path: Path, title: str, prompt: str, output_path: Path) -> Path:
    if not is_openai_ready():
        raise OpenAIUnavailableError("OpenAI is not configured")
    settings = get_settings()
    if settings.openai_image_mode != "responses":
        raise OpenAIUnavailableError("Only Responses image mode is supported")

    client = _client()
    image_data_url = _image_data_url(frame_path)
    response = client.responses.create(
        model=settings.openai_text_model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Create a polished 16:9 premium YouTube thumbnail background based on the reference frame. "
                            "Important: do NOT render any text, letters, captions, stickers, emojis, arrows, fake UI, logos, money icons, or comic bursts. "
                            "Make the subject cinematic, sharp, expressive, high-contrast, and leave clean dark negative space for a separate headline overlay. "
                            "Keep faces natural and undistorted. Make it feel like a high-budget creator thumbnail, not a poster template.\n\n"
                            f"Title: {title}\nPrompt: {prompt}"
                        ),
                    },
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
        tools=[
            {
                "type": "image_generation",
                "action": "auto",
                "size": "1536x864",
                "quality": "high",
            }
        ],
        tool_choice={"type": "image_generation"},
    )
    image_base64 = _extract_image_base64(response)
    if not image_base64:
        raise OpenAIUnavailableError("OpenAI did not return an image")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(image_base64))
    return output_path


def transcribe_video_audio(source: Path, language: str | None = None) -> list[SubtitleCue]:
    if not is_openai_ready():
        raise OpenAIUnavailableError("OpenAI is not configured")
    settings = get_settings()
    with source.open("rb") as audio_file:
        transcription = _client().audio.transcriptions.create(
            file=audio_file,
            model=settings.openai_transcribe_model,
            language=language or None,
            response_format="verbose_json",
            timestamp_granularities=["word"],
            timeout=settings.openai_timeout_seconds,
        )
    return _transcription_to_cues(transcription)


def _client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise OpenAIUnavailableError("Install openai package to enable AI features") from exc

    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)


def _responses_text(system_text: str, user_text: str) -> str:
    settings = get_settings()
    response = _client().responses.create(
        model=settings.openai_text_model,
        input=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        timeout=settings.openai_timeout_seconds,
    )
    return _response_output_text(response)


def _response_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", "")
    if output_text:
        return str(output_text)
    chunks: list[str] = []
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(str(text))
    return "\n".join(chunks)


def _extract_image_base64(response: Any) -> str:
    for output in getattr(response, "output", []) or []:
        if getattr(output, "type", "") == "image_generation_call":
            result = getattr(output, "result", "")
            if result:
                return str(result)
    return ""


def _image_data_url(path: Path) -> str:
    media_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _loads_json_object(value: str) -> dict[str, object]:
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def _normalize_candidates(local_scores: list[dict[str, object]] | list[int], duration: float) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    max_start = max(0, int(duration or 0))
    for item in local_scores[:80]:
        if isinstance(item, dict):
            raw_start = item.get("start")
            score = item.get("score")
        else:
            raw_start = item
            score = None
        try:
            start = max(0, min(max_start, int(float(raw_start))))
        except (TypeError, ValueError):
            continue
        candidate = {"start": start}
        if score is not None:
            try:
                candidate["score"] = round(float(score), 3)
            except (TypeError, ValueError):
                pass
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _transcription_to_cues(transcription: Any) -> list[SubtitleCue]:
    words = _as_list(getattr(transcription, "words", None) or _get_mapping_value(transcription, "words"))
    if words:
        return _word_items_to_cues(words)
    segments = _as_list(getattr(transcription, "segments", None) or _get_mapping_value(transcription, "segments"))
    cues: list[SubtitleCue] = []
    for segment in segments:
        text = _clean_caption(_item_value(segment, "text"))
        start = _float_value(_item_value(segment, "start"), 0.0)
        end = _float_value(_item_value(segment, "end"), start + 1.0)
        if text and end > start:
            cues.append(SubtitleCue(start=start, end=end, text=text))
    return cues


def _word_items_to_cues(words: list[Any]) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    current: list[tuple[float, float, str]] = []
    current_chars = 0
    for word in words:
        text = _clean_caption(_item_value(word, "word"))
        start = _float_value(_item_value(word, "start"), 0.0)
        end = _float_value(_item_value(word, "end"), start + 0.3)
        if not text:
            continue
        gap = start - current[-1][1] if current else 0.0
        duration = end - current[0][0] if current else 0.0
        if current and (current_chars + len(text) > 42 or duration > 3.0 or gap > 0.65):
            cues.append(_cue_from_words(current))
            current = []
            current_chars = 0
        current.append((start, end, text))
        current_chars += len(text) + 1
    if current:
        cues.append(_cue_from_words(current))
    return cues


def _cue_from_words(words: list[tuple[float, float, str]]) -> SubtitleCue:
    return SubtitleCue(start=words[0][0], end=max(words[-1][1], words[0][0] + 0.4), text=" ".join(item[2] for item in words))


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _get_mapping_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _item_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_caption(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_cover_text(value: Any, max_chars: int) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    text = re.sub(r"[#|]+", " ", text).strip(" -:;\"'")
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] or text[:max_chars]
    return text
