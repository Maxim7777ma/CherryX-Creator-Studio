from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessPlan:
    code: str
    name: str
    badge: str
    price_cents: int
    currency: str
    period_days: int
    headline: str
    description: str
    features: tuple[str, ...]
    storage_bytes: int

    @property
    def price_display(self) -> str:
        whole = self.price_cents // 100
        return f"${whole}"

    @property
    def price_label(self) -> str:
        return f"{self.price_display} / {self.period_days} дней"


PLANS: tuple[AccessPlan, ...] = (
    AccessPlan(
        code="starter",
        name="Starter",
        badge="Для теста",
        price_cents=900,
        currency="USD",
        period_days=7,
        headline="Забрать результат и проверить поток",
        description="Недельный доступ для быстрых задач, презентации клиенту или разовой публикации.",
        features=(
            "Скачивание готовых файлов",
            "История задач в аккаунте",
            "Повтор запусков без заполнения форм",
            "Preview до оплаты",
        ),
        storage_bytes=2 * 1024 * 1024 * 1024,
    ),
    AccessPlan(
        code="pro",
        name="Creator Pro",
        badge="Лучший выбор",
        price_cents=1900,
        currency="USD",
        period_days=30,
        headline="Месяц контент-производства без ручной рутины",
        description="Оптимальный план для регулярных Shorts, обложек, субтитров и ZIP-пакетов.",
        features=(
            "30 дней доступа к скачиванию",
            "Личный кабинет и все документы",
            "Пакеты публикаций и PDF-резюме",
            "Приоритетная логика для повторных задач",
        ),
        storage_bytes=20 * 1024 * 1024 * 1024,
    ),
    AccessPlan(
        code="studio",
        name="Studio",
        badge="Для команды",
        price_cents=4900,
        currency="USD",
        period_days=90,
        headline="Доступ для длинных запусков и клиентских проектов",
        description="Три месяца для команды, агентства или проекта, где контент выходит постоянно.",
        features=(
            "90 дней активного доступа",
            "Архивы результатов и быстрые повторы",
            "Подходит для клиентских потоков CherryX",
            "Готово к подключению Stripe/LiqPay",
        ),
        storage_bytes=100 * 1024 * 1024 * 1024,
    ),
)

DEFAULT_PLAN_CODE = "pro"


def get_plan(code: str | None) -> AccessPlan:
    normalized = (code or DEFAULT_PLAN_CODE).strip().lower()
    for plan in PLANS:
        if plan.code == normalized:
            return plan
    return PLANS[1]
