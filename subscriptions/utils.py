from django.contrib.auth.models import User
from .models import UserCredit, Transaction, OrganizationCredit, OrganizationTransaction
from django.db import transaction
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def get_user_credits(user):
    """
    Get a user's current credit balance
    
    Args:
        user: User instance
        
    Returns:
        int: User's current credit balance
    """
    if not user or not user.is_authenticated:
        return 0
        
    try:
        user_credit, created = UserCredit.objects.get_or_create(user=user)
        return user_credit.credits
    except Exception as e:
        logger.error(f"Error getting user credits: {str(e)}")
        return 0

def has_sufficient_credits(user, required_credits):
    """
    Check if a user has sufficient credits
    
    Args:
        user: User instance
        required_credits: Number of credits required
        
    Returns:
        bool: True if user has sufficient credits, False otherwise
    """
    return get_user_credits(user) >= required_credits

@transaction.atomic
def use_credits(user, credits_amount, description="Credits used"):
    """
    Deduct credits from a user's account
    
    Args:
        user: User instance
        credits_amount: Number of credits to deduct
        description: Optional description of the usage
        
    Returns:
        bool: True if credits were successfully deducted, False otherwise
    """
    if not user or not user.is_authenticated:
        return False
        
    if credits_amount <= 0:
        return True  # No credits to deduct
        
    try:
        user_credit, created = UserCredit.objects.get_or_create(user=user)
        
        # Check if user has enough credits
        if user_credit.credits < credits_amount:
            return False
            
        # Deduct credits
        user_credit.credits -= credits_amount
        user_credit.save()
        
        # Optionally, record this usage in a separate model if needed
        # CreditUsage.objects.create(user=user, amount=credits_amount, description=description)
        
        return True
    except Exception as e:
        logger.error(f"Error using credits: {str(e)}")
        return False

@transaction.atomic
def add_credits(user, credits_amount, description="Credits added manually"):
    """
    Add credits to a user's account
    
    Args:
        user: User instance
        credits_amount: Number of credits to add
        description: Optional description of the addition
        
    Returns:
        bool: True if credits were successfully added, False otherwise
    """
    if not user or not user.is_authenticated:
        return False
        
    if credits_amount <= 0:
        return True  # No credits to add
        
    try:
        user_credit, created = UserCredit.objects.get_or_create(user=user)
        
        # Add credits
        user_credit.credits += credits_amount
        user_credit.save()
        
        return True
    except Exception as e:
        logger.error(f"Error adding credits: {str(e)}")
        return False


# Organization Credit Management Functions

def get_organization_credits(organization):
    """
    Get an organization's current credit balance
    
    Args:
        organization: Organization instance
        
    Returns:
        int: Organization's current credit balance
    """
    if not organization:
        return 0
        
    try:
        org_credit, created = OrganizationCredit.objects.get_or_create(organization=organization)
        return org_credit.credits
    except Exception as e:
        logger.error(f"Error getting organization credits: {str(e)}")
        return 0


def has_sufficient_organization_credits(organization, required_credits):
    """
    Check if an organization has sufficient credits
    
    Args:
        organization: Organization instance
        required_credits: Number of credits required
        
    Returns:
        bool: True if organization has sufficient credits, False otherwise
    """
    return get_organization_credits(organization) >= required_credits


@transaction.atomic
def use_organization_credits(organization, credits_amount, description="Credits used"):
    """
    Deduct credits from an organization's account
    
    Args:
        organization: Organization instance
        credits_amount: Number of credits to deduct
        description: Optional description of the usage
        
    Returns:
        bool: True if credits were successfully deducted, False otherwise
    """
    if not organization:
        return False
        
    if credits_amount <= 0:
        return True  # No credits to deduct
        
    try:
        org_credit, created = OrganizationCredit.objects.get_or_create(organization=organization)
        
        # Check if organization has enough credits
        if org_credit.credits < credits_amount:
            return False
            
        # Deduct credits
        org_credit.credits -= credits_amount
        org_credit.save()
        
        return True
    except Exception as e:
        logger.error(f"Error using organization credits: {str(e)}")
        return False


@transaction.atomic
def add_organization_credits(organization, credits_amount, description="Credits added manually"):
    """
    Add credits to an organization's account
    
    Args:
        organization: Organization instance
        credits_amount: Number of credits to add
        description: Optional description of the addition
        
    Returns:
        bool: True if credits were successfully added, False otherwise
    """
    if not organization:
        return False
        
    if credits_amount <= 0:
        return True  # No credits to add
        
    try:
        org_credit, created = OrganizationCredit.objects.get_or_create(organization=organization)
        
        # Add credits
        org_credit.credits += credits_amount
        org_credit.save()
        
        return True
    except Exception as e:
        logger.error(f"Error adding organization credits: {str(e)}")
        return False


def get_effective_credits(user):
    """
    Get effective credits for a user, considering their organization context
    
    Args:
        user: User instance
        
    Returns:
        tuple: (credits, is_organization, organization/user_credit_object)
    """
    try:
        # Check if user is in organization context
        current_org = user.profile.current_organization
        
        if current_org:
            # Use organization credits
            org_credit, created = OrganizationCredit.objects.get_or_create(organization=current_org)
            return org_credit.credits, True, org_credit
        else:
            # Use personal credits
            user_credit, created = UserCredit.objects.get_or_create(user=user)
            return user_credit.credits, False, user_credit
            
    except Exception as e:
        logger.error(f"Error getting effective credits: {str(e)}")
        # Fallback to personal credits
        try:
            user_credit, created = UserCredit.objects.get_or_create(user=user)
            return user_credit.credits, False, user_credit
        except:
            return 0, False, None


def get_effective_token_limits(user):
    """
    Get effective token limits for a user, considering their organization context
    
    Args:
        user: User instance
        
    Returns:
        dict: Token limits and usage information
    """
    try:
        current_org = user.profile.current_organization
        
        if current_org:
            # Use organization token limits
            org_credit, created = OrganizationCredit.objects.get_or_create(organization=current_org)
            return {
                'remaining_tokens': org_credit.get_remaining_tokens(),
                'is_free_tier': org_credit.is_free_tier,
                'subscription_tier': org_credit.subscription_tier,
                'monthly_tokens_used': org_credit.monthly_tokens_used,
                'total_tokens_used': org_credit.total_tokens_used,
                'is_organization': True,
                'organization': current_org,
                'seat_count': org_credit.seat_count,
                'can_use_model': org_credit.can_use_model
            }
        else:
            # Use personal token limits
            user_credit, created = UserCredit.objects.get_or_create(user=user)
            return {
                'remaining_tokens': user_credit.get_remaining_tokens(),
                'is_free_tier': user_credit.is_free_tier,
                'subscription_tier': user_credit.subscription_tier,
                'monthly_tokens_used': user_credit.monthly_tokens_used,
                'total_tokens_used': user_credit.total_tokens_used,
                'is_organization': False,
                'organization': None,
                'seat_count': 1,
                'can_use_model': user_credit.can_use_model
            }
            
    except Exception as e:
        logger.error(f"Error getting effective token limits: {str(e)}")
        return {
            'remaining_tokens': 0,
            'is_free_tier': True,
            'subscription_tier': 'free',
            'monthly_tokens_used': 0,
            'total_tokens_used': 0,
            'is_organization': False,
            'organization': None,
            'seat_count': 1,
            'can_use_model': lambda model: model == 'gpt-5-mini'
        } 