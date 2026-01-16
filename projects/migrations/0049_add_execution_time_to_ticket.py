# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0048_add_conversation_to_ticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectticket',
            name='execution_time_seconds',
            field=models.FloatField(default=0, help_text='Total execution time spent on this ticket in seconds (accumulated across all runs)'),
        ),
        migrations.AddField(
            model_name='projectticket',
            name='last_execution_at',
            field=models.DateTimeField(blank=True, help_text='When the ticket was last executed', null=True),
        ),
    ]
