from django.shortcuts import render
from django.http import JsonResponse

# Create your views here.

def landing_page(request):
    """Render the marketing landing page."""
    return render(request, 'marketing/landing.html')

def health_check(request):
    """Simple health check endpoint to verify the application is running."""
    return JsonResponse({
        "status": "healthy",
        "message": "Application is running correctly"
    })
