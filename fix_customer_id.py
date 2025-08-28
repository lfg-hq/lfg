#!/usr/bin/env python
"""
Script to populate stripe_customer_id for existing users who have transactions.
This needs to be run to fix the payment method display issue.
"""
import os
import sys
import django

# Setup Django environment  
sys.path.append('/home/jitinp/Projects/lfg')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')

try:
    import stripe
    django.setup()
    
    from subscriptions.models import UserCredit, Transaction
    from django.contrib.auth.models import User
    
    # Set your Stripe secret key (use the one from env.sh)
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', 'sk-test-...')  # Replace with actual key
    
    def fix_customer_ids():
        """Find and populate missing customer IDs"""
        print("Looking for users with missing stripe_customer_id...")
        
        # Find users who have transactions but no customer ID
        users_with_transactions = User.objects.filter(
            transactions__status='completed'
        ).distinct()
        
        print(f"Found {users_with_transactions.count()} users with transactions")
        
        for user in users_with_transactions:
            user_credit, created = UserCredit.objects.get_or_create(user=user)
            
            if user_credit.stripe_customer_id:
                print(f"✓ User {user.email} already has customer ID: {user_credit.stripe_customer_id}")
                continue
                
            print(f"\n🔍 Searching for customer ID for user: {user.email}")
            
            # Method 1: Check via subscription if they have one
            if user_credit.stripe_subscription_id:
                try:
                    subscription = stripe.Subscription.retrieve(user_credit.stripe_subscription_id)
                    customer_id = subscription.customer
                    user_credit.stripe_customer_id = customer_id
                    user_credit.save()
                    print(f"✅ Found via subscription: {customer_id}")
                    continue
                except Exception as e:
                    print(f"❌ Subscription lookup failed: {e}")
            
            # Method 2: Search by email
            try:
                customers = stripe.Customer.list(email=user.email, limit=10)
                if customers.data:
                    # Use the most recent customer
                    customer = customers.data[0]
                    user_credit.stripe_customer_id = customer.id
                    user_credit.save()
                    print(f"✅ Found via email search: {customer.id}")
                    
                    # Show payment methods count
                    payment_methods = stripe.PaymentMethod.list(
                        customer=customer.id, 
                        type='card'
                    )
                    print(f"   📋 Customer has {len(payment_methods.data)} payment methods")
                else:
                    print(f"❌ No Stripe customer found for {user.email}")
            except Exception as e:
                print(f"❌ Email search failed: {e}")
    
    if __name__ == "__main__":
        fix_customer_ids()
        
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure Django and Stripe are installed and environment is set up correctly")
except Exception as e:
    print(f"Error: {e}")