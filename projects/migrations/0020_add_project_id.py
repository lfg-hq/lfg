# Generated manually
from django.db import migrations, models
import uuid

class Migration(migrations.Migration):
    atomic = False  # This allows us to handle exceptions within the migration

    dependencies = [
        ('projects', '0019_delete_projecttickets'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                # First, add the column if it doesn't exist
                """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='projects_project' AND column_name='project_id') THEN
                        ALTER TABLE projects_project ADD COLUMN project_id varchar(36);
                    END IF;
                END $$;
                """,
                # Update any null values
                "UPDATE projects_project SET project_id = gen_random_uuid()::text WHERE project_id IS NULL;",
                # Make it NOT NULL
                "ALTER TABLE projects_project ALTER COLUMN project_id SET NOT NULL;",
                # Add unique constraint if it doesn't exist
                """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint 
                                   WHERE conname = 'projects_project_project_id_key') THEN
                        ALTER TABLE projects_project ADD CONSTRAINT projects_project_project_id_key UNIQUE (project_id);
                    END IF;
                END $$;
                """,
                # Add index if it doesn't exist
                """
                CREATE INDEX IF NOT EXISTS projects_project_project_id_c5ed772b 
                ON projects_project(project_id);
                """,
                # Add the 'like' index for pattern matching if it doesn't exist
                """
                CREATE INDEX IF NOT EXISTS projects_project_project_id_c5ed772b_like 
                ON projects_project(project_id varchar_pattern_ops);
                """,
            ],
            reverse_sql=[
                "ALTER TABLE projects_project DROP CONSTRAINT IF EXISTS projects_project_project_id_key;",
                "DROP INDEX IF EXISTS projects_project_project_id_c5ed772b_like;",
                "DROP INDEX IF EXISTS projects_project_project_id_c5ed772b;",
                "ALTER TABLE projects_project DROP COLUMN IF EXISTS project_id;",
            ],
            state_operations=[
                migrations.AddField(
                    model_name='project',
                    name='project_id',
                    field=models.CharField(max_length=36, unique=True, default=uuid.uuid4, db_index=True),
                ),
            ],
        ),
    ]