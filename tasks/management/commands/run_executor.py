"""
Django management command to run the async ticket executor service.

Usage:
    python manage.py run_executor

Options:
    --max-concurrent: Maximum concurrent tasks (default: 50)

Examples:
    # Start with default settings
    python manage.py run_executor

    # Start with custom concurrency
    python manage.py run_executor --max-concurrent 100
"""
import asyncio
import os
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Run the async ticket executor service'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-concurrent',
            type=int,
            default=50,
            help='Maximum concurrent tasks (default: 50)'
        )

    def handle(self, *args, **options):
        max_concurrent = options['max_concurrent']

        self.stdout.write(
            self.style.SUCCESS(
                f'Starting async executor service (max_concurrent={max_concurrent})...'
            )
        )
        self.stdout.write(
            self.style.NOTICE(
                'Press Ctrl+C to stop gracefully'
            )
        )

        # Import and run the service
        from tasks.executor_service import ExecutorService
        import signal

        async def run_service():
            service = ExecutorService(max_concurrent_tasks=max_concurrent)

            # Setup signal handlers
            loop = asyncio.get_event_loop()

            def signal_handler():
                self.stdout.write(
                    self.style.WARNING('\nShutdown requested, please wait...')
                )
                service.request_shutdown()

            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, signal_handler)

            await service.run()

            self.stdout.write(
                self.style.SUCCESS('Executor service stopped')
            )

        # Run the async service
        try:
            asyncio.run(run_service())
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('\nInterrupted')
            )
