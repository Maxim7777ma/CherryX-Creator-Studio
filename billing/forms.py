from __future__ import annotations

from django import forms
from django.contrib.auth.models import User

from studio.localization import clean_language, translate

from .plans import DEFAULT_PLAN_CODE, PLANS, get_plan


class CheckoutForm(forms.Form):
    plan = forms.ChoiceField(label="Plan", choices=[(plan.code, plan.name) for plan in PLANS], initial=DEFAULT_PLAN_CODE)
    name = forms.CharField(label="Name", max_length=120, required=False)
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

        required_fields = ("name", "email", "password", "password_confirm")
        for field in required_fields:
            if not cleaned.get(field):
                self.add_error(field, translate("required_field", self.language))

        email = (cleaned.get("email") or "").strip().lower()
        if email and (User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists()):
            self.add_error("email", translate("email_exists_checkout", self.language))
        if cleaned.get("password") and cleaned.get("password_confirm") and cleaned["password"] != cleaned["password_confirm"]:
            self.add_error("password_confirm", translate("passwords_mismatch", self.language))
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
