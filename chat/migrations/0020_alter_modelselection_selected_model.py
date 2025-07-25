# Generated by Django 4.2.7 on 2025-07-16 20:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0019_noop_model_choices'),
    ]

    operations = [
        migrations.AlterField(
            model_name='modelselection',
            name='selected_model',
            field=models.CharField(choices=[('claude_4_sonnet', 'Claude 4 Sonnet'), ('claude_4_opus', 'Claude 4 Opus'), ('claude_3.5_sonnet', 'Claude 3.5 Sonnet'), ('claude_4_opus', 'Claude 4 Opus'), ('claude_3.5_sonnet', 'Claude 3.5 Sonnet'), ('gpt_4_1', 'OpenAI GPT-4.1'), ('gpt_4o', 'OpenAI GPT-4o'), ('o3', 'OpenAI o3'), ('o4-mini', 'OpenAI o4 mini'), ('grok_4', 'Grok 4'), ('grok_2', 'Grok 2'), ('grok_beta', 'Grok Beta'), ('grok_4', 'Grok 4')], default='claude_4_sonnet', max_length=50),
        ),
    ]
