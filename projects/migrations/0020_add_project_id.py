# Generated manually
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0019_delete_projecttickets'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='project_id',
            field=models.CharField(max_length=36, unique=True, default=uuid.uuid4, db_index=True),
        ),
    ]