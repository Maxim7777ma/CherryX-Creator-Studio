from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import json
import math
import os
from pathlib import Path
import re
import secrets
import string

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.utils import timezone
import httpx

from src import web_actions

from studio.models import AccountProfile, MagicLoginToken

from .models import CustomerAccess, TelegramBotUser, TelegramPaymentIntent, TelegramPromotion, TelegramStarPayment
from .plans import AccessPlan, get_plan


TELEGRAM_TOPUP_PRESETS_CHERRYX = (100, 500, 1000, 2500)
INTENT_TTL_MINUTES = 60
TELEGRAM_STAR_RATE_CACHE = "telegram_star_rate.json"
TELEGRAM_STAR_RATE_SOURCE_URL = "https://core.telegram.org/api/config"
TELEGRAM_STAR_RATE_MAX_AGE_SECONDS = 86400
TELEGRAM_STAR_RATE_RETRY_SECONDS = 3600


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


def telegram_stars_to_cherryx(stars: int) -> int:
    try:
        rate = int(os.getenv("TELEGRAM_STARS_TO_CHERRYX", "10"))
    except ValueError:
        rate = 10
    return max(0, int(stars) * max(1, rate))


def telegram_stars_rate() -> int:
    try:
        rate = int(os.getenv("TELEGRAM_STARS_TO_CHERRYX", "10"))
    except ValueError:
        rate = 10
    return max(1, rate)


def cherryx_to_telegram_stars(cherryx_amount: int) -> int:
    return max(1, math.ceil(max(1, int(cherryx_amount)) / telegram_stars_rate()))


def _telegram_star_env_usd_cents() -> Decimal:
    raw_value = os.getenv("TELEGRAM_STAR_USD_CENTS", "1.3").strip()
    try:
        value = Decimal(raw_value)
    except (InvalidOperation, ValueError):
        value = Decimal("1.3")
    return max(value, Decimal("0.01"))


def _telegram_star_rate_cache_path() -> Path:
    base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    return base_dir / "data" / TELEGRAM_STAR_RATE_CACHE


def _read_telegram_star_rate_cache() -> dict[str, object]:
    try:
        path = _telegram_star_rate_cache_path()
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_telegram_star_rate_cache(data: dict[str, object]) -> None:
    path = _telegram_star_rate_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_telegram_star_rate(force: bool = False) -> dict[str, object]:
    cache = _read_telegram_star_rate_cache()
    now = timezone.now()
    now_ts = int(now.timestamp())
    if not force:
        updated_at = int(cache.get("updated_at_ts") or 0)
        attempted_at = int(cache.get("attempted_at_ts") or 0)
        if updated_at and now_ts - updated_at < TELEGRAM_STAR_RATE_MAX_AGE_SECONDS:
            return {**cache, "ok": True, "cached": True}
        if attempted_at and now_ts - attempted_at < TELEGRAM_STAR_RATE_RETRY_SECONDS:
            return {**cache, "ok": bool(cache.get("usd_cents_per_star")), "cached": True, "retry_later": True}

    next_cache = {**cache, "attempted_at": now.isoformat(), "attempted_at_ts": now_ts}
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            response = client.get(TELEGRAM_STAR_RATE_SOURCE_URL)
            response.raise_for_status()
        match = re.search(r'stars_usd_withdraw_rate_x1000(?:</a>)?"?\s*:\s*([0-9]+(?:\.[0-9]+)?)', response.text)
        if not match:
            raise ValueError("stars_usd_withdraw_rate_x1000 not found")
        withdraw_rate_x1000 = Decimal(match.group(1))
        usd_cents_per_star = max(Decimal("0.01"), withdraw_rate_x1000 / Decimal("1000"))
        next_cache.update(
            {
                "ok": True,
                "source": TELEGRAM_STAR_RATE_SOURCE_URL,
                "source_key": "stars_usd_withdraw_rate_x1000",
                "source_value": str(withdraw_rate_x1000),
                "usd_cents_per_star": str(usd_cents_per_star),
                "updated_at": now.isoformat(),
                "updated_at_ts": now_ts,
                "error": "",
            }
        )
        _write_telegram_star_rate_cache(next_cache)
        return next_cache
    except Exception as exc:
        next_cache.update({"ok": False, "error": str(exc)[:500]})
        _write_telegram_star_rate_cache(next_cache)
        return next_cache


