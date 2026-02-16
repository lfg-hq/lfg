# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0045_add_stack_to_project'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='custom_project_dir',
            field=models.CharField(blank=True, help_text='Override project directory', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='custom_install_cmd',
            field=models.CharField(blank=True, help_text='Override install command', max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='custom_dev_cmd',
            field=models.CharField(blank=True, help_text='Override dev server command', max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='custom_default_port',
            field=models.IntegerField(blank=True, help_text='Override default port', null=True),
        ),
    ]
