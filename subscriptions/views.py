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
import stripe
import json
import os

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
    
    context = {
        'user_credit': user_credit,
        'payment_plans': payment_plans,
        'transactions': transactions,
    }
    
    return render(request, 'subscriptions/dashboard.html', context)

@login_required
def checkout(request, plan_id):
    """View for checkout process using Stripe Checkout"""
    plan = get_object_or_404(PaymentPlan, id=plan_id, is_active=True)
    
    # Get domain for success and cancel URLs
    domain_url = request.build_absolute_uri('/').rstrip('/')
    success_url = domain_url + reverse('subscriptions:payment_success')
    cancel_url = domain_url + reverse('subscriptions:payment_cancel')
    
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
            print(f"Error retrieving subscription: {e}")
    
    # If no customer found via subscription, search by email
    if not existing_customer:
        try:
            customer_query = stripe.Customer.list(email=request.user.email, limit=1)
            if customer_query and customer_query.data:
                existing_customer = customer_query.data[0]
        except Exception as e:
            print(f"Error searching for customer by email: {e}")
    
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
        else:
            customer_id = existing_customer.id
            print(f"Found existing customer: {customer_id}")
        
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
            
            # If already subscribed, we know they have a payment method, so use it directly
            if user_credit.has_active_subscription and existing_customer:
                # First check if customer has payment methods
                payment_methods = None
                try:
                    payment_methods = stripe.PaymentMethod.list(
                        customer=customer_id,
                        type='card'
                    )
                    print(f"Found {len(payment_methods.data)} payment methods for customer {customer_id}")
                except Exception as e:
                    print(f"Error retrieving payment methods: {e}")
                
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
                        
                        print(f"Created payment intent: {payment_intent.id}, status: {payment_intent.status}")
                        
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
                        print(f"Error creating payment intent: {e}")
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
                expires_at=int((timezone.now() + timedelta(minutes=30)).timestamp())  # Session expires after 30 minutes
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
            
            # Check if payment was successful
            if session.payment_status == 'paid' or session.mode == 'subscription':
                # Update transaction status
                transaction = Transaction.objects.get(payment_intent_id=session_id)
                transaction.status = Transaction.COMPLETED
                transaction.save()
                
                # If this was a subscription, update user's subscription status
                if session.mode == 'subscription' and hasattr(session, 'subscription'):
                    user_credit = UserCredit.objects.get(user=transaction.user)
                    user_credit.is_subscribed = True
                    user_credit.stripe_subscription_id = session.subscription
                    
                    # Get subscription details to set end date
                    subscription = stripe.Subscription.retrieve(session.subscription)
                    user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end)
                    user_credit.save()
                
                # Add success message
                if session.mode == 'subscription':
                    messages.success(request, "Subscription started successfully! Credits have been added to your account.")
                else:
                    messages.success(request, "Payment successful! Credits have been added to your account.")
        except Exception as e:
            messages.warning(request, f"Unable to verify payment: {str(e)}")
    
    return render(request, 'subscriptions/payment_success.html')

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
    
    return render(request, 'subscriptions/payment_cancel.html')

@login_required
def cancel_subscription(request):
    """Cancel a user's subscription"""
    user_credit = UserCredit.objects.get(user=request.user)
    
    if not user_credit.is_subscribed or not user_credit.stripe_subscription_id:
        messages.warning(request, "You don't have an active subscription to cancel.")
        return redirect('subscriptions:dashboard')
    
    try:
        # Cancel the subscription in Stripe
        subscription = stripe.Subscription.modify(
            user_credit.stripe_subscription_id,
            cancel_at_period_end=True
        )
        
        # Update the subscription end date
        user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end)
        user_credit.save()
        
        messages.success(request, f"Your subscription has been canceled. You will continue to have access until {user_credit.subscription_end_date.strftime('%B %d, %Y')}.")
    except Exception as e:
        messages.error(request, f"Error canceling subscription: {str(e)}")
    
    return redirect('subscriptions:dashboard')

@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Handle Stripe webhook events"""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return JsonResponse({'error': str(e)}, status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return JsonResponse({'error': str(e)}, status=400)
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session)
    elif event['type'] == 'customer.subscription.created':
        subscription = event['data']['object']
        handle_subscription_created(subscription)
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        handle_subscription_updated(subscription)
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        handle_subscription_canceled(subscription)
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        if hasattr(invoice, 'subscription'):
            handle_subscription_payment(invoice)
    
    return JsonResponse({'status': 'success'})

def handle_successful_payment(session):
    """Process a successful payment"""
    # Update transaction status
    try:
        transaction = Transaction.objects.get(payment_intent_id=session.id)
        transaction.status = Transaction.COMPLETED
        transaction.save()
        
        # Signal will handle updating the user's credits
    except Transaction.DoesNotExist:
        # If transaction doesn't exist, create it
        if 'user_id' in session.metadata and 'plan_id' in session.metadata:
            from django.contrib.auth.models import User
            
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

def handle_subscription_created(subscription):
    """Process a new subscription"""
    # Find the customer
    if not hasattr(subscription, 'customer'):
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
            user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end)
            user_credit.save()
            
            # Add credits for the first subscription period
            from .utils import add_credits
            add_credits(user, 1000000, "Monthly subscription credits")
    except Exception as e:
        print(f"Error handling subscription creation: {str(e)}")

def handle_subscription_updated(subscription):
    """Process an updated subscription"""
    # Find the subscription in our system
    try:
        user_credit = UserCredit.objects.get(stripe_subscription_id=subscription.id)
        
        # Update subscription end date
        user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end)
        
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
        print(f"Error handling subscription update: {str(e)}")

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
        print(f"Error handling subscription cancellation: {str(e)}")

def handle_subscription_payment(invoice):
    """Process a successful subscription payment"""
    if not hasattr(invoice, 'subscription') or not invoice.paid:
        return
    
    try:
        # Find the user with this subscription
        user_credit = UserCredit.objects.get(stripe_subscription_id=invoice.subscription)
        
        # Get subscription to update end date
        subscription = stripe.Subscription.retrieve(invoice.subscription)
        user_credit.subscription_end_date = timezone.datetime.fromtimestamp(subscription.current_period_end)
        user_credit.save()
        
        # Add monthly credits
        from .utils import add_credits
        add_credits(user_credit.user, 1000000, "Monthly subscription credits")
        
        # Create a transaction record
        Transaction.objects.create(
            user=user_credit.user,
            payment_plan=PaymentPlan.objects.get(id=1),  # Monthly Subscription plan
            amount=invoice.amount_paid / 100,  # Convert from cents
            credits_added=1000000,
            status=Transaction.COMPLETED,
            payment_intent_id=invoice.payment_intent
        )
    except UserCredit.DoesNotExist:
        # Subscription not found in our system
        pass
    except Exception as e:
        print(f"Error handling subscription payment: {str(e)}")
