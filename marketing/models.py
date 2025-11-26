from django.db import models


class ServiceInquiry(models.Model):
    """Lead capture for the services landing page."""

    name = models.CharField(max_length=255)
    email = models.EmailField()
    company = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=255, blank=True)
    timeline = models.CharField(max_length=255, blank=True)
    budget = models.CharField(max_length=255, blank=True)
    requirements = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.email}"
