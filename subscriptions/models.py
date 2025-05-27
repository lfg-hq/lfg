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
