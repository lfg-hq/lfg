from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserCredit, Transaction, OrganizationCredit, OrganizationTransaction
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def create_user_credit(sender, instance, created, **kwargs):
    """Create a UserCredit instance when a new user is created."""
    if created:
        UserCredit.objects.create(user=instance)

@receiver(post_save, sender=Transaction)
def update_user_credits(sender, instance, **kwargs):
    """Update user subscription when a transaction is completed."""
    if instance.status == Transaction.COMPLETED:
        # Get or create user credit
        user_credit, created = UserCredit.objects.get_or_create(user=instance.user)
        
        # For subscription transactions, update subscription tier
        if instance.payment_plan and instance.payment_plan.is_subscription:
            # This is a subscription - set to pro tier
            user_credit.subscription_tier = 'pro'
            user_credit.is_subscribed = True
            user_credit.monthly_tokens_used = 0  # Reset monthly tokens
            logger.info(f"Signal: Updated user {instance.user.id} to pro tier via transaction completion")
        else:
            # This is a one-time credit purchase - add credits to user account
            user_credit.credits += instance.credits_added
            logger.info(f"Signal: Added {instance.credits_added} credits to user {instance.user.id} (total: {user_credit.credits})")
        
        user_credit.save()


# Organization-specific signals
@receiver(post_save, sender='accounts.Organization')
def create_organization_credit(sender, instance, created, **kwargs):
    """Create an OrganizationCredit instance when a new organization is created."""
    if created:
        OrganizationCredit.objects.get_or_create(organization=instance)


@receiver(post_save, sender=OrganizationTransaction)
def update_organization_credits(sender, instance, **kwargs):
    """Update organization credits when a transaction is completed."""
    if instance.status == OrganizationTransaction.COMPLETED:
        # Get or create organization credit
        org_credit, created = OrganizationCredit.objects.get_or_create(organization=instance.organization)
        
        # Add credits to organization account
        org_credit.credits += instance.credits_added
        org_credit.save()


@receiver(post_save, sender='accounts.OrganizationMembership')
def update_organization_seat_count(sender, instance, **kwargs):
    """Update organization seat count when membership changes."""
    # Update seat count for the organization
    org_credit, created = OrganizationCredit.objects.get_or_create(organization=instance.organization)
    org_credit.update_seat_count() 