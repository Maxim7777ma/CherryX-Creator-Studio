from __future__ import annotations

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .models import CheckoutRecord, CustomerAccess, TelegramBotUser, TelegramPaymentIntent, TelegramPromotion, TelegramStarPayment
from .services import apply_telegram_intent_to_user, send_telegram_promotion, simulate_telegram_intent_payment, sync_telegram_star_rate, telegram_star_rate_info


@admin.register(CustomerAccess)
class CustomerAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "plan_code", "active_until", "is_active", "updated_at")
    list_filter = ("plan_code", "active_until")
    search_fields = ("user__username", "user__email", "plan_code")
    autocomplete_fields = ("user",)
    date_hierarchy = "active_until"


@admin.register(CheckoutRecord)
class CheckoutRecordAdmin(admin.ModelAdmin):
    list_display = ("email", "user", "plan_code", "amount_display", "currency", "status", "paid_at", "created_at")
    list_filter = ("status", "plan_code", "currency", "created_at", "paid_at")
    search_fields = ("email", "name", "user__username", "user__email", "guest_key")
    autocomplete_fields = ("user",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "paid_at")

    @admin.display(description="Amount")
    def amount_display(self, obj: CheckoutRecord) -> str:
        return f"{obj.amount_cents / 100:.2f} {obj.currency}"


@admin.register(TelegramStarPayment)
class TelegramStarPaymentAdmin(admin.ModelAdmin):
    list_display = ("telegram_user_id", "user", "stars_amount", "cherryx_amount", "status", "plan_code", "created_at", "credited_at")
    list_filter = ("status", "currency", "plan_code", "created_at", "credited_at")
    search_fields = ("telegram_user_id", "telegram_username", "telegram_first_name", "telegram_payment_charge_id", "invoice_payload", "user__email", "user__username")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "credited_at")
    date_hierarchy = "created_at"


@admin.register(TelegramBotUser)
class TelegramBotUserAdmin(admin.ModelAdmin):
    list_display = ("telegram_user_id", "username", "first_name", "language", "last_seen_at", "blocked_at")
    list_filter = ("language", "blocked_at", "last_seen_at")
    search_fields = ("telegram_user_id", "username", "first_name")
    readonly_fields = ("last_seen_at", "blocked_at")
    date_hierarchy = "last_seen_at"


@admin.register(TelegramPaymentIntent)
class TelegramPaymentIntentAdmin(admin.ModelAdmin):
    list_display = ("token", "user", "telegram_user_id", "kind", "plan_code", "cherryx_amount", "stars_amount", "status", "expires_at", "paid_at", "applied_at")
    list_filter = ("kind", "status", "plan_code", "created_at", "paid_at")
    search_fields = ("token", "telegram_user_id", "user__email", "user__username", "telegram_payment_charge_id")
    autocomplete_fields = ("user",)
    readonly_fields = ("token", "invoice_payload", "created_at", "paid_at", "applied_at")
    date_hierarchy = "created_at"


@admin.register(TelegramPromotion)
class TelegramPromotionAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "sent_count", "failed_count", "sent_at", "created_at")
    list_filter = ("status", "sent_at", "created_at")
    search_fields = ("title", "text")
    readonly_fields = ("sent_count", "failed_count", "sent_at", "created_at", "updated_at")
    date_hierarchy = "created_at"

    def save_model(self, request, obj: TelegramPromotion, form, change) -> None:
        super().save_model(request, obj, form, change)
        if obj.status == TelegramPromotion.STATUS_ACTIVE and not obj.sent_at:
            send_telegram_promotion(obj)


def _num(value: int | None) -> str:
    return f"{int(value or 0):,}".replace(",", " ")


def telegram_finance_admin_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Telegram finance is available only for superusers.")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "sync_rate":
            result = sync_telegram_star_rate(force=True)
            if result.get("ok"):
                messages.success(request, "Telegram Stars rate updated.")
            else:
                messages.warning(request, f"Rate sync failed, fallback/last cache is still used: {result.get('error') or 'unknown error'}")
            return redirect("admin:telegram_finance")
        if action == "apply_intent":
            result = apply_telegram_intent_to_user(int(request.POST.get("intent_id") or 0), int(request.POST.get("user_id") or 0))
            if result.get("ok"):
                messages.success(request, "Telegram payment intent applied to the selected user.")
            else:
                messages.error(request, f"Could not apply intent: {result.get('reason') or 'unknown error'}")
            return redirect("admin:telegram_finance")
        if action == "simulate_intent":
            result = simulate_telegram_intent_payment(int(request.POST.get("intent_id") or 0))
            if result.get("ok"):
                messages.success(request, "Test Telegram payment simulated and processed.")
            else:
                messages.error(request, f"Could not simulate intent: {result.get('reason') or 'unknown error'}")
            return redirect("admin:telegram_finance")

    paid_qs = TelegramPaymentIntent.objects.filter(status__in=[TelegramPaymentIntent.STATUS_PAID, TelegramPaymentIntent.STATUS_NEEDS_EMAIL, TelegramPaymentIntent.STATUS_APPLIED])
    applied_qs = TelegramPaymentIntent.objects.filter(status=TelegramPaymentIntent.STATUS_APPLIED)
    pending_link_qs = TelegramPaymentIntent.objects.filter(status=TelegramPaymentIntent.STATUS_NEEDS_EMAIL).order_by("-paid_at", "-created_at")
    testable_qs = TelegramPaymentIntent.objects.filter(status=TelegramPaymentIntent.STATUS_PENDING, telegram_user_id__isnull=False).order_by("-created_at")
    recent_qs = paid_qs.select_related("user").order_by("-paid_at", "-created_at")[:20]
    users = get_user_model().objects.order_by("-date_joined")[:12]
    pending_intents = [
        {"object": item, "admin_url": reverse("admin:billing_telegrampaymentintent_change", args=[item.pk])}
        for item in pending_link_qs[:30]
    ]
    recent_intents = [
        {"object": item, "admin_url": reverse("admin:billing_telegrampaymentintent_change", args=[item.pk])}
        for item in recent_qs
    ]
    testable_intents = [
        {"object": item, "admin_url": reverse("admin:billing_telegrampaymentintent_change", args=[item.pk])}
        for item in testable_qs[:20]
    ]

    context = {
        **admin.site.each_context(request),
        "title": "Telegram finance",
        "rate": telegram_star_rate_info(refresh=False),
        "cards": [
            {"label": "Stars paid", "value": _num(paid_qs.aggregate(total=Sum("stars_amount"))["total"]), "hint": f"{paid_qs.count()} paid intents"},
            {"label": "CherryX credited", "value": _num(applied_qs.aggregate(total=Sum("cherryx_amount"))["total"]), "hint": "applied to accounts"},
            {"label": "Applied payments", "value": applied_qs.count(), "hint": "completed"},
            {"label": "Needs email/link", "value": pending_link_qs.count(), "hint": "manual support queue"},
        ],
        "pending_intents": pending_intents,
        "testable_intents": testable_intents,
        "recent_intents": recent_intents,
        "recent_users": users,
    }
    return TemplateResponse(request, "admin/telegram_finance.html", context)


if not getattr(admin.site, "_telegram_finance_installed", False):
    _default_get_urls = admin.site.get_urls

    def _telegram_finance_get_urls():
        return [
            path("telegram-finance/", admin.site.admin_view(telegram_finance_admin_view), name="telegram_finance"),
        ] + _default_get_urls()

    admin.site.get_urls = _telegram_finance_get_urls
    admin.site._telegram_finance_installed = True