def telegram_star_rate_info(refresh: bool = True) -> dict[str, object]:
    cache = sync_telegram_star_rate() if refresh else _read_telegram_star_rate_cache()
    raw_value = cache.get("usd_cents_per_star") or _telegram_star_env_usd_cents()
    try:
        usd_cents = Decimal(str(raw_value))
    except (InvalidOperation, ValueError):
        usd_cents = _telegram_star_env_usd_cents()
    return {
        "usd_cents_per_star": max(usd_cents, Decimal("0.01")),
        "source": cache.get("source") or "env",
        "source_key": cache.get("source_key") or "TELEGRAM_STAR_USD_CENTS",
        "updated_at": cache.get("updated_at") or "",
        "cached": bool(cache.get("usd_cents_per_star")),
        "ok": bool(cache.get("ok")) if cache else False,
        "error": cache.get("error") or "",
    }


def telegram_star_usd_cents() -> Decimal:
    return telegram_star_rate_info(refresh=False)["usd_cents_per_star"]


def usd_cents_to_telegram_stars(usd_cents: int) -> int:
    cents = Decimal(max(1, int(usd_cents)))
    return max(1, int((cents / telegram_star_usd_cents()).to_integral_value(rounding="ROUND_CEILING")))


def telegram_stars_to_usd_cents_approx(stars_amount: int) -> int:
    cents = Decimal(max(0, int(stars_amount))) * telegram_star_usd_cents()
    return int(cents.to_integral_value(rounding=ROUND_HALF_UP))


def cherryx_to_usd_cents_approx(cherryx_amount: int) -> int:
    return max(0, int(cherryx_amount or 0))


def cherryx_to_usd_display_approx(cherryx_amount: int) -> str:
    return money_display_from_cents(cherryx_to_usd_cents_approx(cherryx_amount))


def money_display_from_cents(cents: int) -> str:
    cents = int(cents or 0)
    return f"{cents // 100}$" if cents % 100 == 0 else f"{cents / 100:.2f}$"


def telegram_plan_price(plan: AccessPlan) -> dict[str, object]:
    stars = usd_cents_to_telegram_stars(plan.price_cents)
    usd_cents = telegram_stars_to_usd_cents_approx(stars)
    return {
        "stars_amount": stars,
        "stars_display": f"{stars} Stars",
        "usd_cents": usd_cents,
        "usd_display": money_display_from_cents(usd_cents),
        "usd_approx_display": f"≈ {money_display_from_cents(usd_cents)}",
    }


def telegram_topup_cherryx_from_stars(stars_amount: int) -> int:
    return int(stars_amount) * telegram_stars_rate()


def telegram_stars_plan_code() -> str:
    return (os.getenv("TELEGRAM_STARS_PLAN_CODE", "pro").strip().lower() or "pro")


def telegram_bot_username() -> str:
    return os.getenv("TELEGRAM_BOT_USERNAME", "cherryxconverter_bot").strip().lstrip("@") or "cherryxconverter_bot"


def telegram_bot_deep_link(token: str) -> str:
    return f"https://t.me/{telegram_bot_username()}?start=pay_{token}"


def public_site_url() -> str:
    return os.getenv("PUBLIC_SITE_URL", os.getenv("MINI_APP_URL", "http://127.0.0.1:8000")).rstrip("/")


def create_magic_login_url(user) -> str:
    token = MagicLoginToken.create_for_user(user, timezone.now() + timedelta(minutes=30))
    return f"{public_site_url()}/accounts/magic/{token.token}/"


def intent_payload(token: str) -> str:
    return f"intent:{token}"


def upsert_telegram_bot_user(telegram_user_id: int, username: str = "", first_name: str = "", language: str = "") -> None:
    TelegramBotUser.objects.update_or_create(
        telegram_user_id=int(telegram_user_id),
        defaults={
            "username": (username or "")[:80],
            "first_name": (first_name or "")[:120],
            "language": (language or "")[:16],
            "last_seen_at": timezone.now(),
            "blocked_at": None,
        },
    )


