from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0059_add_astro_stack_choice'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='stack',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Not set'),
                    ('nextjs', 'Next.js'),
                    ('astro', 'Astro'),
                    ('python-django', 'Python (Django)'),
                    ('python-fastapi', 'Python (FastAPI)'),
                    ('go', 'Go'),
                    ('rust', 'Rust'),
                    ('ruby-rails', 'Ruby on Rails'),
                    ('custom', 'Custom/Existing Repo'),
                ],
                default='',
                help_text='Technology stack for this project. Must be set before ticket execution.',
                max_length=50,
            ),
        ),
    ]
