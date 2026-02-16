import json
import logging
import re
from datetime import datetime
from pathlib import Path

import markdown
import yaml
from django.conf import settings
from django.core.mail import send_mail
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .models import FreePRDRequest, FreePRDVerificationCode, ServiceInquiry

logger = logging.getLogger(__name__)

# Create your views here.

BLOG_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _blog_content_dir() -> Path:
    return Path(settings.BASE_DIR) / "marketing" / "content" / "blog"


def _parse_date(date_value):
    if not date_value:
        return None
    if hasattr(date_value, "strftime"):
        return date_value
    if isinstance(date_value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(date_value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def _estimate_read_minutes(text: str) -> int:
    words = max(1, len(text.split()))
    return max(1, round(words / 200))


def _parse_reading_time(value, body_text: str) -> int:
    if value is not None:
        try:
            minutes = int(value)
            return max(1, minutes)
        except (TypeError, ValueError):
            pass
    return _estimate_read_minutes(body_text)


def _load_blog_posts():
    blog_dir = _blog_content_dir()
    if not blog_dir.exists():
        return []

    posts = []
    for md_file in sorted(blog_dir.glob("*.md")):
        raw_text = md_file.read_text(encoding="utf-8")
        metadata = {}
        body = raw_text

        front_matter_match = BLOG_FRONT_MATTER_RE.match(raw_text)
        if front_matter_match:
            metadata = yaml.safe_load(front_matter_match.group(1)) or {}
            body = front_matter_match.group(2)

        slug = slugify(metadata.get("slug") or md_file.stem) or md_file.stem
        title = metadata.get("title") or md_file.stem.replace("-", " ").title()
        excerpt = metadata.get("excerpt") or body.strip().split("\n")[0][:180]
        parsed_date = _parse_date(metadata.get("date"))
        reading_minutes = _parse_reading_time(metadata.get("reading_time"), body)

        posts.append({
            "slug": slug,
            "title": title,
            "excerpt": excerpt,
            "date": parsed_date,
            "date_display": parsed_date.strftime("%b %d, %Y") if parsed_date else "Undated",
            "reading_minutes": reading_minutes,
            "content_html": mark_safe(markdown.markdown(
                body,
                extensions=["extra", "fenced_code", "tables", "toc", "sane_lists"],
            )),
        })

    posts.sort(
        key=lambda item: (
            item["date"] is not None,
            item["date"] or datetime.min.date(),
            item["title"].lower(),
        ),
        reverse=True,
    )
    return posts


def _get_blog_post_by_slug(slug: str):
    for post in _load_blog_posts():
        if post["slug"] == slug:
            return post
    return None

def landing_page(request):
    """Render the home landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local'),
        'blog_posts': _load_blog_posts()[:3],
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


def blog_index_page(request):
    """Render the blog index page from markdown files."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local'),
        'blog_posts': _load_blog_posts(),
    }
    return render(request, 'home/blog_index.html', context)


def blog_detail_page(request, slug):
    """Render an individual blog post by slug."""
    post = _get_blog_post_by_slug(slug)
    if not post:
        raise Http404("Blog post not found")

    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local'),
        'post': post,
        'recent_posts': [p for p in _load_blog_posts() if p["slug"] != slug][:3],
    }
    return render(request, 'home/blog_post.html', context)

def ai_first_page(request):
    """Render the AI-first landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'home/landing_ai_first.html', context)


def venture_studio_page(request):
    """Render the venture studio rev-share landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'home/landing_venture_studio.html', context)


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


@require_http_methods(["POST"])
@csrf_protect
def request_free_prd_code(request):
    """Create a free PRD request record and send email verification code."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        payload = request.POST

    project_idea = payload.get('project_idea', '').strip()
    email = payload.get('email', '').strip().lower()

    if not project_idea or not email:
        return JsonResponse(
            {'success': False, 'error': 'Project idea and email are required.'},
            status=400
        )

    prd_request = FreePRDRequest.objects.create(
        email=email,
        project_idea=project_idea,
    )
    verification = FreePRDVerificationCode.create_code(prd_request)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@lfg.run')
    subject = "Your LFG free PRD verification code"
    body = f"""Your verification code is: {verification.code}

This code expires in 30 minutes.

We will use it to confirm your email before delivering your free PRD.
"""
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Failed to send free PRD verification code", exc_info=exc)
        return JsonResponse(
            {'success': False, 'error': 'Unable to send verification code right now.'},
            status=500
        )

    return JsonResponse({
        'success': True,
        'request_id': prd_request.id,
    })


@require_http_methods(["POST"])
@csrf_protect
def verify_free_prd_code(request):
    """Verify code for a free PRD request and mark lead as verified."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        payload = request.POST

    request_id = payload.get('request_id')
    code = str(payload.get('code', '')).strip()

    if not request_id or not code:
        return JsonResponse(
            {'success': False, 'error': 'Request ID and code are required.'},
            status=400
        )
    if len(code) != 6 or not code.isdigit():
        return JsonResponse({'success': False, 'error': 'Please enter a valid 6-digit code.'}, status=400)
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid request ID.'}, status=400)

    try:
        prd_request = FreePRDRequest.objects.get(id=request_id)
    except FreePRDRequest.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Request not found.'}, status=404)

    if prd_request.email_verified:
        return JsonResponse({'success': True, 'already_verified': True})

    verification = (
        FreePRDVerificationCode.objects
        .filter(
            request=prd_request,
            code=code,
            used=False,
            expires_at__gt=timezone.now(),
        )
        .order_by('-created_at')
        .first()
    )
    if not verification:
        return JsonResponse({'success': False, 'error': 'Invalid or expired code.'}, status=400)

    verification.used = True
    verification.save(update_fields=['used'])

    prd_request.email_verified = True
    prd_request.verified_at = timezone.now()
    prd_request.save(update_fields=['email_verified', 'verified_at', 'updated_at'])

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@lfg.run')
    try:
        send_mail(
            subject="Thanks - your free PRD request is confirmed",
            message=(
                "Thank you for your request. We received your product idea and will prepare your free PRD.\n\n"
                "— Team LFG"
            ),
            from_email=from_email,
            recipient_list=[prd_request.email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.warning("Failed to send free PRD confirmation email", exc_info=exc)

    return JsonResponse({'success': True})


@require_http_methods(["POST"])
@csrf_protect
def resend_free_prd_code(request):
    """Resend verification code for an existing free PRD request."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        payload = request.POST

    request_id = payload.get('request_id')
    if not request_id:
        return JsonResponse({'success': False, 'error': 'Request ID is required.'}, status=400)
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid request ID.'}, status=400)

    try:
        prd_request = FreePRDRequest.objects.get(id=request_id)
    except FreePRDRequest.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Request not found.'}, status=404)

    if prd_request.email_verified:
        return JsonResponse({'success': True, 'already_verified': True})

    verification = FreePRDVerificationCode.create_code(prd_request)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@lfg.run')
    subject = "Your new LFG free PRD verification code"
    body = f"""Your verification code is: {verification.code}

This code expires in 30 minutes.
"""
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[prd_request.email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Failed to resend free PRD verification code", exc_info=exc)
        return JsonResponse(
            {'success': False, 'error': 'Unable to resend code right now.'},
            status=500
        )

    return JsonResponse({'success': True})