def create_telegram_payment_intent(
    *,
    kind: str,
    user=None,
    plan_code: str = "",
    cherryx_amount: int | None = None,
    telegram_user_id: int | None = None,
) -> dict[str, object]:
    if kind == TelegramPaymentIntent.KIND_PLAN:
        plan = get_plan(plan_code)
        plan_code = plan.code
        cherryx = int(cherryx_amount) if cherryx_amount is not None else int(plan.price_cents)
        if cherryx <= 0:
            raise ValueError("Plan amount must be positive")
        stars = usd_cents_to_telegram_stars(cherryx)
    elif kind == TelegramPaymentIntent.KIND_TOPUP:
        cherryx = int(cherryx_amount or 0)
        if cherryx <= 0:
            raise ValueError("Top up amount must be positive")
        plan_code = ""
        stars = cherryx_to_telegram_stars(cherryx)
    else:
        raise ValueError("Unsupported Telegram payment kind")

    token = secrets.token_urlsafe(18)[:32]
    intent = TelegramPaymentIntent.objects.create(
        token=token,
        user=user if getattr(user, "is_authenticated", False) else None,
        telegram_user_id=int(telegram_user_id) if telegram_user_id else None,
        kind=kind,
        plan_code=plan_code,
        cherryx_amount=cherryx,
        stars_amount=stars,
        status=TelegramPaymentIntent.STATUS_PENDING,
        invoice_payload=intent_payload(token),
        expires_at=timezone.now() + timedelta(minutes=INTENT_TTL_MINUTES),
    )
    return telegram_payment_intent_payload(intent)


def telegram_payment_intent_payload(intent: TelegramPaymentIntent) -> dict[str, object]:
    return {
        "ok": True,
        "token": intent.token,
        "kind": intent.kind,
        "plan_code": intent.plan_code,
        "cherryx_amount": intent.cherryx_amount,
        "stars_amount": intent.stars_amount,
        "status": intent.status,
        "payload": intent.invoice_payload or intent_payload(intent.token),
        "title": telegram_intent_title(intent),
        "description": telegram_intent_description(intent),
        "link": telegram_bot_deep_link(intent.token),
        "expires_at": intent.expires_at,
        "linked": bool(intent.user_id),
    }


def telegram_intent_title(intent: TelegramPaymentIntent) -> str:
    if intent.kind == TelegramPaymentIntent.KIND_PLAN:
        return f"CherryX {get_plan(intent.plan_code).name}"
    return "CherryX balance top up"


def telegram_intent_description(intent: TelegramPaymentIntent) -> str:
    if intent.kind == TelegramPaymentIntent.KIND_PLAN:
        plan = get_plan(intent.plan_code)
        return f"{plan.period_days} days of CherryX access. {intent.cherryx_amount} CherryX."
    return f"Add {intent.cherryx_amount} CherryX to your balance."


@transaction.atomic
def claim_telegram_payment_intent(token: str, telegram_user_id: int, username: str = "", first_name: str = "", language: str = "") -> dict[str, object]:
    upsert_telegram_bot_user(telegram_user_id, username, first_name, language)
    intent = TelegramPaymentIntent.objects.select_for_update().filter(token=(token or "").strip()).first()
    if not intent:
        return {"ok": False, "reason": "not_found"}
    if intent.status != TelegramPaymentIntent.STATUS_PENDING:
        return {"ok": False, "reason": intent.status, **telegram_payment_intent_payload(intent)}
    if intent.expires_at <= timezone.now():
        intent.status = TelegramPaymentIntent.STATUS_EXPIRED
        intent.save(update_fields=["status"])
        return {"ok": False, "reason": "expired"}
    intent.telegram_user_id = int(telegram_user_id)
    intent.save(update_fields=["telegram_user_id"])
    return telegram_payment_intent_payload(intent)


