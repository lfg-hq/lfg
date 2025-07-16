# Generated manually to sync Django's migration state with database

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('development', '0014_alter_serverconfig_unique_together_and_more'),
    ]

    operations = [
        # This migration exists only to tell Django that these constraints
        # already exist in the database (created by migrations 0007 and 0009)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Tell Django about the constraints without creating them
                migrations.AddConstraint(
                    model_name='dockersandbox',
                    constraint=models.UniqueConstraint(
                        condition=models.Q(conversation_id__isnull=True),
                        fields=('project_id',),
                        name='unique_project_sandbox'
                    ),
                ),
                migrations.AddConstraint(
                    model_name='dockersandbox',
                    constraint=models.UniqueConstraint(
                        condition=models.Q(project_id__isnull=True),
                        fields=('conversation_id',),
                        name='unique_conversation_sandbox'
                    ),
                ),
                migrations.AddConstraint(
                    model_name='dockersandbox',
                    constraint=models.UniqueConstraint(
                        condition=models.Q(conversation_id__isnull=False, project_id__isnull=False),
                        fields=('project_id', 'conversation_id'),
                        name='unique_project_conversation_sandbox'
                    ),
                ),
                migrations.AddConstraint(
                    model_name='kubernetespod',
                    constraint=models.UniqueConstraint(
                        condition=models.Q(conversation_id__isnull=True),
                        fields=('project_id',),
                        name='unique_project_pod'
                    ),
                ),
                migrations.AddConstraint(
                    model_name='kubernetespod',
                    constraint=models.UniqueConstraint(
                        condition=models.Q(project_id__isnull=True),
                        fields=('conversation_id',),
                        name='unique_conversation_pod'
                    ),
                ),
                migrations.AddConstraint(
                    model_name='kubernetespod',
                    constraint=models.UniqueConstraint(
                        condition=models.Q(conversation_id__isnull=False, project_id__isnull=False),
                        fields=('project_id', 'conversation_id'),
                        name='unique_project_conversation_pod'
                    ),
                ),
            ],
            database_operations=[
                # No database operations - constraints already exist
            ]
        ),
    ]