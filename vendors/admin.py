from django.contrib import admin
from .models import Vendor


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('center_name', 'user', 'is_approved', 'latitude', 'longitude', 'created_at')
    list_filter = ('is_approved',)
    search_fields = ('center_name', 'user__phone', 'user__username')
    readonly_fields = ('created_at', 'admin_password_used')
    list_editable = ('is_approved',)

    def created_at(self, obj):
        return obj.user.date_joined
    created_at.short_description = "Registered"