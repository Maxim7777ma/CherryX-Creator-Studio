from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studio", "0007_accountprofile_accent_avatar_path"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountprofile",
            name="theme_mode",
            field=models.CharField(default="light", max_length=24),
        ),
    ]
