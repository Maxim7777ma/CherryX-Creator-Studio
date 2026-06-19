from __future__ import annotations

import math
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from billing.services import telegram_stars_rate

from .models import AccountProfile, CherryXTransfer, CherryXWalletTransaction, CherryXWithdrawalRequest


class WalletError(ValueError):
    def __init__(self, reason: str, message: str):
        self.reason = reason
        super().__init__(message)


def _positive_amount(value: int | str, field: str = "amount") -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError) as exc:
        raise WalletError("invalid_amount", f"Invalid {field}.") from exc
    if amount <= 0:
        raise WalletError("invalid_amount", f"{field.title()} must be greater than zero.")
    return amount


def _locked_profile(user) -> AccountProfile:
    profile = AccountProfile.objects.select_for_update().filter(user=user).first()
    if profile:
        return profile
    return AccountProfile.objects.create(user=user)


def _wallet_entry(
    *,
    user,
    entry_type: str,
    amount: int,
    balance_after: int,
    status: str = CherryXWalletTransaction.STATUS_COMPLETED,
    related_user=None,
    metadata: dict[str, Any] | None = None,
) -> CherryXWalletTransaction:
    return CherryXWalletTransaction.objects.create(
        user=user,
        type=entry_type,
        amount=int(amount),
        balance_after=max(0, int(balance_after)),
        status=status,
        related_user=related_user,
        metadata=metadata or {},
    )


def estimated_stars_from_cherryx(cherryx_amount: int) -> int:
    rate = max(1, int(telegram_stars_rate() or 1))
    return max(1, math.ceil(int(cherryx_amount or 0) / rate))


@transaction.atomic
def transfer_cherryx_by_email(sender, email: str, amount: int | str) -> dict[str, object]:
    if not sender or not getattr(sender, "is_authenticated", False):
        raise WalletError("login_required", "Login required.")
    amount_int = _positive_amount(amount, "amount")
    recipient_email = (email or "").strip().lower()
    if not recipient_email:
        raise WalletError("recipient_required", "Recipient email is required.")

    User = get_user_model()
    recipient = User.objects.filter(email__iexact=recipient_email).first()
    if not recipient:
        raise WalletError("recipient_not_found", "Recipient account was not found.")
    if recipient.pk == sender.pk:
        raise WalletError("self_transfer", "You cannot transfer CherryX to your own account.")

    sender_profile = _locked_profile(sender)
    recipient_profile = _locked_profile(recipient)
    if int(sender_profile.cherryx_balance or 0) < amount_int:
        raise WalletError("insufficient_balance", "Not enough CherryX.")

    sender_profile.cherryx_balance = int(sender_profile.cherryx_balance or 0) - amount_int
    sender_profile.save(update_fields=["cherryx_balance", "updated_at"])
    recipient_profile.cherryx_balance = int(recipient_profile.cherryx_balance or 0) + amount_int
    recipient_profile.save(update_fields=["cherryx_balance", "updated_at"])

    transfer = CherryXTransfer.objects.create(
        sender=sender,
        recipient=recipient,
        recipient_email=recipient.email or recipient_email,
        amount=amount_int,
    )
    metadata = {"transfer_id": transfer.id, "recipient_email": recipient.email or recipient_email}
    sender_entry = _wallet_entry(
        user=sender,
        entry_type=CherryXWalletTransaction.TYPE_TRANSFER_OUT,
        amount=-amount_int,
        balance_after=sender_profile.cherryx_balance,
        related_user=recipient,
        metadata=metadata,
    )
    _wallet_entry(
        user=recipient,
        entry_type=CherryXWalletTransaction.TYPE_TRANSFER_IN,
        amount=amount_int,
        balance_after=recipient_profile.cherryx_balance,
        related_user=sender,
        metadata={"transfer_id": transfer.id, "sender_email": sender.email or sender.username},
    )
    return {
        "ok": True,
        "transfer": transfer,
        "transaction": sender_entry,
        "balance": sender_profile.cherryx_balance,
        "recipient_email": recipient.email or recipient_email,
        "amount": amount_int,
    }


