# Generated by Django 4.2.7 on 2025-04-03 19:18

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0003_remove_project_conversations'),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS projects_project_conversations;",
            reverse_sql="",  # No reversible operation as we're fixing a corrupted table
        ),
    ]
