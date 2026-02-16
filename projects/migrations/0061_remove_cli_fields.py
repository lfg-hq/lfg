from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0060_make_stack_optional"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="projectticket",
            name="cli_session_id",
        ),
        migrations.RemoveField(
            model_name="projectticket",
            name="cli_workspace_id",
        ),
    ]
