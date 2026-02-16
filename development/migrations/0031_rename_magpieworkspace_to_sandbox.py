from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("development", "0029_alter_magpieworkspace_unique_user_workspace_type"),
    ]

    operations = [
        # 1. Rename the model class MagpieWorkspace → Sandbox
        migrations.RenameModel(
            old_name="MagpieWorkspace",
            new_name="Sandbox",
        ),
        # 2. Rename the database table
        migrations.AlterModelTable(
            name="sandbox",
            table="development_sandbox",
        ),
        # 3. Add cli_session_id field (moved from ProjectTicket)
        migrations.AddField(
            model_name="sandbox",
            name="cli_session_id",
            field=models.CharField(
                blank=True,
                help_text="Claude Code CLI session ID for resuming conversations",
                max_length=100,
                null=True,
            ),
        ),
        # 4. Rename the unique constraint
        migrations.RemoveConstraint(
            model_name="sandbox",
            name="unique_conversation_magpie_workspace",
        ),
        migrations.AddConstraint(
            model_name="sandbox",
            constraint=models.UniqueConstraint(
                condition=models.Q(("conversation_id__isnull", False)),
                fields=("conversation_id",),
                name="unique_sandbox_conversation",
            ),
        ),
    ]
