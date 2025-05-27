from django.contrib.auth.models import User
from .models import UserCredit, Transaction
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