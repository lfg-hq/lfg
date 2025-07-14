# Generated manually
from django.db import migrations, models
import uuid

def populate_project_id(apps, schema_editor):
    """
    Populate project_id for existing projects
    """
    Project = apps.get_model('projects', 'Project')
    db_alias = schema_editor.connection.alias
    
    for project in Project.objects.using(db_alias).filter(project_id__isnull=True):
        project.project_id = str(uuid.uuid4())
        project.save(update_fields=['project_id'])

def reverse_func(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0019_delete_projecttickets'),
    ]

    operations = [
        # First add the field as nullable
        migrations.AddField(
            model_name='project',
            name='project_id',
            field=models.CharField(max_length=36, null=True, blank=True, db_index=True),
        ),
        # Populate the field for existing records
        migrations.RunPython(populate_project_id, reverse_func),
        # Now make it non-nullable and unique
        migrations.AlterField(
            model_name='project',
            name='project_id',
            field=models.CharField(max_length=36, unique=True, default=uuid.uuid4, db_index=True),
        ),
    ]