from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil

from PIL import Image, ImageOps, ImageSequence


SUPPORTED_IMAGE_FORMATS = {
    "png": "PNG",
    "jpg": "JPEG",
    "webp": "WEBP",
    "pdf": "PDF",
    "bmp": "BMP",
    "tiff": "TIFF",
    "gif": "GIF",
}
WEBP_TARGET_RATIO = 0.5
IMAGE_COMPRESSION_MODES = {"light", "balanced", "quality"}
WEBP_QUALITY_STEPS = {
    "light": [68, 62, 56, 50, 44, 38, 32, 26, 20, 14, 8],
    "balanced": [82, 78, 74, 70, 66, 62, 58, 54, 50, 46, 42, 38, 34, 30, 26, 22, 18, 14, 10, 6],
    "quality": [95, 92, 90, 88, 86, 84, 82, 80],
}
JPEG_QUALITY_STEPS = {
    "light": [78, 72, 66, 60, 54, 48, 42, 36],
    "balanced": [88, 84, 80, 76, 72, 68, 64, 60, 56, 52],
    "quality": [96, 94, 92, 90, 88],
}
PNG_PALETTE_COLORS = {
    "light": [128, 96, 64, 48, 32],
    "balanced": [256, 192, 128, 96, 64],
    "quality": [],
}


@dataclass(frozen=True)
class ImageInfo:
    format: str
    width: int
    height: int
    mode: str
    frames: int
    size_bytes: int


def clean_base_name(value: str, fallback: str = "converted") -> str:
    value = Path(value).stem
    value = re.sub(r"[^\w .()-]+", "_", value, flags=re.UNICODE).strip(" ._")
    return value[:80] or fallback


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{size} B"


def inspect_image(path: Path) -> ImageInfo:
    with Image.open(path) as img:
        return ImageInfo(
            format=img.format or "UNKNOWN",
            width=img.width,
            height=img.height,
            mode=img.mode,
            frames=getattr(img, "n_frames", 1),
            size_bytes=path.stat().st_size,
        )


def available_image_formats(path: Path) -> list[str]:
    current = inspect_image(path).format.lower()
    formats = list(SUPPORTED_IMAGE_FORMATS.keys())
    return [fmt for fmt in formats if fmt != "jpg" or current not in {"jpeg", "jpg"}]


def convert_image(
    source: Path,
    output_dir: Path,
    target_format: str,
    output_base_name: str,
    mode: str = "balanced",
) -> tuple[Path, ImageInfo]:
    target_format = target_format.lower()
    if target_format not in SUPPORTED_IMAGE_FORMATS:
        raise ValueError("Unsupported target format")
    mode = normalize_image_mode(mode)

    output_dir.mkdir(parents=True, exist_ok=True)
    extension = "jpg" if target_format == "jpg" else target_format
    output_path = output_dir / f"{clean_base_name(output_base_name)}.{extension}"
    pil_format = SUPPORTED_IMAGE_FORMATS[target_format]

    with Image.open(source) as img:
        img = ImageOps.exif_transpose(img)
        img = _resize_for_image_mode(img, mode)
        save_kwargs: dict[str, object] = {}

        if pil_format in {"JPEG", "PDF", "BMP"} and img.mode in {"RGBA", "LA", "P"}:
            img = _flatten_to_rgb(img)
        elif pil_format == "JPEG" and img.mode != "RGB":
            img = img.convert("RGB")

        if pil_format == "WEBP":
            _save_webp_optimized(img, output_path, source.stat().st_size, mode)
            return output_path, inspect_image(output_path)
        elif pil_format == "JPEG":
            _save_jpeg_optimized(img, output_path, source.stat().st_size, mode)
            return output_path, inspect_image(output_path)
        elif pil_format == "PNG":
            _save_png_optimized(img, output_path, source.stat().st_size, mode)
            return output_path, inspect_image(output_path)
        elif pil_format in {"GIF", "TIFF"} and getattr(img, "is_animated", False):
            frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
            frames[0].save(
                output_path,
                format=pil_format,
                save_all=True,
                append_images=frames[1:],
                duration=img.info.get("duration", 100),
                loop=img.info.get("loop", 0),
            )
            return output_path, inspect_image(output_path)
        elif pil_format == "PDF":
            save_kwargs.update({
                "resolution": {"light": 96, "balanced": 144, "quality": 200}[mode],
                "quality": {"light": 72, "balanced": 86, "quality": 94}[mode],
            })
        elif pil_format == "TIFF":
            save_kwargs.update({"compression": "tiff_adobe_deflate"})

        img.save(output_path, format=pil_format, **save_kwargs)

    return output_path, inspect_image(output_path)


def normalize_image_mode(mode: str | None) -> str:
    mode = (mode or "balanced").strip().lower()
    return mode if mode in IMAGE_COMPRESSION_MODES else "balanced"


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, rgba).convert("RGB")


