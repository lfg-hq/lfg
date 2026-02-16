from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0026_project_member_invitation'),
        ('development', '0018_state_only_index_renames'),
    ]

    operations = [
        migrations.CreateModel(
            name='MagpieWorkspace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('conversation_id', models.CharField(blank=True, help_text='Conversation identifier associated with this workspace', max_length=255, null=True)),
                ('job_id', models.CharField(help_text='Magpie job identifier', max_length=255, unique=True)),
                ('workspace_id', models.CharField(help_text='Workspace identifier used by the AI agent', max_length=255, unique=True)),
                ('ipv6_address', models.CharField(blank=True, help_text='IPv6 (or IPv4) address assigned to the VM', max_length=128, null=True)),
                ('project_path', models.CharField(blank=True, help_text='Primary project directory inside the VM', max_length=512, null=True)),
                ('status', models.CharField(choices=[('provisioning', 'Provisioning'), ('ready', 'Ready'), ('stopped', 'Stopped'), ('error', 'Error')], default='provisioning', help_text='Current lifecycle status of the workspace', max_length=20)),
                ('metadata', models.JSONField(blank=True, help_text='Arbitrary metadata including project summary, last restart, etc.', null=True)),
                ('last_seen_at', models.DateTimeField(blank=True, help_text='Timestamp when the workspace was last verified', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('project', models.ForeignKey(blank=True, help_text='Project associated with this Magpie workspace', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='magpie_workspaces', to='projects.project')),
            ],
            options={
                'verbose_name': 'Magpie Workspace',
                'verbose_name_plural': 'Magpie Workspaces',
                'indexes': [
                    models.Index(fields=['project'], name='development_magpie_workspace_project_idx'),
                    models.Index(fields=['conversation_id'], name='development_magpie_workspace_convo_idx'),
                    models.Index(fields=['workspace_id'], name='development_magpie_workspace_ws_idx'),
                    models.Index(fields=['status'], name='development_magpie_workspace_status_idx'),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name='magpieworkspace',
            constraint=models.UniqueConstraint(condition=models.Q(project__isnull=False), fields=('project',), name='unique_project_magpie_workspace'),
        ),
        migrations.AddConstraint(
            model_name='magpieworkspace',
            constraint=models.UniqueConstraint(condition=models.Q(conversation_id__isnull=False), fields=('conversation_id',), name='unique_conversation_magpie_workspace'),
        ),
    ]
