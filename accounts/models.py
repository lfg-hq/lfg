from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    sidebar_collapsed = models.BooleanField(default=False)
    
    # API Keys for different services
    openai_api_key = models.CharField(max_length=255, blank=True, null=True)
    anthropic_api_key = models.CharField(max_length=255, blank=True, null=True)
    groq_api_key = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.username}'s profile"

class GitHubToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    access_token = models.CharField(max_length=255)
    github_user_id = models.CharField(max_length=100, blank=True, null=True)
    github_username = models.CharField(max_length=100, blank=True, null=True)
    github_avatar_url = models.URLField(max_length=500, blank=True, null=True)
    scope = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s GitHub token"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    try:
        if created:
            Profile.objects.create(user=instance)
    except:
        # Handle the case when the table doesn't exist yet
        pass

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        instance.profile.save()
    except:
        # Handle the case when the profile doesn't exist
        pass 