# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0040_add_design_canvas_model'),
        ('chat', '0027_remove_feature_id_add_conversation'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='design_canvas',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='conversations',
                to='projects.designcanvas'
            ),
        ),
    ]
