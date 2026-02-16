# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0021_claude_code_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='cli_api_key',
            field=models.CharField(
                blank=True,
                help_text='API key for CLI to call LFG endpoints from VM',
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
    ]
