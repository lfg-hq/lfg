#!/usr/bin/env python
"""
Manual script to create payment plans if management command fails
Run this from the project root directory after setting up Django environment
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/home/jitinp/Projects/lfg')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
django.setup()

from subscriptions.models import PaymentPlan

def create_payment_plans():
    """Create the default payment plans"""
    
    # Define plans
    plans_data = [
        {
            'name': 'Free Tier',
            'price': 0.00,
            'credits': 100000,
            'description': 'Free tier with 100,000 tokens lifetime limit. Only supports gpt-5-mini model.',
            'is_subscription': False,
            'is_active': True
        },
        {
            'name': 'Pro Monthly',
            'price': 9.00,
            'credits': 300000,
            'description': 'Pro tier with 300,000 tokens per month. Access to all AI models.',
            'is_subscription': True,
            'is_active': True
        },
        {
            'name': 'Additional Credits',
            'price': 5.00,
            'credits': 100000,
            'description': 'Get 100,000 more tokens for $5 (one-time purchase).',
            'is_subscription': False,
            'is_active': True
        }
    ]
    
    created_count = 0
    updated_count = 0
    
    for plan_data in plans_data:
        plan, created = PaymentPlan.objects.get_or_create(
            name=plan_data['name'],
            defaults=plan_data
        )
        
        if created:
            created_count += 1
            print(f"✅ Created: {plan.name} - ${plan.price}")
        else:
            # Update existing plan
            for key, value in plan_data.items():
                if key != 'name':  # Don't update the name
                    setattr(plan, key, value)
            plan.save()
            updated_count += 1
            print(f"🔄 Updated: {plan.name} - ${plan.price}")
    
    print(f"\n🎉 Successfully created {created_count} and updated {updated_count} payment plans!")
    print("\nAll Plans in Database:")
    for plan in PaymentPlan.objects.all():
        print(f"  - {plan.name}: ${plan.price} ({plan.credits:,} credits) {'[Subscription]' if plan.is_subscription else '[One-time]'}")

if __name__ == "__main__":
    create_payment_plans()