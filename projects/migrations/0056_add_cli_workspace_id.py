# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0055_add_review_status_choice'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectticket',
            name='cli_workspace_id',
            field=models.CharField(blank=True, help_text='Workspace ID where the CLI session was created', max_length=100, null=True),
        ),
    ]
