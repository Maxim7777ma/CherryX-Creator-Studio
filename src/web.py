from __future__ import annotations

from pathlib import Path
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .config import get_settings
from .image_tools import SUPPORTED_IMAGE_FORMATS, clean_base_name, convert_image
from .video_tools import VIDEO_FORMATS, convert_video
from .web_auth import validate_init_data


settings = get_settings()
app = FastAPI(title="Telegram Image Converter Mini App")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (Path(__file__).parent / "web_static" / "index.html").read_text(encoding="utf-8")


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    target_format: str = Form(...),
    output_name: str = Form("converted"),
    init_data: str = Form(""),
):
    if not settings.allow_web_without_telegram and not validate_init_data(init_data, settings.bot_token):
        raise HTTPException(status_code=403, detail="Invalid Telegram initData")

    target_format = target_format.lower()
    if target_format not in SUPPORTED_IMAGE_FORMATS and target_format not in VIDEO_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported format")

    stamp = str(int(time.time() * 1000))
    input_dir = settings.storage_dir / "web"
    output_dir = settings.output_dir / "web"
    input_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload").suffix
    source = input_dir / f"{stamp}_{clean_base_name(file.filename or 'upload')}{suffix}"

    source.write_bytes(await file.read())
    try:
        upload_is_video = (file.content_type or "").startswith("video/")
        if target_format in VIDEO_FORMATS and (upload_is_video or target_format not in SUPPORTED_IMAGE_FORMATS):
            result = convert_video(
                source,
                output_dir,
                target_format,
                clean_base_name(output_name),
                settings.video_timeout_seconds,
            )
            output = result.path
        else:
            output, _ = convert_image(source, output_dir, target_format, clean_base_name(output_name))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        source.unlink(missing_ok=True)

    return FileResponse(output, filename=output.name, media_type="application/octet-stream")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
