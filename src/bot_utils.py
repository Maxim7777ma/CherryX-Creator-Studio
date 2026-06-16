from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
import time


ACTION_MEDIA_TYPES = {
    "image": ["image"],
    "video": ["video"],
    "resume": ["resume"],
    "cover": ["cover", "youtube_cover"],
    "youtube": ["youtube_shorts", "youtube_backstage", "youtube_preview"],
    "subtitles": ["youtube_subtitles"],
    "package": ["publication_package"],
}


@dataclass(frozen=True)
class ConvertCallbackData:
    session_id: str
    target_format: str
    image_mode: str | None = None


def action_media_types_for(action: str) -> list[str]:
    return list(ACTION_MEDIA_TYPES.get(action, []))


def build_subscription_payload(user_id: int, days: int, stars: int, created_at: int | None = None) -> str:
    timestamp = int(time.time()) if created_at is None else int(created_at)
    return f"subscription:{int(user_id)}:{int(days)}:{int(stars)}:{timestamp}"


def valid_subscription_payload(
    payload: str,
    expected_days: int,
    expected_stars: int,
    user_id: int | None = None,
    now: int | None = None,
    future_skew_seconds: int = 300,
) -> bool:
    parts = (payload or "").split(":")
    if len(parts) != 5 or parts[0] != "subscription":
        return False
    try:
        payload_user_id = int(parts[1])
        days = int(parts[2])
        stars = int(parts[3])
        created_at = int(parts[4])
    except ValueError:
        return False
    if user_id is not None and payload_user_id != user_id:
        return False
    if days != expected_days or stars != expected_stars:
        return False
    current_time = int(time.time()) if now is None else int(now)
    return 0 < created_at <= current_time + future_skew_seconds


def day_start_timestamp(now: float | None = None) -> int:
    local = time.localtime(time.time() if now is None else now)
    return int(time.mktime((local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0, local.tm_wday, local.tm_yday, local.tm_isdst)))


def expired_mapping_keys(items: dict[str, object], now: int, get_expires_at) -> list[str]:
    return [item_id for item_id, item in items.items() if int(get_expires_at(item)) <= now]


def parse_convert_callback_data(data: str | None) -> ConvertCallbackData | None:
    parts = (data or "").split(":")
    if len(parts) not in {3, 4} or parts[0] != "convert":
        return None
    session_id = parts[1].strip()
    target_format = parts[2].strip().lower()
    image_mode = parts[3].strip().lower() if len(parts) == 4 else None
    if not session_id or not target_format:
        return None
    return ConvertCallbackData(session_id=session_id, target_format=target_format, image_mode=image_mode)


def normalize_cover_prompt_text(value: str | None, limit: int = 180) -> str:
    text = (value or "").replace("\r", "\n").strip()
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        cleaned = " ".join(line.strip().split())
        if cleaned:
            lines.append(cleaned)
    text = "\n".join(lines)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return text.strip()


def cover_prompt_preview(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return "без текста"
    title = lines[0]
    description = " ".join(lines[1:]).strip()
    if description:
        return f"Заголовок: {title}\nОписание: {description}"
    return f"Заголовок: {title}"


def normalize_subtitle_language(value: str | None) -> str | None:
    code = (value or "auto").strip().lower()
    if code in {"ru", "uk", "en"}:
        return code
    return None


def image_weight_note(source_size: int, output_size: int) -> str:
    if output_size < source_size:
        saved = 100 - int(output_size / max(1, source_size) * 100)
        return f"\nЭкономия: примерно {saved}%"
    return "\nФайл стал тяжелее: для этого исходника выбранный формат хуже сжимается. Попробуй WEBP в режиме «максимально легко»."


def re_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ0-9]+", text or "")


def publication_hashtags(title: str, transcript_text: str = "") -> list[str]:
    source_words = re_words(f"{title} {transcript_text}")
    words = [word.lower() for word in source_words if _hashtag_word_allowed(word)]
    tags = ["#shorts", "#video"]
    for word in words:
        clean = re.sub(r"[^\w]+", "", word, flags=re.UNICODE)
        if clean and len(clean) >= 3:
            tags.append("#" + clean[:24])
    unique: list[str] = []
    for tag in tags:
        if tag not in unique:
            unique.append(tag)
    return unique[:12]


def publication_description(title: str, duration_text: str, hashtags: list[str], subtitle_note: str, transcript_text: str = "", language: str | None = None) -> str:
    profile = _publication_language_profile(language, title, transcript_text)
    clean_title = _publication_clean_title(title)
    transcript_summary = _publication_summary(transcript_text, clean_title)
    hook = _publication_hook(clean_title, transcript_summary, profile)
    body = _publication_body(clean_title, transcript_summary, duration_text, profile)
    cta = profile["cta"]
    tags = " ".join(hashtags)
    quality_note = _publication_quality_note(subtitle_note, profile)

    parts = [
        hook,
        "",
        body,
        "",
        cta,
    ]
    if quality_note:
        parts.extend(["", quality_note])
    if tags:
        parts.extend(["", tags])
    return "\n".join(part for part in parts if part is not None).strip() + "\n"


def _hashtag_word_allowed(word: str) -> bool:
    lower = word.lower()
    if len(lower) < 4:
        return False
    stop = {
        "video", "shorts", "test", "тест", "тестовое", "видео", "ролик", "short", "this", "that", "with",
        "для", "про", "как", "это", "цей", "для", "und", "the", "and", "или", "или",
    }
    return lower not in stop


