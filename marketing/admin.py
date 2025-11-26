from django.contrib import admin

from .models import ServiceInquiry


@admin.register(ServiceInquiry)
class ServiceInquiryAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'company', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'email', 'company', 'requirements')
