import json
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from .models import ServiceInquiry

logger = logging.getLogger(__name__)

# Create your views here.

def landing_page(request):
    """Render the home landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'home/landing.html', context)


def services_page(request):
    """Render the services-focused landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'home/landing_services.html', context)


def docs_page(request):
    """Render the PRD/docs-focused landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'home/landing_docs.html', context)


@require_http_methods(["POST"])
@csrf_protect
def submit_service_inquiry(request):
    """Capture service inquiries, persist, and send confirmation emails."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        payload = request.POST

    name = payload.get('name', '').strip()
    email = payload.get('email', '').strip()
    company = payload.get('company', '').strip()
    role = payload.get('role', '').strip()
    timeline = payload.get('timeline', '').strip()
    budget = payload.get('budget', '').strip()
    requirements = payload.get('requirements', '').strip()

    if not name or not email or not requirements:
        return JsonResponse({'success': False, 'error': 'Name, email, and requirements are required.'}, status=400)

    inquiry = ServiceInquiry.objects.create(
        name=name,
        email=email,
        company=company,
        role=role,
        timeline=timeline,
        budget=budget,
        requirements=requirements,
    )

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@lfg.run')

    ack_subject = "We've received your LFG Services request"
    ack_body = f"""Hi {name},

Thanks for reaching out! Our engineers will review your request and reply shortly.

Summary:
- Company: {company or 'N/A'}
- Role: {role or 'N/A'}
- Timeline: {timeline or 'N/A'}
- Budget: {budget or 'N/A'}
- Requirements: {requirements}

If you need to add anything else, just reply to this email.

— Team LFG
"""

    admin_subject = "New LFG services inquiry"
    admin_body = f"""New services inquiry submitted:

Name: {name}
Email: {email}
Company: {company or 'N/A'}
Role: {role or 'N/A'}
Timeline: {timeline or 'N/A'}
Budget: {budget or 'N/A'}
Requirements:
{requirements}

Record ID: {inquiry.id}
"""

    try:
        send_mail(
            subject=ack_subject,
            message=ack_body,
            from_email=from_email,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.warning("Failed to send ack email", exc_info=exc)

    try:
        send_mail(
            subject=admin_subject,
            message=admin_body,
            from_email=from_email,
            recipient_list=['hello@lfg.run'],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Failed to notify admin of inquiry", exc_info=exc)

    return JsonResponse({'success': True})


def health_check(request):
    """Simple health check endpoint to verify the application is running."""
    return JsonResponse({
        "status": "healthy",
        "message": "Application is running correctly"
    })
