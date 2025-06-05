from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.utils import get_token_usage_stats
from accounts.models import TokenUsage
import json


class Command(BaseCommand):
    help = 'Display token usage statistics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Username to filter by'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to look back (default: 30)'
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed records'
        )

    def handle(self, *args, **options):
        user = None
        if options['user']:
            try:
                user = User.objects.get(username=options['user'])
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User '{options['user']}' not found"))
                return

        # Get statistics
        stats = get_token_usage_stats(user=user, days=options['days'])
        
        # Display summary
        self.stdout.write(self.style.SUCCESS("\n=== TOKEN USAGE SUMMARY ==="))
        summary = stats['summary']
        self.stdout.write(f"Date Range: {stats['date_range']['start'].strftime('%Y-%m-%d')} to {stats['date_range']['end'].strftime('%Y-%m-%d')}")
        self.stdout.write(f"Total Requests: {summary.get('request_count', 0):,}")
        self.stdout.write(f"Total Input Tokens: {summary.get('total_input_tokens', 0):,}")
        self.stdout.write(f"Total Output Tokens: {summary.get('total_output_tokens', 0):,}")
        self.stdout.write(f"Total Tokens: {summary.get('total_tokens', 0):,}")
        self.stdout.write(f"Total Cost: ${summary.get('total_cost', 0):.4f}")
        
        # Display by provider
        self.stdout.write(self.style.SUCCESS("\n=== BY PROVIDER ==="))
        for provider in stats['by_provider']:
            self.stdout.write(f"\n{provider['provider'].upper()}:")
            self.stdout.write(f"  Requests: {provider['requests']:,}")
            self.stdout.write(f"  Total Tokens: {provider['total_tokens']:,}")
            self.stdout.write(f"  Cost: ${provider.get('cost', 0):.4f}")
        
        # Display by model
        self.stdout.write(self.style.SUCCESS("\n=== BY MODEL ==="))
        for model in stats['by_model']:
            self.stdout.write(f"\n{model['provider']}/{model['model']}:")
            self.stdout.write(f"  Requests: {model['requests']:,}")
            self.stdout.write(f"  Input Tokens: {model['input_tokens']:,}")
            self.stdout.write(f"  Output Tokens: {model['output_tokens']:,}")
            self.stdout.write(f"  Total Tokens: {model['total_tokens']:,}")
            self.stdout.write(f"  Cost: ${model.get('cost', 0):.4f}")
        
        # Show detailed records if requested
        if options['detailed']:
            self.stdout.write(self.style.SUCCESS("\n=== RECENT RECORDS ==="))
            query = TokenUsage.objects.all()
            if user:
                query = query.filter(user=user)
            
            records = query.order_by('-timestamp')[:10]
            for record in records:
                self.stdout.write(f"\n{record.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {record.user.username}")
                self.stdout.write(f"  {record.provider}/{record.model}")
                self.stdout.write(f"  Tokens: {record.input_tokens} in / {record.output_tokens} out / {record.total_tokens} total")
                self.stdout.write(f"  Cost: ${record.cost:.4f}" if record.cost else "  Cost: N/A")
                if record.project:
                    self.stdout.write(f"  Project: {record.project.name}")
                if record.conversation:
                    self.stdout.write(f"  Conversation: {record.conversation.title or record.conversation.id}")