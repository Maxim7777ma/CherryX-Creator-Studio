from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class CustomerAccess(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="billing_access", on_delete=models.CASCADE)
    plan_code = models.CharField(max_length=40)
    active_until = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-active_until"]

    @property
    def is_active(self) -> bool:
        return self.active_until > timezone.now()

    def __str__(self) -> str:
        return f"{self.user_id} {self.plan_code} until {self.active_until:%Y-%m-%d}"


class CheckoutRecord(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="billing_checkouts", null=True, blank=True, on_delete=models.SET_NULL)
    email = models.EmailField()
    name = models.CharField(max_length=150, blank=True)
    plan_code = models.CharField(max_length=40)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=8, default="USD")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    guest_key = models.CharField(max_length=80, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def mark_paid(self, user) -> None:
        self.user = user
        self.status = self.STATUS_PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["user", "status", "paid_at"])

    def __str__(self) -> str:
        return f"{self.email} {self.plan_code} {self.status}"