def _publication_clean_title(title: str) -> str:
    value = re.sub(r"[_\-]+", " ", title or "").strip()
    value = re.sub(r"\s+", " ", value)
    if not value:
        return "Видео"
    return value[:96]


def _publication_summary(transcript_text: str, title: str) -> str:
    text = re.sub(r"\s+", " ", transcript_text or "").strip()
    if not text:
        return title
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    scored = sorted(
        (sentence.strip() for sentence in sentences if len(sentence.strip()) >= 18),
        key=lambda item: (len(re_words(item)), len(item)),
        reverse=True,
    )
    if scored:
        return scored[0][:180].rstrip(" ,;:")
    return text[:180].rstrip(" ,;:")


def _publication_language_profile(language: str | None, title: str, transcript_text: str) -> dict[str, str]:
    code = (language or "").lower()
    sample = f"{title} {transcript_text}".lower()
    if not code or code == "auto":
        if re.search(r"[іїєґ]", sample):
            code = "uk"
        elif re.search(r"[а-яё]", sample):
            code = "ru"
        else:
            code = "en"
    profiles = {
        "ru": {
            "hook_prefix": "Смотрите до конца:",
            "body_prefix": "В этом коротком видео",
            "duration": "Длительность",
            "cta": "Сохрани, чтобы не потерять, и напиши в комментариях, что думаешь.",
            "subtitles": "Субтитры уже добавлены.",
        },
        "uk": {
            "hook_prefix": "Дивіться до кінця:",
            "body_prefix": "У цьому короткому відео",
            "duration": "Тривалість",
            "cta": "Збережи, щоб не загубити, і напиши в коментарях, що думаєш.",
            "subtitles": "Субтитри вже додано.",
        },
        "en": {
            "hook_prefix": "Watch this:",
            "body_prefix": "In this short video",
            "duration": "Duration",
            "cta": "Save it for later and drop your thoughts in the comments.",
            "subtitles": "Subtitles are included.",
        },
    }
    return profiles.get(code, profiles["en"])


def _publication_hook(title: str, summary: str, profile: dict[str, str]) -> str:
    base = summary if summary and summary.lower() != title.lower() else title
    base = re.sub(r"\s+", " ", base).strip(" .")
    if len(base) > 96:
        base = base[:93].rstrip(" ,;:") + "..."
    return f"{profile['hook_prefix']} {base}"


def _publication_body(title: str, summary: str, duration_text: str, profile: dict[str, str]) -> str:
    subject = summary if summary and summary.lower() != title.lower() else title
    subject = subject.strip(" .")
    if len(subject) > 160:
        subject = subject[:157].rstrip(" ,;:") + "..."
    if title and title.lower() not in subject.lower():
        subject = f"{title}: {subject}"
    return f"{profile['body_prefix']} — {subject}. {profile['duration']}: {duration_text}."


def _publication_quality_note(subtitle_note: str, profile: dict[str, str]) -> str:
    if not subtitle_note:
        return ""
    lowered = subtitle_note.lower()
    if "добав" in lowered or "added" in lowered:
        return profile["subtitles"]
    return ""


def unique_archive_name(original_name: str, used_names: set[str]) -> str:
    if original_name not in used_names:
        return original_name

    if "." in original_name and not original_name.startswith("."):
        stem, suffix = original_name.rsplit(".", 1)
        suffix = "." + suffix
    else:
        stem, suffix = original_name, ""

    index = 1
    while True:
        candidate = f"{stem}_{index}{suffix}"
        if candidate not in used_names:
            return candidate
        index += 1


def normalize_resume_text(value: str | None) -> str:
    if not value:
        return ""
    lines = [" ".join(line.split()) for line in str(value).splitlines() if line.strip()]
    return "\n".join(lines)


def resume_safe_text(value: str) -> str:
    return escape(value, quote=False).replace("\n", "<br/>")


def resume_is_empty(value: str) -> bool:
    return value.strip().lower() in {"", "нет", "no", "none", "n/a", "na", "-"}


def resume_clip(value: str, limit: int = 260) -> str:
    value = normalize_resume_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def polish_resume_block(value: str, bulletize: bool = False) -> str:
    lines = [line.strip(" \t•*-") for line in normalize_resume_text(value).splitlines() if line.strip()]
    if not lines:
        return ""
    if bulletize and len(lines) > 1:
        return "\n".join(f"- {line}" for line in lines)
    return "\n".join(lines)


def polish_resume_skills(value: str) -> str:
    raw = normalize_resume_text(value).replace(";", ",").replace("•", ",").replace("\n", ",")
    skills: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        skill = " ".join(item.split()).strip(" .")
        key = skill.lower()
        if skill and key not in seen:
            skills.append(skill)
            seen.add(key)
    return ", ".join(skills)


def resume_section_data(data: dict) -> dict[str, str]:
    prepared = {
        "name": normalize_resume_text(data.get("name")),
        "position": normalize_resume_text(data.get("position")),
        "contact": normalize_resume_text(data.get("contact")),
        "links": normalize_resume_text(data.get("links")),
        "summary": normalize_resume_text(data.get("summary")),
        "experience": normalize_resume_text(data.get("experience")),
        "education": normalize_resume_text(data.get("education")),
        "skills": normalize_resume_text(data.get("skills")),
        "achievements": normalize_resume_text(data.get("achievements")),
        "additional": normalize_resume_text(data.get("additional")),
    }
    for key in ("achievements", "additional"):
        if resume_is_empty(prepared[key]):
            prepared[key] = ""
    if prepared["skills"]:
        prepared["skills"] = prepared["skills"].replace(";", ",")
    return prepared