@transaction.atomic
def create_cherryx_withdrawal_request(user, amount: int | str) -> dict[str, object]:
    if not user or not getattr(user, "is_authenticated", False):
        raise WalletError("login_required", "Login required.")
    amount_int = _positive_amount(amount, "amount")
    profile = _locked_profile(user)
    if not profile.telegram_user_id:
        raise WalletError("telegram_required", "Link Telegram before creating a withdrawal request.")
    if int(profile.cherryx_balance or 0) < amount_int:
        raise WalletError("insufficient_balance", "Not enough CherryX.")

    profile.cherryx_balance = int(profile.cherryx_balance or 0) - amount_int
    profile.save(update_fields=["cherryx_balance", "updated_at"])
    withdrawal = CherryXWithdrawalRequest.objects.create(
        user=user,
        telegram_user_id=int(profile.telegram_user_id),
        amount_cherryx=amount_int,
        estimated_stars=estimated_stars_from_cherryx(amount_int),
    )
    entry = _wallet_entry(
        user=user,
        entry_type=CherryXWalletTransaction.TYPE_WITHDRAWAL_HOLD,
        amount=-amount_int,
        balance_after=profile.cherryx_balance,
        status=CherryXWalletTransaction.STATUS_PENDING,
        metadata={"withdrawal_id": withdrawal.id, "telegram_user_id": withdrawal.telegram_user_id},
    )
    return {
        "ok": True,
        "withdrawal": withdrawal,
        "transaction": entry,
        "balance": profile.cherryx_balance,
        "amount": amount_int,
        "estimated_stars": withdrawal.estimated_stars,
    }


@transaction.atomic
def mark_withdrawal_paid(withdrawal: CherryXWithdrawalRequest, actual_paid_stars: int | None = None, admin_notes: str = "") -> CherryXWithdrawalRequest:
    withdrawal = CherryXWithdrawalRequest.objects.select_for_update().select_related("user").get(pk=withdrawal.pk)
    if withdrawal.status != CherryXWithdrawalRequest.STATUS_PENDING:
        raise WalletError("not_pending", "Only pending withdrawal requests can be marked paid.")
    paid_stars = int(actual_paid_stars or withdrawal.actual_paid_stars or withdrawal.estimated_stars or 0)
    if paid_stars <= 0:
        raise WalletError("invalid_stars", "Actual paid Stars must be greater than zero.")
    withdrawal.status = CherryXWithdrawalRequest.STATUS_PAID
    withdrawal.actual_paid_stars = paid_stars
    withdrawal.admin_notes = admin_notes or withdrawal.admin_notes
    withdrawal.paid_at = timezone.now()
    withdrawal.save(update_fields=["status", "actual_paid_stars", "admin_notes", "paid_at", "updated_at"])
    profile = AccountProfile.objects.filter(user=withdrawal.user).first()
    _wallet_entry(
        user=withdrawal.user,
        entry_type=CherryXWalletTransaction.TYPE_WITHDRAWAL_PAID,
        amount=0,
        balance_after=int(getattr(profile, "cherryx_balance", 0) or 0),
        status=CherryXWalletTransaction.STATUS_COMPLETED,
        metadata={"withdrawal_id": withdrawal.id, "actual_paid_stars": paid_stars},
    )
    CherryXWalletTransaction.objects.filter(
        user=withdrawal.user,
        type=CherryXWalletTransaction.TYPE_WITHDRAWAL_HOLD,
        metadata__withdrawal_id=withdrawal.id,
    ).update(status=CherryXWalletTransaction.STATUS_COMPLETED)
    return withdrawal


@transaction.atomic
def reject_withdrawal_and_refund(withdrawal: CherryXWithdrawalRequest, admin_notes: str = "") -> CherryXWithdrawalRequest:
    withdrawal = CherryXWithdrawalRequest.objects.select_for_update().select_related("user").get(pk=withdrawal.pk)
    if withdrawal.status != CherryXWithdrawalRequest.STATUS_PENDING:
        raise WalletError("not_pending", "Only pending withdrawal requests can be rejected.")
    profile = _locked_profile(withdrawal.user)
    profile.cherryx_balance = int(profile.cherryx_balance or 0) + int(withdrawal.amount_cherryx or 0)
    profile.save(update_fields=["cherryx_balance", "updated_at"])
    withdrawal.status = CherryXWithdrawalRequest.STATUS_REJECTED
    withdrawal.admin_notes = admin_notes or withdrawal.admin_notes
    withdrawal.rejected_at = timezone.now()
    withdrawal.save(update_fields=["status", "admin_notes", "rejected_at", "updated_at"])
    _wallet_entry(
        user=withdrawal.user,
        entry_type=CherryXWalletTransaction.TYPE_WITHDRAWAL_REFUND,
        amount=withdrawal.amount_cherryx,
        balance_after=profile.cherryx_balance,
        status=CherryXWalletTransaction.STATUS_COMPLETED,
        metadata={"withdrawal_id": withdrawal.id},
    )
    CherryXWalletTransaction.objects.filter(
        user=withdrawal.user,
        type=CherryXWalletTransaction.TYPE_WITHDRAWAL_HOLD,
        metadata__withdrawal_id=withdrawal.id,
    ).update(status=CherryXWalletTransaction.STATUS_REVERSED)
    return withdrawal


def recent_wallet_transactions(user, limit: int = 8):
    if not user or not getattr(user, "is_authenticated", False):
        return []
    return list(
        CherryXWalletTransaction.objects.select_related("related_user")
        .filter(user=user)
        .order_by("-created_at", "-id")[: max(1, int(limit))]
    )
