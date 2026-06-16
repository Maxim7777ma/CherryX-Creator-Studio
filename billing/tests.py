from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import CheckoutForm


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
