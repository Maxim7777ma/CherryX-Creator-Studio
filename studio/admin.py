from __future__ import annotations

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q, Sum
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, path, reverse
from django.utils import timezone

from billing.models import CheckoutRecord, CustomerAccess, TelegramPaymentIntent
from billing.plans import PLANS, get_plan

from .models import (
    AccountProfile,
    CommunityPurchase,
    CommunityWork,
    DesignerAsset,
    DesignerProject,
    JobEventRecord,
    JobOutputRecord,
    JobRecord,
    LearningArticle,
    MusicEditorAsset,
    MusicEditorProject,
    VideoEditorAsset,
    VideoEditorProject,
    WorkspaceShare,
)


def _money(cents: int | None, currency: str = "USD") -> str:
    value = int(cents or 0) / 100
    suffix = "$" if currency.upper() == "USD" else f" {currency.upper()}"
    return f"{value:,.2f}{suffix}".replace(",", " ")


def _number(value: int | None) -> str:
    return f"{int(value or 0):,}".replace(",", " ")


def _human_bytes(value: int | None) -> str:
    size = float(value or 0)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return "0 B"


def _safe_sum(queryset, field: str) -> int:
    return int(queryset.aggregate(total=Sum(field)).get("total") or 0)


def _admin_change_url(obj) -> str:
    try:
        meta = obj._meta
        return reverse(f"admin:{meta.app_label}_{meta.model_name}_change", args=[obj.pk])
    except NoReverseMatch:
        return ""


def _user_label(user) -> str:
    display = user.get_full_name() or user.email or user.username
    return display or f"User #{user.pk}"


def _user_search_queryset(query: str):
    User = get_user_model()
    normalized = (query or "").strip()
    queryset = User.objects.all().order_by("-date_joined")
    if not normalized:
        return queryset.none()
    filters = Q(username__icontains=normalized) | Q(email__icontains=normalized) | Q(first_name__icontains=normalized) | Q(last_name__icontains=normalized)
    if normalized.isdigit():
        filters |= Q(pk=int(normalized))
    return queryset.filter(filters)


def _selected_user(query: str):
    matches = _user_search_queryset(query)
    if not query:
        return None, []
    exact_filter = Q(username__iexact=query) | Q(email__iexact=query)
    if query.isdigit():
        exact_filter |= Q(pk=int(query))
    user = matches.filter(exact_filter).first() or matches.first()
    return user, list(matches[:8])


def _project_storage_for_user(user) -> dict[str, int]:
    video = _safe_sum(VideoEditorProject.objects.filter(owner=user), "storage_bytes")
    design = _safe_sum(DesignerProject.objects.filter(owner=user), "storage_bytes")
    music = _safe_sum(MusicEditorProject.objects.filter(owner=user), "storage_bytes")
    return {"video": video, "design": design, "music": music, "total": video + design + music}


