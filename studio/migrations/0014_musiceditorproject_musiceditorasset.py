# Generated migration for Music Editor models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('studio', '0013_workspaceshare'),
    ]

    operations = [
        migrations.CreateModel(
            name='MusicEditorProject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('guest_key', models.CharField(blank=True, db_index=True, max_length=80)),
                ('title', models.CharField(default='Новый проект', max_length=180)),
                ('state_json', models.JSONField(blank=True, default=dict)),
                ('storage_bytes', models.BigIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='music_editor_projects', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='MusicEditorAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(db_index=True, max_length=16)),
                ('file_path', models.TextField()),
                ('media_type', models.CharField(default='application/octet-stream', max_length=120)),
                ('size', models.BigIntegerField(default=0)),
                ('original_name', models.CharField(blank=True, max_length=240)),
                ('duration', models.FloatField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assets', to='studio.musiceditorproject')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.AddIndex(
            model_name='musiceditorproject',
            index=models.Index(fields=['owner', '-updated_at'], name='studio_musi_owner_i_idx'),
        ),
        migrations.AddIndex(
            model_name='musiceditorproject',
            index=models.Index(fields=['guest_key', '-updated_at'], name='studio_musi_guest__idx'),
        ),
    ]
