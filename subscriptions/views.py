from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timedelta

from .models import PaymentPlan, Transaction, UserCredit
from .constants import (
    FREE_TIER_TOKEN_LIMIT,
    PRO_MONTHLY_TOKEN_LIMIT,
)
import stripe
import json
import os
import logging

logger = logging.getLogger(__name__)

# Initialize Stripe with API key from settings or environment
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', '')

@login_required
def dashboard(request):
    """View for user's subscription dashboard"""
    # Get user's credit information
    user_credit, created = UserCredit.objects.get_or_create(user=request.user)
    
    # Clean up old pending transactions (older than 1 hour)
    one_hour_ago = timezone.now() - timedelta(hours=1)
    Transaction.objects.filter(
        user=request.user,
        status=Transaction.PENDING,
        created_at__lt=one_hour_ago
    ).update(status=Transaction.FAILED)
    
    # Get available payment plans
    payment_plans = PaymentPlan.objects.filter(is_active=True)
    
    # Get user's recent transactions
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:5]
    
    # Get Stripe public key for frontend
    stripe_public_key = os.environ.get('STRIPE_PUBLIC_KEY', '')
    
    # Check for setup success/cancel messages
    setup_status = request.GET.get('setup')
    if setup_status == 'success':
        messages.success(request, 'Payment method added successfully!')
    elif setup_status == 'cancel':
        messages.info(request, 'Payment method setup was cancelled.')
    
    # Calculate usage percentage
    if user_credit.is_free_tier:
        usage_percentage = (
            (user_credit.total_tokens_used / FREE_TIER_TOKEN_LIMIT) * 100
            if user_credit.total_tokens_used
            else 0
        )
    else:
        usage_percentage = (
            (user_credit.monthly_tokens_used / PRO_MONTHLY_TOKEN_LIMIT) * 100
            if user_credit.monthly_tokens_used
            else 0
        )
    
    context = {
        'user_credit': user_credit,
        'payment_plans': payment_plans,
        'transactions': transactions,
        'usage_percentage': min(usage_percentage, 100),  # Cap at 100%
        'STRIPE_PUBLIC_KEY': stripe_public_key,
        'free_tier_token_limit': FREE_TIER_TOKEN_LIMIT,
        'pro_monthly_token_limit': PRO_MONTHLY_TOKEN_LIMIT,
    }
    
    return render(request, 'subscriptions/dashboard.html', context)

