from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from src import web_actions

from .models import CustomerAccess
from .plans import AccessPlan, get_plan


def user_has_active_access(user) -> bool:
    if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
        return False
    try:
        return user.billing_access.is_active
    except CustomerAccess.DoesNotExist:
        return False


def active_access_until(user):
    if not user or not user.is_authenticated:
        return None
    try:
        access = user.billing_access
    except CustomerAccess.DoesNotExist:
        return None
    return access.active_until if access.is_active else None


def activate_access(user, plan: AccessPlan) -> CustomerAccess:
    now = timezone.now()
    current_until = active_access_until(user)
    starts_at = current_until if current_until and current_until > now else now
    active_until = starts_at + timedelta(days=plan.period_days)
    access, _ = CustomerAccess.objects.update_or_create(
        user=user,
        defaults={
            "plan_code": plan.code,
            "active_until": active_until,
        },
    )
    return access


def prorated_due_cents(current_plan: AccessPlan | None, new_plan: AccessPlan, left_seconds: float, *, renew_same_plan: bool = True) -> int:
    if renew_same_plan and current_plan and current_plan.code == new_plan.code:
        return new_plan.price_cents
    if not current_plan or not current_plan.period_days or left_seconds <= 0:
        return new_plan.price_cents
    remaining_value = round(current_plan.price_cents * min(1, left_seconds / (current_plan.period_days * 86400)))
    return max(0, new_plan.price_cents - remaining_value)


def transfer_guest_workspace(guest_key: str, user) -> int:
    if not guest_key or not user or not user.is_authenticated:
        return 0
    return web_actions.transfer_guest_jobs_to_user(guest_key, user.id)


__all__ = [
    "activate_access",
    "active_access_until",
    "get_plan",
    "prorated_due_cents",
    "transfer_guest_workspace",
    "user_has_active_access",
]