def create_direct_telegram_intent(kind: str, plan_code: str = "", cherryx_amount: int | None = None, telegram_user_id: int | None = None) -> dict[str, object]:
    return create_telegram_payment_intent(kind=kind, plan_code=plan_code, cherryx_amount=cherryx_amount, telegram_user_id=telegram_user_id)


def create_direct_telegram_topup_by_stars(stars_amount: int, telegram_user_id: int | None = None) -> dict[str, object]:
    stars = int(stars_amount)
    if stars < 1 or stars > 150000:
        raise ValueError("Telegram Stars amount must be between 1 and 150000")

    token = secrets.token_urlsafe(18)[:32]
    intent = TelegramPaymentIntent.objects.create(
        token=token,
        user=None,
        telegram_user_id=int(telegram_user_id) if telegram_user_id else None,
        kind=TelegramPaymentIntent.KIND_TOPUP,
        plan_code="",
        cherryx_amount=telegram_topup_cherryx_from_stars(stars),
        stars_amount=stars,
        status=TelegramPaymentIntent.STATUS_PENDING,
        invoice_payload=intent_payload(token),
        expires_at=timezone.now() + timedelta(minutes=INTENT_TTL_MINUTES),
    )
    return telegram_payment_intent_payload(intent)


@transaction.atomic
def record_telegram_intent_payment(
    *,
    telegram_user_id: int,
    stars_amount: int,
    invoice_payload: str,
    telegram_payment_charge_id: str,
    provider_payment_charge_id: str = "",
    currency: str = "XTR",
    telegram_username: str = "",
    telegram_first_name: str = "",
) -> dict[str, object]:
    token = (invoice_payload or "").split(":", 1)[1] if (invoice_payload or "").startswith("intent:") else ""
    intent = TelegramPaymentIntent.objects.select_for_update().filter(token=token).first()
    if not intent:
        return {"ok": False, "reason": "intent_not_found"}
    if intent.status == TelegramPaymentIntent.STATUS_APPLIED:
        return {"ok": True, "duplicate": True, "needs_email": False, **telegram_payment_intent_payload(intent)}
    if currency != "XTR" or int(stars_amount) != intent.stars_amount:
        return {"ok": False, "reason": "amount_mismatch"}

    upsert_telegram_bot_user(telegram_user_id, telegram_username, telegram_first_name)
    intent.telegram_user_id = int(telegram_user_id)
    intent.status = TelegramPaymentIntent.STATUS_PAID
    intent.paid_at = timezone.now()
    intent.telegram_payment_charge_id = (telegram_payment_charge_id or "")[:160]
    intent.provider_payment_charge_id = (provider_payment_charge_id or "")[:160]
    intent.save(update_fields=["telegram_user_id", "status", "paid_at", "telegram_payment_charge_id", "provider_payment_charge_id"])

    profile = AccountProfile.objects.select_for_update().select_related("user").filter(telegram_user_id=int(telegram_user_id)).first()
    if not profile and intent.user_id:
        profile, _ = AccountProfile.objects.select_for_update().get_or_create(user=intent.user)
        profile.telegram_user_id = int(telegram_user_id)
        profile.telegram_username = (telegram_username or "")[:80]
        profile.telegram_first_name = (telegram_first_name or "")[:120]
        profile.save(update_fields=["telegram_user_id", "telegram_username", "telegram_first_name", "updated_at"])

    if profile:
        _apply_telegram_intent_to_profile(intent, profile)
        return {"ok": True, "needs_email": False, **telegram_payment_intent_payload(intent)}

    intent.status = TelegramPaymentIntent.STATUS_NEEDS_EMAIL
    intent.save(update_fields=["status"])
    return {"ok": True, "needs_email": True, **telegram_payment_intent_payload(intent)}


