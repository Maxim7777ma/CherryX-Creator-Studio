from __future__ import annotations

from django.core.management.base import BaseCommand

from billing.services import sync_telegram_star_rate, telegram_star_rate_info


class Command(BaseCommand):
    help = "Refresh Telegram Stars USD rate cache from Telegram client configuration docs."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--force", action="store_true", help="Refresh even if the cached rate is still fresh.")

    def handle(self, *args, **options) -> None:
        result = sync_telegram_star_rate(force=bool(options["force"]))
        info = telegram_star_rate_info(refresh=False)
        status = "updated" if result.get("ok") else "failed"
        message = (
            f"Telegram Star rate {status}: {info['usd_cents_per_star']} USD cents/star "
            f"source={info['source']} updated_at={info.get('updated_at') or 'fallback'}"
        )
        if result.get("ok"):
            self.stdout.write(self.style.SUCCESS(message))
        else:
            self.stderr.write(self.style.WARNING(f"{message} error={result.get('error') or 'unknown'}"))
