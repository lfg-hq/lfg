# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0056_add_cli_workspace_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='preview_ticket',
            field=models.ForeignKey(
                blank=True,
                help_text='Currently selected ticket for preview (loads its branch)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='preview_projects',
                to='projects.projectticket'
            ),
        ),
    ]