@login_required
def checkout(request, plan_id):
    """View for checkout process using Stripe Checkout"""
    plan = get_object_or_404(PaymentPlan, id=plan_id, is_active=True)
    
    # Get domain for success and cancel URLs
    domain_url = request.build_absolute_uri('/').rstrip('/')
    success_url = domain_url + reverse('subscriptions:payment_success')
    cancel_url = domain_url + reverse('subscriptions:dashboard')
    
    # First, clean up any pending transactions for this plan
    Transaction.objects.filter(
        user=request.user,
        payment_plan=plan,
        status=Transaction.PENDING
    ).delete()
    
    # Check if user already has an active subscription
    user_credit, created = UserCredit.objects.get_or_create(user=request.user)
    if user_credit.has_active_subscription and plan_id == 1:  # If plan is Monthly Subscription
        messages.warning(request, "You already have an active subscription.")
        return redirect('subscriptions:dashboard')
    
    # Look for an existing customer in Stripe
    existing_customer = None
    
    # First check if we have a subscription ID - this guarantees we have a customer
    if user_credit.stripe_subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(user_credit.stripe_subscription_id)
            existing_customer = stripe.Customer.retrieve(subscription.customer)
        except Exception as e:
            logger.error(f"Error retrieving subscription: {e}", extra={'easylogs_metadata': {'user_id': request.user.id, 'error_type': type(e).__name__}})
    
    # If no customer found via subscription, search by email
    if not existing_customer:
        try:
            customer_query = stripe.Customer.list(email=request.user.email, limit=1)
            if customer_query and customer_query.data:
                existing_customer = customer_query.data[0]
        except Exception as e:
            logger.error(f"Error searching for customer by email: {e}", extra={'easylogs_metadata': {'user_email': request.user.email, 'error_type': type(e).__name__}})
    
    # Create a new checkout session
    try:
        # If no existing customer, create a new one
        if not existing_customer:
            stripe_customer = stripe.Customer.create(
                email=request.user.email,
                name=f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                metadata={
                    'user_id': request.user.id
                }
            )
            customer_id = stripe_customer.id
            # Save customer ID immediately
            user_credit.stripe_customer_id = customer_id
            user_credit.save()
        else:
            customer_id = existing_customer.id
            logger.info(f"Found existing customer: {customer_id}", extra={'easylogs_metadata': {'user_id': request.user.id, 'customer_id': customer_id}})
            # Save customer ID if not already saved
            if not user_credit.stripe_customer_id:
                user_credit.stripe_customer_id = customer_id
                user_credit.save()
        
        # Check if this is a subscription plan (Monthly Subscription - plan_id 1)
        if plan_id == 1:  # Monthly Subscription
            # Create a Stripe Price object for the subscription if not already created
            if not plan.stripe_price_id:
                # Create a product for this plan
                product = stripe.Product.create(
                    name=plan.name,
                    description=f"Monthly subscription with {plan.credits:,} credits"
                )
                
                # Create a price for this product
                price = stripe.Price.create(
                    product=product.id,
                    unit_amount=int(plan.price * 100),  # Convert to cents
                    currency='usd',
                    recurring={
                        'interval': 'month'
                    }
                )
                
                # Update the plan with the price ID
                plan.stripe_price_id = price.id
                plan.is_subscription = True
                plan.save()
            
            # Create a subscription checkout session - always use the checkout flow for subscriptions
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                customer=customer_id,
                line_items=[
                    {
                        'price': plan.stripe_price_id,
                        'quantity': 1,
                    }
                ],
                metadata={
                    'user_id': request.user.id,
                    'plan_id': plan.id,
                    'credits': plan.credits
                },
                mode='subscription',
                success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=cancel_url,
                # CRITICAL: Save payment method for future use
                payment_method_collection='if_required',
                invoice_creation={'enabled': True},
                subscription_data={
                    'metadata': {
                        'user_id': request.user.id
                    }
                }
            )
            
            # Create a pending transaction
            transaction = Transaction.objects.create(
                user=request.user,
                payment_plan=plan,
                amount=plan.price,
                credits_added=plan.credits,
                status=Transaction.PENDING,
                payment_intent_id=checkout_session.id
            )
            
            # Redirect to Stripe Checkout page
            return redirect(checkout_session.url)
        else:
            # One-time payment for additional credits
            
            # If customer exists, check for payment methods and use them directly
            if existing_customer:
                # First check if customer has payment methods
                payment_methods = None
                try:
                    payment_methods = stripe.PaymentMethod.list(
                        customer=customer_id,
                        type='card'
                    )
                    logger.info(f"Found {len(payment_methods.data)} payment methods for customer {customer_id}", extra={'easylogs_metadata': {'customer_id': customer_id}})
                except Exception as e:
                    logger.error(f"Error retrieving payment methods: {e}", extra={'easylogs_metadata': {'customer_id': customer_id, 'error_type': type(e).__name__}})
                
                # If customer has existing payment methods, use direct payment
                if payment_methods and payment_methods.data:
                    try:
                        # Create a payment intent directly
                        payment_intent = stripe.PaymentIntent.create(
                            amount=int(plan.price * 100),  # Convert to cents
                            currency='usd',
                            customer=customer_id,
                            payment_method=payment_methods.data[0].id,  # Use the first payment method
                            off_session=True,
                            confirm=True,  # Confirm the payment immediately
                            metadata={
                                'user_id': request.user.id,
                                'plan_id': plan.id,
                                'credits': plan.credits
                            }
                        )
                        
                        logger.info(f"Created payment intent: {payment_intent.id}, status: {payment_intent.status}", extra={'easylogs_metadata': {'payment_intent_id': payment_intent.id, 'status': payment_intent.status}})
                        
                        # Create a transaction record
                        transaction = Transaction.objects.create(
                            user=request.user,
                            payment_plan=plan,
                            amount=plan.price,
                            credits_added=plan.credits,
                            status=Transaction.COMPLETED if payment_intent.status == 'succeeded' else Transaction.PENDING,
                            payment_intent_id=payment_intent.id
                        )
                        
                        # Add success message if payment succeeded
                        if payment_intent.status == 'succeeded':
                            messages.success(request, f"Payment successful! {plan.credits:,} credits have been added to your account.")
                        else:
                            messages.info(request, "Your payment is being processed. Credits will be added soon.")
                        
                        return redirect('subscriptions:dashboard')
                    except Exception as e:
                        logger.error(f"Error creating payment intent: {e}", extra={'easylogs_metadata': {'user_id': request.user.id, 'error_type': type(e).__name__}})
                        # If direct payment fails for any reason, fall back to checkout
                        messages.warning(request, "Could not process payment with saved card. Please try again.")
            
            # If direct payment not possible or failed, use standard checkout
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                customer=customer_id,
                line_items=[
                    {
                        'price_data': {
                            'currency': 'usd',
                            'unit_amount': int(plan.price * 100),  # Convert to cents
                            'product_data': {
                                'name': plan.name,
                                'description': f'Get {plan.credits:,} credits'
                            },
                        },
                        'quantity': 1,
                    }
                ],
                metadata={
                    'user_id': request.user.id,
                    'plan_id': plan.id,
                    'credits': plan.credits
                },
                mode='payment',
                success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=cancel_url,
                expires_at=int((timezone.now() + timedelta(minutes=30)).timestamp()),  # Session expires after 30 minutes
                # CRITICAL: Save payment method for future use
                payment_method_options={
                    'card': {
                        'setup_future_usage': 'off_session'
                    }
                }
            )
            
            # Create a pending transaction
            transaction = Transaction.objects.create(
                user=request.user,
                payment_plan=plan,
                amount=plan.price,
                credits_added=plan.credits,
                status=Transaction.PENDING,
                payment_intent_id=checkout_session.id
            )
            
            # Redirect to Stripe Checkout page
            return redirect(checkout_session.url)
        
    except stripe.error.CardError as e:
        # Since it's a decline, stripe.error.CardError will be caught
        messages.error(request, f"Payment failed: {e.error.message}")
        return redirect('subscriptions:dashboard')
    except Exception as e:
        messages.error(request, f"Error processing payment: {str(e)}")
        return redirect('subscriptions:dashboard')

