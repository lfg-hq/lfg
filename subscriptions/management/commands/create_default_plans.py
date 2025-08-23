from django.core.management.base import BaseCommand
from subscriptions.models import PaymentPlan
from django.db.models import Q

class Command(BaseCommand):
    help = 'Create default payment plans for subscriptions'
    
    def handle(self, *args, **kwargs):
        # Define our default plans
        default_plans = [
            {
                'name': 'Free Tier',
                'price': 0.00,
                'credits': 100000,  # 100K tokens total (all-time)
                'description': 'Free tier with 100,000 tokens lifetime limit. Only supports gpt-5-mini model.',
                'is_subscription': False
            },
            {
                'name': 'Pro Monthly',
                'price': 9.00,
                'credits': 300000,  # 300K tokens per month
                'description': 'Pro tier with 300,000 tokens per month. Access to all AI models.',
                'is_subscription': True
            },
            {
                'name': 'Additional Credits',
                'price': 5.00,
                'credits': 100000,  # 100K additional tokens
                'description': 'Get 100,000 more tokens for $5 (one-time purchase).',
                'is_subscription': False
            }
        ]
        
        plans_created = 0
        plans_updated = 0
        
        for plan_data in default_plans:
            # Try to find an existing plan with the same name
            existing_plan = PaymentPlan.objects.filter(
                Q(name=plan_data['name'])
            ).first()
            
            if existing_plan:
                # Update the existing plan
                existing_plan.price = plan_data['price']
                existing_plan.credits = plan_data['credits']
                existing_plan.description = plan_data['description']
                existing_plan.is_active = True
                existing_plan.is_subscription = plan_data.get('is_subscription', False)
                existing_plan.save()
                plans_updated += 1
                self.stdout.write(self.style.SUCCESS(f"Updated plan: {existing_plan.name}"))
            else:
                # Create a new plan
                new_plan = PaymentPlan.objects.create(
                    name=plan_data['name'],
                    price=plan_data['price'],
                    credits=plan_data['credits'],
                    description=plan_data['description'],
                    is_active=True,
                    is_subscription=plan_data.get('is_subscription', False)
                )
                plans_created += 1
                self.stdout.write(self.style.SUCCESS(f"Created plan: {new_plan.name}"))
        
        self.stdout.write(self.style.SUCCESS(
            f"Successfully created {plans_created} and updated {plans_updated} payment plans."
        )) 