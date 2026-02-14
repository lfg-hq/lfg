"""Add Mags API fields to MagpieWorkspace, update constraints."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("development", "0026_rename_development_user_id_a1b2c3_idx_development_user_id_84f09c_idx"),
    ]

    operations = [
        # Add sleeping status to STATUS_CHOICES (handled by model, no DB change needed)

        # Add new Mags fields
        migrations.AddField(
            model_name="magpieworkspace",
            name="mags_job_id",
            field=models.CharField(
                blank=True, help_text="Mags job request_id", max_length=255, null=True
            ),
        ),
        migrations.AddField(
            model_name="magpieworkspace",
            name="mags_workspace_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Mags workspace overlay name",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="magpieworkspace",
            name="mags_base_workspace_id",
            field=models.CharField(
                blank=True,
                help_text="Mags base workspace (for forked workspaces)",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="magpieworkspace",
            name="ssh_host",
            field=models.CharField(
                blank=True, help_text="SSH host for Mags workspace", max_length=255, null=True
            ),
        ),
        migrations.AddField(
            model_name="magpieworkspace",
            name="ssh_port",
            field=models.IntegerField(
                blank=True, help_text="SSH port for Mags workspace", null=True
            ),
        ),
        migrations.AddField(
            model_name="magpieworkspace",
            name="ssh_private_key",
            field=models.TextField(
                blank=True, help_text="SSH private key for Mags workspace", null=True
            ),
        ),

        # Remove old unique_project_magpie_workspace constraint
        # (tickets now have their own workspaces, not one per project)
        migrations.RemoveConstraint(
            model_name="magpieworkspace",
            name="unique_project_magpie_workspace",
        ),

        # Add unique constraint on mags_workspace_id
        migrations.AddConstraint(
            model_name="magpieworkspace",
            constraint=models.UniqueConstraint(
                condition=models.Q(("mags_workspace_id__isnull", False)),
                fields=("mags_workspace_id",),
                name="unique_mags_workspace_id",
            ),
        ),
    ]