@login_required
def payment_success(request):
    """Handle successful payment"""
    session_id = request.GET.get('session_id')
    
    if session_id:
        try:
            # Retrieve session information
            session = stripe.checkout.Session.retrieve(session_id)
            logger.info(f"Processing payment success for session {session_id}, mode: {session.mode}")
            
            # Check if payment was successful
            if session.payment_status == 'paid' or session.mode == 'subscription':
                # Update transaction status
                try:
                    transaction = Transaction.objects.get(payment_intent_id=session_id)
                    transaction.status = Transaction.COMPLETED
                    transaction.save()
                    logger.info(f"Updated transaction {transaction.id} to completed")
                except Transaction.DoesNotExist:
                    logger.warning(f"Transaction not found for session {session_id}")
                
                # If this was a subscription, update user's subscription status
                if session.mode == 'subscription' and hasattr(session, 'subscription'):
                    user_credit, created = UserCredit.objects.get_or_create(user=request.user)
                    
                    # Set subscription fields
                    user_credit.is_subscribed = True
                    user_credit.stripe_subscription_id = session.subscription
                    user_credit.subscription_tier = 'pro'  # CRITICAL: Set to pro tier
                    
                    # Get subscription details to set dates
                    subscription = stripe.Subscription.retrieve(session.subscription)
                    user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
                    user_credit.monthly_reset_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
                    
                    # Reset monthly token usage for new subscription
                    user_credit.monthly_tokens_used = 0
                    
                    user_credit.save()
                    logger.info(f"Updated user {request.user.id} subscription: tier={user_credit.subscription_tier}, subscribed={user_credit.is_subscribed}")
                
                # For one-time payments (additional credits), just update transaction
                elif session.mode == 'payment':
                    logger.info(f"One-time payment processed for user {request.user.id}")
                
                # Add success message
                if session.mode == 'subscription':
                    messages.success(
                        request,
                        "Subscription started successfully! You now have access to "
                        f"{PRO_MONTHLY_TOKEN_LIMIT:,} tokens per month and all AI models.",
                    )
                else:
                    messages.success(request, "Payment successful! Additional tokens have been added to your account.")
                    
        except Exception as e:
            logger.error(f"Error processing payment success: {str(e)}", extra={'easylogs_metadata': {'session_id': session_id, 'error_type': type(e).__name__}})
            messages.warning(request, f"Payment was successful but there was an issue updating your account. Please contact support if you don't see your subscription activated.")
    
    # Redirect to dashboard with success message instead of showing static page
    return redirect('subscriptions:dashboard')

