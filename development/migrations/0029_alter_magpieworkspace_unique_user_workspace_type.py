from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("development", "0028_alter_magpieworkspace_status"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="magpieworkspace",
            name="unique_user_workspace_type",
        ),
        migrations.AddConstraint(
            model_name="magpieworkspace",
            constraint=models.UniqueConstraint(
                fields=("user", "workspace_type"),
                condition=models.Q(user__isnull=False, workspace_type="claude_auth"),
                name="unique_user_workspace_type",
            ),
        ),
    ]

