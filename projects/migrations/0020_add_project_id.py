# Generated manually
from django.db import migrations, models
import uuid
from django.db.utils import ProgrammingError

def add_project_id_if_not_exists(apps, schema_editor):
    """
    Add project_id field only if it doesn't already exist
    """
    from django.db import connection
    
    # Check if the column already exists
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'projects_project' 
            AND column_name = 'project_id'
        """)
        
        exists = cursor.fetchone() is not None
        
        if not exists:
            # Column doesn't exist, add it
            cursor.execute("""
                ALTER TABLE projects_project 
                ADD COLUMN project_id varchar(36) DEFAULT gen_random_uuid()::text
            """)
            
            # Create index
            cursor.execute("""
                CREATE INDEX projects_project_project_id_idx 
                ON projects_project(project_id)
            """)

def reverse_func(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0019_delete_projecttickets'),
    ]

    operations = [
        migrations.RunPython(add_project_id_if_not_exists, reverse_func),
    ]