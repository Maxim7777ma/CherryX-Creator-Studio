from __future__ import annotations

from django.conf import settings
from django.db import models


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
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"profile:{self.user_id}"
