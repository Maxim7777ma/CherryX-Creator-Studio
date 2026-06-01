from __future__ import annotations

from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
import json
import mimetypes
import secrets
import shutil
import subprocess
import threading
import time
import uuid

from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from PIL import Image, ImageOps

from billing.plans import PLANS, get_plan
from billing.services import active_access_until, prorated_due_cents, transfer_guest_workspace, user_has_active_access
from src import web_actions as actions
from src.config import get_settings
from src.image_tools import clean_base_name, human_size
from src.video_tools import ffmpeg_path
from .forms import AccountSettingsForm, EmailLoginForm, RegisterForm
from .localization import app_messages, clean_language, localized_plan, translate
from .models import AccountProfile, DesignerAsset, DesignerProject, JobEventRecord, JobOutputRecord, JobRecord, VideoEditorAsset, VideoEditorProject, WorkspaceShare


settings = get_settings()
_video_export_executor = ThreadPoolExecutor(max_workers=2)
_video_export_jobs: dict[str, dict[str, object]] = {}
_video_export_lock = threading.RLock()
_video_export_processes: dict[str, subprocess.Popen] = {}
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
        return redirect(_safe_next_url(request) or reverse("studio:index"))
    form = RegisterForm(request.POST or None, language=getattr(request, "interface_language", "en"))
    if request.method == "POST" and form.is_valid():
        guest_key = _guest_key(request)
        user = form.save()
        login(request, user)
        transfer_guest_workspace(guest_key, user)
        _transfer_guest_video_projects(guest_key, user)
        _transfer_guest_design_projects(guest_key, user)
        _accept_pending_workspace_shares(user)
        return redirect(_safe_next_url(request) or reverse("studio:index"))
    return render(request, "studio/auth.html", {**_auth_context(request), "form": form, "mode": "register"})


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest):
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request) or reverse("studio:index"))
    form = EmailLoginForm(request.POST or None, language=getattr(request, "interface_language", "en"))
    if request.method == "POST" and form.is_valid():
        guest_key = _guest_key(request)
        login(request, form.cleaned_data["user"])
        transfer_guest_workspace(guest_key, form.cleaned_data["user"])
        _transfer_guest_video_projects(guest_key, form.cleaned_data["user"])
        _transfer_guest_design_projects(guest_key, form.cleaned_data["user"])
        _accept_pending_workspace_shares(form.cleaned_data["user"])
        return redirect(_safe_next_url(request) or reverse("studio:index"))
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
@ensure_csrf_cookie
def designer_mode(request: HttpRequest):
    language = getattr(request, "interface_language", "en")
    owner_id, guest_key = _workspace_identity(request)
    project = None
    project_id = request.GET.get("project", "")
    if project_id.isdigit():
        project = _design_project_queryset(owner_id, guest_key).filter(id=int(project_id)).first()
    return render(
        request,
        "studio/designer.html",
        {
            "designer_url": reverse("studio:designer"),
            "design_projects_url": reverse("studio:design_project_list"),
            "design_projects_api_url": reverse("studio:design_projects"),
            "current_design_project": _design_project_payload(project, owner_id=owner_id, guest_key=guest_key) if project else None,
            "designer_fullscreen": True,
            "accent_color": _accent_color(request),
            "ui_accent_color": _ui_accent_color(request),
            "theme_mode": _theme_mode(request),
            "app_messages": app_messages(language),
        },
    )


@require_GET
@ensure_csrf_cookie
def design_project_list(request: HttpRequest):
    owner_id, guest_key = _workspace_identity(request)
    projects = [_design_project_payload(project, include_state=False, owner_id=owner_id, guest_key=guest_key) for project in _design_project_queryset(owner_id, guest_key)[:120]]
    return render(
        request,
        "studio/design_projects.html",
        {
            "design_projects": projects,
            "designer_url": reverse("studio:designer"),
            "design_projects_api_url": reverse("studio:design_projects"),
            "accent_color": _accent_color(request),
            "ui_accent_color": _ui_accent_color(request),
            "theme_mode": _theme_mode(request),
            "app_messages": app_messages(getattr(request, "interface_language", "en")),
        },
    )


@require_GET
def design_projects(request: HttpRequest) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    projects = [_design_project_payload(project, include_state=False, owner_id=owner_id, guest_key=guest_key) for project in _design_project_queryset(owner_id, guest_key)[:80]]
    return JsonResponse({"projects": projects})


