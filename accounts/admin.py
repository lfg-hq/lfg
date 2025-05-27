from django.contrib import admin
from .models import Profile, GitHubToken

admin.site.register(Profile)
admin.site.register(GitHubToken) 