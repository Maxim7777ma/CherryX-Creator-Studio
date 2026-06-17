from __future__ import annotations

from django.contrib import admin

from .models import CheckoutRecord, CustomerAccess


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