def _user_payload(user):
    now = timezone.now()
    paid_qs = CheckoutRecord.objects.filter(user=user, status=CheckoutRecord.STATUS_PAID)
    pending_qs = CheckoutRecord.objects.filter(user=user, status=CheckoutRecord.STATUS_PENDING)
    jobs_qs = JobRecord.objects.filter(owner=user)
    outputs_qs = JobOutputRecord.objects.filter(job__owner=user)
    access = CustomerAccess.objects.filter(user=user).first()
    plan = get_plan(access.plan_code if access else "starter")
    project_storage = _project_storage_for_user(user)
    output_storage = _safe_sum(jobs_qs, "total_output_size") or _safe_sum(outputs_qs, "size")
    used_storage = output_storage + project_storage["total"]
    storage_limit = int(plan.storage_bytes or 0)
    storage_percent = 0 if storage_limit <= 0 else min(100, round(used_storage / storage_limit * 100))
    profile = AccountProfile.objects.filter(user=user).first()
    paid_total = _safe_sum(paid_qs, "amount_cents")
    status_counts = {row["status"]: row["count"] for row in jobs_qs.values("status").annotate(count=Count("id"))}

    recent_payments = [
        {
            "plan_code": payment.plan_code,
            "email": payment.email,
            "paid_at": payment.paid_at or payment.created_at,
            "amount": _money(payment.amount_cents, payment.currency),
            "admin_url": _admin_change_url(payment),
        }
        for payment in paid_qs.order_by("-paid_at", "-created_at")[:6]
    ]
    telegram_qs = TelegramPaymentIntent.objects.filter(user=user)
    recent_telegram_payments = [
        {
            "kind": intent.kind,
            "plan_code": intent.plan_code or "topup",
            "paid_at": intent.paid_at or intent.created_at,
            "stars": _number(intent.stars_amount),
            "cherryx": _number(intent.cherryx_amount),
            "status": intent.status,
            "admin_url": _admin_change_url(intent),
        }
        for intent in telegram_qs.order_by("-paid_at", "-created_at")[:6]
    ]

    return {
        "object": user,
        "label": _user_label(user),
        "admin_url": _admin_change_url(user),
        "email": user.email or "No email",
        "username": user.username,
        "joined": user.date_joined,
        "last_login": user.last_login,
        "is_staff": user.is_staff,
        "is_active": user.is_active,
        "profile": profile,
        "language": getattr(profile, "interface_language", "") or "not set",
        "theme": getattr(profile, "theme_mode", "") or "not set",
        "accent": getattr(profile, "accent_color", "") or "#2563eb",
        "cherryx_balance": int(getattr(profile, "cherryx_balance", 0) or 0),
        "paid_total": _money(paid_total),
        "paid_count": paid_qs.count(),
        "pending_count": pending_qs.count(),
        "last_payment": paid_qs.order_by("-paid_at", "-created_at").first(),
        "active_until": access.active_until if access else None,
        "access": access,
        "access_active": bool(access and access.active_until > now),
        "plan_name": plan.name,
        "plan_code": plan.code,
        "storage_used": _human_bytes(used_storage),
        "storage_limit": _human_bytes(storage_limit),
        "storage_percent": storage_percent,
        "output_storage": _human_bytes(output_storage),
        "project_storage": _human_bytes(project_storage["total"]),
        "project_storage_parts": [
            {"label": "Video", "value": _human_bytes(project_storage["video"])},
            {"label": "Design", "value": _human_bytes(project_storage["design"])},
            {"label": "Music", "value": _human_bytes(project_storage["music"])},
        ],
        "jobs_total": jobs_qs.count(),
        "jobs_completed": status_counts.get("completed", 0),
        "jobs_active": sum(status_counts.get(status, 0) for status in ("queued", "running", "processing")),
        "jobs_failed": sum(status_counts.get(status, 0) for status in ("failed", "error", "cancelled")),
        "outputs_total": outputs_qs.count(),
        "projects": {
            "video": VideoEditorProject.objects.filter(owner=user).count(),
            "design": DesignerProject.objects.filter(owner=user).count(),
            "music": MusicEditorProject.objects.filter(owner=user).count(),
        },
        "recent_jobs": list(jobs_qs.order_by("-created_at")[:6]),
        "recent_payments": recent_payments,
        "recent_telegram_payments": recent_telegram_payments,
    }


