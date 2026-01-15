# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
        ('projects', '0047_add_source_document_to_ticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectticket',
            name='conversation',
            field=models.ForeignKey(
                blank=True,
                help_text='The conversation during which this ticket was created',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tickets',
                to='chat.conversation'
            ),
        ),
    ]
