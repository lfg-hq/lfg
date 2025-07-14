# Generated manually to fix project_id duplicates
from django.db import migrations
import uuid

def fix_duplicate_project_ids(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    db_alias = schema_editor.connection.alias
    
    # Get all projects
    projects = Project.objects.using(db_alias).all()
    
    # Track seen project_ids
    seen_ids = set()
    
    for project in projects:
        # If project_id is None or empty, generate a new one
        if not project.project_id:
            project.project_id = str(uuid.uuid4())
            project.save(update_fields=['project_id'])
        # If we've seen this project_id before, generate a new one
        elif project.project_id in seen_ids:
            project.project_id = str(uuid.uuid4())
            project.save(update_fields=['project_id'])
        else:
            seen_ids.add(project.project_id)

def reverse_func(apps, schema_editor):
    # This migration is not reversible
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0019_delete_projecttickets'),
    ]

    operations = [
        migrations.RunPython(fix_duplicate_project_ids, reverse_func),
    ]