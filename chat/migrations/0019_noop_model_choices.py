# Generated manually - no-op migration to satisfy Django's migration detection

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0018_alter_modelselection_selected_model'),
    ]

    operations = [
        # This is a no-op migration
        # Django detects duplicate choices in MODEL_CHOICES but no database change is needed
        # This migration exists only to prevent Django from auto-generating migrations
    ]