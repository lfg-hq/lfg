"""Centralized token and plan configuration for subscriptions."""

from decimal import Decimal


# Token allowances
FREE_TIER_TOKEN_LIMIT = 100_000
PRO_MONTHLY_TOKEN_LIMIT = 1_000_000
ADDITIONAL_CREDIT_TOKENS = 1_000_000


# Default payment plans seeded via `create_default_plans`
DEFAULT_PAYMENT_PLANS = [
    {
        "name": "Free Tier",
        "price": Decimal("0.00"),
        "credits": FREE_TIER_TOKEN_LIMIT,
        "description": "Free tier with 100,000 tokens lifetime limit. Only supports gpt-5-mini model.",
        "is_subscription": False,
    },
    {
        "name": "Pro Monthly",
        "price": Decimal("9.00"),
        "credits": PRO_MONTHLY_TOKEN_LIMIT,
        "description": "Pro tier with 1,000,000 tokens per month. Access to all AI models.",
        "is_subscription": True,
    },
    {
        "name": "Additional Credits",
        "price": Decimal("5.00"),
        "credits": ADDITIONAL_CREDIT_TOKENS,
        "description": "Get 1,000,000 more tokens for $5 (one-time purchase).",
        "is_subscription": False,
    },
]