@transaction.atomic
def create_account_for_paid_telegram_intent(telegram_user_id: int, email: str, username: str = "", first_name: str = "") -> dict[str, object]:
    normalized_email = (email or "").strip().lower()
    if "@" not in normalized_email or "." not in normalized_email.rsplit("@", 1)[-1]:
        return {"ok": False, "reason": "invalid_email"}
    User = get_user_model()
    if User.objects.filter(email__iexact=normalized_email).exists() or User.objects.filter(username__iexact=normalized_email).exists():
        return {"ok": False, "reason": "email_exists"}
    intent = (
        TelegramPaymentIntent.objects.select_for_update()
        .filter(telegram_user_id=int(telegram_user_id), status=TelegramPaymentIntent.STATUS_NEEDS_EMAIL)
        .order_by("-paid_at", "-created_at")
        .first()
    )
    if not intent:
        return {"ok": False, "reason": "no_paid_intent"}

    password = _generated_password()
    user = User.objects.create_user(username=normalized_email, email=normalized_email, password=password, first_name=(first_name or "")[:150])
    profile, _ = AccountProfile.objects.select_for_update().get_or_create(user=user)
    profile.telegram_user_id = int(telegram_user_id)
    profile.telegram_username = (username or "")[:80]
    profile.telegram_first_name = (first_name or "")[:120]
    profile.save(update_fields=["telegram_user_id", "telegram_username", "telegram_first_name", "updated_at"])
    _apply_telegram_intent_to_profile(intent, profile)
    magic_login_url = create_magic_login_url(user)
    return {
        "ok": True,
        "email": normalized_email,
        "password": password,
        "login_url": public_site_url() + "/accounts/login/",
        "magic_login_url": magic_login_url,
        **telegram_payment_intent_payload(intent),
    }


@transaction.atomic
def simulate_telegram_intent_payment(intent_id: int) -> dict[str, object]:
    intent = TelegramPaymentIntent.objects.select_for_update().filter(pk=int(intent_id)).first()
    if not intent:
        return {"ok": False, "reason": "intent_not_found"}
    if intent.status != TelegramPaymentIntent.STATUS_PENDING:
        return {"ok": False, "reason": f"not_pending:{intent.status}"}
    if not intent.telegram_user_id:
        return {"ok": False, "reason": "missing_telegram_user_id"}
    return record_telegram_intent_payment(
        telegram_user_id=intent.telegram_user_id,
        stars_amount=intent.stars_amount,
        invoice_payload=intent.invoice_payload or intent_payload(intent.token),
        telegram_payment_charge_id=f"test:{intent.token}",
        provider_payment_charge_id="admin-simulated",
        currency="XTR",
    )


@transaction.atomic
def apply_telegram_intent_to_user(intent_id: int, user_id: int) -> dict[str, object]:
    User = get_user_model()
    user = User.objects.select_for_update().filter(pk=int(user_id)).first()
    if not user:
        return {"ok": False, "reason": "user_not_found"}
    intent = TelegramPaymentIntent.objects.select_for_update().filter(pk=int(intent_id)).first()
    if not intent:
        return {"ok": False, "reason": "intent_not_found"}
    if intent.status not in {TelegramPaymentIntent.STATUS_PAID, TelegramPaymentIntent.STATUS_NEEDS_EMAIL, TelegramPaymentIntent.STATUS_APPLIED}:
        return {"ok": False, "reason": "intent_not_paid"}
    if intent.status == TelegramPaymentIntent.STATUS_APPLIED and intent.user_id == user.pk:
        return {"ok": True, "already_applied": True, **telegram_payment_intent_payload(intent)}
    if intent.status == TelegramPaymentIntent.STATUS_APPLIED and intent.user_id != user.pk:
        return {"ok": False, "reason": "already_applied_to_other_user"}

    profile, _ = AccountProfile.objects.select_for_update().get_or_create(user=user)
    if intent.telegram_user_id:
        AccountProfile.objects.select_for_update().filter(telegram_user_id=intent.telegram_user_id).exclude(pk=profile.pk).update(
            telegram_user_id=None,
            telegram_username="",
            telegram_first_name="",
            updated_at=timezone.now(),
        )
        profile.telegram_user_id = intent.telegram_user_id
    profile.save(update_fields=["telegram_user_id", "updated_at"])
    _apply_telegram_intent_to_profile(intent, profile)
    return {"ok": True, **telegram_payment_intent_payload(intent)}


