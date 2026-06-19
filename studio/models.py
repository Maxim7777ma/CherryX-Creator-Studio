from __future__ import annotations

import secrets
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageOps


def _webp_upload_to(instance, filename: str) -> str:
    folder = "learn" if isinstance(instance, LearningArticle) else "community"
    suffix = Path(filename).suffix.lower()[:12]
    return f"{folder}/source/{secrets.token_urlsafe(8)}-{Path(filename).stem[:48]}{suffix}"


def _make_unique_slug(model: type[models.Model], value: str, pk: int | None = None) -> str:
    base = slugify(value or "", allow_unicode=True).strip("-") or secrets.token_urlsafe(6)
    slug = base[:80]
    index = 2
    while model.objects.filter(slug=slug).exclude(pk=pk).exists():
        suffix = f"-{index}"
        slug = f"{base[:80 - len(suffix)]}{suffix}"
        index += 1
    return slug


def _convert_image_field_to_webp(instance, field_name: str, target_folder: str) -> None:
    image_field = getattr(instance, field_name)
    if not image_field or str(image_field.name).lower().endswith(".webp"):
        return
    original_name = image_field.name
    try:
        image_field.open("rb")
        with Image.open(image_field) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=84, method=6)
    finally:
        image_field.close()
    webp_name = f"{target_folder}/{Path(original_name).stem[:72] or secrets.token_urlsafe(6)}.webp"
    storage = image_field.storage
    image_field.name = storage.save(webp_name, ContentFile(output.getvalue()))
    if original_name and original_name != image_field.name and storage.exists(original_name):
        storage.delete(original_name)


class JobRecord(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="studio_jobs", null=True, blank=True, on_delete=models.CASCADE)
    guest_key = models.CharField(max_length=80, blank=True, db_index=True)
    job_id = models.CharField(max_length=32, unique=True, db_index=True)
    kind = models.CharField(max_length=48)
    title = models.CharField(max_length=240)
    status = models.CharField(max_length=24, db_index=True, default="queued")
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.TextField(blank=True)
    error = models.TextField(blank=True)
    params_json = models.TextField(blank=True)
    output_count = models.PositiveIntegerField(default=0)
    total_output_size = models.BigIntegerField(default=0)
    primary_output_type = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"], name="studio_jobr_owner_i_8ab6a1_idx"),
            models.Index(fields=["guest_key", "-created_at"], name="studio_jobr_guest_k_739bdb_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.job_id} {self.status} {self.title}"


class JobOutputRecord(models.Model):
    job = models.ForeignKey(JobRecord, related_name="outputs", on_delete=models.CASCADE)
    label = models.CharField(max_length=160)
    path = models.TextField()
    media_type = models.CharField(max_length=120, default="application/octet-stream")
    size = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["job", "created_at"], name="studio_jobo_job_id_7f29d2_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.job.job_id}: {self.label}"


class JobEventRecord(models.Model):
    job = models.ForeignKey(JobRecord, related_name="events", on_delete=models.CASCADE)
    status = models.CharField(max_length=24)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.job.job_id}: {self.progress}% {self.status}"


class VideoEditorProject(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="video_editor_projects", null=True, blank=True, on_delete=models.CASCADE)
    guest_key = models.CharField(max_length=80, blank=True, db_index=True)
    title = models.CharField(max_length=180, default="Новый проект")
    state_json = models.JSONField(default=dict, blank=True)
    storage_bytes = models.BigIntegerField(default=0)
    asset_count = models.PositiveIntegerField(default=0)
    clip_count = models.PositiveIntegerField(default=0)
    duration_seconds = models.FloatField(default=0)
    thumbnail_path = models.TextField(blank=True)
    last_export_status = models.CharField(max_length=24, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["owner", "-updated_at"]),
            models.Index(fields=["guest_key", "-updated_at"]),
        ]

    def __str__(self) -> str:
        return f"video-project:{self.id}:{self.title}"


class VideoEditorAsset(models.Model):
    project = models.ForeignKey(VideoEditorProject, related_name="assets", on_delete=models.CASCADE)
    kind = models.CharField(max_length=16, db_index=True)
    file_path = models.TextField()
    media_type = models.CharField(max_length=120, default="application/octet-stream")
    size = models.BigIntegerField(default=0)
    original_name = models.CharField(max_length=240, blank=True)
    thumbnail_path = models.TextField(blank=True)
    duration = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["project", "kind"], name="studio_vide_project_397c70_idx"),
        ]

    def __str__(self) -> str:
        return f"video-asset:{self.id}:{self.kind}:{self.original_name}"


