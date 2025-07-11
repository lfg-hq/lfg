# Generated by Django 4.2.7 on 2025-07-07 19:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0017_project_linear_project_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectchecklist',
            name='linear_assignee_id',
            field=models.CharField(blank=True, help_text='Linear user ID of assignee', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='projectchecklist',
            name='linear_issue_id',
            field=models.CharField(blank=True, help_text='Linear issue ID for this ticket', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='projectchecklist',
            name='linear_issue_url',
            field=models.URLField(blank=True, help_text='Direct URL to the Linear issue', null=True),
        ),
        migrations.AddField(
            model_name='projectchecklist',
            name='linear_priority',
            field=models.IntegerField(blank=True, help_text='Priority level from Linear (0-4)', null=True),
        ),
        migrations.AddField(
            model_name='projectchecklist',
            name='linear_state',
            field=models.CharField(blank=True, help_text='Current state in Linear (e.g., Todo, In Progress, Done)', max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='projectchecklist',
            name='linear_sync_enabled',
            field=models.BooleanField(default=True, help_text='Whether to sync this specific ticket with Linear'),
        ),
        migrations.AddField(
            model_name='projectchecklist',
            name='linear_synced_at',
            field=models.DateTimeField(blank=True, help_text='Last time this ticket was synced with Linear', null=True),
        ),
    ]
