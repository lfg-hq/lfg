# Subscriptions Module

This module manages user credits and payment processing for the LFG application.

## Features

- User credit management
- Payment processing using Stripe
- Subscription and one-time payment options
- Credit usage tracking

## Models

### UserCredit

Stores the user's current credit balance.

### PaymentPlan

Defines available payment plans and their credit values.

### Transaction

Records all payment transactions made by users.

## Usage

### Setting Up Stripe

1. Create a Stripe account at https://stripe.com/
2. Add your API keys to your environment or .env file:
   ```
   STRIPE_SECRET_KEY=sk_test_your_secret_key
   STRIPE_PUBLIC_KEY=pk_test_your_public_key
   STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
   ```

### Creating Default Payment Plans

Run the management command to create the default payment plans:

```
python manage.py create_default_plans
```

### Using Credits in Your Application

You can use the utility functions in `subscriptions/utils.py` to work with user credits:

```python
from subscriptions.utils import get_user_credits, has_sufficient_credits, use_credits

# Get a user's current credits
credits = get_user_credits(request.user)

# Check if a user has enough credits
if has_sufficient_credits(request.user, 1000):
    # Deduct credits for an operation
    success = use_credits(request.user, 1000, "Generated AI response")
    if success:
        # Perform the operation
        pass
    else:
        # Handle insufficient credits
        pass
```

## Webhook Setup

To properly handle asynchronous payment events, set up a Stripe webhook:

1. Go to the Stripe Dashboard > Developers > Webhooks
2. Add Endpoint: `https://yourdomain.com/subscriptions/webhook/`
3. Add the following events:
   - `payment_intent.succeeded`
   - `payment_intent.payment_failed`
4. Copy the signing secret to your environment as `STRIPE_WEBHOOK_SECRET`

## Credit Plans

- Monthly Subscription: $10 for 1,000,000 credits
- Additional Credits: $5 for 1,000,000 credits (one-time purchase)

## Integration with Templates

The user's current credit balance is available in all templates as `{{ user_credits }}`.

## Extending

To add more payment plans, you can:

1. Add them to the `create_default_plans` command
2. Or create them through the Django admin interface 