from django.contrib import admin

from .models import (
    FreePRDRequest,
    FreePRDVerificationCode,
    ServiceInquiry,
)


@admin.register(ServiceInquiry)
class ServiceInquiryAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'company', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'email', 'company', 'requirements')


@admin.register(FreePRDRequest)
class FreePRDRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'email_verified', 'created_at', 'verified_at')
    list_filter = ('email_verified', 'created_at', 'verified_at')
    search_fields = ('email', 'project_idea')


@admin.register(FreePRDVerificationCode)
class FreePRDVerificationCodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'request', 'code', 'used', 'created_at', 'expires_at')
    list_filter = ('used', 'created_at', 'expires_at')
    search_fields = ('request__email', 'code')
