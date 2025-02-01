from django.db import models
from django.utils import timezone

class Subscription(models.Model):
    SUBSCRIPTION_STATUS = (
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('cancelled', 'Cancelled'),
        ('inactive', 'Inactive'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    )

    user_email = models.EmailField()
    subscription_id = models.CharField(max_length=255, unique=True)
    plan_id = models.CharField(max_length=255)
    total_count = models.IntegerField()
    status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS, default='pending')
    short_url = models.URLField(null=True, blank=True)
    order_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    access_valid_till = models.DateTimeField(null=True, blank=True)
    has_access = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

class Plans(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # Add other plan fields as needed
