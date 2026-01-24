# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0053_add_merge_history_and_revert_v2'),
    ]

    operations = [
        migrations.AddField(
            model_name='projecttodolist',
            name='cli_task_id',
            field=models.CharField(blank=True, help_text='Claude CLI task ID for syncing', max_length=50, null=True),
        ),
    ]
