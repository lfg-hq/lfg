from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0026_project_member_invitation'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='projectchecklist',
            options={'ordering': ['created_at', 'id']},
        ),
    ]
