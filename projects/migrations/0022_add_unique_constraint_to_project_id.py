# Generated manually to add unique constraint to project_id
from django.db import migrations, models
import uuid

class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0021_fix_project_id_duplicates'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='project_id',
            field=models.CharField(max_length=36, unique=True, default=uuid.uuid4, db_index=True),
        ),
    ]