@login_required
def payment_cancel(request):
    """Handle cancelled payment"""
    # Mark any pending transactions as failed
    session_id = request.GET.get('session_id')
    if session_id:
        Transaction.objects.filter(
            payment_intent_id=session_id,
            status=Transaction.PENDING
        ).update(status=Transaction.FAILED)
    
    return render(
        request,
        'subscriptions/payment_cancel.html',
        {
            'free_tier_token_limit': FREE_TIER_TOKEN_LIMIT,
            'pro_monthly_token_limit': PRO_MONTHLY_TOKEN_LIMIT,
        },
    )

@login_required
def cancel_subscription(request):
    """Cancel a user's subscription"""
    user_credit = UserCredit.objects.get(user=request.user)
    
    if not user_credit.is_subscribed or not user_credit.stripe_subscription_id:
        messages.warning(request, "You don't have an active subscription to cancel.")
        redirect_to = request.POST.get('redirect_to', 'dashboard')
        if redirect_to == 'settings':
            return redirect('accounts:integrations')
        return redirect('subscriptions:dashboard')
    
    try:
        # Cancel the subscription in Stripe
        subscription = stripe.Subscription.modify(
            user_credit.stripe_subscription_id,
            cancel_at_period_end=True
        )
        
        # Update the subscription end date
        user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
        user_credit.save()
        
        messages.success(request, f"Your subscription has been canceled. You will continue to have access until {user_credit.subscription_end_date.strftime('%B %d, %Y')}.")
    except Exception as e:
        messages.error(request, f"Error canceling subscription: {str(e)}")
    
    redirect_to = request.POST.get('redirect_to', 'dashboard')
    if redirect_to == 'settings':
        return redirect('accounts:integrations')
    return redirect('subscriptions:dashboard')

