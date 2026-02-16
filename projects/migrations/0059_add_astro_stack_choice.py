from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0058_projectticket_linked_documents'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='stack',
            field=models.CharField(
                choices=[
                    ('nextjs', 'Next.js'),
                    ('astro', 'Astro'),
                    ('python-django', 'Python (Django)'),
                    ('python-fastapi', 'Python (FastAPI)'),
                    ('go', 'Go'),
                    ('rust', 'Rust'),
                    ('ruby-rails', 'Ruby on Rails'),
                    ('custom', 'Custom/Existing Repo'),
                ],
                default='nextjs',
                help_text='Technology stack for this project',
                max_length=50,
            ),
        ),
    ]
