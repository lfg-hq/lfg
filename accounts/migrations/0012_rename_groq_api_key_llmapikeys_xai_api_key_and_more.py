# Generated by Django 4.2.7 on 2025-07-17 03:32

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def move_linear_keys(apps, schema_editor):
    """Move linear keys from LLMApiKeys to ExternalServicesAPIKeys"""
    LLMApiKeys = apps.get_model('accounts', 'LLMApiKeys')
    ExternalServicesAPIKeys = apps.get_model('accounts', 'ExternalServicesAPIKeys')
    
    # Move all linear keys before the field is removed
    for llm_keys in LLMApiKeys.objects.exclude(linear_api_key__isnull=True).exclude(linear_api_key=''):
        external_keys, created = ExternalServicesAPIKeys.objects.get_or_create(
            user=llm_keys.user,
            defaults={'linear_api_key': llm_keys.linear_api_key}
        )
        if not created and not external_keys.linear_api_key:
            external_keys.linear_api_key = llm_keys.linear_api_key
            external_keys.save()


def reverse_linear_keys(apps, schema_editor):
    """Reverse the migration"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0011_migrate_to_llm_api_keys'),
    ]

    operations = [
        migrations.RenameField(
            model_name='llmapikeys',
            old_name='groq_api_key',
            new_name='xai_api_key',
        ),
        migrations.CreateModel(
            name='ExternalServicesAPIKeys',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('linear_api_key', models.CharField(blank=True, max_length=255, null=True)),
                ('jira_api_key', models.CharField(blank=True, max_length=255, null=True)),
                ('notion_api_key', models.CharField(blank=True, max_length=255, null=True)),
                ('google_docs_api_key', models.CharField(blank=True, max_length=255, null=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='external_api_keys', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(move_linear_keys, reverse_linear_keys),
        migrations.RemoveField(
            model_name='llmapikeys',
            name='linear_api_key',
        ),
        migrations.AlterField(
            model_name='tokenusage',
            name='provider',
            field=models.CharField(choices=[('openai', 'OpenAI'), ('anthropic', 'Anthropic'), ('xai', 'XAI')], max_length=20),
        ),
    ]