def admin_analytics_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Admin analytics is available only for superusers.")

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    User = get_user_model()

    paid_qs = CheckoutRecord.objects.filter(status=CheckoutRecord.STATUS_PAID)
    pending_qs = CheckoutRecord.objects.filter(status=CheckoutRecord.STATUS_PENDING)
    telegram_paid_qs = TelegramPaymentIntent.objects.filter(status__in=[TelegramPaymentIntent.STATUS_PAID, TelegramPaymentIntent.STATUS_NEEDS_EMAIL, TelegramPaymentIntent.STATUS_APPLIED])
    telegram_applied_qs = TelegramPaymentIntent.objects.filter(status=TelegramPaymentIntent.STATUS_APPLIED)
    telegram_needs_email_qs = TelegramPaymentIntent.objects.filter(status=TelegramPaymentIntent.STATUS_NEEDS_EMAIL)
    active_access_qs = CustomerAccess.objects.filter(active_until__gt=now)
    all_job_bytes = _safe_sum(JobRecord.objects.all(), "total_output_size")
    all_project_bytes = (
        _safe_sum(VideoEditorProject.objects.all(), "storage_bytes")
        + _safe_sum(DesignerProject.objects.all(), "storage_bytes")
        + _safe_sum(MusicEditorProject.objects.all(), "storage_bytes")
    )

    query = (request.GET.get("q") or "").strip()
    user, matches = _selected_user(query)
    selected = _user_payload(user) if user else None

    plan_names = {plan.code: plan.name for plan in PLANS}
    plan_breakdown = []
    for row in active_access_qs.values("plan_code").annotate(count=Count("id")).order_by("-count"):
        plan_breakdown.append({"code": row["plan_code"], "name": plan_names.get(row["plan_code"], row["plan_code"]), "count": row["count"]})

    revenue_by_plan = []
    for row in paid_qs.values("plan_code", "currency").annotate(total=Sum("amount_cents"), count=Count("id")).order_by("-total"):
        revenue_by_plan.append(
            {
                "code": row["plan_code"],
                "name": plan_names.get(row["plan_code"], row["plan_code"]),
                "count": row["count"],
                "total": _money(row["total"], row["currency"] or "USD"),
            }
        )

    status_breakdown = list(JobRecord.objects.values("status").annotate(count=Count("id")).order_by("-count")[:8])
    top_customers = [
        {
            "email": row["email"],
            "user_id": row["user_id"],
            "payments": row["payments"],
            "total": _money(row["total"], row["currency"] or "USD"),
            "last_paid": row["last_paid"],
        }
        for row in paid_qs.values("email", "user_id", "currency").annotate(total=Sum("amount_cents"), payments=Count("id"), last_paid=Max("paid_at")).order_by("-total")[:8]
    ]

    recent_payments = [
        {
            "email": payment.email,
            "plan_code": payment.plan_code,
            "paid_at": payment.paid_at or payment.created_at,
            "amount": _money(payment.amount_cents, payment.currency),
            "admin_url": _admin_change_url(payment),
        }
        for payment in paid_qs.select_related("user").order_by("-paid_at", "-created_at")[:8]
    ]
    recent_telegram_payments = [
        {
            "user": intent.user.email if intent.user_id and intent.user.email else (intent.user.username if intent.user_id else f"TG {intent.telegram_user_id or '-'}"),
            "kind": intent.kind,
            "plan_code": intent.plan_code or "topup",
            "paid_at": intent.paid_at or intent.created_at,
            "stars": _number(intent.stars_amount),
            "cherryx": _number(intent.cherryx_amount),
            "status": intent.status,
            "admin_url": _admin_change_url(intent),
        }
        for intent in telegram_paid_qs.select_related("user").order_by("-paid_at", "-created_at")[:8]
    ]

    context = {
        **admin.site.each_context(request),
        "title": "CherryX analytics",
        "query": query,
        "selected": selected,
        "matches": [{"label": _user_label(item), "email": item.email, "url": f"?q={item.pk}"} for item in matches],
        "summary_cards": [
            {"label": "Аккаунты", "value": User.objects.count(), "hint": f"+{User.objects.filter(date_joined__gte=week_ago).count()} за 7 дней"},
            {"label": "Активный доступ", "value": active_access_qs.count(), "hint": "пользователей с действующим планом"},
            {"label": "Оплаты", "value": paid_qs.count(), "hint": f"{_money(_safe_sum(paid_qs, 'amount_cents'))} оплачено всего"},
            {"label": "30 дней", "value": _money(_safe_sum(paid_qs.filter(paid_at__gte=month_ago), "amount_cents")), "hint": f"{paid_qs.filter(paid_at__gte=month_ago).count()} платежей"},
            {"label": "Ожидают", "value": pending_qs.count(), "hint": f"{_money(_safe_sum(pending_qs, 'amount_cents'))} pending"},
            {"label": "Хранилище", "value": _human_bytes(all_job_bytes + all_project_bytes), "hint": "результаты задач и проекты"},
            {"label": "Telegram Stars paid", "value": _number(_safe_sum(telegram_paid_qs, "stars_amount")), "hint": f"{telegram_paid_qs.count()} paid Telegram intents"},
            {"label": "CherryX credited", "value": _number(_safe_sum(telegram_applied_qs.filter(kind=TelegramPaymentIntent.KIND_TOPUP), "cherryx_amount")), "hint": "applied Telegram topups"},
            {"label": "Telegram payments", "value": telegram_applied_qs.count(), "hint": "applied Telegram intents"},
            {"label": "Needs email/link", "value": telegram_needs_email_qs.count(), "hint": "paid but not linked yet"},
        ],
        "operations": [
            {"label": "Все задачи", "value": JobRecord.objects.count()},
            {"label": "Completed", "value": JobRecord.objects.filter(status="completed").count()},
            {"label": "Outputs", "value": JobOutputRecord.objects.count()},
            {"label": "Video projects", "value": VideoEditorProject.objects.count()},
            {"label": "Design projects", "value": DesignerProject.objects.count()},
            {"label": "Music projects", "value": MusicEditorProject.objects.count()},
        ],
        "plan_breakdown": plan_breakdown,
        "revenue_by_plan": revenue_by_plan,
        "status_breakdown": status_breakdown,
        "top_customers": top_customers,
        "recent_users": User.objects.order_by("-date_joined")[:8],
        "recent_payments": recent_payments,
        "recent_telegram_payments": recent_telegram_payments,
        "recent_jobs": JobRecord.objects.select_related("owner").order_by("-created_at")[:8],
    }
    return TemplateResponse(request, "admin/studio_analytics.html", context)


