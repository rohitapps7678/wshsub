from django.contrib import admin
from .models import User, VehicleType, Plan, Subscription


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('phone', 'username', 'is_customer', 'is_vendor', 'is_staff')
    search_fields = ('phone', 'username')


@admin.register(VehicleType)
class VehicleTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'vehicle_type', 'washes', 'price')
    list_filter = ('vehicle_type',)
    search_fields = ('name',)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'plan', 'remaining_washes', 'is_active', 'start_date')
    list_filter = ('is_active', 'plan')
    search_fields = ('customer__phone',)
    readonly_fields = ('qr_string', 'start_date')