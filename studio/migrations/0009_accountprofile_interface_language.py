from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studio", "0008_accountprofile_theme_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountprofile",
            name="interface_language",
            field=models.CharField(default="en", max_length=8),
        ),
    ]
