from __future__ import annotations

from pathlib import Path
import json
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from billing.services import sync_telegram_star_rate
from src import web_actions
from studio.models import JobRecord
from studio import views


GENERIC_JOB_KINDS = {
    "convert",
    "youtube",
    "download",
    "youtube_cover",
    "cover",
    "subtitles",
    "package",
    "resume",
}
VIDEO_JOB_KINDS = {"video_export", "video_cover", "video_subtitles"}
SUPPORTED_JOB_KINDS = GENERIC_JOB_KINDS | VIDEO_JOB_KINDS


class Command(BaseCommand):
    help = "Run persistent CherryX background jobs from the Django database queue."
    _last_rate_sync_check = 0.0

    def add_arguments(self, parser) -> None:
        parser.add_argument("--once", action="store_true", help="Process available jobs and exit.")
        parser.add_argument("--sleep", type=float, default=1.0, help="Seconds to wait between empty queue polls.")
        parser.add_argument("--recover-running", action="store_true", default=True, help="Requeue running jobs on worker startup.")
        parser.add_argument("--no-recover-running", action="store_false", dest="recover_running", help="Leave running jobs untouched on startup.")

    def handle(self, *args, **options) -> None:
        if options["recover_running"]:
            recovered = JobRecord.objects.filter(kind__in=SUPPORTED_JOB_KINDS, status="running").update(
                status="queued",
                message="Requeued after worker restart",
                error="",
                updated_at=timezone.now(),
            )
            if recovered:
                self.stdout.write(self.style.WARNING(f"Requeued {recovered} interrupted job(s)."))

        self.stdout.write(self.style.SUCCESS("CherryX worker started."))
        while True:
            self._write_heartbeat()
            self._sync_daily_rates()
            record = self._claim_next_job()
            if not record:
                if options["once"]:
                    break
                time.sleep(max(0.1, float(options["sleep"] or 1.0)))
                continue
            self._run_record(record)
            if options["once"]:
                continue

    def _claim_next_job(self) -> JobRecord | None:
        close_old_connections()
        record = JobRecord.objects.filter(kind__in=SUPPORTED_JOB_KINDS, status="queued").order_by("created_at", "id").first()
        if not record:
            return None
        claimed = JobRecord.objects.filter(id=record.id, status="queued").update(
            status="running",
            progress=max(2, record.progress),
            message="Worker claimed task",
            error="",
            updated_at=timezone.now(),
        )
        if not claimed:
            return None
        record.refresh_from_db()
        return record

    def _run_record(self, record: JobRecord) -> None:
        self.stdout.write(f"Running {record.job_id} ({record.kind})")
        try:
            if record.kind in VIDEO_JOB_KINDS:
                self._run_video_record(record)
            else:
                web_actions.run_persisted_job(record.job_id)
            self.stdout.write(self.style.SUCCESS(f"Finished {record.job_id}"))
        except Exception as exc:
            JobRecord.objects.filter(id=record.id).update(
                status="failed",
                progress=100,
                message="Worker failed task",
                error=str(exc),
                updated_at=timezone.now(),
            )
            self.stderr.write(self.style.ERROR(f"Failed {record.job_id}: {exc}"))
        finally:
            close_old_connections()

    def _sync_daily_rates(self) -> None:
        now = time.time()
        if now - self._last_rate_sync_check < 300:
            return
        self._last_rate_sync_check = now
        try:
            sync_telegram_star_rate()
        except Exception:
            self.stderr.write(self.style.WARNING("Telegram Star rate sync failed."))

    def _write_heartbeat(self) -> None:
        try:
            path = Path("data") / "worker_heartbeat.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "service": "worker",
                        "status": "ok",
                        "time": time.time(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            self.stderr.write(self.style.WARNING("Worker heartbeat write failed."))

    def _run_video_record(self, record: JobRecord) -> None:
        params = _loads_params(record.params_json)
        project_id = int(params.get("project_id") or 0)
        if record.kind == "video_export":
            output = Path(str(params.get("path") or ""))
            quality = str(params.get("quality") or "720p")
            views._run_video_project_export(record.job_id, project_id, quality, output)
            return
        if record.kind == "video_cover":
            output = Path(str(params.get("path") or ""))
            time_seconds = float(params.get("time") or 0)
            views._run_video_project_cover(record.job_id, project_id, output, time_seconds)
            return
        if record.kind == "video_subtitles":
            asset_id = int(params.get("asset_id") or 0)
            views._run_video_project_subtitles(record.job_id, project_id, asset_id, params)
            return
        raise ValueError(f"Unsupported video job kind: {record.kind}")


def _loads_params(raw: str) -> dict[str, object]:
    try:
        data = json.loads(raw or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
