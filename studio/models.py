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
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

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

    def __str__(self) -> str:
        return f"video-asset:{self.id}:{self.kind}:{self.original_name}"


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