def _generated_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _apply_telegram_intent_to_profile(intent: TelegramPaymentIntent, profile: AccountProfile) -> None:
    if intent.status == TelegramPaymentIntent.STATUS_APPLIED:
        return
    if intent.kind == TelegramPaymentIntent.KIND_PLAN:
        access = activate_access(profile.user, get_plan(intent.plan_code))
        intent.user = profile.user
        intent.status = TelegramPaymentIntent.STATUS_APPLIED
        intent.applied_at = timezone.now()
        intent.save(update_fields=["user", "status", "applied_at"])
        TelegramStarPayment.objects.get_or_create(
            telegram_payment_charge_id=intent.telegram_payment_charge_id or f"intent:{intent.token}",
            defaults={
                "user": profile.user,
                "telegram_user_id": intent.telegram_user_id or profile.telegram_user_id or 0,
                "telegram_username": profile.telegram_username,
                "telegram_first_name": profile.telegram_first_name,
                "currency": "XTR",
                "stars_amount": intent.stars_amount,
                "cherryx_amount": intent.cherryx_amount,
                "plan_code": intent.plan_code,
                "status": TelegramStarPayment.STATUS_CREDITED,
                "invoice_payload": intent.invoice_payload,
                "provider_payment_charge_id": intent.provider_payment_charge_id,
                "active_until": access.active_until,
                "credited_at": timezone.now(),
            },
        )
        return

    profile.cherryx_balance = int(profile.cherryx_balance or 0) + int(intent.cherryx_amount or 0)
    profile.save(update_fields=["cherryx_balance", "updated_at"])
    intent.user = profile.user
    intent.status = TelegramPaymentIntent.STATUS_APPLIED
    intent.applied_at = timezone.now()
    intent.save(update_fields=["user", "status", "applied_at"])
    TelegramStarPayment.objects.get_or_create(
        telegram_payment_charge_id=intent.telegram_payment_charge_id or f"intent:{intent.token}",
        defaults={
            "user": profile.user,
            "telegram_user_id": intent.telegram_user_id or profile.telegram_user_id or 0,
            "telegram_username": profile.telegram_username,
            "telegram_first_name": profile.telegram_first_name,
            "currency": "XTR",
            "stars_amount": intent.stars_amount,
            "cherryx_amount": intent.cherryx_amount,
            "plan_code": "",
            "status": TelegramStarPayment.STATUS_CREDITED,
            "invoice_payload": intent.invoice_payload,
            "provider_payment_charge_id": intent.provider_payment_charge_id,
            "credited_at": timezone.now(),
        },
    )


def ensure_telegram_link_token(user) -> str:
    profile, _ = AccountProfile.objects.get_or_create(user=user)
    if not profile.telegram_link_token:
        profile.telegram_link_token = secrets.token_urlsafe(18)[:32]
        profile.telegram_link_token_created_at = timezone.now()
        profile.save(update_fields=["telegram_link_token", "telegram_link_token_created_at", "updated_at"])
    return profile.telegram_link_token


@transaction.atomic
def link_telegram_account_by_token(token: str, telegram_user_id: int, username: str = "", first_name: str = "") -> dict[str, object]:
    normalized = (token or "").strip()
    if not normalized:
        return {"ok": False, "reason": "empty_token"}
    profile = AccountProfile.objects.select_for_update().select_related("user").filter(telegram_link_token=normalized).first()
    if not profile:
        return {"ok": False, "reason": "not_found"}
    AccountProfile.objects.select_for_update().filter(telegram_user_id=int(telegram_user_id)).exclude(pk=profile.pk).update(
        telegram_user_id=None,
        telegram_username="",
        telegram_first_name="",
        updated_at=timezone.now(),
    )
    profile.telegram_user_id = int(telegram_user_id)
    profile.telegram_username = (username or "")[:80]
    profile.telegram_first_name = (first_name or "")[:120]
    profile.telegram_link_token = ""
    profile.telegram_link_token_created_at = None
    profile.save(update_fields=[
        "telegram_user_id",
        "telegram_username",
        "telegram_first_name",
        "telegram_link_token",
        "telegram_link_token_created_at",
        "updated_at",
    ])
    _credit_pending_telegram_payments(profile)
    _apply_pending_telegram_intents(profile)
    return {
        "ok": True,
        "user_id": profile.user_id,
        "email": profile.user.email,
        "balance": profile.cherryx_balance,
        "telegram_user_id": profile.telegram_user_id,
    }


