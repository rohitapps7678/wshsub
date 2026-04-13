from django.db import models
from customers.models import User  # cross-app import


class Vendor(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='vendor_profile'
    )
    center_name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    registration_code = models.CharField(max_length=32, blank=True, null=True, unique=True)
    registration_code_used = models.BooleanField(default=False)
    registration_code_created_at = models.DateTimeField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Registration security
    admin_password_used = models.CharField(max_length=128, blank=True)
    
    # Customer-facing map visibility
    map_visible = models.BooleanField(
        default=True,
        verbose_name="Visible on Customer Map",
        help_text="If False, this center will NOT appear on the customer-facing nearby centers map."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.center_name} ({self.user.phone})"

    class Meta:
        ordering = ['-created_at']