if not getattr(admin.site, "_studio_analytics_installed", False):
    _default_get_urls = admin.site.get_urls

    def _studio_get_urls():
        return [
            path("analytics/", admin.site.admin_view(admin_analytics_view), name="studio_admin_analytics"),
        ] + _default_get_urls()

    admin.site.get_urls = _studio_get_urls
    admin.site._studio_analytics_installed = True
    admin.site.site_header = "CherryX Creator Studio"
    admin.site.site_title = "CherryX admin"
    admin.site.index_title = "Workspace control center"


@admin.register(JobRecord)
class JobRecordAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "status", "progress", "owner", "output_count", "total_output_size_display", "created_at")
    list_filter = ("status", "kind", "created_at")
    search_fields = ("job_id", "title", "owner__username", "owner__email", "guest_key")
    readonly_fields = ("job_id", "created_at", "updated_at")
    date_hierarchy = "created_at"

    @admin.display(description="Output size")
    def total_output_size_display(self, obj: JobRecord) -> str:
        return _human_bytes(obj.total_output_size)


@admin.register(JobOutputRecord)
class JobOutputRecordAdmin(admin.ModelAdmin):
    list_display = ("label", "job", "media_type", "size_display", "created_at")
    list_filter = ("media_type", "created_at")
    search_fields = ("label", "path", "job__job_id", "job__title")
    list_select_related = ("job",)

    @admin.display(description="Size")
    def size_display(self, obj: JobOutputRecord) -> str:
        return _human_bytes(obj.size)


@admin.register(JobEventRecord)
class JobEventRecordAdmin(admin.ModelAdmin):
    list_display = ("job", "status", "progress", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("job__job_id", "message")
    list_select_related = ("job",)


@admin.register(AccountProfile)
class AccountProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "interface_language", "theme_mode", "accent_color", "updated_at")
    list_filter = ("interface_language", "theme_mode")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)


@admin.register(LearningArticle)
class LearningArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "featured", "published_at", "updated_at")
    list_filter = ("status", "featured", "published_at", "created_at")
    search_fields = ("title", "excerpt", "body", "seo_title", "seo_description")
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        ("Content", {"fields": ("title", "slug", "excerpt", "body", "cover_image")}),
        ("SEO", {"fields": ("seo_title", "seo_description")}),
        ("Publishing", {"fields": ("status", "featured", "published_at")}),
    )


