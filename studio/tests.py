from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import secrets
import subprocess
from tempfile import TemporaryDirectory
import time

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from . import views
from .models import DesignerAsset, DesignerProject, JobRecord, VideoEditorAsset, VideoEditorProject, WorkspaceShare


class VideoProjectDeleteTests(TransactionTestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_settings = views.settings
        views.settings = replace(views.settings, storage_dir=Path(self.temp_dir.name))
        self.addCleanup(lambda: setattr(views, "settings", self.original_settings))
        self.user = get_user_model().objects.create_user("owner@example.com", password="pass12345")
        self.other_user = get_user_model().objects.create_user("other@example.com", password="pass12345")
        self.client.force_login(self.user)

    def make_project(self, owner=None, title: str = "Project") -> tuple[VideoEditorProject, Path, Path]:
        project = VideoEditorProject.objects.create(owner=owner or self.user, title=title, state_json={"title": title})
        media_dir = views._video_project_media_dir(project)
        media_dir.mkdir(parents=True, exist_ok=True)
        file_path = media_dir / "clip.mp4"
        thumb_path = media_dir / "thumb.jpg"
        file_path.write_bytes(b"video")
        thumb_path.write_bytes(b"thumb")
        VideoEditorAsset.objects.create(
            project=project,
            kind="video",
            file_path=str(file_path),
            thumbnail_path=str(thumb_path),
            size=file_path.stat().st_size,
            original_name="clip.mp4",
        )
        project.storage_bytes = views._video_project_storage_bytes(project)
        project.save(update_fields=["storage_bytes"])
        return project, media_dir, file_path

    def test_single_delete_removes_project_and_media_directory(self) -> None:
        project, media_dir, file_path = self.make_project()

        response = self.client.post(reverse("studio:delete_video_project", args=[project.id]), data="{}", content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(VideoEditorProject.objects.filter(id=project.id).exists())
        self.assertFalse(file_path.exists())
        self.assertFalse(media_dir.exists())

    def test_bulk_delete_removes_media_for_owned_projects_only(self) -> None:
        project_a, media_dir_a, file_path_a = self.make_project(title="A")
        project_b, media_dir_b, file_path_b = self.make_project(title="B")
        other_project, other_media_dir, other_file_path = self.make_project(owner=self.other_user, title="Other")

        response = self.client.post(
            reverse("studio:delete_video_projects"),
            data=json.dumps({"ids": [project_a.id, project_b.id, other_project.id]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deleted_count"], 2)
        self.assertCountEqual(payload["deleted_ids"], [project_a.id, project_b.id])
        self.assertFalse(VideoEditorProject.objects.filter(id__in=[project_a.id, project_b.id]).exists())
        self.assertTrue(VideoEditorProject.objects.filter(id=other_project.id).exists())
        self.assertFalse(file_path_a.exists())
        self.assertFalse(file_path_b.exists())
        self.assertFalse(media_dir_a.exists())
        self.assertFalse(media_dir_b.exists())
        self.assertTrue(other_file_path.exists())
        self.assertTrue(other_media_dir.exists())

    def test_rename_updates_title_without_clearing_project_state(self) -> None:
        project, _, _ = self.make_project(title="Original")
        project.state_json = {"title": "Original", "clips": [{"id": "clip-1"}], "tracks": [{"id": "track-1"}]}
        project.save(update_fields=["state_json"])

        response = self.client.post(
            reverse("studio:rename_video_project", args=[project.id]),
            data=json.dumps({"title": "Fresh cut"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.title, "Fresh cut")
        self.assertEqual(project.state_json["clips"], [{"id": "clip-1"}])
        self.assertEqual(project.state_json["tracks"], [{"id": "track-1"}])

    def test_asset_delete_removes_files_and_referencing_clips(self) -> None:
        project, media_dir, file_path = self.make_project(title="Asset delete")
        asset = project.assets.first()
        project.state_json = {"clips": [{"id": "clip-1", "assetId": asset.id}, {"id": "clip-2", "assetId": 999}]}
        project.save(update_fields=["state_json"])

        response = self.client.post(reverse("studio:delete_video_project_asset", args=[project.id, asset.id]))

        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertFalse(file_path.exists())
        self.assertEqual(project.state_json["clips"], [{"id": "clip-2", "assetId": 999}])
        self.assertTrue(media_dir.exists())

    def test_asset_rename_updates_owned_asset_display_name_only(self) -> None:
        project, _, file_path = self.make_project(title="Rename asset")
        asset = project.assets.first()

        response = self.client.post(
            reverse("studio:rename_video_project_asset", args=[project.id, asset.id]),
            data=json.dumps({"name": "Fresh name.mp4"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        asset.refresh_from_db()
        self.assertEqual(asset.original_name, "Fresh name.mp4")
        self.assertEqual(Path(asset.file_path), file_path)
        self.assertEqual(response.json()["asset"]["name"], "Fresh name.mp4")

    def test_asset_rename_rejects_foreign_project(self) -> None:
        other_project, _, _ = self.make_project(owner=self.other_user, title="Other asset")
        asset = other_project.assets.first()

        response = self.client.post(
            reverse("studio:rename_video_project_asset", args=[other_project.id, asset.id]),
            data=json.dumps({"name": "Nope.mp4"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_export_endpoint_rejects_foreign_project(self) -> None:
        other_project, _, _ = self.make_project(owner=self.other_user, title="Other export")

        response = self.client.post(
            reverse("studio:start_video_project_export", args=[other_project.id]),
            data=json.dumps({"quality": "720p"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_export_job_creates_mp4_for_empty_project(self) -> None:
        project = VideoEditorProject.objects.create(owner=self.user, title="Exportable", state_json={"aspect": "1 / 1", "clips": []})

        response = self.client.post(
            reverse("studio:start_video_project_export", args=[project.id]),
            data=json.dumps({"quality": "720p"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        job = response.json()["job"]
        deadline = time.time() + 20
        while job["status"] not in {"done", "failed"} and time.time() < deadline:
            time.sleep(0.4)
            job = self.client.get(reverse("studio:video_project_export_status", args=[project.id, job["id"]])).json()["job"]
        self.assertEqual(job["status"], "done", job.get("error"))
        self.assertTrue(JobRecord.objects.filter(job_id=job["id"], kind="video_export", status="completed").exists())
        self.assertTrue(job["download_url"])
        download = self.client.get(job["download_url"])
        self.assertEqual(download.status_code, 200)
        download.close()


class DesignerProjectTests(TransactionTestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_settings = views.settings
        views.settings = replace(views.settings, storage_dir=Path(self.temp_dir.name))
        self.addCleanup(lambda: setattr(views, "settings", self.original_settings))
        self.user = get_user_model().objects.create_user("designer@example.com", password="pass12345")
        self.other_user = get_user_model().objects.create_user("designer-other@example.com", password="pass12345")
        self.client.force_login(self.user)

    def image_upload(self, name: str = "poster.png") -> SimpleUploadedFile:
        image = Image.new("RGB", (64, 48), "#2563eb")
        buffer = BytesIO()
        image.save(buffer, "PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def make_project(self, owner=None, title: str = "Design") -> DesignerProject:
        project = DesignerProject.objects.create(owner=owner or self.user, title=title, state_json={"title": title, "objects": [], "vectors": []})
        media_dir = views._design_project_media_dir(project)
        media_dir.mkdir(parents=True, exist_ok=True)
        file_path = media_dir / "image.jpg"
        file_path.write_bytes(b"image")
        DesignerAsset.objects.create(project=project, kind="image", file_path=str(file_path), media_type="image/jpeg", size=file_path.stat().st_size, original_name="image.jpg")
        project.storage_bytes = views._design_project_storage_bytes(project)
        project.save(update_fields=["storage_bytes"])
        return project

    def test_create_save_rename_and_detail_for_owned_project(self) -> None:
        response = self.client.post(
            reverse("studio:create_design_project"),
            data=json.dumps({"title": "Brand board", "state": {"title": "Brand board", "objects": [{"id": "a"}], "vectors": []}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        project_id = response.json()["project"]["id"]
        response = self.client.post(
            reverse("studio:save_design_project", args=[project_id]),
            data=json.dumps({"title": "Brand board v2", "state": {"title": "Brand board v2", "objects": [{"id": "b"}], "vectors": []}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        project = DesignerProject.objects.get(id=project_id)
        self.assertEqual(project.title, "Brand board v2")
        self.assertEqual(project.state_json["objects"], [{"id": "b"}])

        response = self.client.post(
            reverse("studio:rename_design_project", args=[project_id]),
            data=json.dumps({"title": "Launch cover"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"]["title"], "Launch cover")

    def test_foreign_design_project_is_not_accessible(self) -> None:
        other_project = self.make_project(owner=self.other_user)

        response = self.client.get(reverse("studio:design_project_detail", args=[other_project.id]))

        self.assertEqual(response.status_code, 404)

    def test_upload_image_optimizes_and_counts_storage(self) -> None:
        project = DesignerProject.objects.create(owner=self.user, title="Upload", state_json={"objects": []})

        response = self.client.post(reverse("studio:upload_design_project_asset", args=[project.id]), data={"file": self.image_upload()})

        self.assertEqual(response.status_code, 200)
        asset = DesignerAsset.objects.get(project=project)
        self.assertTrue(Path(asset.file_path).exists())
        project.refresh_from_db()
        self.assertGreater(project.storage_bytes, asset.size)
        self.assertEqual(response.json()["asset"]["kind"], "image")

    def test_delete_design_project_removes_media_directory(self) -> None:
        project = self.make_project()
        media_dir = views._design_project_media_dir(project)

        response = self.client.post(reverse("studio:delete_design_project", args=[project.id]), data="{}", content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(DesignerProject.objects.filter(id=project.id).exists())
        self.assertFalse(media_dir.exists())

    def test_bulk_delete_ignores_foreign_projects(self) -> None:
        project = self.make_project(title="A")
        other_project = self.make_project(owner=self.other_user, title="Other")

        response = self.client.post(
            reverse("studio:delete_design_projects"),
            data=json.dumps({"ids": [project.id, other_project.id]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_ids"], [project.id])
        self.assertFalse(DesignerProject.objects.filter(id=project.id).exists())
        self.assertTrue(DesignerProject.objects.filter(id=other_project.id).exists())

    def test_storage_quota_includes_design_project_bytes(self) -> None:
        project = self.make_project()
        stats = views._storage_quota(self.client.get(reverse("studio:index")).wsgi_request, {"total_output_size": 0})

        self.assertIn("total_output_size_text", stats)
        self.assertGreaterEqual(stats["storage_percent"], 0)
        self.assertLess(stats["storage_available"], stats["storage_limit"])
        self.assertGreater(project.storage_bytes, 0)

    def test_export_list_rejects_foreign_project_and_lists_owned_job(self) -> None:
        project = VideoEditorProject.objects.create(owner=self.user, title="Export list", state_json={"aspect": "1 / 1", "clips": []})
        other_project = VideoEditorProject.objects.create(owner=self.other_user, title="Other list", state_json={"clips": []})
        JobRecord.objects.create(owner=self.user, job_id="owned-export", kind="video_export", title="Export", params_json=json.dumps({"project_id": project.id}), status="completed", progress=100)

        response = self.client.get(reverse("studio:list_video_project_exports", args=[project.id]))
        foreign = self.client.get(reverse("studio:list_video_project_exports", args=[other_project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(response.json()["jobs"][0]["id"], "owned-export")

    def test_cancel_export_marks_job_cancelled(self) -> None:
        project = VideoEditorProject.objects.create(owner=self.user, title="Cancel export", state_json={"clips": []})
        JobRecord.objects.create(owner=self.user, job_id="cancel-me", kind="video_export", title="Export", params_json=json.dumps({"project_id": project.id}), status="queued", progress=2)
        views._video_export_jobs["cancel-me"] = {"id": "cancel-me", "project_id": project.id, "owner_id": self.user.id, "guest_key": "", "status": "queued", "path": "", "quality": "720p"}

        response = self.client.post(reverse("studio:cancel_video_project_export", args=[project.id, "cancel-me"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"]["status"], "cancelled")
        self.assertEqual(JobRecord.objects.get(job_id="cancel-me").status, "cancelled")

    def test_upload_image_returns_optimized_visual_asset(self) -> None:
        project = VideoEditorProject.objects.create(owner=self.user, title="Image upload", state_json={"clips": []})
        image_io = BytesIO()
        Image.new("RGB", (3200, 1800), "#4f46e5").save(image_io, "JPEG", quality=95)
        upload = SimpleUploadedFile("poster.jpg", image_io.getvalue(), content_type="image/jpeg")

        response = self.client.post(reverse("studio:upload_video_project_asset", args=[project.id]), {"file": upload, "kind": "image"})

        self.assertEqual(response.status_code, 200)
        asset_payload = response.json()["asset"]
        self.assertEqual(asset_payload["kind"], "image")
        self.assertEqual(asset_payload["visual_kind"], "image")
        self.assertTrue(asset_payload["is_previewable_image"])
        asset = VideoEditorAsset.objects.get(id=asset_payload["id"])
        self.assertIn(asset.media_type, {"image/jpeg", "image/webp"})
        self.assertTrue(Path(asset.file_path).exists())
        with Image.open(asset.file_path) as saved:
            self.assertLessEqual(max(saved.size), 2560)

    def test_upload_pdf_returns_visual_file_payload_and_preview(self) -> None:
        project = VideoEditorProject.objects.create(owner=self.user, title="PDF upload", state_json={"clips": []})
        upload = SimpleUploadedFile("brief.pdf", b"%PDF-1.4\n%test\n", content_type="application/pdf")

        response = self.client.post(reverse("studio:upload_video_project_asset", args=[project.id]), {"file": upload, "kind": "image"})

        self.assertEqual(response.status_code, 200)
        asset_payload = response.json()["asset"]
        self.assertEqual(asset_payload["kind"], "image")
        self.assertEqual(asset_payload["visual_kind"], "pdf")
        self.assertFalse(asset_payload["is_previewable_image"])
        preview = self.client.get(asset_payload["preview_url"])
        self.assertEqual(preview.status_code, 200)
        preview.close()

    def test_waveform_endpoint_creates_compact_json_for_audio_asset(self) -> None:
        project = VideoEditorProject.objects.create(owner=self.user, title="Waveform", state_json={"clips": []})
        media_dir = views._video_project_media_dir(project)
        media_dir.mkdir(parents=True, exist_ok=True)
        audio_path = media_dir / "tone.mp3"
        audio_path.write_bytes(bytes(range(256)) * 8)
        asset = VideoEditorAsset.objects.create(project=project, kind="audio", file_path=str(audio_path), media_type="audio/mpeg", size=audio_path.stat().st_size, original_name="tone.mp3")

        response = self.client.post(reverse("studio:video_project_asset_waveform", args=[project.id, asset.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 96)
        self.assertEqual(len(payload["samples"]), 96)

    def test_cover_endpoint_creates_protected_image_output(self) -> None:
        project = VideoEditorProject.objects.create(owner=self.user, title="Cover", state_json={"aspect": "1 / 1", "clips": []})

        response = self.client.post(
            reverse("studio:export_video_project_cover", args=[project.id]),
            data=json.dumps({"time": 0}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        job = response.json()["job"]
        self.assertEqual(job["status"], "done")
        download = self.client.get(job["download_url"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "image/jpeg")
        download.close()

    def test_export_job_creates_mp4_for_image_and_pdf_timeline(self) -> None:
        project = VideoEditorProject.objects.create(owner=self.user, title="Visual export", state_json={"aspect": "1 / 1", "clips": []})
        media_dir = views._video_project_media_dir(project)
        media_dir.mkdir(parents=True, exist_ok=True)
        image_path = media_dir / "poster.jpg"
        Image.new("RGB", (720, 720), "#10b981").save(image_path, "JPEG", quality=90)
        pdf_path = media_dir / "brief.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%test\n")
        image_asset = VideoEditorAsset.objects.create(project=project, kind="image", file_path=str(image_path), media_type="image/jpeg", size=image_path.stat().st_size, original_name="poster.jpg")
        pdf_asset = VideoEditorAsset.objects.create(project=project, kind="image", file_path=str(pdf_path), media_type="application/pdf", size=pdf_path.stat().st_size, original_name="brief.pdf")
        project.state_json = {
            "aspect": "1 / 1",
            "clips": [
                {"id": "image-1", "type": "image", "assetId": image_asset.id, "start": 0, "duration": 1.2, "x": 50, "y": 50},
                {"id": "pdf-1", "type": "image", "assetId": pdf_asset.id, "start": 0.4, "duration": 1.0, "x": 50, "y": 70},
            ],
        }
        project.save(update_fields=["state_json"])

        response = self.client.post(
            reverse("studio:start_video_project_export", args=[project.id]),
            data=json.dumps({"quality": "720p"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        job = response.json()["job"]
        deadline = time.time() + 20
        while job["status"] not in {"done", "failed"} and time.time() < deadline:
            time.sleep(0.4)
            job = self.client.get(reverse("studio:video_project_export_status", args=[project.id, job["id"]])).json()["job"]
        self.assertEqual(job["status"], "done", job.get("error"))
        download = self.client.get(job["download_url"])
        self.assertEqual(download.status_code, 200)
        download.close()

    def test_export_job_creates_mp4_for_video_with_image_and_text_overlays(self) -> None:
        project = VideoEditorProject.objects.create(owner=self.user, title="Overlay export", state_json={"aspect": "16 / 9", "clips": []})
        media_dir = views._video_project_media_dir(project)
        media_dir.mkdir(parents=True, exist_ok=True)
        video_path = media_dir / "base.mp4"
        image_path = media_dir / "overlay.jpg"
        Image.new("RGB", (320, 240), "#f59e0b").save(image_path, "JPEG", quality=90)
        completed = subprocess.run(
            [
                views.ffmpeg_path(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=320x180:d=1.2:r=24",
                "-pix_fmt",
                "yuv420p",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        video_asset = VideoEditorAsset.objects.create(project=project, kind="video", file_path=str(video_path), media_type="video/mp4", size=video_path.stat().st_size, original_name="base.mp4", duration=1.2)
        image_asset = VideoEditorAsset.objects.create(project=project, kind="image", file_path=str(image_path), media_type="image/jpeg", size=image_path.stat().st_size, original_name="overlay.jpg")
        project.state_json = {
            "aspect": "16 / 9",
            "clips": [
                {"id": "video-1", "type": "video", "assetId": video_asset.id, "start": 0, "duration": 1.2, "sourceStart": 0},
                {"id": "image-1", "type": "image", "assetId": image_asset.id, "start": 0.1, "duration": 0.8, "x": 55, "y": 45, "scale": 30},
                {"id": "text-1", "type": "text", "start": 0.2, "duration": 0.7, "text": "Hello", "y": 72, "style": {"size": 28}},
            ],
        }
        project.save(update_fields=["state_json"])

        response = self.client.post(
            reverse("studio:start_video_project_export", args=[project.id]),
            data=json.dumps({"quality": "720p"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        job = response.json()["job"]
        deadline = time.time() + 20
        while job["status"] not in {"done", "failed"} and time.time() < deadline:
            time.sleep(0.4)
            job = self.client.get(reverse("studio:video_project_export_status", args=[project.id, job["id"]])).json()["job"]
        self.assertEqual(job["status"], "done", job.get("error"))
        download = self.client.get(job["download_url"])
        self.assertEqual(download.status_code, 200)
        download.close()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class WorkspaceSharingTests(TransactionTestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_settings = views.settings
        views.settings = replace(views.settings, storage_dir=Path(self.temp_dir.name))
        self.addCleanup(lambda: setattr(views, "settings", self.original_settings))
        mail.outbox = []
        self.owner = get_user_model().objects.create_user("owner-share@example.com", email="owner-share@example.com", password="pass12345", first_name="Owner")
        self.viewer = get_user_model().objects.create_user("viewer-share@example.com", email="viewer-share@example.com", password="pass12345")
        self.editor = get_user_model().objects.create_user("editor-share@example.com", email="editor-share@example.com", password="pass12345")
        self.other = get_user_model().objects.create_user("other-share@example.com", email="other-share@example.com", password="pass12345")
        self.design = DesignerProject.objects.create(owner=self.owner, title="Shared design", state_json={"objects": [], "vectors": []})
        self.video = VideoEditorProject.objects.create(owner=self.owner, title="Shared video", state_json={"clips": []})
        self.client.force_login(self.owner)

    def make_share(self, resource_type: str, resource, user=None, email: str = "", role: str = WorkspaceShare.ROLE_VIEWER, status: str = WorkspaceShare.STATUS_ACCEPTED, expires_at=None) -> WorkspaceShare:
        email = email or getattr(user, "email", "")
        return WorkspaceShare.objects.create(
            owner=self.owner,
            invited_user=user if status == WorkspaceShare.STATUS_ACCEPTED else None,
            resource_type=resource_type,
            resource_id=resource.id,
            email=email.lower(),
            role=role,
            status=status,
            token=secrets.token_urlsafe(12),
            expires_at=expires_at or timezone.now() + timezone.timedelta(days=14),
        )

    def image_upload(self, name: str = "share.png") -> SimpleUploadedFile:
        image_io = BytesIO()
        Image.new("RGB", (64, 64), "#2563eb").save(image_io, "PNG")
        return SimpleUploadedFile(name, image_io.getvalue(), content_type="image/png")

    def test_owner_invites_existing_and_new_email(self) -> None:
        response = self.client.post(
            reverse("studio:workspace_shares"),
            data=json.dumps({"resource_type": WorkspaceShare.RESOURCE_DESIGN, "resource_id": self.design.id, "email": self.viewer.email, "role": WorkspaceShare.ROLE_EDITOR}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        share = WorkspaceShare.objects.get(id=response.json()["share"]["id"])
        self.assertEqual(share.invited_user, self.viewer)
        self.assertEqual(share.status, WorkspaceShare.STATUS_PENDING)
        self.assertEqual(share.role, WorkspaceShare.ROLE_EDITOR)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(share.token, mail.outbox[0].body)

        response = self.client.post(
            reverse("studio:workspace_shares"),
            data=json.dumps({"resource_type": WorkspaceShare.RESOURCE_VIDEO, "resource_id": self.video.id, "email": "new-person@example.com", "role": WorkspaceShare.ROLE_VIEWER}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        share = WorkspaceShare.objects.get(id=response.json()["share"]["id"])
        self.assertIsNone(share.invited_user)
        self.assertEqual(len(mail.outbox), 2)

    def test_login_and_register_auto_accept_pending_invite(self) -> None:
        login_share = self.make_share(WorkspaceShare.RESOURCE_DESIGN, self.design, user=self.viewer, status=WorkspaceShare.STATUS_PENDING)
        self.client.logout()

        response = self.client.post(
            reverse("studio:login"),
            data={"email": self.viewer.email, "password": "pass12345", "next": reverse("studio:workspace_invite", args=[login_share.token])},
        )

        self.assertEqual(response.status_code, 302)
        login_share.refresh_from_db()
        self.assertEqual(login_share.status, WorkspaceShare.STATUS_ACCEPTED)
        self.assertEqual(login_share.invited_user, self.viewer)

        register_share = self.make_share(WorkspaceShare.RESOURCE_VIDEO, self.video, email="brand-new-share@example.com", status=WorkspaceShare.STATUS_PENDING)
        self.client.logout()
        response = self.client.post(
            reverse("studio:register"),
            data={
                "name": "Brand New",
                "email": "brand-new-share@example.com",
                "password": "pass12345",
                "password_confirm": "pass12345",
                "next": reverse("studio:workspace_invite", args=[register_share.token]),
            },
        )

        self.assertEqual(response.status_code, 302)
        register_share.refresh_from_db()
        self.assertEqual(register_share.status, WorkspaceShare.STATUS_ACCEPTED)
        self.assertEqual(register_share.invited_user.email, "brand-new-share@example.com")

    def test_viewer_can_read_but_cannot_mutate_or_share(self) -> None:
        self.make_share(WorkspaceShare.RESOURCE_DESIGN, self.design, self.viewer, role=WorkspaceShare.ROLE_VIEWER)
        self.client.force_login(self.viewer)

        detail = self.client.get(reverse("studio:design_project_detail", args=[self.design.id]))
        save = self.client.post(reverse("studio:save_design_project", args=[self.design.id]), data=json.dumps({"state": {"objects": [{"id": "x"}]}}), content_type="application/json")
        upload = self.client.post(reverse("studio:upload_design_project_asset", args=[self.design.id]), data={"file": self.image_upload()})
        delete = self.client.post(reverse("studio:delete_design_project", args=[self.design.id]), data="{}", content_type="application/json")
        share = self.client.post(
            reverse("studio:workspace_shares"),
            data=json.dumps({"resource_type": WorkspaceShare.RESOURCE_DESIGN, "resource_id": self.design.id, "email": self.other.email, "role": WorkspaceShare.ROLE_VIEWER}),
            content_type="application/json",
        )

        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.json()["project"]["is_owner"])
        self.assertFalse(detail.json()["project"]["can_edit"])
        self.assertFalse(detail.json()["project"]["can_share"])
        self.assertEqual(save.status_code, 404)
        self.assertEqual(upload.status_code, 404)
        self.assertEqual(delete.status_code, 404)
        self.assertEqual(share.status_code, 404)

    def test_editor_can_edit_content_but_cannot_manage_project(self) -> None:
        self.make_share(WorkspaceShare.RESOURCE_DESIGN, self.design, self.editor, role=WorkspaceShare.ROLE_EDITOR)
        self.make_share(WorkspaceShare.RESOURCE_VIDEO, self.video, self.editor, role=WorkspaceShare.ROLE_EDITOR)
        self.client.force_login(self.editor)

        save = self.client.post(reverse("studio:save_design_project", args=[self.design.id]), data=json.dumps({"state": {"objects": [{"id": "editor"}]}}), content_type="application/json")
        upload = self.client.post(reverse("studio:upload_design_project_asset", args=[self.design.id]), data={"file": self.image_upload("editor.png")})
        export = self.client.post(reverse("studio:start_video_project_export", args=[self.video.id]), data=json.dumps({"quality": "720p"}), content_type="application/json")
        delete = self.client.post(reverse("studio:delete_design_project", args=[self.design.id]), data="{}", content_type="application/json")
        share = self.client.post(
            reverse("studio:workspace_shares"),
            data=json.dumps({"resource_type": WorkspaceShare.RESOURCE_VIDEO, "resource_id": self.video.id, "email": self.other.email, "role": WorkspaceShare.ROLE_VIEWER}),
            content_type="application/json",
        )

        self.assertEqual(save.status_code, 200)
        self.assertEqual(upload.status_code, 200)
        self.assertEqual(export.status_code, 200)
        self.assertEqual(delete.status_code, 404)
        self.assertEqual(share.status_code, 404)

    def test_revoked_and_expired_shares_do_not_grant_access(self) -> None:
        self.make_share(WorkspaceShare.RESOURCE_DESIGN, self.design, self.viewer, status=WorkspaceShare.STATUS_REVOKED)
        self.make_share(WorkspaceShare.RESOURCE_VIDEO, self.video, self.viewer, status=WorkspaceShare.STATUS_ACCEPTED, expires_at=timezone.now() - timezone.timedelta(seconds=1))
        self.client.force_login(self.viewer)

        design = self.client.get(reverse("studio:design_project_detail", args=[self.design.id]))
        video = self.client.get(reverse("studio:video_project_detail", args=[self.video.id]))

        self.assertEqual(design.status_code, 404)
        self.assertEqual(video.status_code, 404)

    def test_shared_projects_appear_in_project_lists_with_access_flags(self) -> None:
        self.make_share(WorkspaceShare.RESOURCE_DESIGN, self.design, self.viewer, role=WorkspaceShare.ROLE_VIEWER)
        self.make_share(WorkspaceShare.RESOURCE_VIDEO, self.video, self.viewer, role=WorkspaceShare.ROLE_EDITOR)
        self.client.force_login(self.viewer)

        design_projects = self.client.get(reverse("studio:design_projects")).json()["projects"]
        video_projects = self.client.get(reverse("studio:video_projects")).json()["projects"]

        self.assertEqual(design_projects[0]["id"], self.design.id)
        self.assertEqual(design_projects[0]["access_role"], WorkspaceShare.ROLE_VIEWER)
        self.assertFalse(design_projects[0]["is_owner"])
        self.assertFalse(design_projects[0]["can_edit"])
        self.assertEqual(video_projects[0]["id"], self.video.id)
        self.assertEqual(video_projects[0]["access_role"], WorkspaceShare.ROLE_EDITOR)
        self.assertTrue(video_projects[0]["can_edit"])

    def test_wrong_email_cannot_accept_invite(self) -> None:
        share = self.make_share(WorkspaceShare.RESOURCE_DESIGN, self.design, user=self.viewer, status=WorkspaceShare.STATUS_PENDING)
        self.client.force_login(self.other)

        response = self.client.get(reverse("studio:workspace_invite", args=[share.token]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This invite is for another email")
        share.refresh_from_db()
        self.assertEqual(share.status, WorkspaceShare.STATUS_PENDING)
