from django.contrib import admin
from .models import UserCredit, PaymentPlan, Transaction, OrganizationCredit, OrganizationTransaction

# Register your models here.
@admin.register(UserCredit)
class UserCreditAdmin(admin.ModelAdmin):
    list_display = ('user', 'credits')
    search_fields = ('user__username', 'user__email')

@admin.register(PaymentPlan)
class PaymentPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'credits', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'payment_plan', 'amount', 'credits_added', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'user__email', 'payment_intent_id')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(OrganizationCredit)
class OrganizationCreditAdmin(admin.ModelAdmin):
    list_display = ('organization', 'credits', 'seat_count', 'subscription_tier', 'is_subscribed', 'monthly_seat_cost')
    list_filter = ('subscription_tier', 'is_subscribed', 'price_per_seat')
    search_fields = ('organization__name', 'organization__owner__username', 'stripe_subscription_id')
    readonly_fields = ('monthly_seat_cost',)
    
    fieldsets = (
        ('Organization', {
            'fields': ('organization',)
        }),
        ('Credits & Usage', {
            'fields': ('credits', 'total_tokens_used', 'monthly_tokens_used', 'free_tokens_used', 'paid_tokens_used')
        }),
        ('Subscription', {
            'fields': ('is_subscribed', 'subscription_tier', 'stripe_subscription_id', 'subscription_end_date', 'monthly_reset_date')
        }),
        ('Billing', {
            'fields': ('seat_count', 'price_per_seat', 'monthly_seat_cost')
        })
    )
    
    def monthly_seat_cost(self, obj):
        return f"${obj.monthly_seat_cost}"
    monthly_seat_cost.short_description = 'Monthly Cost'


@admin.register(OrganizationTransaction)
class OrganizationTransactionAdmin(admin.ModelAdmin):
    list_display = ('organization', 'amount', 'seat_count', 'per_seat_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at', 'seat_count')
    search_fields = ('organization__name', 'payment_intent_id', 'stripe_invoice_id')
    readonly_fields = ('created_at', 'updated_at', 'per_seat_amount')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Organization', {
            'fields': ('organization', 'payment_plan')
        }),
        ('Payment Details', {
            'fields': ('amount', 'credits_added', 'seat_count', 'per_seat_amount', 'status')
        }),
        ('Stripe Details', {
            'fields': ('payment_intent_id', 'stripe_invoice_id')
        }),
        ('Billing Period', {
            'fields': ('billing_period_start', 'billing_period_end'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def per_seat_amount(self, obj):
        return f"${obj.per_seat_amount:.2f}"
    per_seat_amount.short_description = 'Per Seat'
