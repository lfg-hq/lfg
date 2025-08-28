from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from subscriptions.models import UserCredit, Transaction
import stripe
import os

class Command(BaseCommand):
    help = 'Fix missing stripe_customer_id for users with transactions'
    
    def handle(self, *args, **options):
        # Set Stripe API key
        stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
        
        if not stripe.api_key:
            self.stdout.write(self.style.ERROR('STRIPE_SECRET_KEY not found in environment'))
            return
        
        # Find users who have completed transactions but no customer ID
        users_with_transactions = User.objects.filter(
            transactions__status=Transaction.COMPLETED
        ).distinct()
        
        self.stdout.write(f"Found {users_with_transactions.count()} users with transactions")
        
        fixed_count = 0
        for user in users_with_transactions:
            user_credit, created = UserCredit.objects.get_or_create(user=user)
            
            if user_credit.stripe_customer_id:
                self.stdout.write(f"✓ {user.email} already has customer ID")
                continue
            
            self.stdout.write(f"🔍 Searching for customer: {user.email}")
            
            # Method 1: Check via subscription
            if user_credit.stripe_subscription_id:
                try:
                    subscription = stripe.Subscription.retrieve(user_credit.stripe_subscription_id)
                    user_credit.stripe_customer_id = subscription.customer
                    user_credit.save()
                    self.stdout.write(self.style.SUCCESS(f"✅ Fixed via subscription: {subscription.customer}"))
                    fixed_count += 1
                    continue
                except Exception as e:
                    self.stdout.write(f"❌ Subscription lookup failed: {e}")
            
            # Method 2: Search by email
            try:
                customers = stripe.Customer.list(email=user.email, limit=5)
                if customers.data:
                    customer = customers.data[0]  # Use the first (most recent)
                    user_credit.stripe_customer_id = customer.id
                    user_credit.save()
                    
                    # Check payment methods
                    payment_methods = stripe.PaymentMethod.list(customer=customer.id, type='card')
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"✅ Fixed via email: {customer.id} ({len(payment_methods.data)} payment methods)"
                    ))
                    fixed_count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"❌ No customer found for {user.email}"))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Email search failed for {user.email}: {e}"))
        
        self.stdout.write(self.style.SUCCESS(f"\n🎉 Fixed {fixed_count} customer IDs!"))