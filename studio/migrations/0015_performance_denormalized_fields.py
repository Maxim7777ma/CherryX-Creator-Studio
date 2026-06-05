from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studio", "0014_musiceditorproject_musiceditorasset"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobrecord",
            name="output_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="jobrecord",
            name="total_output_size",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="jobrecord",
            name="primary_output_type",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="videoeditorproject",
            name="asset_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="videoeditorproject",
            name="clip_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="videoeditorproject",
            name="duration_seconds",
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name="videoeditorproject",
            name="thumbnail_path",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="videoeditorproject",
            name="last_export_status",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AddField(
            model_name="designerproject",
            name="asset_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="designerproject",
            name="object_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="designerproject",
            name="last_export_status",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AddField(
            model_name="musiceditorproject",
            name="asset_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="musiceditorproject",
            name="clip_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="musiceditorproject",
            name="duration_seconds",
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name="musiceditorproject",
            name="last_export_status",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AlterField(
            model_name="workspaceshare",
            name="resource_type",
            field=models.CharField(
                choices=[
                    ("design_project", "Design project"),
                    ("video_project", "Video project"),
                    ("music_project", "Music project"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
        migrations.AddIndex(
            model_name="jobrecord",
            index=models.Index(fields=["owner", "-created_at"], name="studio_jobr_owner_i_8ab6a1_idx"),
        ),
        migrations.AddIndex(
            model_name="jobrecord",
            index=models.Index(fields=["guest_key", "-created_at"], name="studio_jobr_guest_k_739bdb_idx"),
        ),
        migrations.AddIndex(
            model_name="joboutputrecord",
            index=models.Index(fields=["job", "created_at"], name="studio_jobo_job_id_7f29d2_idx"),
        ),
        migrations.AddIndex(
            model_name="videoeditorasset",
            index=models.Index(fields=["project", "kind"], name="studio_vide_project_397c70_idx"),
        ),
        migrations.AddIndex(
            model_name="designerasset",
            index=models.Index(fields=["project", "kind"], name="studio_desi_project_5a35b9_idx"),
        ),
        migrations.AddIndex(
            model_name="musiceditorasset",
            index=models.Index(fields=["project", "kind"], name="studio_musi_project_2c31ad_idx"),
        ),
    ]
