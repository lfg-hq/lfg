from django.core.management.base import BaseCommand
from django.db.models import Q

from subscriptions.models import PaymentPlan
from subscriptions.constants import DEFAULT_PAYMENT_PLANS

class Command(BaseCommand):
    help = 'Create default payment plans for subscriptions'
    
    def handle(self, *args, **kwargs):
        # Define our default plans
        default_plans = DEFAULT_PAYMENT_PLANS
        
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