@transaction.atomic
def record_telegram_stars_payment(
    *,
    telegram_user_id: int,
    stars_amount: int,
    invoice_payload: str,
    telegram_payment_charge_id: str,
    provider_payment_charge_id: str = "",
    currency: str = "XTR",
    telegram_username: str = "",
    telegram_first_name: str = "",
) -> dict[str, object]:
    existing = TelegramStarPayment.objects.select_related("user").filter(telegram_payment_charge_id=telegram_payment_charge_id).first()
    if existing:
        profile = AccountProfile.objects.filter(user=existing.user).first() if existing.user_id else None
        return _telegram_payment_result(existing, profile, duplicate=True)

    profile = AccountProfile.objects.select_for_update().select_related("user").filter(telegram_user_id=int(telegram_user_id)).first()
    plan_code = telegram_stars_plan_code()
    payment = TelegramStarPayment.objects.create(
        user=profile.user if profile else None,
        telegram_user_id=int(telegram_user_id),
        telegram_username=(telegram_username or "")[:80],
        telegram_first_name=(telegram_first_name or "")[:120],
        currency=currency or "XTR",
        stars_amount=max(0, int(stars_amount)),
        cherryx_amount=telegram_stars_to_cherryx(stars_amount),
        plan_code=plan_code,
        status=TelegramStarPayment.STATUS_PENDING_LINK,
        invoice_payload=(invoice_payload or "")[:160],
        telegram_payment_charge_id=telegram_payment_charge_id,
        provider_payment_charge_id=(provider_payment_charge_id or "")[:160],
    )
    if profile:
        _credit_telegram_payment(payment, profile)
    return _telegram_payment_result(payment, profile)


def telegram_wallet_for_user(telegram_user_id: int) -> dict[str, object]:
    profile = AccountProfile.objects.select_related("user").filter(telegram_user_id=int(telegram_user_id)).first()
    pending = TelegramStarPayment.objects.filter(telegram_user_id=int(telegram_user_id), status=TelegramStarPayment.STATUS_PENDING_LINK).order_by("-created_at")
    if not profile:
        return {
            "linked": False,
            "pending_stars": sum(item.stars_amount for item in pending),
            "pending_cherryx": sum(item.cherryx_amount for item in pending),
            "payments": pending.count(),
        }
    recent_payment = TelegramStarPayment.objects.filter(user=profile.user).order_by("-created_at").first()
    return {
        "linked": True,
        "user_id": profile.user_id,
        "email": profile.user.email,
        "balance": profile.cherryx_balance,
        "active_until": active_access_until(profile.user),
        "last_payment_stars": recent_payment.stars_amount if recent_payment else 0,
    }


def _credit_pending_telegram_payments(profile: AccountProfile) -> None:
    for payment in TelegramStarPayment.objects.select_for_update().filter(telegram_user_id=profile.telegram_user_id, status=TelegramStarPayment.STATUS_PENDING_LINK):
        payment.user = profile.user
        _credit_telegram_payment(payment, profile)


def _apply_pending_telegram_intents(profile: AccountProfile) -> None:
    for intent in TelegramPaymentIntent.objects.select_for_update().filter(
        telegram_user_id=profile.telegram_user_id,
        status__in=[TelegramPaymentIntent.STATUS_PAID, TelegramPaymentIntent.STATUS_NEEDS_EMAIL],
    ):
        _apply_telegram_intent_to_profile(intent, profile)


