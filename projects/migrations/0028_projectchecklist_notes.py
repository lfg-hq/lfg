from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0027_projectchecklist_ordering'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectchecklist',
            name='notes',
            field=models.TextField(blank=True, default='', help_text='Execution notes, issues, and progress updates for this ticket'),
        ),
    ]
