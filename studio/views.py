from __future__ import annotations

from base64 import b64decode
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
import json
import mimetypes
import shutil
import uuid

from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from PIL import Image

from billing.plans import PLANS, get_plan
from billing.services import active_access_until, transfer_guest_workspace, user_has_active_access
from src import web_actions as actions
from src.config import get_settings
from src.image_tools import clean_base_name, human_size
from .forms import AccountSettingsForm, EmailLoginForm, RegisterForm
from .localization import app_messages, clean_language, localized_plan, translate
from .models import AccountProfile, VideoEditorAsset, VideoEditorProject


settings = get_settings()
RESUME_FIELDS = [
    "name",
    "position",
    "contact",
    "links",
    "summary",
    "experience",
    "education",
    "skills",
    "achievements",
    "additional",
]


@require_GET
def landing(request: HttpRequest):
    if request.user.is_authenticated:
        return redirect("studio:index")
    return render(request, "studio/landing.html")


@require_http_methods(["GET", "POST"])
def register(request: HttpRequest):
    if request.user.is_authenticated:
        return redirect("studio:index")
    form = RegisterForm(request.POST or None, language=getattr(request, "interface_language", "en"))
    if request.method == "POST" and form.is_valid():
        guest_key = _guest_key(request)
        user = form.save()
        login(request, user)
        transfer_guest_workspace(guest_key, user)
        _transfer_guest_video_projects(guest_key, user)
        return redirect("studio:index")
    return render(request, "studio/auth.html", {**_auth_context(request), "form": form, "mode": "register"})


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest):
    if request.user.is_authenticated:
        return redirect("studio:index")
    form = EmailLoginForm(request.POST or None, language=getattr(request, "interface_language", "en"))
    if request.method == "POST" and form.is_valid():
        guest_key = _guest_key(request)
        login(request, form.cleaned_data["user"])
        transfer_guest_workspace(guest_key, form.cleaned_data["user"])
        _transfer_guest_video_projects(guest_key, form.cleaned_data["user"])
        return redirect("studio:index")
    return render(request, "studio/auth.html", {**_auth_context(request), "form": form, "mode": "login"})


@require_POST
def logout_view(request: HttpRequest):
    logout(request)
    return redirect("studio:landing")


