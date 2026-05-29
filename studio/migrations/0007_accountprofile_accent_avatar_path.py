from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studio", "0006_accountprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountprofile",
            name="accent_color",
            field=models.CharField(default="#2563eb", max_length=24),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="avatar_path",
            field=models.TextField(blank=True),
        ),
    ]