def _save_webp_optimized(img: Image.Image, output_path: Path, source_size: int, mode: str) -> None:
    prepared = _prepare_for_webp(img)
    target_size = int(source_size * _target_ratio(mode))
    best_path: Path | None = None
    best_size: int | None = None
    temp_paths: list[Path] = []

    for quality in WEBP_QUALITY_STEPS[mode]:
        candidate = output_path.with_name(f"{output_path.stem}.q{quality}.tmp.webp")
        temp_paths.append(candidate)
        prepared.save(
            candidate,
            format="WEBP",
            quality=quality,
            method=6,
            alpha_quality=max(55, min(90, quality + 12)),
        )
        current_size = candidate.stat().st_size
        if best_size is None or current_size < best_size:
            best_path = candidate
            best_size = current_size
        if current_size <= target_size:
            best_path = candidate
            best_size = current_size
            break

    if not best_path:
        prepared.save(output_path, format="WEBP", quality=70, method=6)
        return

    output_path.unlink(missing_ok=True)
    shutil.copyfile(best_path, output_path)
    for temp_path in temp_paths:
        temp_path.unlink(missing_ok=True)


def _save_jpeg_optimized(img: Image.Image, output_path: Path, source_size: int, mode: str) -> None:
    prepared = _flatten_to_rgb(img) if img.mode in {"RGBA", "LA", "P"} else img.convert("RGB")
    _save_lossy_candidates(
        prepared,
        output_path,
        "JPEG",
        JPEG_QUALITY_STEPS[mode],
        source_size,
        _target_ratio(mode),
        {"optimize": True, "progressive": True},
    )


def _save_png_optimized(img: Image.Image, output_path: Path, source_size: int, mode: str) -> None:
    candidates: list[Path] = []
    original = output_path.with_name(f"{output_path.stem}.truecolor.tmp.png")
    candidates.append(original)
    img.save(original, format="PNG", optimize=True)

    if mode != "quality" and not getattr(img, "is_animated", False):
        for colors in PNG_PALETTE_COLORS[mode]:
            candidate = output_path.with_name(f"{output_path.stem}.p{colors}.tmp.png")
            candidates.append(candidate)
            prepared = _prepare_png_palette(img, colors)
            prepared.save(candidate, format="PNG", optimize=True)

    target_size = int(source_size * _target_ratio(mode))
    best = min(candidates, key=lambda path: path.stat().st_size)
    for candidate in candidates:
        if candidate.stat().st_size <= target_size:
            best = candidate
            break
    output_path.unlink(missing_ok=True)
    shutil.copyfile(best, output_path)
    for candidate in candidates:
        candidate.unlink(missing_ok=True)


def _save_lossy_candidates(
    img: Image.Image,
    output_path: Path,
    pil_format: str,
    qualities: list[int],
    source_size: int,
    target_ratio: float,
    save_kwargs: dict[str, object],
) -> None:
    target_size = int(source_size * target_ratio)
    best_path: Path | None = None
    best_size: int | None = None
    temp_paths: list[Path] = []
    extension = output_path.suffix.lstrip(".")
    for quality in qualities:
        candidate = output_path.with_name(f"{output_path.stem}.q{quality}.tmp.{extension}")
        temp_paths.append(candidate)
        img.save(candidate, format=pil_format, quality=quality, **save_kwargs)
        current_size = candidate.stat().st_size
        if best_size is None or current_size < best_size:
            best_path = candidate
            best_size = current_size
        if current_size <= target_size:
            best_path = candidate
            break
    if not best_path:
        img.save(output_path, format=pil_format, quality=qualities[-1], **save_kwargs)
        return
    output_path.unlink(missing_ok=True)
    shutil.copyfile(best_path, output_path)
    for temp_path in temp_paths:
        temp_path.unlink(missing_ok=True)


def _prepare_for_webp(img: Image.Image) -> Image.Image:
    if getattr(img, "is_animated", False):
        img.seek(0)
    if img.mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    if img.mode in {"RGBA", "RGB", "L"}:
        return img.copy()
    if img.mode in {"LA"}:
        return img.convert("RGBA")
    return img.convert("RGB")


def _prepare_png_palette(img: Image.Image, colors: int) -> Image.Image:
    if img.mode in {"RGBA", "LA"}:
        rgba = img.convert("RGBA")
        rgb = _flatten_to_rgb(rgba)
        return rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    return img.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT)


def _resize_for_image_mode(img: Image.Image, mode: str) -> Image.Image:
    if getattr(img, "is_animated", False):
        return img
    limits = {"light": 1600, "balanced": 2560, "quality": 4096}
    limit = limits[mode]
    width, height = img.size
    if max(width, height) <= limit:
        return img.copy()
    resized = img.copy()
    resized.thumbnail((limit, limit), Image.Resampling.LANCZOS)
    return resized


def _target_ratio(mode: str) -> float:
    return {"light": 0.35, "balanced": WEBP_TARGET_RATIO, "quality": 1.0}[mode]