@require_POST
def set_interface_language(request: HttpRequest):
    language = clean_language(request.POST.get("language"))
    request.session["interface_language"] = language
    request.interface_language = language
    if request.user.is_authenticated:
        profile, _ = AccountProfile.objects.get_or_create(user=request.user)
        profile.interface_language = language
        profile.save(update_fields=["interface_language", "updated_at"])
    response = redirect(request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("studio:landing"))
    response.set_cookie("interface_language", language, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response


@login_required
@require_http_methods(["GET", "POST"])
def account_settings(request: HttpRequest):
    profile, _ = AccountProfile.objects.get_or_create(user=request.user)
    form = AccountSettingsForm(
        request.POST or None,
        request.FILES or None,
        user=request.user,
        profile=profile,
        language=getattr(request, "interface_language", "en"),
    )
    if request.method == "POST" and form.is_valid():
        password_changed = form.save_profile()
        avatar_crop_data = form.cleaned_data.get("avatar_crop_data")
        avatar = form.cleaned_data.get("avatar_file")
        if avatar_crop_data:
            profile.avatar_path = str(_save_avatar_crop(avatar_crop_data, request.user.id))
            profile.avatar_url = ""
            profile.save(update_fields=["avatar_path", "avatar_url", "updated_at"])
        elif avatar:
            profile.avatar_path = str(_save_avatar_upload(avatar, request.user.id))
            profile.avatar_url = ""
            profile.save(update_fields=["avatar_path", "avatar_url", "updated_at"])
        if password_changed:
            update_session_auth_hash(request, request.user)
        return redirect("studio:account_settings")
    return render(
        request,
        "studio/account_settings.html",
        {
            "form": form,
            "avatar_url": _avatar_url(request),
            "display_name": _display_name(request),
            "accent_color": _accent_color(request),
            "ui_accent_color": _ui_accent_color(request),
            "theme_mode": _theme_mode(request),
            "language_options": _language_options_for_form(form),
        },
    )


@login_required
@require_GET
def account_avatar(request: HttpRequest):
    try:
        avatar_path = request.user.studio_profile.avatar_path
    except AccountProfile.DoesNotExist:
        avatar_path = ""
    if not avatar_path:
        raise Http404("Avatar not found")
    path = Path(avatar_path)
    if not path.exists() or not path.is_file():
        raise Http404("Avatar not found")
    return FileResponse(path.open("rb"), as_attachment=False)


@require_GET
def index(request: HttpRequest):
    owner_id, guest_key = _workspace_identity(request)
    initial_jobs = [_attach_output_urls(job) for job in actions.get_recent_jobs(5, owner_id, guest_key)]
    account_stats = actions.get_account_stats(owner_id, guest_key)
    account_stats.update(_storage_quota(request, account_stats))
    has_access = user_has_active_access(request.user)
    language = getattr(request, "interface_language", "en")
    return render(
        request,
        "studio/index.html",
        {
            "image_formats": actions.IMAGE_FORMAT_CHOICES,
            "video_formats": actions.VIDEO_FORMAT_CHOICES,
            "image_modes": _localized_image_modes(language),
            "youtube_modes": _localized_youtube_modes(language),
            "subtitle_styles": actions.SUBTITLE_STYLE_CHOICES,
            "subtitle_languages": _localized_subtitle_languages(language),
            "resume_templates": _localized_resume_templates(language),
            "max_image_mb": settings.max_image_mb,
            "max_video_mb": settings.max_video_mb,
            "initial_jobs": initial_jobs,
            "account_stats": account_stats,
            "has_access": has_access,
            "active_until": active_access_until(request.user),
            "is_guest": not request.user.is_authenticated,
            "display_name": _display_name(request),
            "checkout_url": _checkout_url(request),
            "pricing_url": reverse("billing:pricing"),
            "login_url": reverse("studio:login"),
            "settings_url": reverse("studio:account_settings"),
            "designer_url": reverse("studio:designer"),
            "video_editor_url": reverse("studio:video_project_list"),
            "avatar_url": _avatar_url(request),
            "accent_color": _accent_color(request),
            "ui_accent_color": _ui_accent_color(request),
            "theme_mode": _theme_mode(request),
            "subscription_meter": _subscription_meter(request),
            "subscription_panel": _subscription_panel(request, account_stats, language),
            "app_messages": app_messages(language),
        },
    )


@require_GET
def designer_mode(request: HttpRequest):
    language = getattr(request, "interface_language", "en")
    return render(
        request,
        "studio/designer.html",
        {
            "designer_url": reverse("studio:designer"),
            "designer_fullscreen": True,
            "accent_color": _accent_color(request),
            "ui_accent_color": _ui_accent_color(request),
            "theme_mode": _theme_mode(request),
            "app_messages": app_messages(language),
        },
    )


@require_GET
@ensure_csrf_cookie
def video_editor(request: HttpRequest):
    language = getattr(request, "interface_language", "en")
    owner_id, guest_key = _workspace_identity(request)
    project = None
    project_id = request.GET.get("project", "")
    if project_id.isdigit():
        project = _video_project_queryset(owner_id, guest_key).filter(id=int(project_id)).first()
    return render(
        request,
        "studio/video_editor.html",
        {
            "current_video_project": _video_project_payload(project) if project else None,
            "video_projects_api_url": reverse("studio:video_projects"),
            "accent_color": _accent_color(request),
            "ui_accent_color": _ui_accent_color(request),
            "theme_mode": _theme_mode(request),
            "app_messages": app_messages(language),
        },
    )


@require_GET
@ensure_csrf_cookie
def video_project_list(request: HttpRequest):
    owner_id, guest_key = _workspace_identity(request)
    projects = [_video_project_payload(project, include_state=False) for project in _video_project_queryset(owner_id, guest_key)[:120]]
    return render(
        request,
        "studio/video_projects.html",
        {
            "video_projects": projects,
            "video_editor_url": reverse("studio:video_editor"),
            "video_projects_api_url": reverse("studio:video_projects"),
            "accent_color": _accent_color(request),
            "ui_accent_color": _ui_accent_color(request),
            "theme_mode": _theme_mode(request),
            "app_messages": app_messages(getattr(request, "interface_language", "en")),
        },
    )


@require_GET
def video_projects(request: HttpRequest) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    projects = [_video_project_payload(project, include_state=False) for project in _video_project_queryset(owner_id, guest_key)[:80]]
    return JsonResponse({"projects": projects})


@require_POST
def create_video_project(request: HttpRequest) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    data = _json_body(request)
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    title = _clean_project_title(str(data.get("title") or state.get("title") or "Новый проект"))
    project = VideoEditorProject.objects.create(
        owner=request.user if request.user.is_authenticated else None,
        guest_key="" if owner_id else guest_key,
        title=title,
        state_json=state,
        storage_bytes=_json_size(state),
    )
    project.storage_bytes = _video_project_storage_bytes(project)
    project.save(update_fields=["storage_bytes", "updated_at"])
    return JsonResponse({"project": _video_project_payload(project)})


@require_GET
def video_project_detail(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    return JsonResponse({"project": _video_project_payload(project)})


@require_POST
def save_video_project(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    data = _json_body(request)
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    title = _clean_project_title(str(data.get("title") or state.get("title") or project.title))
    project.title = title
    project.state_json = state
    project.storage_bytes = _video_project_storage_bytes(project)
    project.save(update_fields=["title", "state_json", "storage_bytes", "updated_at"])
    return JsonResponse({"project": _video_project_payload(project)})


@require_POST
def delete_video_project(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    _delete_video_project_media(project)
    deleted, _ = project.delete()
    if not deleted:
        raise Http404("Project not found")
    stats = actions.get_account_stats(owner_id, guest_key)
    stats.update(_storage_quota(request, stats))
    return JsonResponse({"ok": True, "account_stats": stats})


@require_POST
def upload_video_project_asset(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    upload = _require_file(request, "file")
    media_type = upload.content_type or mimetypes.guess_type(upload.name or "")[0] or "application/octet-stream"
    kind = (request.POST.get("kind") or "").strip().lower()
    if kind not in {"video", "audio", "image"}:
        if media_type.startswith("video/"):
            kind = "video"
        elif media_type.startswith("audio/"):
            kind = "audio"
        elif media_type.startswith("image/"):
            kind = "image"
        else:
            return _error_json(ValueError("Unsupported asset type"), 400)
    if kind == "video" and upload.size > settings.max_video_mb * 1024 * 1024:
        return _error_json(ValueError(f"Video limit: {settings.max_video_mb} MB"), 400)
    if kind == "image" and upload.size > settings.max_image_mb * 1024 * 1024:
        return _error_json(ValueError(f"Image limit: {settings.max_image_mb} MB"), 400)
    asset_dir = _video_project_media_dir(project)
    asset_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.name or "").suffix[:16] or mimetypes.guess_extension(media_type) or ".bin"
    base = clean_base_name(upload.name or kind, kind)
    path = asset_dir / f"{uuid.uuid4().hex[:12]}_{base}{suffix}"
    with path.open("wb") as destination:
        for chunk in upload.chunks():
            destination.write(chunk)
    thumbnail_path = ""
    thumbnail_data = request.POST.get("thumbnail", "")
    if thumbnail_data.startswith("data:image/"):
        thumbnail_path = str(_save_project_thumbnail(thumbnail_data, asset_dir))
    asset = VideoEditorAsset.objects.create(
        project=project,
        kind=kind,
        file_path=str(path),
        media_type=media_type,
        size=path.stat().st_size,
        original_name=(upload.name or kind)[:240],
        thumbnail_path=thumbnail_path,
        duration=float(request.POST.get("duration") or 0),
    )
    project.storage_bytes = _video_project_storage_bytes(project)
    project.save(update_fields=["storage_bytes", "updated_at"])
    return JsonResponse({"asset": _video_asset_payload(asset), "project": _video_project_payload(project)})


@require_GET
def preview_video_project_asset(request: HttpRequest, project_id: int, asset_id: int) -> HttpResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    asset = project.assets.filter(id=asset_id).first()
    if not asset:
        raise Http404("Asset not found")
    path = Path(asset.file_path)
    if not path.exists() or not path.is_file():
        raise Http404("Asset file not found")
    if asset.kind in {"video", "audio"}:
        return _range_file_response(request, path, asset.media_type, asset.original_name or path.name)
    return FileResponse(path.open("rb"), as_attachment=False, filename=asset.original_name or path.name, content_type=asset.media_type)


@require_GET
def thumbnail_video_project_asset(request: HttpRequest, project_id: int, asset_id: int) -> HttpResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    asset = project.assets.filter(id=asset_id).first()
    if not asset or not asset.thumbnail_path:
        raise Http404("Thumbnail not found")
    path = Path(asset.thumbnail_path)
    if not path.exists() or not path.is_file():
        raise Http404("Thumbnail not found")
    return FileResponse(path.open("rb"), as_attachment=False, filename=path.name, content_type="image/jpeg")


@require_POST
def delete_video_project_asset(request: HttpRequest, project_id: int, asset_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    asset = project.assets.filter(id=asset_id).first()
    if not asset:
        raise Http404("Asset not found")
    _delete_video_asset_files(asset)
    asset.delete()
    state = project.state_json or {}
    if isinstance(state, dict):
        state["clips"] = [clip for clip in state.get("clips", []) if str(clip.get("assetId", "")) != str(asset_id)]
        project.state_json = state
    project.storage_bytes = _video_project_storage_bytes(project)
    project.save(update_fields=["state_json", "storage_bytes", "updated_at"])
    return JsonResponse({"ok": True, "project": _video_project_payload(project)})


@require_GET
def dashboard_detail(request: HttpRequest, section: str):
    owner_id, guest_key = _workspace_identity(request)
    jobs = [_attach_output_urls(job) for job in actions.get_recent_jobs(200, owner_id, guest_key)]
    stats = actions.get_account_stats(owner_id, guest_key)
    stats.update(_storage_quota(request, stats))
    normalized = section if section in {"all", "active", "completed", "files", "storage"} else "all"
    if normalized == "active":
        visible_jobs = [job for job in jobs if job.get("status") in {"queued", "running"}]
    elif normalized == "completed":
        visible_jobs = [job for job in jobs if job.get("status") == "completed"]
    else:
        visible_jobs = jobs
    outputs = [
        dict(output, job_title=job.get("title"), job_id=job.get("id"), detail_url=job.get("detail_url"))
        for job in jobs
        for output in job.get("outputs", [])
    ]
    return render(
        request,
        "studio/dashboard_detail.html",
        {
            "section": normalized,
            "jobs": visible_jobs,
            "outputs": outputs,
            "account_stats": stats,
            "is_guest": not request.user.is_authenticated,
            "checkout_url": _checkout_url(request),
            "pricing_url": reverse("billing:pricing"),
            "login_url": reverse("studio:login"),
            "settings_url": reverse("studio:account_settings"),
            "avatar_url": _avatar_url(request),
            "accent_color": _accent_color(request),
            "ui_accent_color": _ui_accent_color(request),
            "theme_mode": _theme_mode(request),
        },
    )


@require_POST
def start_convert(request: HttpRequest) -> JsonResponse:
    try:
        owner_id, guest_key = _workspace_identity(request)
        upload = _require_file(request, "file")
        target_format = request.POST.get("target_format", "webp")
        _validate_convert_target(upload, target_format, getattr(request, "interface_language", "en"))
        source = _save_upload(upload, "convert")
        job = actions.start_conversion_job(
            source=source,
            original_name=upload.name or "upload",
            content_type=getattr(upload, "content_type", ""),
            target_format=target_format,
            output_name=request.POST.get("output_name", "converted"),
            image_mode=request.POST.get("image_mode", "balanced"),
            owner_id=owner_id,
            guest_key=guest_key,
        )
        return _job_json(job)
    except Exception as exc:
        return _error_json(exc)


@require_POST
def start_youtube(request: HttpRequest) -> JsonResponse:
    try:
        owner_id, guest_key = _workspace_identity(request)
        job = actions.start_youtube_job(
            url=request.POST.get("url", ""),
            mode=request.POST.get("mode", "regular"),
            owner_id=owner_id,
            guest_key=guest_key,
        )
        return _job_json(job)
    except Exception as exc:
        return _error_json(exc)


@require_POST
def start_cover(request: HttpRequest) -> JsonResponse:
    try:
        owner_id, guest_key = _workspace_identity(request)
        upload = _require_file(request, "file")
        source = _save_upload(upload, "cover")
        variants = int(request.POST.get("variants", "1") or 1)
        job = actions.start_cover_job(
            source=source,
            original_name=upload.name or "video",
            title=request.POST.get("title", ""),
            variants=variants,
            owner_id=owner_id,
            guest_key=guest_key,
        )
        return _job_json(job)
    except Exception as exc:
        return _error_json(exc)


@require_POST
def start_subtitles(request: HttpRequest) -> JsonResponse:
    try:
        owner_id, guest_key = _workspace_identity(request)
        upload = _require_file(request, "file")
        source = _save_upload(upload, "subtitles")
        job = actions.start_subtitle_job(
            source=source,
            original_name=upload.name or "video",
            title=request.POST.get("title", ""),
            style=request.POST.get("style", "pop"),
            language=request.POST.get("language", "auto"),
            owner_id=owner_id,
            guest_key=guest_key,
        )
        return _job_json(job)
    except Exception as exc:
        return _error_json(exc)


@require_POST
def start_package(request: HttpRequest) -> JsonResponse:
    try:
        owner_id, guest_key = _workspace_identity(request)
        upload = _require_file(request, "file")
        source = _save_upload(upload, "package")
        job = actions.start_package_job(
            source=source,
            original_name=upload.name or "video",
            title=request.POST.get("title", ""),
            style=request.POST.get("style", "pop"),
            language=request.POST.get("language", "auto"),
            owner_id=owner_id,
            guest_key=guest_key,
        )
        return _job_json(job)
    except Exception as exc:
        return _error_json(exc)


@require_POST
def start_resume(request: HttpRequest) -> JsonResponse:
    try:
        owner_id, guest_key = _workspace_identity(request)
        data = {field: request.POST.get(field, "").strip() for field in RESUME_FIELDS}
        data["lang"] = getattr(request, "interface_language", "en")
        photo = request.FILES.get("photo")
        if photo:
            data["photo_path"] = str(_save_upload(photo, "resume_photo"))
        job = actions.start_resume_job(data, request.POST.get("template", "1"), owner_id, guest_key)
        return _job_json(job)
    except Exception as exc:
        return _error_json(exc)


@require_GET
def job_detail(request: HttpRequest, job_id: str):
    owner_id, guest_key = _workspace_identity(request)
    job = actions.get_job(job_id, owner_id, guest_key)
    if not job:
        raise Http404("Job not found")
    language = getattr(request, "interface_language", "en")
    return render(
        request,
        "studio/job_detail.html",
        {
            "job": _localize_job(_attach_output_urls(job), language),
            "events": _localize_events(actions.get_job_events(job_id, owner_id, guest_key), language),
            "has_access": user_has_active_access(request.user),
            "active_until": active_access_until(request.user),
            "is_guest": not request.user.is_authenticated,
            "display_name": _display_name(request),
            "checkout_url": _checkout_url(request),
            "pricing_url": reverse("billing:pricing"),
            "login_url": reverse("studio:login"),
            "settings_url": reverse("studio:account_settings"),
            "avatar_url": _avatar_url(request),
            "accent_color": _accent_color(request),
            "ui_accent_color": _ui_accent_color(request),
            "theme_mode": _theme_mode(request),
        },
    )


@require_GET
def job_status(request: HttpRequest, job_id: str) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    job = actions.get_job(job_id, owner_id, guest_key)
    if not job:
        raise Http404("Job not found")
    return _job_json(job)


@require_POST
def repeat_job(request: HttpRequest, job_id: str) -> JsonResponse:
    try:
        owner_id, guest_key = _workspace_identity(request)
        job = actions.repeat_job(job_id, owner_id, guest_key)
    except Exception as exc:
        return _error_json(exc)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return _job_json(job)
    return redirect("studio:job_detail", job_id=job["id"])


@require_POST
def delete_job(request: HttpRequest, job_id: str):
    try:
        owner_id, guest_key = _workspace_identity(request)
        actions.delete_job_and_media(job_id, owner_id, guest_key)
    except Exception as exc:
        return _error_json(exc)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        stats = actions.get_account_stats(owner_id, guest_key)
        stats.update(_storage_quota(request, stats))
        return JsonResponse({"ok": True, "account_stats": stats})
    return redirect("studio:index")


@require_GET
def preview_output(request: HttpRequest, job_id: str, index: int) -> HttpResponse:
    owner_id, guest_key = _workspace_identity(request)
    output = actions.get_output(job_id, index, owner_id, guest_key)
    if not output:
        raise Http404("Output not found")
    if str(output.media_type).startswith("video/"):
        return _range_file_response(request, output.path, output.media_type, output.name)
    return FileResponse(
        output.path.open("rb"),
        as_attachment=False,
        filename=output.name,
        content_type=output.media_type,
    )


def _range_file_response(request: HttpRequest, path: Path, content_type: str, filename: str) -> HttpResponse:
    file_size = path.stat().st_size
    range_header = request.headers.get("Range", "").strip()
    if not range_header.startswith("bytes="):
        response = FileResponse(path.open("rb"), as_attachment=False, filename=filename, content_type=content_type)
        response["Accept-Ranges"] = "bytes"
        response["Content-Length"] = str(file_size)
        return response

    start_text, _, end_text = range_header.removeprefix("bytes=").partition("-")
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
        else:
            suffix_length = int(end_text)
            start = max(0, file_size - suffix_length)
            end = file_size - 1
    except ValueError:
        start, end = 0, file_size - 1

    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    length = end - start + 1

    def stream():
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    response = StreamingHttpResponse(stream(), status=206, content_type=content_type)
    response["Accept-Ranges"] = "bytes"
    response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    response["Content-Length"] = str(length)
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@require_GET
def download_output(request: HttpRequest, job_id: str, index: int) -> FileResponse:
    owner_id, guest_key = _workspace_identity(request)
    output = actions.get_output(job_id, index, owner_id, guest_key)
    if not output:
        raise Http404("Output not found")
    if not user_has_active_access(request.user):
        return redirect(_checkout_url(request))
    return FileResponse(
        output.path.open("rb"),
        as_attachment=True,
        filename=output.name,
        content_type=output.media_type,
    )


@require_GET
def download_all_outputs(request: HttpRequest, job_id: str) -> FileResponse:
    owner_id, guest_key = _workspace_identity(request)
    if not actions.get_job(job_id, owner_id, guest_key):
        raise Http404("Job not found")
    if not user_has_active_access(request.user):
        return redirect(_checkout_url(request))
    try:
        archive = actions.zip_job_outputs(job_id, owner_id, guest_key)
    except Exception as exc:
        raise Http404(str(exc)) from exc
    return FileResponse(
        archive.open("rb"),
        as_attachment=True,
        filename=archive.name,
        content_type="application/zip",
    )


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def _workspace_identity(request: HttpRequest) -> tuple[int | None, str]:
    if request.user.is_authenticated:
        return request.user.id, ""
    return None, _guest_key(request)


def _guest_key(request: HttpRequest) -> str:
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def _video_project_queryset(owner_id: int | None, guest_key: str):
    queryset = VideoEditorProject.objects.all()
    if owner_id:
        return queryset.filter(owner_id=owner_id)
    return queryset.filter(owner__isnull=True, guest_key=guest_key)


def _video_project_payload(project: VideoEditorProject, include_state: bool = True) -> dict[str, object]:
    state = project.state_json or {}
    layers = state.get("layers") if isinstance(state.get("layers"), list) else []
    assets = list(project.assets.all()) if project else []
    first_thumb = next((asset for asset in assets if asset.thumbnail_path), None)
    payload: dict[str, object] = {
        "id": project.id,
        "title": project.title,
        "thumbnail": reverse("studio:video_project_asset_thumbnail", args=[project.id, first_thumb.id]) if first_thumb else (state.get("thumbnail", "") if isinstance(state, dict) else ""),
        "aspect": state.get("aspect", "9 / 16") if isinstance(state, dict) else "9 / 16",
        "clip_name": state.get("clipName", "") if isinstance(state, dict) else "",
        "layer_count": len(state.get("clips", []) if isinstance(state.get("clips"), list) else layers),
        "track_count": len(state.get("tracks", []) if isinstance(state.get("tracks"), list) else []),
        "storage_bytes": project.storage_bytes,
        "storage_text": human_size(project.storage_bytes),
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "assets": [_video_asset_payload(asset) for asset in assets],
    }
    if include_state:
        payload["state"] = project.state_json or {}
    return payload


def _json_body(request: HttpRequest) -> dict[str, object]:
    if not request.body:
        return {}
    try:
        value = json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _video_asset_payload(asset: VideoEditorAsset) -> dict[str, object]:
    payload = {
        "id": asset.id,
        "kind": asset.kind,
        "name": asset.original_name,
        "media_type": asset.media_type,
        "size": asset.size,
        "size_text": human_size(asset.size),
        "duration": asset.duration,
        "preview_url": reverse("studio:video_project_asset_preview", args=[asset.project_id, asset.id]),
        "delete_url": reverse("studio:delete_video_project_asset", args=[asset.project_id, asset.id]),
        "thumbnail_url": "",
    }
    if asset.thumbnail_path:
        payload["thumbnail_url"] = reverse("studio:video_project_asset_thumbnail", args=[asset.project_id, asset.id])
    return payload


def _video_project_storage_bytes(project: VideoEditorProject) -> int:
    return _json_size(project.state_json or {}) + sum(asset.size + _path_size(asset.thumbnail_path) for asset in project.assets.all())


def _path_size(path_text: str) -> int:
    if not path_text:
        return 0
    path = Path(path_text)
    return path.stat().st_size if path.exists() and path.is_file() else 0


def _video_project_media_dir(project: VideoEditorProject) -> Path:
    owner = f"user_{project.owner_id}" if project.owner_id else f"guest_{project.guest_key or 'anon'}"
    return settings.storage_dir / "django_video_projects" / owner / str(project.id)


def _save_project_thumbnail(data_url: str, target_dir: Path) -> Path:
    raw = data_url.split(",", 1)[1] if "," in data_url else data_url
    image = Image.open(BytesIO(b64decode(raw))).convert("RGB")
    image.thumbnail((960, 540))
    path = target_dir / f"thumb_{uuid.uuid4().hex[:12]}.jpg"
    image.save(path, "JPEG", quality=82, optimize=True)
    return path


def _delete_video_asset_files(asset: VideoEditorAsset) -> None:
    for path_text in (asset.file_path, asset.thumbnail_path):
        if not path_text:
            continue
        path = Path(path_text)
        try:
            if path.resolve().is_relative_to(settings.storage_dir.resolve()) and path.exists() and path.is_file():
                path.unlink()
        except Exception:
            pass


def _delete_video_project_media(project: VideoEditorProject) -> None:
    for asset in project.assets.all():
        _delete_video_asset_files(asset)
    directory = _video_project_media_dir(project)
    try:
        if directory.resolve().is_relative_to(settings.storage_dir.resolve()) and directory.exists():
            shutil.rmtree(directory)
    except Exception:
        pass


def _clean_project_title(value: str) -> str:
    title = " ".join(value.strip().split())
    return (title or "Новый проект")[:180]


def _transfer_guest_video_projects(guest_key: str, user) -> None:
    if not guest_key:
        return
    VideoEditorProject.objects.filter(owner__isnull=True, guest_key=guest_key).update(owner=user, guest_key="")


def _checkout_url(request: HttpRequest) -> str:
    return f"{reverse('billing:checkout')}?{urlencode({'next': request.get_full_path()})}"


def _display_name(request: HttpRequest) -> str:
    if request.user.is_authenticated:
        return request.user.first_name or request.user.email or "CherryX user"
    return "Guest workspace"


def _avatar_url(request: HttpRequest) -> str:
    if request.user.is_authenticated:
        try:
            if request.user.studio_profile.avatar_path:
                return reverse("studio:account_avatar")
            if request.user.studio_profile.avatar_url:
                return request.user.studio_profile.avatar_url
        except AccountProfile.DoesNotExist:
            pass
    return "https://api.iconify.design/lucide/circle-user-round.svg?color=%232563eb&width=80&height=80"


def _accent_color(request: HttpRequest) -> str:
    if request.user.is_authenticated:
        try:
            return request.user.studio_profile.accent_color or "#2563eb"
        except AccountProfile.DoesNotExist:
            pass
    return "#2563eb"


def _theme_mode(request: HttpRequest) -> str:
    if request.user.is_authenticated:
        try:
            mode = request.user.studio_profile.theme_mode or "light"
            return mode if mode in {"light", "soft", "dark"} else "light"
        except AccountProfile.DoesNotExist:
            pass
    return "light"


def _ui_accent_color(request: HttpRequest) -> str:
    accent = _accent_color(request)
    if _theme_mode(request) == "dark" and accent.lower() in {"#111827", "#000000", "black"}:
        return "#7aa2ff"
    return accent


def _auth_context(request: HttpRequest) -> dict[str, str]:
    return {
        "accent_color": _accent_color(request),
        "ui_accent_color": _ui_accent_color(request),
        "theme_mode": _theme_mode(request),
    }


def _subscription_meter(request: HttpRequest) -> dict[str, object]:
    if not request.user.is_authenticated:
        return {"percent": 0, "days_left": 0}
    try:
        access = request.user.billing_access
    except Exception:
        return {"percent": 0, "days_left": 0}
    now = timezone.now()
    if access.active_until <= now:
        return {"percent": 0, "days_left": 0}
    total_seconds = max((access.active_until - access.created_at).total_seconds(), 1)
    left_seconds = max((access.active_until - now).total_seconds(), 0)
    percent = max(0, min(100, round((left_seconds / total_seconds) * 100)))
    days_left = max(1, int((left_seconds + 86399) // 86400))
    return {"percent": percent, "days_left": days_left}


def _subscription_panel(request: HttpRequest, account_stats: dict[str, object], language: str) -> dict[str, object]:
    now = timezone.now()
    access = None
    if request.user.is_authenticated:
        try:
            access = request.user.billing_access
        except Exception:
            access = None
    current_plan = get_plan(access.plan_code if access else "starter")
    active_until = access.active_until if access and access.active_until > now else None
    left_seconds = max((active_until - now).total_seconds(), 0) if active_until else 0
    days_left = int((left_seconds + 86399) // 86400) if left_seconds else 0
    remaining_value_cents = 0
    if active_until and current_plan.period_days:
        remaining_value_cents = round(current_plan.price_cents * min(1, left_seconds / (current_plan.period_days * 86400)))
    plan_payload = []
    for plan in PLANS:
        localized = localized_plan(plan, language)
        due_cents = max(0, plan.price_cents - remaining_value_cents)
        plan_payload.append(
            {
                **vars(localized),
                "checkout_url": f"{reverse('billing:checkout')}?{urlencode({'plan': plan.code, 'next': request.get_full_path()})}",
                "due_cents": due_cents,
                "due_display": f"${due_cents // 100}" if due_cents % 100 == 0 else f"${due_cents / 100:.2f}",
                "is_current": plan.code == current_plan.code,
            }
        )
    return {
        "current_plan": localized_plan(current_plan, language),
        "plans": plan_payload,
        "active_until": active_until,
        "days_left": days_left,
        "remaining_value_cents": remaining_value_cents,
        "remaining_value_display": f"${remaining_value_cents // 100}" if remaining_value_cents % 100 == 0 else f"${remaining_value_cents / 100:.2f}",
        "storage_used_text": account_stats.get("total_output_size_text", ""),
        "storage_available_text": account_stats.get("storage_available_text", ""),
        "storage_percent": account_stats.get("storage_percent", 0),
    }


def _storage_quota(request: HttpRequest, account_stats: dict[str, object]) -> dict[str, object]:
    used = int(account_stats.get("total_output_size") or 0)
    owner_id, guest_key = _workspace_identity(request)
    project_bytes = sum(_video_project_queryset(owner_id, guest_key).values_list("storage_bytes", flat=True))
    used += int(project_bytes or 0)
    plan_code = "starter"
    if request.user.is_authenticated:
        try:
            plan_code = request.user.billing_access.plan_code
        except Exception:
            plan_code = "starter"
    limit = get_plan(plan_code).storage_bytes
    percent = 0 if limit <= 0 else max(0, min(100, round((used / limit) * 100)))
    return {
        "storage_limit": limit,
        "storage_limit_text": human_size(limit),
        "storage_available": max(0, limit - used),
        "storage_available_text": human_size(max(0, limit - used)),
        "storage_percent": percent,
        "total_output_size_text": f"{human_size(used)} / {human_size(limit)}",
    }


def _language_options_for_form(form: AccountSettingsForm) -> list[dict[str, object]]:
    current = form["interface_language"].value() or "en"
    return [
        {
            "code": value,
            "native": label,
            "flag": {
                "en": "https://flagcdn.com/gb.svg",
                "ru": "https://flagcdn.com/ru.svg",
                "uk": "https://flagcdn.com/ua.svg",
                "fr": "https://flagcdn.com/fr.svg",
                "de": "https://flagcdn.com/de.svg",
                "es": "https://flagcdn.com/es.svg",
                "ka": "https://flagcdn.com/ge.svg",
                "hy": "https://flagcdn.com/am.svg",
                "it": "https://flagcdn.com/it.svg",
            }.get(value, "https://flagcdn.com/gb.svg"),
            "active": value == current,
        }
        for value, label in form.fields["interface_language"].choices
    ]


def _localized_image_modes(language: str) -> list[tuple[str, str]]:
    labels = {
        "light": {"en": "Light file", "ru": "Лёгкий файл", "uk": "Легкий файл", "fr": "Fichier léger", "de": "Leichte Datei", "es": "Archivo ligero", "ka": "მსუბუქი ფაილი", "hy": "Թեթև ֆայլ", "it": "File leggero"},
        "balanced": {"en": "Balanced", "ru": "Баланс", "uk": "Баланс", "fr": "Équilibre", "de": "Ausgewogen", "es": "Equilibrado", "ka": "ბალანსი", "hy": "Բալանս", "it": "Bilanciato"},
        "quality": {"en": "Quality", "ru": "Качество", "uk": "Якість", "fr": "Qualité", "de": "Qualität", "es": "Calidad", "ka": "ხარისხი", "hy": "Որակ", "it": "Qualità"},
    }
    return [(value, labels.get(value, {}).get(language, labels.get(value, {}).get("en", label))) for value, label in actions.IMAGE_MODE_CHOICES]


def _localized_youtube_modes(language: str) -> list[tuple[str, str]]:
    labels = {
        "download": {"en": "Download MP4", "ru": "Скачать MP4", "uk": "Завантажити MP4", "fr": "Télécharger MP4", "de": "MP4 herunterladen", "es": "Descargar MP4", "ka": "MP4 ჩამოტვირთვა", "hy": "Ներբեռնել MP4", "it": "Scarica MP4"},
        "cover": {"en": "PNG cover", "ru": "PNG-обложка", "uk": "PNG-обкладинка", "fr": "Couverture PNG", "de": "PNG-Cover", "es": "Portada PNG", "ka": "PNG ყდა", "hy": "PNG շապիկ", "it": "Copertina PNG"},
    }
    return [(value, labels.get(value, {}).get(language, labels.get(value, {}).get("en", label))) for value, label in actions.YOUTUBE_MODE_CHOICES]


def _localized_subtitle_languages(language: str) -> list[tuple[str, str]]:
    labels = {
        "auto": {"en": "Auto", "ru": "Авто", "uk": "Авто", "fr": "Auto", "de": "Auto", "es": "Auto", "ka": "ავტო", "hy": "Ավտո", "it": "Auto"},
        "ru": {"en": "Russian", "ru": "Русский", "uk": "Російська", "fr": "Russe", "de": "Russisch", "es": "Ruso", "ka": "რუსული", "hy": "Ռուսերեն", "it": "Russo"},
        "uk": {"en": "Ukrainian", "ru": "Украинский", "uk": "Українська", "fr": "Ukrainien", "de": "Ukrainisch", "es": "Ucraniano", "ka": "უკრაინული", "hy": "Ուկրաիներեն", "it": "Ucraino"},
        "en": {"en": "English", "ru": "Английский", "uk": "Англійська", "fr": "Anglais", "de": "Englisch", "es": "Inglés", "ka": "ინგლისური", "hy": "Անգլերեն", "it": "Inglese"},
    }
    return [(value, labels.get(value, {}).get(language, labels.get(value, {}).get("en", label))) for value, label in actions.SUBTITLE_LANGUAGE_CHOICES]


def _localized_resume_templates(language: str) -> list[tuple[str, str]]:
    labels = {
        "1": {"en": "Classic", "ru": "Классика", "uk": "Класика", "fr": "Classique", "de": "Klassisch", "es": "Clásico", "ka": "კლასიკური", "hy": "Դասական", "it": "Classico"},
        "2": {"en": "Executive", "ru": "Руководитель", "uk": "Керівник", "fr": "Direction", "de": "Executive", "es": "Ejecutivo", "ka": "აღმასრულებელი", "hy": "Ղեկավար", "it": "Executive"},
        "3": {"en": "Creative", "ru": "Креатив", "uk": "Креатив", "fr": "Créatif", "de": "Kreativ", "es": "Creativo", "ka": "კრეატიული", "hy": "Ստեղծարար", "it": "Creativo"},
        "4": {"en": "Modern", "ru": "Современный", "uk": "Сучасний", "fr": "Moderne", "de": "Modern", "es": "Moderno", "ka": "თანამედროვე", "hy": "Ժամանակակից", "it": "Moderno"},
        "5": {"en": "Tech", "ru": "Техно", "uk": "Техно", "fr": "Tech", "de": "Tech", "es": "Tech", "ka": "ტექ", "hy": "Տեխ", "it": "Tech"},
        "6": {"en": "Minimal", "ru": "Минимал", "uk": "Мінімал", "fr": "Minimal", "de": "Minimal", "es": "Minimal", "ka": "მინიმალი", "hy": "Մինիմալ", "it": "Minimal"},
        "7": {"en": "Premium", "ru": "Премиум", "uk": "Преміум", "fr": "Premium", "de": "Premium", "es": "Premium", "ka": "პრემიუმი", "hy": "Պրեմիում", "it": "Premium"},
        "8": {"en": "Focus", "ru": "Фокус", "uk": "Фокус", "fr": "Focus", "de": "Fokus", "es": "Enfoque", "ka": "ფოკუსი", "hy": "Ֆոկուս", "it": "Focus"},
        "9": {"en": "Nordic", "ru": "Сканди", "uk": "Сканди", "fr": "Nordique", "de": "Nordisch", "es": "Nórdico", "ka": "ნორდიკული", "hy": "Նորդիկ", "it": "Nordico"},
        "10": {"en": "Legal", "ru": "Юридический", "uk": "Юридичний", "fr": "Juridique", "de": "Legal", "es": "Legal", "ka": "იურიდიული", "hy": "Իրավական", "it": "Legale"},
        "11": {"en": "Startup", "ru": "Стартап", "uk": "Стартап", "fr": "Startup", "de": "Startup", "es": "Startup", "ka": "სტარტაპი", "hy": "Ստարտափ", "it": "Startup"},
        "12": {"en": "Finance", "ru": "Финансы", "uk": "Фінанси", "fr": "Finance", "de": "Finanzen", "es": "Finanzas", "ka": "ფინანსები", "hy": "Ֆինանսներ", "it": "Finanza"},
        "13": {"en": "Academic", "ru": "Академический", "uk": "Академічний", "fr": "Académique", "de": "Akademisch", "es": "Académico", "ka": "აკადემიური", "hy": "Ակադեմիական", "it": "Accademico"},
        "14": {"en": "Compact", "ru": "Компактный", "uk": "Компактний", "fr": "Compact", "de": "Kompakt", "es": "Compacto", "ka": "კომპაქტური", "hy": "Կոմպակտ", "it": "Compatto"},
    }
    return [(value, labels.get(value, {}).get(language, labels.get(value, {}).get("en", label))) for value, label in actions.RESUME_TEMPLATE_CHOICES]


def _localized_value(key: str, language: str, fallback: str) -> str:
    values = {
        "queued": {"en": "Queued", "ru": "Очередь", "uk": "Черга", "fr": "En file", "de": "Warteschlange", "es": "En cola", "ka": "რიგშია", "hy": "Հերթում", "it": "In coda"},
        "running": {"en": "Running", "ru": "В работе", "uk": "В роботі", "fr": "En cours", "de": "Läuft", "es": "En curso", "ka": "მიმდინარეობს", "hy": "Ընթացքում", "it": "In corso"},
        "completed": {"en": "Completed", "ru": "Готово", "uk": "Готово", "fr": "Terminé", "de": "Abgeschlossen", "es": "Completado", "ka": "დასრულდა", "hy": "Ավարտված", "it": "Completato"},
        "failed": {"en": "Failed", "ru": "Ошибка", "uk": "Помилка", "fr": "Échec", "de": "Fehler", "es": "Error", "ka": "შეცდომა", "hy": "Սխալ", "it": "Errore"},
        "convert": {"en": "Convert", "ru": "Конвертер", "uk": "Конвертер", "fr": "Convertir", "de": "Konvertieren", "es": "Convertir", "ka": "კონვერტაცია", "hy": "Փոխարկել", "it": "Converti"},
        "image": {"en": "Image", "ru": "Изображение", "uk": "Зображення", "fr": "Image", "de": "Bild", "es": "Imagen", "ka": "სურათი", "hy": "Պատկեր", "it": "Immagine"},
        "video": {"en": "Video", "ru": "Видео", "uk": "Відео", "fr": "Vidéo", "de": "Video", "es": "Vídeo", "ka": "ვიდეო", "hy": "Տեսանյութ", "it": "Video"},
        "ready": {"en": "Done", "ru": "Готово", "uk": "Готово", "fr": "Terminé", "de": "Fertig", "es": "Listo", "ka": "მზადაა", "hy": "Պատրաստ", "it": "Pronto"},
        "queued_msg": {"en": "Queued", "ru": "В очереди", "uk": "У черзі", "fr": "En file", "de": "In der Warteschlange", "es": "En cola", "ka": "რიგშია", "hy": "Հերթում է", "it": "In coda"},
        "starting": {"en": "Starting task", "ru": "Стартую задачу", "uk": "Запускаю задачу", "fr": "Démarrage de la tâche", "de": "Aufgabe startet", "es": "Iniciando tarea", "ka": "ამოცანა იწყება", "hy": "Առաջադրանքը սկսվում է", "it": "Avvio attività"},
        "convert_image": {"en": "Converting image", "ru": "Конвертирую изображение", "uk": "Конвертую зображення", "fr": "Conversion de l'image", "de": "Bild wird konvertiert", "es": "Convirtiendo imagen", "ka": "სურათი კონვერტირდება", "hy": "Պատկերը փոխարկվում է", "it": "Conversione immagine"},
        "read_video": {"en": "Reading video parameters", "ru": "Читаю параметры видео", "uk": "Читаю параметри відео", "fr": "Lecture des paramètres vidéo", "de": "Videoparameter werden gelesen", "es": "Leyendo parámetros de vídeo", "ka": "ვიდეო პარამეტრების კითხვა", "hy": "Տեսանյութի պարամետրերի ընթերցում", "it": "Lettura parametri video"},
        "ready_file": {"en": "File ready", "ru": "Файл готов", "uk": "Файл готовий", "fr": "Fichier prêt", "de": "Datei bereit", "es": "Archivo listo", "ka": "ფაილი მზადაა", "hy": "Ֆայլը պատրաստ է", "it": "File pronto"},
        "interrupted": {"en": "Task interrupted", "ru": "Задача прервана", "uk": "Задачу перервано", "fr": "Tâche interrompue", "de": "Aufgabe unterbrochen", "es": "Tarea interrumpida", "ka": "ამოცანა შეწყდა", "hy": "Առաջադրանքը ընդհատվեց", "it": "Attività interrotta"},
        "server_restarted": {"en": "The server restarted before the task finished.", "ru": "Сервер был перезапущен до завершения задачи.", "uk": "Сервер було перезапущено до завершення задачі.", "fr": "Le serveur a redémarré avant la fin de la tâche.", "de": "Der Server wurde vor Abschluss der Aufgabe neu gestartet.", "es": "El servidor se reinició antes de finalizar la tarea.", "ka": "სერვერი ამოცანის დასრულებამდე გადაიტვირთა.", "hy": "Սերվերը վերագործարկվեց մինչև առաջադրանքի ավարտը։", "it": "Il server si è riavviato prima della fine dell'attività."},
    }
    return values.get(key, {}).get(language, values.get(key, {}).get("en", fallback))


def _localize_runtime_text(text: str, language: str) -> str:
    if not text:
        return text
    replacements = {
        "В очереди": _localized_value("queued_msg", language, "Queued"),
        "Стартую задачу": _localized_value("starting", language, "Starting task"),
        "Конвертирую изображение": _localized_value("convert_image", language, "Converting image"),
        "Читаю параметры видео": _localized_value("read_video", language, "Reading video parameters"),
        "Задача прервана": _localized_value("interrupted", language, "Task interrupted"),
        "Сервер был перезапущен до завершения задачи.": _localized_value("server_restarted", language, "The server restarted before the task finished."),
        "Ошибка": _localized_value("failed", language, "Failed"),
    }
    value = str(text)
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = value.replace("Файл готов", _localized_value("ready_file", language, "File ready"))
    value = value.replace("Готово", _localized_value("ready", language, "Done"))
    value = value.replace("Изображение", _localized_value("image", language, "Image"))
    value = value.replace("Видео", _localized_value("video", language, "Video"))
    value = value.replace("Конвертация", _localized_value("convert", language, "Convert"))
    return value


def _localize_job(job: dict, language: str) -> dict:
    prepared = dict(job)
    prepared["title"] = _localize_runtime_text(str(prepared.get("title") or ""), language)
    prepared["message"] = _localize_runtime_text(str(prepared.get("message") or ""), language)
    prepared["error"] = _localize_runtime_text(str(prepared.get("error") or ""), language)
    prepared["status_label"] = _localized_value(str(prepared.get("status") or ""), language, str(prepared.get("status") or ""))
    prepared["kind_label"] = _localized_value(str(prepared.get("kind") or ""), language, str(prepared.get("kind") or ""))
    outputs = []
    for output in prepared.get("outputs", []):
        item = dict(output)
        item["label"] = _localize_runtime_text(str(item.get("label") or ""), language)
        outputs.append(item)
    prepared["outputs"] = outputs
    return prepared


def _localize_events(events: list[dict], language: str) -> list[dict]:
    localized = []
    for event in events:
        item = dict(event)
        item["status_label"] = _localized_value(str(item.get("status") or ""), language, str(item.get("status") or ""))
        item["message"] = _localize_runtime_text(str(item.get("message") or ""), language)
        localized.append(item)
    return localized


def _require_file(request: HttpRequest, field: str):
    upload = request.FILES.get(field)
    if not upload:
        raise ValueError("Файл не выбран")
    return upload


def _validate_convert_target(upload, target_format: str, language: str) -> None:
    image_formats = {value for value, _ in actions.IMAGE_FORMAT_CHOICES}
    video_formats = {value for value, _ in actions.VIDEO_FORMAT_CHOICES}
    kind = _upload_kind(upload)
    if kind == "image" and target_format in video_formats:
        raise ValueError(_localized_format_error("image", language))
    if kind == "video" and target_format in image_formats:
        raise ValueError(_localized_format_error("video", language))


def _upload_kind(upload) -> str:
    content_type = str(getattr(upload, "content_type", "") or "").lower()
    if content_type.startswith("video/"):
        return "video"
    if content_type.startswith("image/"):
        return "image"
    suffix = Path(getattr(upload, "name", "") or "").suffix.lower()
    if suffix in {".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi", ".wmv", ".flv"}:
        return "video"
    return "image"


def _localized_format_error(kind: str, language: str) -> str:
    messages = {
        "image": {
            "en": "Images can only be converted to image formats.",
            "ru": "Фото можно конвертировать только в форматы изображений.",
            "uk": "Фото можна конвертувати тільки у формати зображень.",
            "fr": "Les images ne peuvent être converties qu'en formats image.",
            "de": "Bilder können nur in Bildformate konvertiert werden.",
            "es": "Las imágenes solo se pueden convertir a formatos de imagen.",
            "ka": "სურათების კონვერტაცია მხოლოდ სურათის ფორმატებში შეიძლება.",
            "hy": "Պատկերները կարելի է փոխարկել միայն պատկերի ձևաչափերի։",
            "it": "Le immagini possono essere convertite solo in formati immagine.",
        },
        "video": {
            "en": "Videos can only be converted to video formats.",
            "ru": "Видео можно конвертировать только в видеоформаты.",
            "uk": "Відео можна конвертувати тільки у відеоформати.",
            "fr": "Les vidéos ne peuvent être converties qu'en formats vidéo.",
            "de": "Videos können nur in Videoformate konvertiert werden.",
            "es": "Los vídeos solo se pueden convertir a formatos de vídeo.",
            "ka": "ვიდეოს კონვერტაცია მხოლოდ ვიდეო ფორმატებში შეიძლება.",
            "hy": "Տեսանյութերը կարելի է փոխարկել միայն տեսանյութի ձևաչափերի։",
            "it": "I video possono essere convertiti solo in formati video.",
        },
    }
    return messages[kind].get(clean_language(language), messages[kind]["en"])


def _save_upload(upload, group: str) -> Path:
    base = clean_base_name(upload.name or "upload", "upload")
    suffix = Path(upload.name or "").suffix[:16]
    target_dir = settings.storage_dir / "django_uploads" / group
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{uuid.uuid4().hex[:12]}_{base}{suffix}"
    with path.open("wb") as destination:
        for chunk in upload.chunks():
            destination.write(chunk)
    return path


def _save_avatar_upload(upload, user_id: int) -> Path:
    suffix = Path(upload.name or "").suffix.lower()[:8] or ".jpg"
    target_dir = settings.storage_dir / "django_uploads" / "avatars" / str(user_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"avatar_{uuid.uuid4().hex[:12]}{suffix}"
    with path.open("wb") as destination:
        for chunk in upload.chunks():
            destination.write(chunk)
    return path


def _save_avatar_crop(data_url: str, user_id: int) -> Path:
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw = b64decode(data_url)
    image = Image.open(BytesIO(raw)).convert("RGB")
    image.thumbnail((1200, 1200))
    target_dir = settings.storage_dir / "django_uploads" / "avatars" / str(user_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"avatar_{uuid.uuid4().hex[:12]}.jpg"
    image.save(path, format="JPEG", quality=92, optimize=True)
    return path


def _job_json(job: dict) -> JsonResponse:
    return JsonResponse({"job": _attach_output_urls(job)})


def _error_json(exc: Exception, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": str(exc) or exc.__class__.__name__}, status=status)


def _attach_output_urls(job: dict) -> dict:
    prepared = dict(job)
    prepared["detail_url"] = reverse("studio:job_detail", args=[job["id"]])
    prepared["download_all_url"] = reverse("studio:download_all_outputs", args=[job["id"]])
    prepared["delete_url"] = reverse("studio:delete_job", args=[job["id"]])
    prepared["repeat_url"] = reverse("studio:repeat_job", args=[job["id"]])
    outputs = []
    for output in job.get("outputs", []):
        item = dict(output)
        item["url"] = reverse("studio:download_output", args=[job["id"], item["index"]])
        item["preview_url"] = reverse("studio:preview_output", args=[job["id"], item["index"]])
        item["preview_kind"] = _preview_kind(item)
        outputs.append(item)
    prepared["outputs"] = outputs
    return prepared


def _preview_kind(output: dict) -> str:
    media_type = str(output.get("media_type") or "")
    name = str(output.get("name") or "").lower()
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("video/"):
        return "video"
    if media_type == "application/pdf" or name.endswith(".pdf"):
        return "embed"
    if media_type.startswith("text/") or name.endswith((".txt", ".ass", ".srt", ".json", ".csv")):
        return "embed"
    return "download"
