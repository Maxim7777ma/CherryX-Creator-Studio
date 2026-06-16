from __future__ import annotations

import re

from django import forms
from django.contrib.auth.models import User

from studio.localization import clean_language, translate

from .plans import DEFAULT_PLAN_CODE, PLANS, get_plan


class CheckoutForm(forms.Form):
    plan = forms.ChoiceField(label="Plan", choices=[(plan.code, plan.name) for plan in PLANS], initial=DEFAULT_PLAN_CODE)
    name = forms.CharField(label="Name", min_length=2, max_length=90, required=False)
    email = forms.EmailField(label="Email", required=False)
    password = forms.CharField(label="Password", min_length=8, required=False, widget=forms.PasswordInput)
    password_confirm = forms.CharField(label="Repeat password", min_length=8, required=False, widget=forms.PasswordInput)
    next = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, user=None, language=None, **kwargs):
        self.user = user
        self.language = clean_language(language)
        super().__init__(*args, **kwargs)
        self.fields["plan"].label = translate("pricing", self.language)
        self.fields["name"].label = translate("name", self.language)
        self.fields["email"].label = translate("email", self.language)
        self.fields["password"].label = translate("password", self.language)
        self.fields["password_confirm"].label = translate("password_confirm", self.language)
        if "name" in self.fields:
            self.fields["name"].widget.attrs.update({"minlength": "2", "maxlength": "90", "autocomplete": "name"})
        if "email" in self.fields:
            self.fields["email"].widget.attrs.update({"autocomplete": "email", "inputmode": "email"})
        if "password" in self.fields:
            self.fields["password"].widget.attrs.update({"minlength": "8", "autocomplete": "new-password"})
        if "password_confirm" in self.fields:
            self.fields["password_confirm"].widget.attrs.update({"minlength": "8", "autocomplete": "new-password"})
        if user and user.is_authenticated:
            del self.fields["name"]
            del self.fields["email"]
            del self.fields["password"]
            del self.fields["password_confirm"]

    def clean_plan(self) -> str:
        return get_plan(self.cleaned_data["plan"]).code

    def clean(self) -> dict:
        cleaned = super().clean()
        if self.user and self.user.is_authenticated:
            return cleaned

        required_messages = {
            "name": "checkout_name_required",
            "email": "checkout_email_required",
            "password": "checkout_password_required",
            "password_confirm": "checkout_password_confirm_required",
        }
        for field, message_key in required_messages.items():
            if field not in self.errors and not cleaned.get(field):
                self.add_error(field, translate(message_key, self.language))

        name = " ".join(str(cleaned.get("name") or "").split())
        if name and not 2 <= len(name) <= 90:
            self.add_error("name", translate("checkout_name_length", self.language))

        email = (cleaned.get("email") or "").strip().lower()
        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", email):
            self.add_error("email", translate("checkout_email_invalid", self.language))
        if email and (User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists()):
            self.add_error("email", translate("email_exists_checkout", self.language))

        password = str(cleaned.get("password") or "")
        password_has_letter = bool(re.search(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]", password))
        password_has_digit = bool(re.search(r"\d", password))
        if password and (len(password) < 8 or not password_has_letter or not password_has_digit):
            self.add_error("password", translate("checkout_password_weak", self.language))
        password = ""
        if password and (len(password) < 8 or not re.search(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]", password) or not re.search(r"\d", password)):
            self.add_error("password", translate("checkout_password_weak", self.language))
        if cleaned.get("password") and cleaned.get("password_confirm") and cleaned["password"] != cleaned["password_confirm"]:
            self.add_error("password_confirm", translate("passwords_mismatch", self.language))
        cleaned["name"] = name
        cleaned["email"] = email
        return cleaned

    def create_user(self) -> User:
        if self.user and self.user.is_authenticated:
            return self.user
        name = " ".join(self.cleaned_data["name"].split())
        email = self.cleaned_data["email"]
        return User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data["password"],
            first_name=name[:150],
        )
