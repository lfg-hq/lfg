# Generated manually - no-op migration to satisfy Django's migration detection

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('development', '0015_empty_state_update'),
    ]

    operations = [
        # This is a no-op migration
        # Django thinks indexes need to be renamed but they don't exist with old names
        # This migration exists only to prevent Django from auto-generating migrations
    ]