@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Handle Stripe webhook events"""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    
    logger.info(f"Received webhook with signature: {sig_header[:20] if sig_header else 'None'}...")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
        logger.info(f"Webhook event verified successfully: {event['type']}")
    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid webhook payload: {e}")
        return JsonResponse({'error': str(e)}, status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid webhook signature: {e}")
        return JsonResponse({'error': str(e)}, status=400)
    
    # Handle the event
    try:
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            logger.info(f"Processing checkout.session.completed for session {session.id}")
            handle_successful_payment(session)
        elif event['type'] == 'customer.subscription.created':
            subscription = event['data']['object']
            logger.info(f"Processing customer.subscription.created for subscription {subscription.id}")
            handle_subscription_created(subscription)
        elif event['type'] == 'customer.subscription.updated':
            subscription = event['data']['object']
            logger.info(f"Processing customer.subscription.updated for subscription {subscription.id}")
            handle_subscription_updated(subscription)
        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            logger.info(f"Processing customer.subscription.deleted for subscription {subscription.id}")
            handle_subscription_canceled(subscription)
        elif event['type'] == 'invoice.payment_succeeded':
            invoice = event['data']['object']
            logger.info(f"Processing invoice.payment_succeeded for invoice {invoice.id}")
            if hasattr(invoice, 'subscription'):
                handle_subscription_payment(invoice)
        else:
            logger.info(f"Unhandled webhook event type: {event['type']}")
    except Exception as e:
        logger.error(f"Error processing webhook event {event['type']}: {e}")
        # Still return success to prevent Stripe from retrying
    
    return JsonResponse({'status': 'success'})

def handle_successful_payment(session):
    """Process a successful payment"""
    logger.info(f"Processing successful payment webhook for session {session.id}")
    
    # Update transaction status
    try:
        transaction = Transaction.objects.get(payment_intent_id=session.id)
        transaction.status = Transaction.COMPLETED
        transaction.save()
        logger.info(f"Updated transaction {transaction.id} status to completed")
        
        # If this was a subscription payment, update user subscription
        if session.mode == 'subscription' and hasattr(session, 'subscription'):
            user_credit, created = UserCredit.objects.get_or_create(user=transaction.user)
            user_credit.subscription_tier = 'pro'
            user_credit.is_subscribed = True
            user_credit.stripe_subscription_id = session.subscription
            user_credit.monthly_tokens_used = 0  # Reset monthly tokens
            
            # Get subscription details for dates
            try:
                subscription = stripe.Subscription.retrieve(session.subscription)
                user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
                user_credit.monthly_reset_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
            except Exception as e:
                logger.error(f"Error retrieving subscription details: {e}")
            
            user_credit.save()
            logger.info(f"Updated user {transaction.user.id} subscription via webhook: tier=pro, subscribed=True")
        
    except Transaction.DoesNotExist:
        logger.warning(f"Transaction not found for session {session.id}")
        # If transaction doesn't exist, create it
        if 'user_id' in session.metadata and 'plan_id' in session.metadata:
            from django.contrib.auth.models import User
            
            try:
                user = User.objects.get(id=session.metadata['user_id'])
                plan = PaymentPlan.objects.get(id=session.metadata['plan_id'])
                
                transaction = Transaction.objects.create(
                    user=user,
                    payment_plan=plan,
                    amount=session.amount_total / 100,  # Convert from cents
                    credits_added=int(session.metadata['credits']),
                    status=Transaction.COMPLETED,
                    payment_intent_id=session.id
                )
                logger.info(f"Created new transaction {transaction.id} from webhook")
                
                # If subscription, update user credit directly
                if session.mode == 'subscription' and hasattr(session, 'subscription'):
                    user_credit, created = UserCredit.objects.get_or_create(user=user)
                    user_credit.subscription_tier = 'pro'
                    user_credit.is_subscribed = True
                    user_credit.stripe_subscription_id = session.subscription
                    user_credit.stripe_customer_id = session.customer  # Save customer ID
                    user_credit.monthly_tokens_used = 0
                    user_credit.save()
                    logger.info(f"Set user {user.id} to pro tier via webhook")
                else:
                    # For one-time purchases, also save the customer ID
                    user_credit, created = UserCredit.objects.get_or_create(user=user)
                    user_credit.stripe_customer_id = session.customer
                    user_credit.save()
                    logger.info(f"Saved customer ID {session.customer} for user {user.id}")
                    
            except Exception as e:
                logger.error(f"Error creating transaction from webhook: {e}")

def handle_subscription_created(subscription):
    """Process a new subscription"""
    logger.info(f"Processing subscription created webhook for subscription {subscription.id}")
    
    # Find the customer
    if not hasattr(subscription, 'customer'):
        logger.warning("Subscription has no customer attribute")
        return
    
    # Get the customer to find the user
    try:
        customer = stripe.Customer.retrieve(subscription.customer)
        if 'user_id' in customer.metadata:
            from django.contrib.auth.models import User
            
            user_id = customer.metadata['user_id']
            user = User.objects.get(id=user_id)
            
            # Update user's subscription status
            user_credit, created = UserCredit.objects.get_or_create(user=user)
            user_credit.is_subscribed = True
            user_credit.stripe_subscription_id = subscription.id
            user_credit.stripe_customer_id = subscription.customer  # Save customer ID
            user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
            user_credit.subscription_tier = 'pro'  # CRITICAL: Set to pro tier
            user_credit.monthly_reset_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
            
            # Reset monthly token usage for new subscription
            user_credit.monthly_tokens_used = 0
            
            user_credit.save()
            logger.info(f"Updated user {user_id} subscription via webhook: tier=pro, subscription_id={subscription.id}")
            
            # Do NOT add to old credits system - that's the bug
            # The token system is what actually matters
            
    except Exception as e:
        logger.error(f"Error handling subscription creation: {str(e)}", extra={'easylogs_metadata': {'subscription_id': subscription.id, 'error_type': type(e).__name__}})

def handle_subscription_updated(subscription):
    """Process an updated subscription"""
    # Find the subscription in our system
    try:
        user_credit = UserCredit.objects.get(stripe_subscription_id=subscription.id)
        
        # Update subscription end date
        user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
        
        # Check if subscription is still active
        if subscription.status in ['active', 'trialing']:
            user_credit.is_subscribed = True
        else:
            user_credit.is_subscribed = False
        
        user_credit.save()
    except UserCredit.DoesNotExist:
        # Subscription not found in our system, ignore
        pass
    except Exception as e:
        logger.error(f"Error handling subscription update: {str(e)}", extra={'easylogs_metadata': {'error_type': type(e).__name__}})

def handle_subscription_canceled(subscription):
    """Process a canceled subscription"""
    try:
        user_credit = UserCredit.objects.get(stripe_subscription_id=subscription.id)
        user_credit.is_subscribed = False
        user_credit.save()
    except UserCredit.DoesNotExist:
        # Subscription not found in our system, ignore
        pass
    except Exception as e:
        logger.error(f"Error handling subscription cancellation: {str(e)}", extra={'easylogs_metadata': {'error_type': type(e).__name__}})

@login_required
def payment_methods(request):
    """Get user's payment methods"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        user_credit = UserCredit.objects.get(user=request.user)
        
        # Find existing customer
        existing_customer = None
        customer_search_method = "none"
        
        # First try direct customer ID lookup
        if user_credit.stripe_customer_id:
            try:
                existing_customer = stripe.Customer.retrieve(user_credit.stripe_customer_id)
                customer_search_method = "direct_customer_id"
                logger.info(f"Found customer via direct customer ID: {existing_customer.id}")
            except Exception as e:
                logger.error(f"Error retrieving customer from direct ID: {e}")
        
        # Fallback to subscription lookup
        if not existing_customer and user_credit.stripe_subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(user_credit.stripe_subscription_id)
                existing_customer = stripe.Customer.retrieve(subscription.customer)
                customer_search_method = "subscription"
                logger.info(f"Found customer via subscription: {existing_customer.id}")
                
                # Save the customer ID for future use
                user_credit.stripe_customer_id = existing_customer.id
                user_credit.save()
            except Exception as e:
                logger.error(f"Error retrieving customer from subscription: {e}")
        
        # Final fallback to email search
        if not existing_customer:
            try:
                customer_query = stripe.Customer.list(email=request.user.email, limit=1)
                if customer_query and customer_query.data:
                    existing_customer = customer_query.data[0]
                    customer_search_method = "email"
                    logger.info(f"Found customer via email search: {existing_customer.id}")
                    
                    # Save the customer ID for future use
                    user_credit.stripe_customer_id = existing_customer.id
                    user_credit.save()
            except Exception as e:
                logger.error(f"Error searching for customer: {e}")
        
        payment_methods = []
        if existing_customer:
            try:
                # Get customer's payment methods
                stripe_methods = stripe.PaymentMethod.list(
                    customer=existing_customer.id,
                    type='card'
                )
                
                logger.info(f"Found {len(stripe_methods.data)} payment methods for customer {existing_customer.id}")
                
                # Get default payment method
                default_pm_id = existing_customer.invoice_settings.default_payment_method
                
                for pm in stripe_methods.data:
                    payment_methods.append({
                        'id': pm.id,
                        'card': {
                            'brand': pm.card.brand,
                            'last4': pm.card.last4,
                            'exp_month': pm.card.exp_month,
                            'exp_year': pm.card.exp_year
                        },
                        'is_default': pm.id == default_pm_id
                    })
            except Exception as e:
                logger.error(f"Error retrieving payment methods: {e}")
        else:
            logger.warning(f"No customer found for user {request.user.email}")
        
        return JsonResponse({
            'payment_methods': payment_methods,
            'debug': {
                'customer_found': existing_customer is not None,
                'customer_search_method': customer_search_method,
                'customer_id': existing_customer.id if existing_customer else None,
                'user_email': request.user.email,
                'has_subscription_id': bool(user_credit.stripe_subscription_id)
            }
        })
    except UserCredit.DoesNotExist:
        return JsonResponse({'payment_methods': []})
    except Exception as e:
        logger.error(f"Error in payment_methods view: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)

@login_required
@require_POST
def create_setup_intent(request):
    """Create a setup session for adding payment methods"""
    try:
        user_credit, created = UserCredit.objects.get_or_create(user=request.user)
        
        # Find or create customer
        existing_customer = None
        if user_credit.stripe_subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(user_credit.stripe_subscription_id)
                existing_customer = stripe.Customer.retrieve(subscription.customer)
            except Exception:
                pass
        
        if not existing_customer:
            # Search by email
            try:
                customer_query = stripe.Customer.list(email=request.user.email, limit=1)
                if customer_query and customer_query.data:
                    existing_customer = customer_query.data[0]
            except Exception:
                pass
        
        if not existing_customer:
            # Create new customer
            existing_customer = stripe.Customer.create(
                email=request.user.email,
                name=f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                metadata={'user_id': request.user.id}
            )
            # Save customer ID immediately
            user_credit.stripe_customer_id = existing_customer.id
            user_credit.save()
        
        # Get domain for success and cancel URLs
        domain_url = request.build_absolute_uri('/').rstrip('/')
        success_url = domain_url + '/subscriptions/?setup=success'
        cancel_url = domain_url + '/subscriptions/?setup=cancel'
        
        # Create a checkout session for setup mode
        checkout_session = stripe.checkout.Session.create(
            customer=existing_customer.id,
            mode='setup',
            currency='usd',  # Required for setup mode
            success_url=success_url,
            cancel_url=cancel_url,
        )
        
        return JsonResponse({
            'setup_url': checkout_session.url,
            'session_id': checkout_session.id
        })
    except Exception as e:
        logger.error(f"Error creating setup session: {e}")
        return JsonResponse({'error': f'Failed to create setup session: {str(e)}'}, status=500)

@login_required
@require_POST
def set_default_payment_method(request):
    """Set default payment method"""
    try:
        data = json.loads(request.body)
        payment_method_id = data.get('payment_method_id')
        
        if not payment_method_id:
            return JsonResponse({'error': 'Payment method ID required'}, status=400)
        
        user_credit = UserCredit.objects.get(user=request.user)
        
        # Find customer
        existing_customer = None
        if user_credit.stripe_subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(user_credit.stripe_subscription_id)
                existing_customer = stripe.Customer.retrieve(subscription.customer)
            except Exception:
                pass
        
        if not existing_customer:
            customer_query = stripe.Customer.list(email=request.user.email, limit=1)
            if customer_query and customer_query.data:
                existing_customer = customer_query.data[0]
        
        if not existing_customer:
            return JsonResponse({'error': 'Customer not found'}, status=404)
        
        # Update customer's default payment method
        stripe.Customer.modify(
            existing_customer.id,
            invoice_settings={
                'default_payment_method': payment_method_id
            }
        )
        
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error setting default payment method: {e}")
        return JsonResponse({'error': 'Failed to set default payment method'}, status=500)

@login_required
@require_POST
def remove_payment_method(request):
    """Remove a payment method"""
    try:
        data = json.loads(request.body)
        payment_method_id = data.get('payment_method_id')
        
        if not payment_method_id:
            return JsonResponse({'error': 'Payment method ID required'}, status=400)
        
        # Detach the payment method from customer
        stripe.PaymentMethod.detach(payment_method_id)
        
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error removing payment method: {e}")
        return JsonResponse({'error': 'Failed to remove payment method'}, status=500)

def handle_subscription_payment(invoice):
    """Process a successful subscription payment"""
    if not hasattr(invoice, 'subscription') or not invoice.paid:
        return
    
    try:
        # Find the user with this subscription
        user_credit = UserCredit.objects.get(stripe_subscription_id=invoice.subscription)
        
        # Get subscription to update end date
        subscription = stripe.Subscription.retrieve(invoice.subscription)
        user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
        user_credit.save()
        
        # Add monthly credits and reset monthly usage
        from .utils import add_credits
        add_credits(
            user_credit.user,
            PRO_MONTHLY_TOKEN_LIMIT,
            "Pro Monthly subscription credits",
        )
        
        # Reset monthly token usage
        user_credit.monthly_tokens_used = 0
        user_credit.monthly_reset_date = timezone.datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
        user_credit.save()
        
        # Create a transaction record
        Transaction.objects.create(
            user=user_credit.user,
            payment_plan=PaymentPlan.objects.get(id=1),  # Monthly Subscription plan
            amount=invoice.amount_paid / 100,  # Convert from cents
            credits_added=PRO_MONTHLY_TOKEN_LIMIT,
            status=Transaction.COMPLETED,
            payment_intent_id=invoice.payment_intent
        )
    except UserCredit.DoesNotExist:
        # Subscription not found in our system
        pass
    except Exception as e:
        logger.error(f"Error handling subscription payment: {str(e)}", extra={'easylogs_metadata': {'error_type': type(e).__name__}})


@login_required
def fix_customer_ids(request):
    """Fix missing customer IDs for users - temporary endpoint"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        user = request.user
        user_credit, created = UserCredit.objects.get_or_create(user=user)
        
        if user_credit.stripe_customer_id:
            return JsonResponse({
                'status': 'already_fixed',
                'customer_id': user_credit.stripe_customer_id,
                'message': 'Customer ID already exists'
            })
        
        # Method 1: Check via subscription
        if user_credit.stripe_subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(user_credit.stripe_subscription_id)
                user_credit.stripe_customer_id = subscription.customer
                user_credit.save()
                return JsonResponse({
                    'status': 'fixed_via_subscription',
                    'customer_id': subscription.customer,
                    'message': 'Customer ID found via subscription'
                })
            except Exception as e:
                logger.error(f"Subscription lookup failed: {e}")
        
        # Method 2: Search by email
        try:
            customers = stripe.Customer.list(email=user.email, limit=5)
            if customers.data:
                customer = customers.data[0]
                user_credit.stripe_customer_id = customer.id
                user_credit.save()
                
                # Check payment methods
                payment_methods = stripe.PaymentMethod.list(customer=customer.id, type='card')
                
                return JsonResponse({
                    'status': 'fixed_via_email',
                    'customer_id': customer.id,
                    'payment_methods_count': len(payment_methods.data),
                    'message': f'Customer ID found via email search ({len(payment_methods.data)} payment methods)'
                })
            else:
                return JsonResponse({
                    'status': 'not_found',
                    'message': f'No Stripe customer found for {user.email}'
                })
                
        except Exception as e:
            logger.error(f"Email search failed: {e}")
            return JsonResponse({
                'status': 'error',
                'message': f'Search failed: {str(e)}'
            })
            
    except Exception as e:
        logger.error(f"Error in fix_customer_ids: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


@login_required
def debug_account(request):
    """Debug endpoint to check account status"""
    try:
        user = request.user
        user_credit, created = UserCredit.objects.get_or_create(user=user)
        
        # Check if stripe_customer_id field exists
        has_customer_id_field = hasattr(user_credit, 'stripe_customer_id')
        
        # Get recent transactions
        recent_transactions = Transaction.objects.filter(user=user).order_by('-created_at')[:5]
        transactions_data = [
            {
                'id': t.id,
                'amount': str(t.amount),
                'status': t.status,
                'created_at': t.created_at.isoformat(),
                'payment_plan': t.payment_plan.name if t.payment_plan else None
            }
            for t in recent_transactions
        ]
        
        debug_info = {
            'user_email': user.email,
            'user_id': user.id,
            'has_customer_id_field': has_customer_id_field,
            'user_credit': {
                'stripe_subscription_id': user_credit.stripe_subscription_id,
                'stripe_customer_id': getattr(user_credit, 'stripe_customer_id', 'FIELD_MISSING'),
                'subscription_tier': user_credit.subscription_tier,
                'is_subscribed': user_credit.is_subscribed,
                'has_active_subscription': user_credit.has_active_subscription,
            },
            'recent_transactions': transactions_data,
        }
        
        # Try to find Stripe customer
        stripe_customer_info = None
        if has_customer_id_field and user_credit.stripe_customer_id:
            try:
                customer = stripe.Customer.retrieve(user_credit.stripe_customer_id)
                payment_methods = stripe.PaymentMethod.list(customer=customer.id, type='card')
                stripe_customer_info = {
                    'customer_id': customer.id,
                    'email': customer.email,
                    'payment_methods_count': len(payment_methods.data),
                    'payment_methods': [
                        {
                            'id': pm.id,
                            'brand': pm.card.brand,
                            'last4': pm.card.last4
                        } for pm in payment_methods.data
                    ]
                }
            except Exception as e:
                stripe_customer_info = {'error': str(e)}
        
        debug_info['stripe_customer_info'] = stripe_customer_info
        
        return JsonResponse(debug_info)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required  
def fix_pro_subscription(request):
    """Fix pro subscription without proper monthly reset date"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        user = request.user
        user_credit, created = UserCredit.objects.get_or_create(user=user)
        
        if user_credit.subscription_tier == 'pro' and user_credit.is_subscribed:
            # Set monthly reset date to next month if not set
            if not user_credit.monthly_reset_date:
                from django.utils import timezone
                from datetime import timedelta
                
                user_credit.monthly_reset_date = timezone.now() + timedelta(days=30)
                user_credit.monthly_tokens_used = 0  # Reset monthly usage
                user_credit.save()
                
                return JsonResponse({
                    'status': 'fixed',
                    'message': 'Pro subscription monthly reset date set',
                    'new_remaining_tokens': user_credit.get_remaining_tokens(),
                    'monthly_reset_date': user_credit.monthly_reset_date.isoformat()
                })
            else:
                return JsonResponse({
                    'status': 'already_ok',
                    'message': 'Monthly reset date already set',
                    'remaining_tokens': user_credit.get_remaining_tokens()
                })
        else:
            return JsonResponse({
                'status': 'not_pro',
                'message': f'User is not pro (tier: {user_credit.subscription_tier}, subscribed: {user_credit.is_subscribed})'
            })
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
