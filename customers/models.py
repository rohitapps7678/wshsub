# customers/models.py (updated)
from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid

class User(AbstractUser):
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    is_customer = models.BooleanField(default=True)
    is_vendor = models.BooleanField(default=False)

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.phone or self.username


class VehicleType(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Plan(models.Model):

    vendor = models.ForeignKey(
        'vendors.Vendor',
        on_delete=models.CASCADE,
        related_name="plans"
    )

    name = models.CharField(max_length=100)

    vehicle_type = models.ForeignKey(
        VehicleType,
        on_delete=models.PROTECT
    )

    washes = models.PositiveIntegerField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    duration_type = models.CharField(
        max_length=10,
        choices=[
            ("month","Monthly"),
            ("year","Yearly")
        ]
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.vendor.center_name}"


class Subscription(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    remaining_washes = models.PositiveIntegerField()
    start_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    qr_string = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    qr_image = models.ImageField(upload_to='qr_codes/subscriptions/', null=True, blank=True)
    
    # ─── नया फील्ड ────────────────────────────────
    vehicle_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Vehicle Number"
    )
    vehicle_number_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Vehicle Number Updated At"
    )

    def __str__(self):
        veh = f" ({self.vehicle_number})" if self.vehicle_number else ""
        return f"{self.customer.phone} - {self.plan.name}{veh} ({self.remaining_washes} left)"

class WashHistory(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name='wash_history')
    vendor = models.ForeignKey('vendors.Vendor', on_delete=models.PROTECT, null=True)
    wash_time = models.DateTimeField(auto_now_add=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-wash_time']
        verbose_name_plural = "Wash Histories"

    def __str__(self):
        return f"Wash {self.id} - {self.subscription.customer.phone} @ {self.wash_time.date()}"