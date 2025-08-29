from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings

# Create your views here.

def landing_page(request):
    """Render the home landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'home/landing.html', context)

def agencies_landing(request):
    """Render the agencies-focused landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'marketing/agencies.html', context)

def startups_landing(request):
    """Render the startups-focused landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'marketing/startups.html', context)

def product_managers_landing(request):
    """Render the product managers-focused landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'marketing/product_managers.html', context)

def technical_analysis_landing(request):
    """Render the technical analysis-focused landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'marketing/technical_analysis.html', context)

def project_planning_landing(request):
    """Render the project planning-focused landing page."""
    context = {
        'ENVIRONMENT': getattr(settings, 'ENVIRONMENT', 'local')
    }
    return render(request, 'marketing/project_planning.html', context)

def health_check(request):
    """Simple health check endpoint to verify the application is running."""
    return JsonResponse({
        "status": "healthy",
        "message": "Application is running correctly"
    })
