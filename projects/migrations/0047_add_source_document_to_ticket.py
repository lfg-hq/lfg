# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0046_add_custom_stack_overrides'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectticket',
            name='source_document',
            field=models.ForeignKey(
                blank=True,
                help_text='The document (PRD, spec) this ticket was created from',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tickets',
                to='projects.projectfile'
            ),
        ),
    ]
