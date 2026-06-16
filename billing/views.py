from __future__ import annotations

from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods
from urllib.parse import urlencode

from .forms import CheckoutForm
from .models import CheckoutRecord
from .plans import PLANS, get_plan
from .services import activate_access, active_access_until, prorated_due_cents, transfer_guest_workspace, user_has_active_access
from studio.localization import localized_plan


@require_GET
def pricing(request: HttpRequest):
    language = getattr(request, "interface_language", "en")
    next_url = request.GET.get("next") or reverse("studio:index")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse("studio:index")
    return render(
        request,
        "billing/pricing.html",
        {
            "plans": [localized_plan(plan, language) for plan in PLANS],
            "has_access": user_has_active_access(request.user),
            "active_until": active_access_until(request.user),
            "current_plan_code": _current_access_plan_code(request),
            "checkout_return_url": f"{reverse('billing:checkout')}?{urlencode({'next': next_url})}",
            "focused_plan_code": request.GET.get("focus") or "",
        },
    )


@require_http_methods(["GET", "POST"])
def checkout(request: HttpRequest):
    selected_plan = get_plan(request.POST.get("plan") or request.GET.get("plan"))
    language = getattr(request, "interface_language", "en")
    next_url = request.POST.get("next") or request.GET.get("next") or reverse("studio:index")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse("studio:index")

    initial = {"plan": selected_plan.code, "next": next_url}
    form = CheckoutForm(request.POST or None, initial=initial, user=request.user, language=language)
    checkout_price = _checkout_price_context(request, selected_plan, request.GET.get("due"))
    if request.method == "POST" and form.is_valid():
        plan = get_plan(form.cleaned_data["plan"])
        checkout_price = _checkout_price_context(request, plan, request.POST.get("due") or request.GET.get("due"))
        guest_key = _session_guest_key(request)
        user = form.create_user()
        CheckoutRecord.objects.create(
            user=user,
            email=user.email,
            name=user.first_name,
            plan_code=plan.code,
            amount_cents=checkout_price["due_cents"],
            currency=plan.currency,
            status=CheckoutRecord.STATUS_PAID,
            guest_key=guest_key,
            paid_at=timezone.now(),
        )
        activate_access(user, plan)
        transferred = transfer_guest_workspace(guest_key, user)
        login(request, user)
        request.session["billing_last_transfer_count"] = transferred
        return redirect(form.cleaned_data.get("next") or reverse("studio:index"))

    return render(
        request,
        "billing/checkout.html",
        {
            "form": form,
            "plans": [_localized_checkout_plan(request, plan, language) for plan in PLANS],
            "selected_plan": localized_plan(selected_plan, language),
            "checkout_price": checkout_price,
            "next_url": next_url,
            "has_access": user_has_active_access(request.user),
            "active_until": active_access_until(request.user),
            "current_plan_code": _current_access_plan_code(request),
        },
    )


@require_GET
def check_email(request: HttpRequest) -> JsonResponse:
    email = (request.GET.get("email") or "").strip().lower()
    exists = bool(email) and (User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists())
    return JsonResponse({"exists": exists})


def _session_guest_key(request: HttpRequest) -> str:
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def _current_access_plan_code(request: HttpRequest) -> str:
    if not request.user.is_authenticated:
        return ""
    try:
        access = request.user.billing_access
    except Exception:
        return ""
    return access.plan_code if access.is_active else ""


def _checkout_price_context(request: HttpRequest, selected_plan, due_override: str | None = None) -> dict[str, object]:
    now = timezone.now()
    current_plan = None
    left_seconds = 0
    if request.user.is_authenticated:
        try:
            access = request.user.billing_access
            if access.active_until > now:
                current_plan = get_plan(access.plan_code)
                left_seconds = max((access.active_until - now).total_seconds(), 0)
        except Exception:
            pass
    credit_cents = 0
    if current_plan and current_plan.code != selected_plan.code and current_plan.period_days:
        credit_cents = round(current_plan.price_cents * min(1, left_seconds / (current_plan.period_days * 86400)))
        credit_cents = min(selected_plan.price_cents, credit_cents)
    calculated_due_cents = prorated_due_cents(current_plan, selected_plan, left_seconds)
    due_cents = calculated_due_cents
    try:
        override_cents = int(due_override) if due_override is not None else None
    except (TypeError, ValueError):
        override_cents = None
    if override_cents is not None and override_cents == calculated_due_cents:
        due_cents = override_cents
    return {
        "due_cents": due_cents,
        "due_display": _money_display(due_cents),
        "calculated_due_cents": calculated_due_cents,
        "credit_cents": credit_cents,
        "credit_display": _money_display(credit_cents),
        "list_display": selected_plan.price_display,
    }


def _localized_checkout_plan(request: HttpRequest, plan, language: str):
    from types import SimpleNamespace

    localized = localized_plan(plan, language)
    price = _checkout_price_context(request, plan)
    return SimpleNamespace(**vars(localized), **price)


def _money_display(cents: int) -> str:
    return f"{cents // 100}$" if cents % 100 == 0 else f"{cents / 100:.2f}$"