def _credit_telegram_payment(payment: TelegramStarPayment, profile: AccountProfile) -> None:
    if payment.status == TelegramStarPayment.STATUS_CREDITED:
        return
    profile.cherryx_balance = int(profile.cherryx_balance or 0) + int(payment.cherryx_amount or 0)
    profile.telegram_username = payment.telegram_username or profile.telegram_username
    profile.telegram_first_name = payment.telegram_first_name or profile.telegram_first_name
    profile.save(update_fields=["cherryx_balance", "telegram_username", "telegram_first_name", "updated_at"])
    access = activate_access(profile.user, get_plan(payment.plan_code or telegram_stars_plan_code()))
    payment.user = profile.user
    payment.status = TelegramStarPayment.STATUS_CREDITED
    payment.active_until = access.active_until
    payment.credited_at = timezone.now()
    payment.save(update_fields=["user", "status", "active_until", "credited_at"])


def _telegram_payment_result(payment: TelegramStarPayment, profile: AccountProfile | None, duplicate: bool = False) -> dict[str, object]:
    return {
        "ok": True,
        "duplicate": duplicate,
        "linked": bool(profile),
        "status": payment.status,
        "stars": payment.stars_amount,
        "cherryx": payment.cherryx_amount,
        "balance": profile.cherryx_balance if profile else 0,
        "active_until": payment.active_until,
        "email": profile.user.email if profile else "",
    }


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


def send_telegram_promotion(promotion: TelegramPromotion) -> dict[str, int]:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return {"sent": 0, "failed": TelegramBotUser.objects.count()}
    users = TelegramBotUser.objects.all()
    sent = 0
    failed = 0
    for user in users.iterator():
        ok = _send_promotion_to_user(token, promotion, user.telegram_user_id)
        if ok:
            sent += 1
        else:
            failed += 1
            TelegramBotUser.objects.filter(pk=user.pk).update(blocked_at=timezone.now())
    promotion.sent_count = sent
    promotion.failed_count = failed
    promotion.sent_at = timezone.now()
    promotion.status = TelegramPromotion.STATUS_SENT
    promotion.save(update_fields=["sent_count", "failed_count", "sent_at", "status", "updated_at"])
    return {"sent": sent, "failed": failed}


def _send_promotion_to_user(bot_token: str, promotion: TelegramPromotion, telegram_user_id: int) -> bool:
    reply_markup = None
    if promotion.button_text and promotion.button_url:
        reply_markup = {"inline_keyboard": [[{"text": promotion.button_text, "url": promotion.button_url}]]}
    try:
        with httpx.Client(timeout=20) as client:
            if promotion.image:
                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                data = {
                    "chat_id": str(telegram_user_id),
                    "caption": promotion.text[:1024],
                    "parse_mode": "HTML",
                }
                if reply_markup:
                    data["reply_markup"] = _json_dumps(reply_markup)
                with promotion.image.open("rb") as image_file:
                    response = client.post(url, data=data, files={"photo": (promotion.image.name, image_file)})
            else:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": telegram_user_id,
                    "text": promotion.text,
                    "parse_mode": "HTML",
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                response = client.post(url, json=payload)
        return bool(response.status_code == 200 and response.json().get("ok"))
    except Exception:
        return False


def _json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


__all__ = [
    "activate_access",
    "active_access_until",
    "ensure_telegram_link_token",
    "cherryx_to_telegram_stars",
    "claim_telegram_payment_intent",
    "create_account_for_paid_telegram_intent",
    "create_direct_telegram_intent",
    "create_direct_telegram_topup_by_stars",
    "create_telegram_payment_intent",
    "apply_telegram_intent_to_user",
    "get_plan",
    "link_telegram_account_by_token",
    "prorated_due_cents",
    "record_telegram_intent_payment",
    "record_telegram_stars_payment",
    "send_telegram_promotion",
    "simulate_telegram_intent_payment",
    "telegram_bot_deep_link",
    "telegram_payment_intent_payload",
    "telegram_plan_price",
    "telegram_star_rate_info",
    "telegram_star_usd_cents",
    "telegram_stars_rate",
    "telegram_stars_to_usd_cents_approx",
    "cherryx_to_usd_cents_approx",
    "cherryx_to_usd_display_approx",
    "telegram_topup_cherryx_from_stars",
    "sync_telegram_star_rate",
    "usd_cents_to_telegram_stars",
    "upsert_telegram_bot_user",
    "telegram_wallet_for_user",
    "transfer_guest_workspace",
    "user_has_active_access",
]
