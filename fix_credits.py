#!/usr/bin/env python
"""
Script to fix missing credits from completed transactions.
This should be run after the signal fix to process any completed transactions
that didn't get their credits added.
"""

import os
import sys
import django
import logging

# Setup Django environment
sys.path.append('/home/jitinp/Projects/lfg')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
django.setup()

from subscriptions.models import Transaction, UserCredit, PaymentPlan
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

def fix_missing_credits():
    """Check for completed transactions that haven't added credits"""
    
    # Find completed transactions for non-subscription plans
    completed_transactions = Transaction.objects.filter(
        status=Transaction.COMPLETED,
        payment_plan__is_subscription=False  # One-time purchases
    )
    
    logger.info(f"Found {completed_transactions.count()} completed one-time transactions")
    
    for transaction in completed_transactions:
        user_credit, created = UserCredit.objects.get_or_create(user=transaction.user)
        
        logger.info(f"\nTransaction ID: {transaction.id}")
        logger.info(f"User: {transaction.user.email}")
        logger.info(f"Plan: {transaction.payment_plan.name if transaction.payment_plan else 'N/A'}")
        logger.info(f"Credits to add: {transaction.credits_added}")
        logger.info(f"Current user credits: {user_credit.credits}")
        logger.info(f"Current remaining tokens: {user_credit.get_remaining_tokens()}")
        
        # Add credits (the signal should handle this going forward)
        user_credit.credits += transaction.credits_added
        user_credit.save()
        
        logger.info(f"Updated user credits: {user_credit.credits}")
        logger.info(f"New remaining tokens: {user_credit.get_remaining_tokens()}")
        logger.info("-" * 50)

if __name__ == "__main__":
    fix_missing_credits()