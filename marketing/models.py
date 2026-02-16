from django.db import models
from django.utils import timezone
from datetime import timedelta
import random


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


class FreePRDRequest(models.Model):
    """Lead capture for free PRD generation on landing page."""

    email = models.EmailField(db_index=True)
    project_idea = models.TextField()
    email_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Free PRD Request {self.id} - {self.email}"


class FreePRDVerificationCode(models.Model):
    """6-digit verification codes for free PRD requests."""

    request = models.ForeignKey(
        FreePRDRequest,
        on_delete=models.CASCADE,
        related_name='verification_codes',
    )
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"Code for request {self.request_id}"

    @classmethod
    def create_code(cls, prd_request):
        cls.objects.filter(request=prd_request, used=False).update(used=True)
        code = str(random.randint(100000, 999999))
        expires_at = timezone.now() + timedelta(minutes=30)
        return cls.objects.create(
            request=prd_request,
            code=code,
            expires_at=expires_at,
        )

    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at
