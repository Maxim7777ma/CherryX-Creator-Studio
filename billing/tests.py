from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from unittest import mock

from .forms import CheckoutForm
from .admin import TelegramPromotionAdmin
from .models import CustomerAccess, TelegramPaymentIntent, TelegramPromotion
from .services import (
    cherryx_to_telegram_stars,
    create_account_for_paid_telegram_intent,
    create_direct_telegram_topup_by_stars,
    create_telegram_payment_intent,
    record_telegram_intent_payment,
    simulate_telegram_intent_payment,
    sync_telegram_star_rate,
    telegram_star_rate_info,
    telegram_plan_price,
    telegram_topup_cherryx_from_stars,
    usd_cents_to_telegram_stars,
    apply_telegram_intent_to_user,
)
from .plans import get_plan
from studio.models import AccountProfile, MagicLoginToken
from studio.admin import admin_analytics_view


class CheckoutValidationTests(TestCase):
    def test_checkout_form_rejects_weak_account_data(self):
        form = CheckoutForm(
            data={
                "plan": "starter",
                "name": "A",
                "email": "not-real@example",
                "password": "abcdefgh",
                "password_confirm": "abcdefghi",
                "next": "/app/",
            },
            language="en",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("email", form.errors)
        self.assertIn("password", form.errors)

    def test_checkout_form_rejects_password_mismatch(self):
        form = CheckoutForm(
            data={
                "plan": "starter",
                "name": "CherryX Digital",
                "email": "new@example.com",
                "password": "Strong123",
                "password_confirm": "Strong124",
                "next": "/app/",
            },
            language="en",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password_confirm", form.errors)

    def test_checkout_form_rejects_existing_email(self):
        get_user_model().objects.create_user(username="used@example.com", email="used@example.com", password="Strong123")
        form = CheckoutForm(
            data={
                "plan": "starter",
                "name": "CherryX Digital",
                "email": "used@example.com",
                "password": "Strong123",
                "password_confirm": "Strong123",
                "next": "/app/",
            },
            language="en",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_check_email_endpoint_reports_existing_email(self):
        get_user_model().objects.create_user(username="used@example.com", email="used@example.com", password="Strong123")

        response = self.client.get(reverse("billing:check_email"), {"email": "used@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["exists"])


class TelegramPaymentIntentTests(TestCase):
    def test_cherryx_to_stars_uses_configured_rate(self):
        with mock.patch.dict("os.environ", {"TELEGRAM_STARS_TO_CHERRYX": "10"}):
            self.assertEqual(cherryx_to_telegram_stars(1900), 190)
            self.assertEqual(cherryx_to_telegram_stars(1), 1)

    def test_plan_stars_use_telegram_usd_rate(self):
        with mock.patch.dict("os.environ", {"TELEGRAM_STAR_USD_CENTS": "1.3"}):
            self.assertEqual(usd_cents_to_telegram_stars(1900), 1462)
            price = telegram_plan_price(get_plan("pro"))

        self.assertEqual(price["stars_amount"], 1462)
        self.assertEqual(price["usd_display"], "19.01$")

    def test_sync_telegram_star_rate_parses_official_config(self):
        class Response:
            text = '{"stars_usd_withdraw_rate_x1000": 1300}'

            def raise_for_status(self):
                return None

        with mock.patch("billing.services._telegram_star_rate_cache_path") as mocked_path:
            mocked_path.return_value = self.settings_temp_path("telegram_star_rate.json")
            with mock.patch("httpx.Client") as mocked_client:
                mocked_client.return_value.__enter__.return_value.get.return_value = Response()
                result = sync_telegram_star_rate(force=True)

            info = telegram_star_rate_info(refresh=False)

        self.assertTrue(result["ok"])
        self.assertEqual(str(info["usd_cents_per_star"]), "1.3")

    def settings_temp_path(self, name: str):
        from pathlib import Path
        import tempfile

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name) / name

    def test_direct_topup_by_stars_uses_exact_stars_and_rate(self):
        with mock.patch.dict("os.environ", {"TELEGRAM_STARS_TO_CHERRYX": "10"}):
            self.assertEqual(telegram_topup_cherryx_from_stars(1), 10)
            intent_payload = create_direct_telegram_topup_by_stars(150000, telegram_user_id=999)

        self.assertEqual(intent_payload["kind"], "topup")
        self.assertEqual(intent_payload["stars_amount"], 150000)
        self.assertEqual(intent_payload["cherryx_amount"], 1500000)

    def test_direct_topup_by_stars_rejects_out_of_range(self):
        for stars_amount in (0, -1, 150001):
            with self.subTest(stars_amount=stars_amount):
                with self.assertRaises(ValueError):
                    create_direct_telegram_topup_by_stars(stars_amount, telegram_user_id=999)

    def test_telegram_intent_endpoint_creates_plan_link(self):
        response = self.client.post(reverse("billing:telegram_intent"), {"kind": "plan", "plan": "pro"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "plan")
        self.assertEqual(payload["cherryx_amount"], 1900)
        self.assertEqual(payload["stars_amount"], 1462)
        self.assertIn("https://t.me/", payload["link"])

    def test_telegram_intent_endpoint_accepts_prorated_plan_due(self):
        user = get_user_model().objects.create_user(username="due@example.com", email="due@example.com", password="Strong123")
        CustomerAccess.objects.create(
            user=user,
            plan_code="pro",
            active_until=timezone.now() + timedelta(days=15),
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("billing:telegram_intent"),
            {"kind": "plan", "plan": "studio", "cherryx_amount": "3950"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "plan")
        self.assertEqual(payload["plan_code"], "studio")
        self.assertEqual(payload["cherryx_amount"], 3950)
        self.assertEqual(payload["stars_amount"], usd_cents_to_telegram_stars(3950))

        invalid = self.client.post(
            reverse("billing:telegram_intent"),
            {"kind": "plan", "plan": "studio", "cherryx_amount": "4900"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"], "invalid_due")

    def test_intent_plan_payment_activates_linked_account(self):
        user = get_user_model().objects.create_user(username="linked@example.com", email="linked@example.com", password="Strong123")
        AccountProfile.objects.create(user=user, telegram_user_id=123)
        intent_payload = create_telegram_payment_intent(kind="plan", user=user, plan_code="starter")

        result = record_telegram_intent_payment(
            telegram_user_id=123,
            stars_amount=intent_payload["stars_amount"],
            invoice_payload=intent_payload["payload"],
            telegram_payment_charge_id="charge-plan-1",
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["needs_email"])
        self.assertEqual(user.billing_access.plan_code, "starter")
        self.assertEqual(TelegramPaymentIntent.objects.get(token=intent_payload["token"]).status, TelegramPaymentIntent.STATUS_APPLIED)

    def test_intent_topup_payment_adds_balance(self):
        user = get_user_model().objects.create_user(username="top@example.com", email="top@example.com", password="Strong123")
        profile = AccountProfile.objects.create(user=user, telegram_user_id=456, cherryx_balance=20)
        intent_payload = create_telegram_payment_intent(kind="topup", user=user, cherryx_amount=500)

        result = record_telegram_intent_payment(
            telegram_user_id=456,
            stars_amount=intent_payload["stars_amount"],
            invoice_payload=intent_payload["payload"],
            telegram_payment_charge_id="charge-topup-1",
        )

        profile.refresh_from_db()
        self.assertTrue(result["ok"])
        self.assertEqual(profile.cherryx_balance, 520)

    def test_direct_topup_by_stars_payment_adds_rate_balance(self):
        user = get_user_model().objects.create_user(username="stars@example.com", email="stars@example.com", password="Strong123")
        profile = AccountProfile.objects.create(user=user, telegram_user_id=654, cherryx_balance=5)
        with mock.patch.dict("os.environ", {"TELEGRAM_STARS_TO_CHERRYX": "10"}):
            intent_payload = create_direct_telegram_topup_by_stars(100, telegram_user_id=654)

        result = record_telegram_intent_payment(
            telegram_user_id=654,
            stars_amount=100,
            invoice_payload=intent_payload["payload"],
            telegram_payment_charge_id="charge-stars-topup-1",
        )

        profile.refresh_from_db()
        self.assertTrue(result["ok"])
        self.assertEqual(profile.cherryx_balance, 1005)

    def test_direct_payment_waits_for_email_and_creates_account(self):
        intent_payload = create_telegram_payment_intent(kind="topup", cherryx_amount=100, telegram_user_id=777)
        result = record_telegram_intent_payment(
            telegram_user_id=777,
            stars_amount=intent_payload["stars_amount"],
            invoice_payload=intent_payload["payload"],
            telegram_payment_charge_id="charge-direct-1",
            telegram_username="direct",
        )
        self.assertTrue(result["needs_email"])

        created = create_account_for_paid_telegram_intent(777, "direct@example.com", username="direct", first_name="Direct")

        self.assertTrue(created["ok"])
        self.assertIn("/accounts/magic/", created["magic_login_url"])
        self.assertEqual(MagicLoginToken.objects.filter(user__email="direct@example.com", used_at__isnull=True).count(), 1)
        user = get_user_model().objects.get(email="direct@example.com")
        self.assertEqual(user.studio_profile.telegram_user_id, 777)
        self.assertEqual(user.studio_profile.cherryx_balance, 100)

    def test_existing_email_is_not_auto_claimed(self):
        get_user_model().objects.create_user(username="used@example.com", email="used@example.com", password="Strong123")
        intent_payload = create_telegram_payment_intent(kind="topup", cherryx_amount=100, telegram_user_id=888)
        record_telegram_intent_payment(
            telegram_user_id=888,
            stars_amount=intent_payload["stars_amount"],
            invoice_payload=intent_payload["payload"],
            telegram_payment_charge_id="charge-direct-2",
        )

        result = create_account_for_paid_telegram_intent(888, "used@example.com")

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "email_exists")
        self.assertEqual(TelegramPaymentIntent.objects.get(token=intent_payload["token"]).status, TelegramPaymentIntent.STATUS_NEEDS_EMAIL)


class TelegramPromotionAdminTests(TestCase):
    def test_active_promotion_sends_on_save(self):
        admin = TelegramPromotionAdmin(TelegramPromotion, AdminSite())
        request = RequestFactory().post("/")
        promotion = TelegramPromotion(title="Sale", text="Hello", status=TelegramPromotion.STATUS_ACTIVE)

        with mock.patch("billing.admin.send_telegram_promotion") as mocked_send:
            admin.save_model(request, promotion, form=None, change=False)

        mocked_send.assert_called_once_with(promotion)


class TelegramAnalyticsTests(TestCase):
    def test_admin_analytics_context_includes_telegram_summary(self):
        user = get_user_model().objects.create_superuser(username="admin@example.com", email="admin@example.com", password="Strong123")
        intent_payload = create_direct_telegram_topup_by_stars(25, telegram_user_id=321)
        record_telegram_intent_payment(
            telegram_user_id=321,
            stars_amount=25,
            invoice_payload=intent_payload["payload"],
            telegram_payment_charge_id="charge-analytics-1",
        )
        request = RequestFactory().get("/admin/analytics/")
        request.user = user

        response = admin_analytics_view(request)
        context = response.context_data

        labels = {card["label"]: card for card in context["summary_cards"]}
        self.assertEqual(labels["Telegram Stars paid"]["value"], "25")
        self.assertEqual(labels["Needs email/link"]["value"], 1)
        self.assertEqual(len(context["recent_telegram_payments"]), 1)

    def test_apply_waiting_intent_to_existing_user(self):
        user = get_user_model().objects.create_user(username="manual@example.com", email="manual@example.com", password="Strong123")
        intent_payload = create_direct_telegram_topup_by_stars(10, telegram_user_id=4321)
        record_telegram_intent_payment(
            telegram_user_id=4321,
            stars_amount=10,
            invoice_payload=intent_payload["payload"],
            telegram_payment_charge_id="charge-manual-1",
        )
        intent = TelegramPaymentIntent.objects.get(token=intent_payload["token"])

        result = apply_telegram_intent_to_user(intent.pk, user.pk)

        self.assertTrue(result["ok"])
        profile = user.studio_profile
        self.assertEqual(profile.telegram_user_id, 4321)
        self.assertGreater(profile.cherryx_balance, 0)
        intent.refresh_from_db()
        self.assertEqual(intent.status, TelegramPaymentIntent.STATUS_APPLIED)

    def test_admin_simulated_intent_payment_uses_normal_apply_path(self):
        user = get_user_model().objects.create_user(username="simulate@example.com", email="simulate@example.com", password="Strong123")
        AccountProfile.objects.create(user=user, telegram_user_id=9876, cherryx_balance=1)
        intent_payload = create_direct_telegram_topup_by_stars(7, telegram_user_id=9876)
        intent = TelegramPaymentIntent.objects.get(token=intent_payload["token"])

        result = simulate_telegram_intent_payment(intent.pk)

        self.assertTrue(result["ok"])
        intent.refresh_from_db()
        user.studio_profile.refresh_from_db()
        self.assertEqual(intent.status, TelegramPaymentIntent.STATUS_APPLIED)
        self.assertEqual(intent.telegram_payment_charge_id, f"test:{intent.token}")
        self.assertGreater(user.studio_profile.cherryx_balance, 1)

    def test_telegram_finance_admin_page_renders(self):
        admin_user = get_user_model().objects.create_superuser(username="finance-admin@example.com", email="finance-admin@example.com", password="Strong123")
        self.client.force_login(admin_user)

        response = self.client.get("/admin/telegram-finance/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Telegram finance")
