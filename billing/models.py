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


class TelegramStarPayment(models.Model):
    STATUS_PENDING_LINK = "pending_link"
    STATUS_CREDITED = "credited"
    STATUS_CHOICES = (
        (STATUS_PENDING_LINK, "Pending account link"),
        (STATUS_CREDITED, "Credited"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="telegram_star_payments", null=True, blank=True, on_delete=models.SET_NULL)
    telegram_user_id = models.BigIntegerField(db_index=True)
    telegram_username = models.CharField(max_length=80, blank=True)
    telegram_first_name = models.CharField(max_length=120, blank=True)
    currency = models.CharField(max_length=8, default="XTR")
    stars_amount = models.PositiveIntegerField()
    cherryx_amount = models.PositiveIntegerField(default=0)
    plan_code = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING_LINK, db_index=True)
    invoice_payload = models.CharField(max_length=160, db_index=True)
    telegram_payment_charge_id = models.CharField(max_length=160, unique=True)
    provider_payment_charge_id = models.CharField(max_length=160, blank=True)
    active_until = models.DateTimeField(null=True, blank=True)
    credited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["telegram_user_id", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.telegram_user_id} {self.stars_amount} Stars {self.status}"


class TelegramBotUser(models.Model):
    telegram_user_id = models.BigIntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=80, blank=True)
    first_name = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=16, blank=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    blocked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self) -> str:
        return f"{self.telegram_user_id} @{self.username}".strip()


class TelegramPaymentIntent(models.Model):
    KIND_PLAN = "plan"
    KIND_TOPUP = "topup"
    KIND_CHOICES = (
        (KIND_PLAN, "Plan"),
        (KIND_TOPUP, "Top up"),
    )

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_NEEDS_EMAIL = "needs_email"
    STATUS_APPLIED = "applied"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_NEEDS_EMAIL, "Needs email"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_EXPIRED, "Expired"),
    )

    token = models.CharField(max_length=48, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="telegram_payment_intents", null=True, blank=True, on_delete=models.SET_NULL)
    telegram_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    plan_code = models.CharField(max_length=40, blank=True)
    cherryx_amount = models.PositiveIntegerField(default=0)
    stars_amount = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    invoice_payload = models.CharField(max_length=160, blank=True, db_index=True)
    telegram_payment_charge_id = models.CharField(max_length=160, blank=True, db_index=True)
    provider_payment_charge_id = models.CharField(max_length=160, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["telegram_user_id", "-created_at"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.token}:{self.status}"


class TelegramPromotion(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_SENT = "sent"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_SENT, "Sent"),
    )

    title = models.CharField(max_length=160)
    text = models.TextField()
    image = models.ImageField(upload_to="telegram_promotions/", blank=True)
    button_text = models.CharField(max_length=80, blank=True)
    button_url = models.URLField(max_length=600, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
