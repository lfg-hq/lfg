from django.contrib import admin
from .models import UserCredit, PaymentPlan, Transaction

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
