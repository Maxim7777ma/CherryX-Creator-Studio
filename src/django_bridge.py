from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studio_site.settings")
    import django

    django.setup()


def link_telegram_account(token: str, telegram_user_id: int, username: str = "", first_name: str = "") -> dict[str, Any]:
    _setup_django()
    from billing.services import link_telegram_account_by_token

    return link_telegram_account_by_token(token, telegram_user_id, username, first_name)


def record_stars_payment(
    *,
    telegram_user_id: int,
    stars_amount: int,
    invoice_payload: str,
    telegram_payment_charge_id: str,
    provider_payment_charge_id: str = "",
    currency: str = "XTR",
    telegram_username: str = "",
    telegram_first_name: str = "",
) -> dict[str, Any]:
    _setup_django()
    from billing.services import record_telegram_stars_payment

    return record_telegram_stars_payment(
        telegram_user_id=telegram_user_id,
        stars_amount=stars_amount,
        invoice_payload=invoice_payload,
        telegram_payment_charge_id=telegram_payment_charge_id,
        provider_payment_charge_id=provider_payment_charge_id,
        currency=currency,
        telegram_username=telegram_username,
        telegram_first_name=telegram_first_name,
    )


def telegram_wallet(telegram_user_id: int) -> dict[str, Any]:
    _setup_django()
    from billing.services import telegram_wallet_for_user

    return telegram_wallet_for_user(telegram_user_id)


def upsert_bot_user(telegram_user_id: int, username: str = "", first_name: str = "", language: str = "") -> None:
    _setup_django()
    from billing.services import upsert_telegram_bot_user

    upsert_telegram_bot_user(telegram_user_id, username, first_name, language)


def claim_payment_intent(token: str, telegram_user_id: int, username: str = "", first_name: str = "", language: str = "") -> dict[str, Any]:
    _setup_django()
    from billing.services import claim_telegram_payment_intent

    return claim_telegram_payment_intent(token, telegram_user_id, username, first_name, language)


def get_payment_intent_by_payload(invoice_payload: str) -> dict[str, Any]:
    _setup_django()
    from billing.models import TelegramPaymentIntent
    from billing.services import telegram_payment_intent_payload

    token = (invoice_payload or "").split(":", 1)[1] if (invoice_payload or "").startswith("intent:") else ""
    intent = TelegramPaymentIntent.objects.filter(token=token).first()
    if not intent:
        return {"ok": False, "reason": "not_found"}
    return telegram_payment_intent_payload(intent)


def create_direct_payment_intent(kind: str, plan_code: str = "", cherryx_amount: int | None = None, telegram_user_id: int | None = None) -> dict[str, Any]:
    _setup_django()
    from billing.services import create_direct_telegram_intent

    return create_direct_telegram_intent(kind, plan_code=plan_code, cherryx_amount=cherryx_amount, telegram_user_id=telegram_user_id)


def create_direct_topup_by_stars(stars_amount: int, telegram_user_id: int | None = None) -> dict[str, Any]:
    _setup_django()
    from billing.services import create_direct_telegram_topup_by_stars

    return create_direct_telegram_topup_by_stars(stars_amount, telegram_user_id=telegram_user_id)


def record_intent_payment(
    *,
    telegram_user_id: int,
    stars_amount: int,
    invoice_payload: str,
    telegram_payment_charge_id: str,
    provider_payment_charge_id: str = "",
    currency: str = "XTR",
    telegram_username: str = "",
    telegram_first_name: str = "",
) -> dict[str, Any]:
    _setup_django()
    from billing.services import record_telegram_intent_payment

    return record_telegram_intent_payment(
        telegram_user_id=telegram_user_id,
        stars_amount=stars_amount,
        invoice_payload=invoice_payload,
        telegram_payment_charge_id=telegram_payment_charge_id,
        provider_payment_charge_id=provider_payment_charge_id,
        currency=currency,
        telegram_username=telegram_username,
        telegram_first_name=telegram_first_name,
    )


def create_account_for_paid_intent(telegram_user_id: int, email: str, username: str = "", first_name: str = "") -> dict[str, Any]:
    _setup_django()
    from billing.services import create_account_for_paid_telegram_intent

    return create_account_for_paid_telegram_intent(telegram_user_id, email, username, first_name)
