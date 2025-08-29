from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('checkout/<int:plan_id>/', views.checkout, name='checkout'),
    path('success/', views.payment_success, name='payment_success'),
    path('cancel/', views.payment_cancel, name='payment_cancel'),
    path('webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('subscription/cancel/', views.cancel_subscription, name='cancel_subscription'),
    # Payment method management
    path('payment-methods/', views.payment_methods, name='payment_methods'),
    path('create-setup-intent/', views.create_setup_intent, name='create_setup_intent'),
    path('set-default-payment-method/', views.set_default_payment_method, name='set_default_payment_method'),
    path('remove-payment-method/', views.remove_payment_method, name='remove_payment_method'),
    path('fix-customer-ids/', views.fix_customer_ids, name='fix_customer_ids'),
    path('debug-account/', views.debug_account, name='debug_account'),
    path('fix-pro-subscription/', views.fix_pro_subscription, name='fix_pro_subscription'),
    path('init-default-plans/', views.init_default_plans, name='init_default_plans'),
] 