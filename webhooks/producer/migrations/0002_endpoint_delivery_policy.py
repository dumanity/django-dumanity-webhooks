from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("producer", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhookendpoint",
            name="max_retries",
            field=models.PositiveIntegerField(default=5),
        ),
        migrations.AddField(
            model_name="webhookendpoint",
            name="request_timeout_seconds",
            field=models.PositiveIntegerField(default=10),
        ),
    ]
