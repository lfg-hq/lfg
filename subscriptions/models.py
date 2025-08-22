from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# Create your models here.
class UserCredit(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='credit')
    credits = models.BigIntegerField(default=0)
    is_subscribed = models.BooleanField(default=False)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    subscription_end_date = models.DateTimeField(null=True, blank=True)
    total_tokens_used = models.BigIntegerField(default=0)  # Track all-time token usage
    monthly_tokens_used = models.BigIntegerField(default=0)  # Track monthly token usage
    monthly_reset_date = models.DateTimeField(null=True, blank=True)  # When to reset monthly usage
    free_tokens_used = models.BigIntegerField(default=0)  # Track free tier token usage
    paid_tokens_used = models.BigIntegerField(default=0)  # Track paid tier token usage
    subscription_tier = models.CharField(max_length=50, default='free', choices=[
        ('free', 'Free Tier'),
        ('pro', 'Pro Monthly'),
    ])
    
    def __str__(self):
        return f"{self.user.username} - {self.credits} credits"
    
    @property
    def has_active_subscription(self):
        """Check if the user has an active subscription"""
        if not self.is_subscribed:
            return False
        if not self.subscription_end_date:
            return False
        return self.subscription_end_date > timezone.now()
    
    @property
    def is_free_tier(self):
        """Check if user is on free tier"""
        return self.subscription_tier == 'free' and not self.has_active_subscription
    
    def get_remaining_tokens(self):
        """Get remaining tokens based on subscription tier"""
        if self.is_free_tier:
            # Free tier: 100K lifetime limit
            return max(0, 100000 - self.total_tokens_used)
        elif self.has_active_subscription and self.subscription_tier == 'pro':
            # Pro tier: 300K monthly limit
            # Check if we need to reset monthly usage
            if self.monthly_reset_date and timezone.now() > self.monthly_reset_date:
                self.monthly_tokens_used = 0
                self.monthly_reset_date = timezone.now() + timezone.timedelta(days=30)
                self.save()
            return max(0, 300000 - self.monthly_tokens_used)
        return 0
    
    def can_use_model(self, model_name):
        """Check if user can use a specific model"""
        if self.is_free_tier:
            # Free tier can only use gpt-5-mini
            return model_name == 'gpt-5-mini'
        return True  # Pro tier can use all models

class PaymentPlan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    credits = models.BigIntegerField()
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_subscription = models.BooleanField(default=False)
    stripe_price_id = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"{self.name} - ${self.price} for {self.credits} credits"

class Transaction(models.Model):
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    REFUNDED = 'refunded'
    
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (COMPLETED, 'Completed'),
        (FAILED, 'Failed'),
        (REFUNDED, 'Refunded'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    payment_plan = models.ForeignKey(PaymentPlan, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    credits_added = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.username} - ${self.amount} - {self.credits_added} credits - {self.status}"
