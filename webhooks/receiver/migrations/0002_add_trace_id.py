from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds trace_id field to EventLog, AuditLog and DeadLetter (v2.1.0)."""

    dependencies = [
        ('dumanity_webhooks_receiver', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventlog',
            name='trace_id',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='trace_id',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name='deadletter',
            name='trace_id',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
    ]
