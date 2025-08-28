import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
django.setup()

from subscriptions.models import Transaction, UserCredit

# Check completed transactions
transactions = Transaction.objects.filter(status='completed')
print(f"Total completed transactions: {transactions.count()}")

for t in transactions:
    print(f"Transaction {t.id}: User {t.user.email}, Plan: {t.payment_plan.name if t.payment_plan else 'N/A'}, Credits: {t.credits_added}, Status: {t.status}")

# Check user credits
try:
    # Get the current user's credit info (assuming the user making the purchase)
    # You'll need to replace this with the actual user email
    user_credits = UserCredit.objects.all()
    for uc in user_credits:
        print(f"User {uc.user.email}: Credits: {uc.credits}, Remaining tokens: {uc.get_remaining_tokens()}")
except Exception as e:
    print(f"Error: {e}")