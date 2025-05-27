from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserCredit, Transaction

@receiver(post_save, sender=User)
def create_user_credit(sender, instance, created, **kwargs):
    """Create a UserCredit instance when a new user is created."""
    if created:
        UserCredit.objects.create(user=instance)

@receiver(post_save, sender=Transaction)
def update_user_credits(sender, instance, **kwargs):
    """Update user credits when a transaction is completed."""
    if instance.status == Transaction.COMPLETED:
        # Get or create user credit
        user_credit, created = UserCredit.objects.get_or_create(user=instance.user)
        
        # Add credits to user account
        user_credit.credits += instance.credits_added
        user_credit.save() 