class DesignerProject(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="designer_projects", null=True, blank=True, on_delete=models.CASCADE)
    guest_key = models.CharField(max_length=80, blank=True, db_index=True)
    title = models.CharField(max_length=180, default="New design")
    state_json = models.JSONField(default=dict, blank=True)
    storage_bytes = models.BigIntegerField(default=0)
    preview_path = models.TextField(blank=True)
    asset_count = models.PositiveIntegerField(default=0)
    object_count = models.PositiveIntegerField(default=0)
    last_export_status = models.CharField(max_length=24, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["owner", "-updated_at"]),
            models.Index(fields=["guest_key", "-updated_at"]),
        ]

    def __str__(self) -> str:
        return f"design-project:{self.id}:{self.title}"


class DesignerAsset(models.Model):
    project = models.ForeignKey(DesignerProject, related_name="assets", on_delete=models.CASCADE)
    kind = models.CharField(max_length=16, db_index=True, default="image")
    file_path = models.TextField()
    media_type = models.CharField(max_length=120, default="application/octet-stream")
    size = models.BigIntegerField(default=0)
    original_name = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["project", "kind"], name="studio_desi_project_5a35b9_idx"),
        ]

    def __str__(self) -> str:
        return f"design-asset:{self.id}:{self.original_name}"


class MusicEditorProject(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="music_editor_projects", null=True, blank=True, on_delete=models.CASCADE)
    guest_key = models.CharField(max_length=80, blank=True, db_index=True)
    title = models.CharField(max_length=180, default="Новый проект")
    state_json = models.JSONField(default=dict, blank=True)
    storage_bytes = models.BigIntegerField(default=0)
    asset_count = models.PositiveIntegerField(default=0)
    clip_count = models.PositiveIntegerField(default=0)
    duration_seconds = models.FloatField(default=0)
    last_export_status = models.CharField(max_length=24, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["owner", "-updated_at"], name="studio_musi_owner_i_idx"),
            models.Index(fields=["guest_key", "-updated_at"], name="studio_musi_guest__idx"),
        ]

    def __str__(self) -> str:
        return f"music-project:{self.id}:{self.title}"


class MusicEditorAsset(models.Model):
    project = models.ForeignKey(MusicEditorProject, related_name="assets", on_delete=models.CASCADE)
    kind = models.CharField(max_length=16, db_index=True)
    file_path = models.TextField()
    media_type = models.CharField(max_length=120, default="application/octet-stream")
    size = models.BigIntegerField(default=0)
    original_name = models.CharField(max_length=240, blank=True)
    duration = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["project", "kind"], name="studio_musi_project_2c31ad_idx"),
        ]

    def __str__(self) -> str:
        return f"music-asset:{self.id}:{self.kind}:{self.original_name}"


class WorkspaceShare(models.Model):
    RESOURCE_DESIGN = "design_project"
    RESOURCE_VIDEO = "video_project"
    RESOURCE_MUSIC = "music_project"

    RESOURCE_CHOICES = [
        (RESOURCE_DESIGN, "Design project"),
        (RESOURCE_VIDEO, "Video project"),
        (RESOURCE_MUSIC, "Music project"),
    ]
    ROLE_VIEWER = "viewer"
    ROLE_EDITOR = "editor"
    ROLE_CHOICES = [
        (ROLE_VIEWER, "Viewer"),
        (ROLE_EDITOR, "Editor"),
    ]
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REVOKED = "revoked"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REVOKED, "Revoked"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="owned_workspace_shares", on_delete=models.CASCADE)
    invited_user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="workspace_shares", null=True, blank=True, on_delete=models.SET_NULL)
    resource_type = models.CharField(max_length=32, choices=RESOURCE_CHOICES, db_index=True)
    resource_id = models.PositiveBigIntegerField(db_index=True)
    email = models.EmailField(db_index=True)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    token = models.CharField(max_length=80, unique=True, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "resource_type", "resource_id", "email"], name="unique_workspace_share_invite"),
        ]
        indexes = [
            models.Index(fields=["resource_type", "resource_id", "status"]),
            models.Index(fields=["invited_user", "status"]),
        ]

    def __str__(self) -> str:
        return f"share:{self.resource_type}:{self.resource_id}:{self.email}:{self.role}:{self.status}"


class AccountProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="studio_profile", on_delete=models.CASCADE)
    avatar_url = models.URLField(max_length=600, blank=True)
    avatar_path = models.TextField(blank=True)
    accent_color = models.CharField(max_length=24, default="#2563eb")
    theme_mode = models.CharField(max_length=24, default="light")
    interface_language = models.CharField(max_length=8, default="en")
    telegram_user_id = models.BigIntegerField(null=True, blank=True, unique=True)
    telegram_username = models.CharField(max_length=80, blank=True)
    telegram_first_name = models.CharField(max_length=120, blank=True)
    telegram_link_token = models.CharField(max_length=48, blank=True, db_index=True)
    telegram_link_token_created_at = models.DateTimeField(null=True, blank=True)
    cherryx_balance = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"profile:{self.user_id}"


class MagicLoginToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="magic_login_tokens", on_delete=models.CASCADE)
    token = models.CharField(max_length=80, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "used_at", "expires_at"], name="studio_magi_token_46e7b8_idx"),
        ]

    @classmethod
    def create_for_user(cls, user, expires_at):
        return cls.objects.create(user=user, token=secrets.token_urlsafe(32), expires_at=expires_at)

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()

    def __str__(self) -> str:
        return f"magic-login:{self.user_id}:{self.created_at:%Y-%m-%d}"


class LearningArticle(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_PUBLISHED, "Published")]

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=96, unique=True, allow_unicode=True, blank=True)
    excerpt = models.TextField(blank=True)
    body = models.TextField()
    cover_image = models.ImageField(upload_to=_webp_upload_to, blank=True)
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    featured = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-featured", "-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "-published_at"]),
            models.Index(fields=["featured", "status"]),
        ]

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = _make_unique_slug(LearningArticle, self.title, self.pk)
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)
        if self.cover_image and not self.cover_image.name.lower().endswith(".webp"):
            _convert_image_field_to_webp(self, "cover_image", "learn/webp")
            super().save(update_fields=["cover_image", "updated_at"])

    def __str__(self) -> str:
        return self.title


class CommunityWork(models.Model):
    KIND_VIDEO = "video"
    KIND_IMAGE = "image"
    KIND_TEXT = "text"
    KIND_MUSIC = "music"
    KIND_CHOICES = [(KIND_VIDEO, "Video"), (KIND_IMAGE, "Image"), (KIND_TEXT, "Text"), (KIND_MUSIC, "Music")]
    ACCESS_FREE = "free"
    ACCESS_PAID = "paid"
    ACCESS_CHOICES = [(ACCESS_FREE, "Free"), (ACCESS_PAID, "Paid with CherryX")]
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_PUBLISHED, "Published")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="community_works", null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=96, unique=True, allow_unicode=True, blank=True)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, db_index=True)
    excerpt = models.TextField(blank=True)
    body = models.TextField(blank=True)
    media_file = models.FileField(upload_to="community/private/", blank=True)
    cover_image = models.ImageField(upload_to=_webp_upload_to, blank=True)
    source_job = models.ForeignKey(JobRecord, related_name="published_works", null=True, blank=True, on_delete=models.SET_NULL)
    source_video_project = models.ForeignKey(VideoEditorProject, related_name="published_works", null=True, blank=True, on_delete=models.SET_NULL)
    source_design_project = models.ForeignKey(DesignerProject, related_name="published_works", null=True, blank=True, on_delete=models.SET_NULL)
    source_music_project = models.ForeignKey(MusicEditorProject, related_name="published_works", null=True, blank=True, on_delete=models.SET_NULL)
    access = models.CharField(max_length=16, choices=ACCESS_CHOICES, default=ACCESS_FREE, db_index=True)
    price_cherryx = models.PositiveIntegerField(default=0)
    download_count = models.PositiveIntegerField(default=0)
    purchase_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    featured = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-featured", "-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["kind", "status", "-published_at"]),
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["access", "status"]),
        ]

    @property
    def is_paid(self) -> bool:
        return self.access == self.ACCESS_PAID and self.price_cherryx > 0

    @property
    def price_usd_display(self) -> str:
        from billing.services import cherryx_to_usd_display_approx

        return cherryx_to_usd_display_approx(int(self.price_cherryx or 0))

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = _make_unique_slug(CommunityWork, self.title, self.pk)
        if self.access == self.ACCESS_FREE:
            self.price_cherryx = 0
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)
        if self.cover_image and not self.cover_image.name.lower().endswith(".webp"):
            _convert_image_field_to_webp(self, "cover_image", "community/webp")
            super().save(update_fields=["cover_image", "updated_at"])
        if self.kind == self.KIND_IMAGE and self.media_file and not self.media_file.name.lower().endswith(".webp"):
            _convert_image_field_to_webp(self, "media_file", "community/private/webp")
            super().save(update_fields=["media_file", "updated_at"])

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title}"


class CommunityPurchase(models.Model):
    work = models.ForeignKey(CommunityWork, related_name="purchases", on_delete=models.CASCADE)
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="community_purchases", on_delete=models.CASCADE)
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="community_sales", null=True, blank=True, on_delete=models.SET_NULL)
    price_cherryx = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["work", "buyer"], name="unique_community_purchase"),
        ]
        indexes = [
            models.Index(fields=["buyer", "-created_at"]),
            models.Index(fields=["seller", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"purchase:{self.work_id}:{self.buyer_id}:{self.price_cherryx}"
