"""
Management command to test email configuration.
Usage: python manage.py test_email recipient@example.com
"""
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = 'Test email configuration by sending a test email'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'recipient_email',
            type=str,
            help='Email address to send the test email to'
        )
        parser.add_argument(
            '--subject',
            type=str,
            default='LFG Test Email',
            help='Subject of the test email'
        )
    
    def handle(self, *args, **options):
        recipient = options['recipient_email']
        subject = options['subject']
        
        self.stdout.write(f"Sending test email to: {recipient}")
        self.stdout.write(f"From: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"Email backend: {settings.EMAIL_BACKEND}")
        
        if hasattr(settings, 'SENDGRID_API_KEY') and settings.SENDGRID_API_KEY:
            self.stdout.write(self.style.SUCCESS("Using SendGrid"))
        else:
            self.stdout.write(f"Using SMTP: {settings.EMAIL_HOST}")
        
        try:
            send_mail(
                subject=subject,
                message=f'''This is a test email from LFG.

If you're receiving this email, your email configuration is working correctly!

Email Backend: {settings.EMAIL_BACKEND}
Sent from: {settings.DEFAULT_FROM_EMAIL}

Best regards,
The LFG Team 🚀
''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully sent test email to {recipient}')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to send email: {str(e)}')
            )
            self.stdout.write(
                self.style.WARNING('\nTroubleshooting tips:')
            )
            self.stdout.write('1. Check your SENDGRID_API_KEY environment variable')
            self.stdout.write('2. Verify SMTP settings if not using SendGrid')
            self.stdout.write('3. Ensure your email service allows sending from the configured address')