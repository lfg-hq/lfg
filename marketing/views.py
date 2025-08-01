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

def health_check(request):
    """Simple health check endpoint to verify the application is running."""
    return JsonResponse({
        "status": "healthy",
        "message": "Application is running correctly"
    })
