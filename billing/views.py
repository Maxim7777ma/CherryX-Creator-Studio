from __future__ import annotations

from django.contrib.auth import login
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods

from .forms import CheckoutForm
from .models import CheckoutRecord
from .plans import PLANS, get_plan
from .services import activate_access, active_access_until, transfer_guest_workspace, user_has_active_access
from studio.localization import localized_plan


@require_GET
def pricing(request: HttpRequest):
    language = getattr(request, "interface_language", "en")
    return render(
        request,
        "billing/pricing.html",
        {
            "plans": [localized_plan(plan, language) for plan in PLANS],
            "has_access": user_has_active_access(request.user),
            "active_until": active_access_until(request.user),
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
    if request.method == "POST" and form.is_valid():
        plan = get_plan(form.cleaned_data["plan"])
        guest_key = _session_guest_key(request)
        user = form.create_user()
        CheckoutRecord.objects.create(
            user=user,
            email=user.email,
            name=user.first_name,
            plan_code=plan.code,
            amount_cents=plan.price_cents,
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
            "plans": [localized_plan(plan, language) for plan in PLANS],
            "selected_plan": localized_plan(selected_plan, language),
            "next_url": next_url,
            "has_access": user_has_active_access(request.user),
            "active_until": active_access_until(request.user),
        },
    )


def _session_guest_key(request: HttpRequest) -> str:
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""