@require_POST
def create_design_project(request: HttpRequest) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    data = _json_body(request)
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    title = _clean_project_title(str(data.get("title") or state.get("title") or "New design"))
    project = DesignerProject.objects.create(
        owner=request.user if request.user.is_authenticated else None,
        guest_key="" if owner_id else guest_key,
        title=title,
        state_json=state,
        storage_bytes=_json_size(state),
    )
    preview = str(data.get("preview") or "")
    if preview.startswith("data:image/"):
        if project.preview_path:
            try:
                old_preview = Path(project.preview_path)
                if old_preview.resolve().is_relative_to(settings.storage_dir.resolve()) and old_preview.exists() and old_preview.is_file():
                    old_preview.unlink()
            except Exception:
                pass
        project.preview_path = str(_save_design_project_preview(preview, _design_project_media_dir(project)))
    project.storage_bytes = _design_project_storage_bytes(project)
    project.save(update_fields=["preview_path", "storage_bytes", "updated_at"])
    return JsonResponse({"project": _design_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


@require_GET
def design_project_detail(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _design_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Design project not found")
    return JsonResponse({"project": _design_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


@require_POST
def save_design_project(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _design_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Design project not found")
    if not _resource_can_edit(WorkspaceShare.RESOURCE_DESIGN, project, owner_id, guest_key):
        raise Http404("Design project not found")
    data = _json_body(request)
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    title = _clean_project_title(str(data.get("title") or state.get("title") or project.title))
    project.title = title
    project.state_json = state
    preview = str(data.get("preview") or "")
    if preview.startswith("data:image/"):
        if project.preview_path:
            try:
                old_preview = Path(project.preview_path)
                if old_preview.resolve().is_relative_to(settings.storage_dir.resolve()) and old_preview.exists() and old_preview.is_file():
                    old_preview.unlink()
            except Exception:
                pass
        project.preview_path = str(_save_design_project_preview(preview, _design_project_media_dir(project)))
    project.storage_bytes = _design_project_storage_bytes(project)
    project.save(update_fields=["title", "state_json", "preview_path", "storage_bytes", "updated_at"])
    return JsonResponse({"project": _design_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


@require_POST
def rename_design_project(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _design_owner_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Design project not found")
    data = _json_body(request)
    project.title = _clean_project_title(str(data.get("title") or project.title))
    project.save(update_fields=["title", "updated_at"])
    return JsonResponse({"project": _design_project_payload(project, include_state=False, owner_id=owner_id, guest_key=guest_key)})


@require_POST
def duplicate_design_project(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    source = _design_owner_queryset(owner_id, guest_key).prefetch_related("assets").filter(id=project_id).first()
    if not source:
        raise Http404("Design project not found")
    copy = DesignerProject.objects.create(
        owner=source.owner,
        guest_key=source.guest_key,
        title=_clean_project_title(f"Copy of {source.title}"),
        state_json=source.state_json or {},
        preview_path="",
    )
    target_dir = _design_project_media_dir(copy)
    target_dir.mkdir(parents=True, exist_ok=True)
    asset_id_map: dict[str, int] = {}
    for asset in source.assets.all():
        source_path = Path(asset.file_path)
        if not source_path.exists() or not source_path.is_file():
            continue
        target_path = target_dir / f"{uuid.uuid4().hex[:12]}_{source_path.name}"
        shutil.copy2(source_path, target_path)
        new_asset = DesignerAsset.objects.create(project=copy, kind=asset.kind, file_path=str(target_path), media_type=asset.media_type, size=target_path.stat().st_size, original_name=asset.original_name)
        asset_id_map[str(asset.id)] = new_asset.id
    if source.preview_path:
        preview_path = Path(source.preview_path)
        if preview_path.exists() and preview_path.is_file():
            target_preview = target_dir / f"preview_{uuid.uuid4().hex[:12]}.jpg"
            shutil.copy2(preview_path, target_preview)
            copy.preview_path = str(target_preview)
    state = json.loads(json.dumps(source.state_json or {}))
    if isinstance(state, dict):
        for obj in state.get("objects", []) if isinstance(state.get("objects"), list) else []:
            asset_id = str(obj.get("assetId") or "")
            if asset_id in asset_id_map:
                obj["assetId"] = asset_id_map[asset_id]
                obj["src"] = reverse("studio:design_project_asset_preview", args=[copy.id, asset_id_map[asset_id]])
    copy.state_json = state
    copy.storage_bytes = _design_project_storage_bytes(copy)
    copy.save(update_fields=["state_json", "preview_path", "storage_bytes", "updated_at"])
    return JsonResponse({"project": _design_project_payload(copy, owner_id=owner_id, guest_key=guest_key)})


@require_POST
def delete_design_project(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _design_owner_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Design project not found")
    _delete_design_project_media(project)
    deleted, _ = project.delete()
    if not deleted:
        raise Http404("Design project not found")
    stats = actions.get_account_stats(owner_id, guest_key)
    stats.update(_storage_quota(request, stats))
    return JsonResponse({"ok": True, "deleted_ids": [project_id], "account_stats": stats})


@require_POST
def delete_design_projects(request: HttpRequest) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    data = _json_body(request)
    raw_ids = data.get("ids") if isinstance(data.get("ids"), list) else []
    project_ids = []
    for raw_id in raw_ids:
        try:
            project_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if project_id > 0 and project_id not in project_ids:
            project_ids.append(project_id)
    projects = list(_design_owner_queryset(owner_id, guest_key).filter(id__in=project_ids))
    deleted_ids = []
    for project in projects:
        _delete_design_project_media(project)
        deleted_ids.append(project.id)
    if deleted_ids:
        DesignerProject.objects.filter(id__in=deleted_ids).delete()
    stats = actions.get_account_stats(owner_id, guest_key)
    stats.update(_storage_quota(request, stats))
    return JsonResponse({"ok": True, "deleted_ids": deleted_ids, "deleted_count": len(deleted_ids), "account_stats": stats})


@require_POST
def upload_design_project_asset(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _design_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Design project not found")
    if not _resource_can_edit(WorkspaceShare.RESOURCE_DESIGN, project, owner_id, guest_key):
        raise Http404("Design project not found")
    upload = _require_file(request, "file")
    media_type = upload.content_type or mimetypes.guess_type(upload.name or "")[0] or "application/octet-stream"
    if not media_type.startswith("image/"):
        return _error_json(ValueError("Only image assets are supported"), 400)
    if upload.size > settings.max_image_mb * 1024 * 1024:
        return _error_json(ValueError(f"Image limit: {settings.max_image_mb} MB"), 400)
    asset_dir = _design_project_media_dir(project)
    asset_dir.mkdir(parents=True, exist_ok=True)
    path, media_type = _save_optimized_editor_image(upload, asset_dir, clean_base_name(upload.name or "image", "image"))
    asset = DesignerAsset.objects.create(project=project, kind="image", file_path=str(path), media_type=media_type, size=path.stat().st_size, original_name=(upload.name or "image")[:240])
    project.storage_bytes = _design_project_storage_bytes(project)
    project.save(update_fields=["storage_bytes", "updated_at"])
    return JsonResponse({"asset": _design_asset_payload(asset), "project": _design_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


@require_GET
def preview_design_project_asset(request: HttpRequest, project_id: int, asset_id: int) -> FileResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _design_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Design project not found")
    asset = project.assets.filter(id=asset_id).first()
    if not asset:
        raise Http404("Design asset not found")
    path = Path(asset.file_path)
    if not path.exists() or not path.is_file():
        raise Http404("Design asset file not found")
    return FileResponse(path.open("rb"), as_attachment=False, filename=asset.original_name or path.name, content_type=asset.media_type)


@require_GET
def preview_design_project(request: HttpRequest, project_id: int) -> FileResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _design_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project or not project.preview_path:
        raise Http404("Design preview not found")
    path = Path(project.preview_path)
    if not path.exists() or not path.is_file():
        raise Http404("Design preview not found")
    return FileResponse(path.open("rb"), as_attachment=False, filename=path.name, content_type="image/jpeg")


@require_GET
def workspace_invite(request: HttpRequest, token: str):
    share = WorkspaceShare.objects.filter(token=token).select_related("owner", "invited_user").first()
    if not share or share.status == WorkspaceShare.STATUS_REVOKED or share.expires_at <= timezone.now():
        return render(request, "studio/invite.html", {**_invite_context(request, share, "expired"), "status": "expired"})
    resource = _share_resource(share.resource_type, share.resource_id)
    if not resource:
        return render(request, "studio/invite.html", {**_invite_context(request, share, "missing"), "status": "missing"})
    if request.user.is_authenticated:
        if _clean_email(request.user.email) != share.email:
            return render(request, "studio/invite.html", {**_invite_context(request, share, "wrong_email"), "status": "wrong_email"})
        if share.status == WorkspaceShare.STATUS_PENDING:
            share.invited_user = request.user
            share.status = WorkspaceShare.STATUS_ACCEPTED
            share.save(update_fields=["invited_user", "status", "updated_at"])
        return redirect(_share_resource_url(share.resource_type, share.resource_id))
    return render(request, "studio/invite.html", {**_invite_context(request, share, "ready"), "status": "ready"})


@require_http_methods(["GET", "POST"])
def workspace_shares(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _error_json(ValueError("Sign in to share projects"), 403)
    if request.method == "GET":
        resource_type = str(request.GET.get("resource_type") or "")
        try:
            resource_id = int(request.GET.get("resource_id") or 0)
        except (TypeError, ValueError):
            resource_id = 0
        resource = _share_resource(resource_type, resource_id)
        if not resource or not _resource_is_owner(resource, request.user.id, ""):
            raise Http404("Project not found")
        shares = WorkspaceShare.objects.filter(owner=request.user, resource_type=resource_type, resource_id=resource_id).exclude(status=WorkspaceShare.STATUS_REVOKED)
        return JsonResponse({"shares": [_workspace_share_payload(request, share) for share in shares]})

    data = _json_body(request)
    resource_type = str(data.get("resource_type") or "").strip()
    try:
        resource_id = int(data.get("resource_id") or 0)
    except (TypeError, ValueError):
        resource_id = 0
    resource = _share_resource(resource_type, resource_id)
    if resource_type not in SHARE_RESOURCE_TYPES or not resource or not _resource_is_owner(resource, request.user.id, ""):
        raise Http404("Project not found")
    email = _clean_email(str(data.get("email") or ""))
    if not email:
        return _error_json(ValueError("Email is required"), 400)
    if email == _clean_email(request.user.email):
        return _error_json(ValueError("You already own this project"), 400)
    role = str(data.get("role") or WorkspaceShare.ROLE_VIEWER).strip().lower()
    if role not in {WorkspaceShare.ROLE_VIEWER, WorkspaceShare.ROLE_EDITOR}:
        role = WorkspaceShare.ROLE_VIEWER
    invited_user = get_user_model().objects.filter(email__iexact=email).first()
    share, _ = WorkspaceShare.objects.update_or_create(
        owner=request.user,
        resource_type=resource_type,
        resource_id=resource_id,
        email=email,
        defaults={
            "invited_user": invited_user,
            "role": role,
            "status": WorkspaceShare.STATUS_PENDING,
            "token": secrets.token_urlsafe(32),
            "expires_at": timezone.now() + timezone.timedelta(days=14),
        },
    )
    _send_workspace_invite(request, share)
    return JsonResponse({"share": _workspace_share_payload(request, share)})


@require_POST
def workspace_share_role(request: HttpRequest, share_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _error_json(ValueError("Sign in to manage sharing"), 403)
    share = WorkspaceShare.objects.filter(id=share_id, owner=request.user).first()
    if not share:
        raise Http404("Share not found")
    data = _json_body(request)
    role = str(data.get("role") or "").strip().lower()
    if role not in {WorkspaceShare.ROLE_VIEWER, WorkspaceShare.ROLE_EDITOR}:
        return _error_json(ValueError("Invalid role"), 400)
    share.role = role
    share.save(update_fields=["role", "updated_at"])
    return JsonResponse({"share": _workspace_share_payload(request, share)})


@require_POST
def revoke_workspace_share(request: HttpRequest, share_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _error_json(ValueError("Sign in to manage sharing"), 403)
    share = WorkspaceShare.objects.filter(id=share_id, owner=request.user).first()
    if not share:
        raise Http404("Share not found")
    share.status = WorkspaceShare.STATUS_REVOKED
    share.save(update_fields=["status", "updated_at"])
    return JsonResponse({"ok": True, "share": _workspace_share_payload(request, share)})


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
            "current_video_project": _video_project_payload(project, owner_id=owner_id, guest_key=guest_key) if project else None,
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
    projects = [_video_project_payload(project, include_state=False, owner_id=owner_id, guest_key=guest_key) for project in _video_project_queryset(owner_id, guest_key)[:120]]
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
    projects = [_video_project_payload(project, include_state=False, owner_id=owner_id, guest_key=guest_key) for project in _video_project_queryset(owner_id, guest_key)[:80]]
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
    return JsonResponse({"project": _video_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


@require_GET
def video_project_detail(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    return JsonResponse({"project": _video_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


@require_POST
def save_video_project(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _resource_can_edit(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
        raise Http404("Project not found")
    data = _json_body(request)
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    title = _clean_project_title(str(data.get("title") or state.get("title") or project.title))
    project.title = title
    project.state_json = state
    project.storage_bytes = _video_project_storage_bytes(project)
    project.save(update_fields=["title", "state_json", "storage_bytes", "updated_at"])
    return JsonResponse({"project": _video_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


@require_POST
def rename_video_project(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_owner_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    data = _json_body(request)
    title = _clean_project_title(str(data.get("title") or project.title))
    project.title = title
    project.save(update_fields=["title", "updated_at"])
    return JsonResponse({"project": _video_project_payload(project, include_state=False, owner_id=owner_id, guest_key=guest_key)})


@require_POST
def start_video_project_export(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _resource_can_edit(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
        raise Http404("Project not found")
    data = _json_body(request)
    quality = "1080p" if data.get("quality") == "1080p" else "720p"
    preset = str(data.get("preset") or "").strip()
    job_id = uuid.uuid4().hex[:16]
    output_dir = _video_project_media_dir(project) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{clean_base_name(project.title, 'video-project')}_{quality}_{job_id}.mp4"
    job_record = JobRecord.objects.create(
        owner=project.owner,
        guest_key=project.guest_key,
        job_id=job_id,
        kind="video_export",
        title=f"Export {project.title}",
        status="queued",
        progress=2,
        message="Queued",
        params_json=json.dumps({"project_id": project.id, "path": str(output), "quality": quality, "preset": preset}, ensure_ascii=False),
    )
    JobEventRecord.objects.create(job=job_record, status="queued", progress=2, message="Queued")
    with _video_export_lock:
        _video_export_jobs[job_id] = {
            "id": job_id,
            "project_id": project.id,
            "owner_id": owner_id,
            "guest_key": guest_key,
            "status": "queued",
            "progress": 2,
            "message": "Queued",
            "error": "",
            "path": str(output),
            "quality": quality,
            "preset": preset,
            "created_at": time.time(),
        }
    _video_export_executor.submit(_run_video_project_export, job_id, project.id, quality, output)
    return JsonResponse({"job": _video_export_payload(request, project, job_id)})


@require_GET
def list_video_project_exports(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    jobs = JobRecord.objects.filter(kind__in=["video_export", "video_cover"], params_json__contains=f'"project_id": {project.id}').prefetch_related("outputs").order_by("-created_at")[:12]
    return JsonResponse({"jobs": [_video_export_record_payload(request, project, job) for job in jobs]})


@require_GET
def video_project_export_status(request: HttpRequest, project_id: int, job_id: str) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _video_export_access(job_id, project, owner_id, guest_key):
        raise Http404("Export not found")
    return JsonResponse({"job": _video_export_payload(request, project, job_id)})


@require_POST
def cancel_video_project_export(request: HttpRequest, project_id: int, job_id: str) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _video_export_access(job_id, project, owner_id, guest_key):
        raise Http404("Export not found")
    if not _resource_can_edit(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
        raise Http404("Export not found")
    with _video_export_lock:
        process = _video_export_processes.get(job_id)
    if process and process.poll() is None:
        try:
            process.terminate()
        except Exception:
            pass
    _set_video_export_job(job_id, status="cancelled", progress=100, message="Cancelled")
    return JsonResponse({"job": _video_export_payload(request, project, job_id)})


@require_GET
def download_video_project_export(request: HttpRequest, project_id: int, job_id: str) -> FileResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _video_export_access(job_id, project, owner_id, guest_key):
        raise Http404("Export not found")
    record = JobRecord.objects.filter(job_id=job_id).prefetch_related("outputs").first()
    output = record.outputs.first() if record else None
    if output:
        path = Path(output.path)
        ready = record.status in {"completed", "done"}
        media_type = output.media_type
    else:
        job = _video_export_jobs.get(job_id) or {}
        path = Path(str(job.get("path") or ""))
        ready = job.get("status") == "done"
        media_type = "video/mp4"
    if not ready or not path.exists() or not path.is_file():
        raise Http404("Export not ready")
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name, content_type=media_type)


@require_POST
def export_video_project_cover(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).prefetch_related("assets").filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _resource_can_edit(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
        raise Http404("Project not found")
    data = _json_body(request)
    time_seconds = max(0, float(data.get("time") or 0))
    job_id = uuid.uuid4().hex[:16]
    output_dir = _video_project_media_dir(project) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{clean_base_name(project.title, 'cover')}_{job_id}.jpg"
    job_record = JobRecord.objects.create(
        owner=project.owner,
        guest_key=project.guest_key,
        job_id=job_id,
        kind="video_cover",
        title=f"Cover {project.title}",
        status="running",
        progress=20,
        message="Rendering cover",
        params_json=json.dumps({"project_id": project.id, "path": str(output), "time": time_seconds}, ensure_ascii=False),
    )
    try:
        _render_video_project_cover(project, output, time_seconds)
        JobOutputRecord.objects.create(job=job_record, label="Cover frame", path=str(output), media_type="image/jpeg", size=output.stat().st_size)
        job_record.status = "completed"
        job_record.progress = 100
        job_record.message = "Ready"
        job_record.save(update_fields=["status", "progress", "message", "updated_at"])
        JobEventRecord.objects.create(job=job_record, status="completed", progress=100, message="Ready")
    except Exception as exc:
        job_record.status = "failed"
        job_record.progress = 100
        job_record.error = str(exc)
        job_record.message = "Cover failed"
        job_record.save(update_fields=["status", "progress", "message", "error", "updated_at"])
        JobEventRecord.objects.create(job=job_record, status="failed", progress=100, message=str(exc))
    return JsonResponse({"job": _video_export_record_payload(request, project, job_record)})


@require_POST
def delete_video_project(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_owner_queryset(owner_id, guest_key).filter(id=project_id).first()
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
def delete_video_projects(request: HttpRequest) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    data = _json_body(request)
    raw_ids = data.get("ids") if isinstance(data.get("ids"), list) else []
    project_ids: list[int] = []
    for raw_id in raw_ids:
        try:
            project_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if project_id > 0 and project_id not in project_ids:
            project_ids.append(project_id)
    if not project_ids:
        stats = actions.get_account_stats(owner_id, guest_key)
        stats.update(_storage_quota(request, stats))
        return JsonResponse({"ok": True, "deleted_ids": [], "deleted_count": 0, "account_stats": stats})

    projects = list(_video_owner_queryset(owner_id, guest_key).filter(id__in=project_ids))
    deleted_ids: list[int] = []
    for project in projects:
        _delete_video_project_media(project)
        deleted_ids.append(project.id)
    if deleted_ids:
        VideoEditorProject.objects.filter(id__in=deleted_ids).delete()
    stats = actions.get_account_stats(owner_id, guest_key)
    stats.update(_storage_quota(request, stats))
    return JsonResponse({"ok": True, "deleted_ids": deleted_ids, "deleted_count": len(deleted_ids), "account_stats": stats})


@require_POST
def upload_video_project_asset(request: HttpRequest, project_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _resource_can_edit(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
        raise Http404("Project not found")
    upload = _require_file(request, "file")
    media_type = upload.content_type or mimetypes.guess_type(upload.name or "")[0] or "application/octet-stream"
    kind = (request.POST.get("kind") or "").strip().lower()
    if kind not in {"video", "audio", "image"}:
        if media_type.startswith("video/"):
            kind = "video"
        elif media_type.startswith("audio/"):
            kind = "audio"
        elif media_type.startswith("image/") or _is_visual_document_type(media_type, upload.name or ""):
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
    if kind == "image" and media_type.startswith("image/"):
        path, media_type = _save_optimized_editor_image(upload, asset_dir, base)
    else:
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
    return JsonResponse({"asset": _video_asset_payload(asset), "project": _video_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


@require_GET
def preview_video_project_asset(request: HttpRequest, project_id: int, asset_id: int) -> HttpResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _resource_can_view(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
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
    if not _resource_can_view(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
        raise Http404("Project not found")
    asset = project.assets.filter(id=asset_id).first()
    if not asset or not asset.thumbnail_path:
        raise Http404("Thumbnail not found")
    path = Path(asset.thumbnail_path)
    if not path.exists() or not path.is_file():
        raise Http404("Thumbnail not found")
    return FileResponse(path.open("rb"), as_attachment=False, filename=path.name, content_type="image/jpeg")


@require_http_methods(["GET", "POST"])
def video_project_asset_waveform(request: HttpRequest, project_id: int, asset_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    can_edit = _resource_can_edit(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key)
    if request.method == "POST" and not can_edit:
        raise Http404("Waveform asset not found")
    asset = project.assets.filter(id=asset_id).first()
    if not asset or asset.kind not in {"audio", "video"}:
        raise Http404("Waveform asset not found")
    path = _video_asset_waveform_path(asset)
    if request.method == "POST" or (can_edit and not path.exists()):
        path.parent.mkdir(parents=True, exist_ok=True)
        samples = _build_compact_waveform(Path(asset.file_path))
        path.write_text(json.dumps({"samples": samples, "count": len(samples)}, separators=(",", ":")), encoding="utf-8")
    if not path.exists():
        return JsonResponse({"samples": [], "count": 0})
    return JsonResponse(json.loads(path.read_text(encoding="utf-8")))


@require_POST
def rename_video_project_asset(request: HttpRequest, project_id: int, asset_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _resource_can_edit(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
        raise Http404("Project not found")
    asset = project.assets.filter(id=asset_id).first()
    if not asset:
        raise Http404("Asset not found")
    data = _json_body(request)
    name = str(data.get("name") or asset.original_name or "").strip()
    if not name:
        return _error_json(ValueError("Asset name is required"), 400)
    asset.original_name = name[:240]
    asset.save(update_fields=["original_name"])
    project.save(update_fields=["updated_at"])
    return JsonResponse({"asset": _video_asset_payload(asset), "project": _video_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


@require_POST
def delete_video_project_asset(request: HttpRequest, project_id: int, asset_id: int) -> JsonResponse:
    owner_id, guest_key = _workspace_identity(request)
    project = _video_project_queryset(owner_id, guest_key).filter(id=project_id).first()
    if not project:
        raise Http404("Project not found")
    if not _resource_can_edit(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
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
    return JsonResponse({"ok": True, "project": _video_project_payload(project, owner_id=owner_id, guest_key=guest_key)})


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


SHARE_VIEW_ROLES = {WorkspaceShare.ROLE_VIEWER, WorkspaceShare.ROLE_EDITOR}
SHARE_EDIT_ROLES = {WorkspaceShare.ROLE_EDITOR}
SHARE_RESOURCE_TYPES = {WorkspaceShare.RESOURCE_DESIGN, WorkspaceShare.RESOURCE_VIDEO}


def _active_share_filter() -> Q:
    return Q(status=WorkspaceShare.STATUS_ACCEPTED, expires_at__gt=timezone.now())


def _shared_resource_ids(resource_type: str, owner_id: int | None) -> list[int]:
    if not owner_id:
        return []
    return list(
        WorkspaceShare.objects.filter(_active_share_filter(), resource_type=resource_type, invited_user_id=owner_id)
        .values_list("resource_id", flat=True)
    )


def _video_owner_queryset(owner_id: int | None, guest_key: str):
    queryset = VideoEditorProject.objects.all()
    if owner_id:
        return queryset.filter(owner_id=owner_id)
    return queryset.filter(owner__isnull=True, guest_key=guest_key)


def _design_owner_queryset(owner_id: int | None, guest_key: str):
    queryset = DesignerProject.objects.all()
    if owner_id:
        return queryset.filter(owner_id=owner_id)
    return queryset.filter(owner__isnull=True, guest_key=guest_key)


def _video_project_queryset(owner_id: int | None, guest_key: str):
    queryset = VideoEditorProject.objects.all()
    if owner_id:
        return queryset.filter(Q(owner_id=owner_id) | Q(id__in=_shared_resource_ids(WorkspaceShare.RESOURCE_VIDEO, owner_id))).distinct()
    return queryset.filter(owner__isnull=True, guest_key=guest_key)


def _design_project_queryset(owner_id: int | None, guest_key: str):
    queryset = DesignerProject.objects.all()
    if owner_id:
        return queryset.filter(Q(owner_id=owner_id) | Q(id__in=_shared_resource_ids(WorkspaceShare.RESOURCE_DESIGN, owner_id))).distinct()
    return queryset.filter(owner__isnull=True, guest_key=guest_key)


def _resource_access_role(resource_type: str, project, owner_id: int | None, guest_key: str = "") -> str:
    if not project:
        return ""
    if owner_id and project.owner_id == owner_id:
        return "owner"
    if not owner_id and project.owner_id is None and project.guest_key == guest_key:
        return "owner"
    if owner_id:
        share = WorkspaceShare.objects.filter(
            _active_share_filter(),
            resource_type=resource_type,
            resource_id=project.id,
            invited_user_id=owner_id,
        ).first()
        if share:
            return share.role
    return ""


def _resource_can_view(resource_type: str, project, owner_id: int | None, guest_key: str = "") -> bool:
    role = _resource_access_role(resource_type, project, owner_id, guest_key)
    return role == "owner" or role in SHARE_VIEW_ROLES


def _resource_can_edit(resource_type: str, project, owner_id: int | None, guest_key: str = "") -> bool:
    role = _resource_access_role(resource_type, project, owner_id, guest_key)
    return role == "owner" or role in SHARE_EDIT_ROLES


def _resource_is_owner(project, owner_id: int | None, guest_key: str = "") -> bool:
    if not project:
        return False
    if owner_id:
        return project.owner_id == owner_id
    return project.owner_id is None and project.guest_key == guest_key


def _clean_email(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _share_resource(resource_type: str, resource_id: int):
    if resource_type == WorkspaceShare.RESOURCE_DESIGN:
        return DesignerProject.objects.filter(id=resource_id).first()
    if resource_type == WorkspaceShare.RESOURCE_VIDEO:
        return VideoEditorProject.objects.filter(id=resource_id).first()
    return None


def _share_resource_url(resource_type: str, resource_id: int) -> str:
    if resource_type == WorkspaceShare.RESOURCE_DESIGN:
        return f"{reverse('studio:designer')}?{urlencode({'project': resource_id})}"
    if resource_type == WorkspaceShare.RESOURCE_VIDEO:
        return f"{reverse('studio:video_editor')}?{urlencode({'project': resource_id})}"
    return reverse("studio:index")


def _share_resource_label(resource_type: str) -> str:
    return {
        WorkspaceShare.RESOURCE_DESIGN: "Design board",
        WorkspaceShare.RESOURCE_VIDEO: "Video edit",
    }.get(resource_type, "Project")


def _share_resource_preview(resource_type: str, resource) -> str:
    if resource_type == WorkspaceShare.RESOURCE_DESIGN and getattr(resource, "preview_path", ""):
        return reverse("studio:design_project_preview", args=[resource.id])
    if resource_type == WorkspaceShare.RESOURCE_VIDEO:
        state = resource.state_json or {}
        first_thumb = next((asset for asset in resource.assets.all() if asset.thumbnail_path), None)
        if first_thumb:
            return reverse("studio:video_project_asset_thumbnail", args=[resource.id, first_thumb.id])
        if isinstance(state, dict):
            return str(state.get("thumbnail") or "")
    return ""


def _workspace_share_payload(request: HttpRequest, share: WorkspaceShare) -> dict[str, object]:
    return {
        "id": share.id,
        "resource_type": share.resource_type,
        "resource_id": share.resource_id,
        "email": share.email,
        "role": share.role,
        "status": share.status,
        "invite_url": request.build_absolute_uri(reverse("studio:workspace_invite", args=[share.token])),
        "expires_at": share.expires_at.isoformat(),
        "created_at": share.created_at.isoformat(),
    }


def _invite_context(request: HttpRequest, share: WorkspaceShare | None, status: str) -> dict[str, object]:
    resource = _share_resource(share.resource_type, share.resource_id) if share else None
    next_url = reverse("studio:workspace_invite", args=[share.token]) if share else reverse("studio:index")
    return {
        "share": share,
        "resource": resource,
        "resource_title": getattr(resource, "title", "Shared project") if resource else "Shared project",
        "resource_label": _share_resource_label(share.resource_type) if share else "Project",
        "preview_url": _share_resource_preview(share.resource_type, resource) if share and resource else "",
        "owner_display": (share.owner.first_name or share.owner.email) if share else "CherryX user",
        "role": share.role if share else "",
        "status": status,
        "login_url": f"{reverse('studio:login')}?{urlencode({'next': next_url})}",
        "register_url": f"{reverse('studio:register')}?{urlencode({'next': next_url})}",
        "accent_color": _accent_color(request),
        "ui_accent_color": _ui_accent_color(request),
        "theme_mode": _theme_mode(request),
    }


def _send_workspace_invite(request: HttpRequest, share: WorkspaceShare) -> None:
    resource = _share_resource(share.resource_type, share.resource_id)
    if not resource:
        return
    preview_url = _share_resource_preview(share.resource_type, resource)
    if preview_url and preview_url.startswith("/"):
        preview_url = request.build_absolute_uri(preview_url)
    elif preview_url and not preview_url.startswith(("http://", "https://")):
        preview_url = ""
    context = {
        "share": share,
        "resource_title": getattr(resource, "title", "Shared project"),
        "resource_label": _share_resource_label(share.resource_type),
        "owner_display": share.owner.first_name or share.owner.email,
        "invite_url": request.build_absolute_uri(reverse("studio:workspace_invite", args=[share.token])),
        "preview_url": preview_url,
        "role": share.role,
    }
    html = render_to_string("studio/email/invite.html", context)
    message = EmailMultiAlternatives(
        subject=f"{context['owner_display']} invited you to CherryX",
        body=strip_tags(html),
        from_email=None,
        to=[share.email],
    )
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=True)


def _accept_pending_workspace_shares(user) -> None:
    email = _clean_email(getattr(user, "email", "") or "")
    if not email:
        return
    WorkspaceShare.objects.filter(
        email=email,
        status=WorkspaceShare.STATUS_PENDING,
        expires_at__gt=timezone.now(),
    ).update(invited_user=user, status=WorkspaceShare.STATUS_ACCEPTED, updated_at=timezone.now())


def _design_project_payload(project: DesignerProject | None, include_state: bool = True, owner_id: int | None = None, guest_key: str = "") -> dict[str, object]:
    if not project:
        return {}
    state = project.state_json or {}
    objects = state.get("objects") if isinstance(state.get("objects"), list) else []
    vectors = state.get("vectors") if isinstance(state.get("vectors"), list) else []
    frames = [item for item in objects if isinstance(item, dict) and item.get("type") == "frame"]
    access_role = _resource_access_role(WorkspaceShare.RESOURCE_DESIGN, project, owner_id, guest_key) if owner_id is not None or guest_key else "owner"
    is_owner = access_role == "owner"
    payload: dict[str, object] = {
        "id": project.id,
        "title": project.title,
        "preview_url": reverse("studio:design_project_preview", args=[project.id]) if project.preview_path else "",
        "object_count": len(objects),
        "frame_count": len(frames),
        "vector_count": len(vectors),
        "storage_bytes": project.storage_bytes,
        "storage_text": human_size(project.storage_bytes),
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "assets": [_design_asset_payload(asset) for asset in project.assets.all()],
        "access_role": access_role,
        "is_owner": is_owner,
        "can_edit": is_owner or access_role == WorkspaceShare.ROLE_EDITOR,
        "can_share": is_owner and owner_id is not None,
    }
    if include_state:
        payload["state"] = project.state_json or {}
    return payload


def _design_asset_payload(asset: DesignerAsset) -> dict[str, object]:
    return {
        "id": asset.id,
        "kind": asset.kind,
        "name": asset.original_name,
        "media_type": asset.media_type,
        "size": asset.size,
        "size_text": human_size(asset.size),
        "preview_url": reverse("studio:design_project_asset_preview", args=[asset.project_id, asset.id]),
    }


def _video_project_payload(project: VideoEditorProject, include_state: bool = True, owner_id: int | None = None, guest_key: str = "") -> dict[str, object]:
    state = project.state_json or {}
    layers = state.get("layers") if isinstance(state.get("layers"), list) else []
    assets = list(project.assets.all()) if project else []
    first_thumb = next((asset for asset in assets if asset.thumbnail_path), None)
    access_role = _resource_access_role(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key) if owner_id is not None or guest_key else "owner"
    is_owner = access_role == "owner"
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
        "access_role": access_role,
        "is_owner": is_owner,
        "can_edit": is_owner or access_role == WorkspaceShare.ROLE_EDITOR,
        "can_share": is_owner and owner_id is not None,
    }
    if include_state:
        payload["state"] = project.state_json or {}
    return payload


def _video_export_payload(request: HttpRequest, project: VideoEditorProject, job_id: str) -> dict[str, object]:
    record = JobRecord.objects.filter(job_id=job_id).prefetch_related("outputs").first()
    if record:
        return _video_export_record_payload(request, project, record)
    with _video_export_lock:
        job = dict(_video_export_jobs.get(job_id) or {})
    if not job:
        raise Http404("Export not found")
    payload = {
        "id": job_id,
        "status": job.get("status", "missing"),
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
        "error": job.get("error", ""),
        "quality": job.get("quality", "720p"),
    }
    path = Path(str(job.get("path") or ""))
    if job.get("status") == "done" and path.exists():
        payload["download_url"] = reverse("studio:download_video_project_export", args=[project.id, job_id])
        payload["size_text"] = human_size(path.stat().st_size)
        payload["filename"] = path.name
    return payload


def _video_export_record_payload(request: HttpRequest, project: VideoEditorProject, record: JobRecord) -> dict[str, object]:
    output = record.outputs.first()
    status = "done" if record.status in {"completed", "done"} else record.status
    try:
        events = [{"status": event.status, "progress": event.progress, "message": event.message} for event in record.events.all().order_by("-id")[:6]]
    except Exception:
        events = []
    payload: dict[str, object] = {
        "id": record.job_id,
        "status": status,
        "progress": record.progress,
        "message": record.message,
        "error": record.error,
        "quality": _job_param(record, "quality", "720p"),
        "kind": record.kind,
        "created_at": record.created_at.isoformat(),
        "events": events,
    }
    if output and Path(output.path).exists() and status == "done":
        payload["download_url"] = reverse("studio:download_video_project_export", args=[project.id, record.job_id])
        payload["size_text"] = human_size(output.size or Path(output.path).stat().st_size)
        payload["filename"] = Path(output.path).name
        payload["media_type"] = output.media_type
    return payload


def _video_export_access(job_id: str, project: VideoEditorProject, owner_id: int | None, guest_key: str) -> bool:
    if not _resource_can_view(WorkspaceShare.RESOURCE_VIDEO, project, owner_id, guest_key):
        return False
    record = JobRecord.objects.filter(job_id=job_id).first()
    if record:
        return int(_job_param(record, "project_id", 0) or 0) == project.id
    with _video_export_lock:
        job = _video_export_jobs.get(job_id)
    if not job or int(job.get("project_id") or 0) != project.id:
        return False
    return True


def _set_video_export_job(job_id: str, **values: object) -> None:
    with _video_export_lock:
        job = _video_export_jobs.get(job_id)
        if not job:
            return
        job.update(values)
    try:
        record = JobRecord.objects.filter(job_id=job_id).first()
        if record:
            status = str(values.get("status", record.status))
            record.status = "completed" if status == "done" else status
            record.progress = int(values.get("progress", record.progress) or 0)
            record.message = str(values.get("message", record.message) or "")
            record.error = str(values.get("error", record.error) or "")
            record.save(update_fields=["status", "progress", "message", "error", "updated_at"])
            try:
                JobEventRecord.objects.create(job=record, status=record.status, progress=record.progress, message=record.error or record.message)
            except Exception:
                pass
    except Exception:
        pass


def _run_video_project_export(job_id: str, project_id: int, quality: str, output: Path) -> None:
    try:
        _set_video_export_job(job_id, status="running", progress=8, message="Preparing timeline")
        project = VideoEditorProject.objects.prefetch_related("assets").get(id=project_id)
        width, height = _video_export_size(project.state_json or {}, quality)
        duration = _video_export_duration(project.state_json or {})
        assets = {asset.id: asset for asset in project.assets.all()}
        clips = (project.state_json or {}).get("clips", []) if isinstance(project.state_json, dict) else []
        video_clip = next((clip for clip in clips if clip.get("type") == "video" and assets.get(int(clip.get("assetId") or 0))), None)
        _set_video_export_job(job_id, progress=22, message="Rendering MP4")
        output.parent.mkdir(parents=True, exist_ok=True)
        if video_clip:
            _render_video_project_from_clip(video_clip, assets, project.state_json or {}, output, width, height, duration)
        elif _video_export_visual_clips(project.state_json or {}, assets):
            _render_visual_card_project(project.state_json or {}, assets, output, width, height, duration)
        else:
            _render_empty_video_project(output, width, height, duration)
        if JobRecord.objects.filter(job_id=job_id, status="cancelled").exists():
            return
        project.storage_bytes = _video_project_storage_bytes(project)
        project.save(update_fields=["storage_bytes", "updated_at"])
        record = JobRecord.objects.filter(job_id=job_id).first()
        if record and output.exists():
            JobOutputRecord.objects.get_or_create(
                job=record,
                path=str(output),
                label="MP4 export",
                defaults={"media_type": "video/mp4", "size": output.stat().st_size},
            )
        _set_video_export_job(job_id, status="done", progress=100, message="Ready")
    except Exception as exc:
        _set_video_export_job(job_id, status="failed", progress=100, message="Export failed", error=str(exc))


def _video_export_size(state: dict[str, object], quality: str) -> tuple[int, int]:
    aspect = str(state.get("aspect") or "9 / 16").replace(" ", "")
    long_side = 1080 if quality == "1080p" else 720
    if aspect == "16/9":
        return (1920, 1080) if quality == "1080p" else (1280, 720)
    if aspect == "1/1":
        return long_side, long_side
    return (1080, 1920) if quality == "1080p" else (720, 1280)


def _video_export_duration(state: dict[str, object]) -> float:
    clips = state.get("clips") if isinstance(state.get("clips"), list) else []
    duration = max((float(clip.get("start") or 0) + float(clip.get("duration") or 0) for clip in clips if isinstance(clip, dict)), default=5.0)
    return max(0.25, min(duration, 60 * 30))


def _render_video_project_from_clip(clip: dict[str, object], assets: dict[int, VideoEditorAsset], state: dict[str, object], output: Path, width: int, height: int, duration: float) -> None:
    asset = assets[int(clip.get("assetId") or 0)]
    source = Path(asset.file_path)
    if not source.exists():
        raise FileNotFoundError(asset.original_name or "Video asset not found")
    source_start = max(0, float(clip.get("sourceStart") or 0))
    clip_duration = max(0.25, min(float(clip.get("duration") or duration), duration))
    fit = (clip.get("style") or {}).get("fit", "contain") if isinstance(clip.get("style"), dict) else "contain"
    if fit in {"cover", "crop"}:
        base_filter = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
    else:
        base_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    args = [
        ffmpeg_path(),
        "-y",
        "-ss",
        str(source_start),
        "-t",
        str(clip_duration),
        "-i",
        str(source),
    ]
    overlay_inputs: list[tuple[dict[str, object], VideoEditorAsset]] = []
    for visual_clip in _video_export_visual_clips(state, assets):
        if visual_clip is clip or visual_clip.get("type") != "image":
            continue
        overlay_asset = assets.get(int(visual_clip.get("assetId") or 0))
        if overlay_asset and _asset_is_previewable_image(overlay_asset):
            overlay_inputs.append((visual_clip, overlay_asset))
            args += ["-loop", "1", "-t", str(duration), "-i", str(overlay_asset.file_path)]
    filters = [f"[0:v]{base_filter}[v0]"]
    current_label = "v0"
    for index, (visual_clip, overlay_asset) in enumerate(overlay_inputs, start=1):
        scale_pct = max(8, min(120, float(visual_clip.get("scale") or 42))) / 100
        overlay_width = max(24, min(width, int(width * scale_pct)))
        x_pct = max(0, min(100, float(visual_clip.get("x") or 50))) / 100
        y_pct = max(0, min(100, float(visual_clip.get("y") or 50))) / 100
        start = max(0, float(visual_clip.get("start") or 0))
        end = min(duration, start + max(0.25, float(visual_clip.get("duration") or 5)))
        img_label = f"img{index}"
        out_label = f"v{index}"
        filters.append(f"[{index}:v]scale={overlay_width}:-1[{img_label}]")
        filters.append(
            f"[{current_label}][{img_label}]overlay="
            f"x=(W-w)*{x_pct:.4f}:y=(H-h)*{y_pct:.4f}:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{out_label}]"
        )
        current_label = out_label
    text_index = 0
    for visual_clip in _video_export_visual_clips(state, assets):
        if visual_clip.get("type") != "image":
            continue
        visual_asset = assets.get(int(visual_clip.get("assetId") or 0))
        if not visual_asset or _asset_is_previewable_image(visual_asset):
            continue
        text = _ffmpeg_drawtext_escape(f"{_asset_visual_kind(visual_asset).upper()}  {visual_asset.original_name or 'File'}")
        start = max(0, float(visual_clip.get("start") or 0))
        end = min(duration, start + max(0.25, float(visual_clip.get("duration") or 5)))
        y = int(height * (float(visual_clip.get("y") or 50) / 100))
        next_label = f"doc{text_index}"
        filters.append(
            f"[{current_label}]drawtext="
            f"text='{text}':"
            f"x=(w-text_w)/2:y={max(40, min(height - 90, y))}:fontsize={max(18, int(width * 0.045))}:fontcolor=white:"
            "box=1:boxcolor=black@0.55:boxborderw=22:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{next_label}]"
        )
        current_label = next_label
        text_index += 1
    for text_clip in _video_export_text_clips(state):
        text = _ffmpeg_drawtext_escape(str(text_clip.get("text") or "Text"))
        style = text_clip.get("style") if isinstance(text_clip.get("style"), dict) else {}
        size = max(12, min(96, int(float(style.get("size") or 32))))
        start = max(0, float(text_clip.get("start") or 0))
        end = min(duration, start + max(0.25, float(text_clip.get("duration") or 4)))
        y = int(height * (float(text_clip.get("y") or 78) / 100))
        filters.append(
            f"[{current_label}]drawtext="
            f"text='{text}':"
            f"x=(w-text_w)/2:y={y}:fontsize={size}:fontcolor=white:"
            "box=1:boxcolor=black@0.45:boxborderw=18:"
            f"enable='between(t,{start:.3f},{end:.3f})'[txt{text_index}]"
        )
        current_label = f"txt{text_index}"
        text_index += 1
    args += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        f"[{current_label}]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
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
    completed = subprocess.run(args, capture_output=True, text=True, timeout=settings.video_timeout_seconds)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr.strip().splitlines() or ["FFmpeg export failed"])[-1])


def _render_empty_video_project(output: Path, width: int, height: int, duration: float) -> None:
    args = [
        ffmpeg_path(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:d={duration}:r=30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        str(output),
    ]
    completed = subprocess.run(args, capture_output=True, text=True, timeout=settings.video_timeout_seconds)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr.strip().splitlines() or ["FFmpeg export failed"])[-1])


def _render_visual_card_project(state: dict[str, object], assets: dict[int, VideoEditorAsset], output: Path, width: int, height: int, duration: float) -> None:
    clips = _video_export_visual_clips(state, assets)
    first_image = next((clip for clip in clips if _asset_is_previewable_image(assets.get(int(clip.get("assetId") or 0)))), None)
    first_asset = assets.get(int(first_image.get("assetId") or 0)) if first_image else None
    filters: list[str] = []
    args = [ffmpeg_path(), "-y"]
    if first_asset:
        args += ["-loop", "1", "-t", str(duration), "-i", str(first_asset.file_path)]
        filters.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    else:
        args += ["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d={duration}:r=30"]
    for visual_clip in clips:
        asset = assets.get(int(visual_clip.get("assetId") or 0))
        if not asset or (first_asset and asset.id == first_asset.id and visual_clip is first_image):
            continue
        if _asset_is_previewable_image(asset):
            text = _ffmpeg_drawtext_escape(asset.original_name or "Image")
        else:
            text = _ffmpeg_drawtext_escape(f"{_asset_visual_kind(asset).upper()}  {asset.original_name or 'File'}")
        start = max(0, float(visual_clip.get("start") or 0))
        end = min(duration, start + max(0.25, float(visual_clip.get("duration") or 5)))
        y = int(height * (float(visual_clip.get("y") or 50) / 100))
        filters.append(
            "drawtext="
            f"text='{text}':"
            f"x=(w-text_w)/2:y={max(40, min(height - 90, y))}:fontsize={max(18, int(width * 0.045))}:fontcolor=white:"
            "box=1:boxcolor=black@0.55:boxborderw=22:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
    for text_clip in _video_export_text_clips(state):
        text = _ffmpeg_drawtext_escape(str(text_clip.get("text") or "Text"))
        style = text_clip.get("style") if isinstance(text_clip.get("style"), dict) else {}
        size = max(12, min(96, int(float(style.get("size") or 32))))
        start = max(0, float(text_clip.get("start") or 0))
        end = min(duration, start + max(0.25, float(text_clip.get("duration") or 4)))
        y = int(height * (float(text_clip.get("y") or 78) / 100))
        filters.append(
            "drawtext="
            f"text='{text}':"
            f"x=(w-text_w)/2:y={y}:fontsize={size}:fontcolor=white:"
            "box=1:boxcolor=black@0.45:boxborderw=18:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
    if filters:
        args += ["-vf", ",".join(filters)]
    args += [
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    completed = subprocess.run(args, capture_output=True, text=True, timeout=settings.video_timeout_seconds)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr.strip().splitlines() or ["FFmpeg export failed"])[-1])


def _video_export_text_clips(state: dict[str, object]) -> list[dict[str, object]]:
    clips = state.get("clips") if isinstance(state.get("clips"), list) else []
    return [clip for clip in clips if isinstance(clip, dict) and clip.get("type") in {"text", "caption"}]


def _video_export_visual_clips(state: dict[str, object], assets: dict[int, VideoEditorAsset]) -> list[dict[str, object]]:
    clips = state.get("clips") if isinstance(state.get("clips"), list) else []
    visual: list[dict[str, object]] = []
    for clip in clips:
        if not isinstance(clip, dict) or clip.get("type") not in {"video", "image"}:
            continue
        asset = assets.get(int(clip.get("assetId") or 0))
        if asset and asset.kind in {"video", "image"}:
            visual.append(clip)
    return sorted(visual, key=lambda item: float(item.get("start") or 0))


def _ffmpeg_drawtext_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("\n", " ")[:500]


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
    extension = Path(asset.original_name or asset.file_path).suffix.lower()
    payload = {
        "id": asset.id,
        "kind": asset.kind,
        "name": asset.original_name,
        "media_type": asset.media_type,
        "visual_kind": _asset_visual_kind(asset),
        "is_previewable_image": _asset_is_previewable_image(asset),
        "extension": extension,
        "size": asset.size,
        "size_text": human_size(asset.size),
        "duration": asset.duration,
        "preview_url": reverse("studio:video_project_asset_preview", args=[asset.project_id, asset.id]),
        "waveform_url": reverse("studio:video_project_asset_waveform", args=[asset.project_id, asset.id]) if asset.kind in {"audio", "video"} else "",
        "rename_url": reverse("studio:rename_video_project_asset", args=[asset.project_id, asset.id]),
        "delete_url": reverse("studio:delete_video_project_asset", args=[asset.project_id, asset.id]),
        "thumbnail_url": "",
    }
    if asset.thumbnail_path:
        payload["thumbnail_url"] = reverse("studio:video_project_asset_thumbnail", args=[asset.project_id, asset.id])
    return payload


def _asset_visual_kind(asset: VideoEditorAsset) -> str:
    if asset.kind != "image":
        return asset.kind
    media_type = asset.media_type or ""
    extension = Path(asset.original_name or asset.file_path).suffix.lower()
    if media_type.startswith("image/"):
        return "image"
    if media_type == "application/pdf" or extension == ".pdf":
        return "pdf"
    if media_type.startswith("text/") or extension in {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".csv", ".json", ".rtf"}:
        return "document"
    return "file"


def _asset_is_previewable_image(asset: VideoEditorAsset | None) -> bool:
    return bool(asset and asset.media_type.startswith("image/") and Path(asset.file_path).exists())


def _is_visual_document_type(media_type: str, filename: str) -> bool:
    extension = Path(filename or "").suffix.lower()
    return (
        media_type == "application/pdf"
        or media_type.startswith("text/")
        or extension in {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".csv", ".json", ".rtf"}
    )


def _save_optimized_editor_image(upload, target_dir: Path, base: str) -> tuple[Path, str]:
    try:
        image = Image.open(upload)
        image = ImageOps.exif_transpose(image)
        image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
        has_alpha = image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)
        suffix = ".webp" if has_alpha else ".jpg"
        path = target_dir / f"{uuid.uuid4().hex[:12]}_{base}{suffix}"
        if has_alpha:
            image.save(path, "WEBP", quality=88, method=6)
            return path, "image/webp"
        image.convert("RGB").save(path, "JPEG", quality=88, optimize=True, progressive=True)
        return path, "image/jpeg"
    except Exception:
        upload.seek(0)
        media_type = upload.content_type or mimetypes.guess_type(upload.name or "")[0] or "image/jpeg"
        suffix = Path(upload.name or "").suffix[:16] or mimetypes.guess_extension(media_type) or ".img"
        path = target_dir / f"{uuid.uuid4().hex[:12]}_{base}{suffix}"
        with path.open("wb") as destination:
            for chunk in upload.chunks():
                destination.write(chunk)
        return path, media_type


def _video_project_storage_bytes(project: VideoEditorProject) -> int:
    return _json_size(project.state_json or {}) + sum(asset.size + _path_size(asset.thumbnail_path) for asset in project.assets.all())


def _design_project_storage_bytes(project: DesignerProject) -> int:
    return _json_size(project.state_json or {}) + _path_size(project.preview_path) + sum(asset.size for asset in project.assets.all())


def _owned_job_records(owner_id: int | None, guest_key: str = ""):
    queryset = JobRecord.objects.all()
    if owner_id is not None:
        return queryset.filter(owner_id=owner_id)
    return queryset.filter(owner__isnull=True, guest_key=guest_key)


def _job_param(record: JobRecord, key: str, default=None):
    try:
        params = json.loads(record.params_json or "{}")
    except Exception:
        params = {}
    return params.get(key, default) if isinstance(params, dict) else default


def _video_asset_waveform_path(asset: VideoEditorAsset) -> Path:
    return _video_project_media_dir(asset.project) / "waveforms" / f"{asset.id}.json"


def _build_compact_waveform(path: Path, count: int = 96) -> list[float]:
    if not path.exists():
        return [0.0] * count
    data = path.read_bytes()
    if not data:
        return [0.0] * count
    step = max(1, len(data) // count)
    samples: list[float] = []
    for index in range(count):
        chunk = data[index * step : (index + 1) * step]
        if not chunk:
            samples.append(0.0)
            continue
        value = sum(abs(byte - 128) for byte in chunk) / (len(chunk) * 128)
        samples.append(round(max(0.04, min(1.0, value)), 3))
    return samples


def _render_video_project_cover(project: VideoEditorProject, output: Path, time_seconds: float) -> None:
    state = project.state_json or {}
    width, height = _video_export_size(state, "720p")
    assets = {asset.id: asset for asset in project.assets.all()}
    clips = state.get("clips") if isinstance(state.get("clips"), list) else []
    active = [clip for clip in clips if isinstance(clip, dict) and float(clip.get("start") or 0) <= time_seconds <= float(clip.get("start") or 0) + float(clip.get("duration") or 0)]
    image = Image.new("RGB", (width, height), _state_background_color(state))
    visual = next((clip for clip in active if clip.get("type") in {"image", "video"} and assets.get(int(clip.get("assetId") or 0))), None)
    if visual:
        asset = assets[int(visual.get("assetId") or 0)]
        source = Path(asset.thumbnail_path or asset.file_path)
        if source.exists() and asset.media_type.startswith("image/"):
            overlay = Image.open(source).convert("RGB")
            overlay.thumbnail((width, height), Image.Resampling.LANCZOS)
            image.paste(overlay, ((width - overlay.width) // 2, (height - overlay.height) // 2))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=90, optimize=True)


def _state_background_color(state: dict[str, object]) -> str:
    value = str(state.get("backgroundValue") or state.get("background") or "#000000")
    if value.startswith("#") and len(value) in {4, 7}:
        return value
    return "#000000"


def _path_size(path_text: str) -> int:
    if not path_text:
        return 0
    path = Path(path_text)
    return path.stat().st_size if path.exists() and path.is_file() else 0


def _video_project_media_dir(project: VideoEditorProject) -> Path:
    owner = f"user_{project.owner_id}" if project.owner_id else f"guest_{project.guest_key or 'anon'}"
    return settings.storage_dir / "django_video_projects" / owner / str(project.id)


def _design_project_media_dir(project: DesignerProject) -> Path:
    owner = f"user_{project.owner_id}" if project.owner_id else f"guest_{project.guest_key or 'anon'}"
    return settings.storage_dir / "django_design_projects" / owner / str(project.id)


def _save_design_project_preview(data_url: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    raw = data_url.split(",", 1)[1] if "," in data_url else data_url
    image = Image.open(BytesIO(b64decode(raw))).convert("RGB")
    image.thumbnail((900, 640), Image.Resampling.LANCZOS)
    path = target_dir / f"preview_{uuid.uuid4().hex[:12]}.jpg"
    image.save(path, "JPEG", quality=82, optimize=True)
    return path


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


def _delete_design_project_media(project: DesignerProject) -> None:
    for asset in project.assets.all():
        path = Path(asset.file_path)
        try:
            if path.resolve().is_relative_to(settings.storage_dir.resolve()) and path.exists() and path.is_file():
                path.unlink()
        except Exception:
            pass
    if project.preview_path:
        path = Path(project.preview_path)
        try:
            if path.resolve().is_relative_to(settings.storage_dir.resolve()) and path.exists() and path.is_file():
                path.unlink()
        except Exception:
            pass
    directory = _design_project_media_dir(project)
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


def _transfer_guest_design_projects(guest_key: str, user) -> None:
    if not guest_key:
        return
    DesignerProject.objects.filter(owner__isnull=True, guest_key=guest_key).update(owner=user, guest_key="")


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
        "next_url": _safe_next_url(request),
    }


def _safe_next_url(request: HttpRequest) -> str:
    value = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if value and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return value
    return ""


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
    period_seconds = max(current_plan.period_days * 86400, 1)
    used_seconds = max(0, period_seconds - left_seconds) if active_until else 0
    days_used = min(current_plan.period_days, int(used_seconds // 86400)) if active_until else 0
    remaining_value_cents = 0
    if active_until and current_plan.period_days:
        remaining_value_cents = round(current_plan.price_cents * min(1, left_seconds / period_seconds))
    plan_payload = []
    for plan in PLANS:
        localized = localized_plan(plan, language)
        due_cents = prorated_due_cents(current_plan if active_until else None, plan, left_seconds)
        credit_cents = 0 if plan.code == current_plan.code else min(plan.price_cents, remaining_value_cents)
        plan_payload.append(
            {
                **vars(localized),
                "checkout_url": f"{reverse('billing:checkout')}?{urlencode({'plan': plan.code, 'due': due_cents, 'next': request.get_full_path()})}",
                "due_cents": due_cents,
                "due_display": _money_display(due_cents),
                "credit_cents": credit_cents,
                "credit_display": _money_display(credit_cents),
                "is_current": plan.code == current_plan.code,
            }
        )
    return {
        "current_plan": localized_plan(current_plan, language),
        "plans": plan_payload,
        "active_until": active_until,
        "days_left": days_left,
        "days_used": days_used,
        "remaining_value_cents": remaining_value_cents,
        "remaining_value_display": _money_display(remaining_value_cents),
        "storage_used_text": account_stats.get("total_output_size_text", ""),
        "storage_available_text": account_stats.get("storage_available_text", ""),
        "storage_percent": account_stats.get("storage_percent", 0),
    }


def _money_display(cents: int) -> str:
    return f"{cents // 100}$" if cents % 100 == 0 else f"{cents / 100:.2f}$"


def _storage_quota(request: HttpRequest, account_stats: dict[str, object]) -> dict[str, object]:
    used = int(account_stats.get("total_output_size") or 0)
    owner_id, guest_key = _workspace_identity(request)
    project_bytes = sum(_video_owner_queryset(owner_id, guest_key).values_list("storage_bytes", flat=True))
    design_bytes = sum(_design_owner_queryset(owner_id, guest_key).values_list("storage_bytes", flat=True))
    used += int(project_bytes or 0)
    used += int(design_bytes or 0)
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