@admin.register(CommunityWork)
class CommunityWorkAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "owner", "access", "price_cherryx", "status", "featured", "published_at")
    list_filter = ("kind", "access", "status", "featured", "published_at", "created_at")
    search_fields = ("title", "excerpt", "body", "owner__username", "owner__email")
    autocomplete_fields = ("owner", "source_job", "source_video_project", "source_design_project")
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        ("Publication", {"fields": ("owner", "title", "slug", "kind", "excerpt", "body")}),
        ("Media", {"fields": ("media_file", "cover_image")}),
        ("Source", {"fields": ("source_job", "source_video_project", "source_design_project")}),
        ("CherryX access", {"fields": ("access", "price_cherryx")}),
        ("Status", {"fields": ("status", "featured", "published_at")}),
        ("Stats", {"fields": ("download_count", "purchase_count")}),
    )
    readonly_fields = ("download_count", "purchase_count")


@admin.register(CommunityPurchase)
class CommunityPurchaseAdmin(admin.ModelAdmin):
    list_display = ("work", "buyer", "seller", "price_cherryx", "created_at")
    list_filter = ("created_at",)
    search_fields = ("work__title", "buyer__username", "buyer__email", "seller__username", "seller__email")
    autocomplete_fields = ("work", "buyer", "seller")


@admin.register(VideoEditorProject)
class VideoEditorProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "asset_count", "clip_count", "storage_display", "last_export_status", "updated_at")
    list_filter = ("last_export_status", "created_at", "updated_at")
    search_fields = ("title", "owner__username", "owner__email", "guest_key")

    @admin.display(description="Storage")
    def storage_display(self, obj: VideoEditorProject) -> str:
        return _human_bytes(obj.storage_bytes)


@admin.register(DesignerProject)
class DesignerProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "asset_count", "object_count", "storage_display", "last_export_status", "updated_at")
    list_filter = ("last_export_status", "created_at", "updated_at")
    search_fields = ("title", "owner__username", "owner__email", "guest_key")

    @admin.display(description="Storage")
    def storage_display(self, obj: DesignerProject) -> str:
        return _human_bytes(obj.storage_bytes)


@admin.register(MusicEditorProject)
class MusicEditorProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "asset_count", "clip_count", "storage_display", "last_export_status", "updated_at")
    list_filter = ("last_export_status", "created_at", "updated_at")
    search_fields = ("title", "owner__username", "owner__email", "guest_key")

    @admin.display(description="Storage")
    def storage_display(self, obj: MusicEditorProject) -> str:
        return _human_bytes(obj.storage_bytes)


@admin.register(VideoEditorAsset)
class VideoEditorAssetAdmin(admin.ModelAdmin):
    list_display = ("original_name", "project", "kind", "media_type", "size_display", "created_at")
    list_filter = ("kind", "media_type", "created_at")
    search_fields = ("original_name", "file_path", "project__title")

    @admin.display(description="Size")
    def size_display(self, obj: VideoEditorAsset) -> str:
        return _human_bytes(obj.size)


@admin.register(DesignerAsset)
class DesignerAssetAdmin(admin.ModelAdmin):
    list_display = ("original_name", "project", "kind", "media_type", "size_display", "created_at")
    list_filter = ("kind", "media_type", "created_at")
    search_fields = ("original_name", "file_path", "project__title")

    @admin.display(description="Size")
    def size_display(self, obj: DesignerAsset) -> str:
        return _human_bytes(obj.size)


@admin.register(MusicEditorAsset)
class MusicEditorAssetAdmin(admin.ModelAdmin):
    list_display = ("original_name", "project", "kind", "media_type", "size_display", "created_at")
    list_filter = ("kind", "media_type", "created_at")
    search_fields = ("original_name", "file_path", "project__title")

    @admin.display(description="Size")
    def size_display(self, obj: MusicEditorAsset) -> str:
        return _human_bytes(obj.size)


@admin.register(WorkspaceShare)
class WorkspaceShareAdmin(admin.ModelAdmin):
    list_display = ("email", "resource_type", "resource_id", "role", "status", "owner", "invited_user", "expires_at")
    list_filter = ("resource_type", "role", "status", "created_at")
    search_fields = ("email", "token", "owner__username", "owner__email", "invited_user__username", "invited_user__email")
    autocomplete_fields = ("owner", "invited_user")
