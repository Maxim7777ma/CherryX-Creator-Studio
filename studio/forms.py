from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import User

from .localization import LANGUAGE_OPTIONS, clean_language, translate
from .models import CommunityWork


ACCENT_CHOICES = (
    ("#2563eb", "Blue"),
    ("#0f4db8", "Royal"),
    ("#0284c7", "Sky"),
    ("#0891b2", "Cyan"),
    ("#4f46e5", "Indigo"),
    ("#7c3aed", "Violet"),
    ("#c026d3", "Fuchsia"),
    ("#e11d48", "Rose"),
    ("#ea580c", "Orange"),
    ("#ca8a04", "Gold"),
    ("#16a34a", "Emerald"),
    ("#111827", "Black"),
)

LANGUAGE_CHOICES = tuple((item["code"], item["native"]) for item in LANGUAGE_OPTIONS)


class RegisterForm(forms.Form):
    name = forms.CharField(label="Name", max_length=120)
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Password", min_length=8, widget=forms.PasswordInput)
    password_confirm = forms.CharField(label="Repeat password", min_length=8, widget=forms.PasswordInput)

    def __init__(self, *args, language=None, **kwargs):
        self.language = clean_language(language)
        super().__init__(*args, **kwargs)
        self.fields["name"].label = translate("name", self.language)
        self.fields["email"].label = translate("email", self.language)
        self.fields["password"].label = translate("password", self.language)
        self.fields["password_confirm"].label = translate("password_confirm", self.language)

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
            raise forms.ValidationError(translate("email_exists", self.language))
        return email

    def clean(self) -> dict:
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password_confirm") and cleaned["password"] != cleaned["password_confirm"]:
            raise forms.ValidationError(translate("passwords_mismatch", self.language))
        return cleaned

    def save(self) -> User:
        name = " ".join(self.cleaned_data["name"].split())
        email = self.cleaned_data["email"]
        return User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data["password"],
            first_name=name[:150],
        )


class EmailLoginForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Password", widget=forms.PasswordInput)

    def __init__(self, *args, language=None, **kwargs):
        self.language = clean_language(language)
        super().__init__(*args, **kwargs)
        self.fields["email"].label = translate("email", self.language)
        self.fields["password"].label = translate("password", self.language)

    def clean(self) -> dict:
        cleaned = super().clean()
        email = (cleaned.get("email") or "").strip().lower()
        password = cleaned.get("password") or ""
        if email and password:
            user = authenticate(username=email, password=password)
            if user is None:
                raise forms.ValidationError(translate("invalid_login", self.language))
            cleaned["user"] = user
        return cleaned


class AccountSettingsForm(forms.Form):
    name = forms.CharField(label="Name", max_length=120, required=False)
    avatar_file = forms.ImageField(label="Profile photo", required=False)
    avatar_crop_data = forms.CharField(required=False, widget=forms.HiddenInput)
    avatar_url = forms.URLField(
        label="Photo by URL",
        max_length=600,
        required=False,
        widget=forms.URLInput(attrs={"placeholder": "https://.../photo.jpg"}),
    )
    accent_color = forms.ChoiceField(label="Interface accent", choices=ACCENT_CHOICES, widget=forms.RadioSelect)
    theme_mode = forms.ChoiceField(label="Interface theme", choices=(), widget=forms.RadioSelect)
    interface_language = forms.ChoiceField(label="Language", choices=LANGUAGE_CHOICES, widget=forms.RadioSelect)
    current_password = forms.CharField(label="Current password", required=False, widget=forms.PasswordInput)
    new_password = forms.CharField(label="New password", min_length=8, required=False, widget=forms.PasswordInput)
    new_password_confirm = forms.CharField(label="Repeat new password", min_length=8, required=False, widget=forms.PasswordInput)

    def __init__(self, *args, user=None, profile=None, language=None, **kwargs):
        self.user = user
        self.profile = profile
        self.language = clean_language(language or getattr(profile, "interface_language", None))
        initial = kwargs.pop("initial", {})
        if user:
            initial.setdefault("name", user.first_name)
        if profile:
            initial.setdefault("avatar_url", profile.avatar_url)
            initial.setdefault("accent_color", profile.accent_color)
            initial.setdefault("theme_mode", profile.theme_mode)
            initial.setdefault("interface_language", profile.interface_language)
        super().__init__(*args, initial=initial, **kwargs)
        self.fields["name"].label = translate("name", self.language)
        self.fields["avatar_file"].label = translate("avatar_profile", self.language)
        self.fields["avatar_url"].label = translate("avatar_url", self.language)
        self.fields["accent_color"].label = translate("accent_color", self.language)
        self.fields["theme_mode"].label = translate("theme_mode", self.language)
        self.fields["theme_mode"].choices = (
            ("light", translate("theme_light", self.language)),
            ("soft", translate("theme_soft", self.language)),
            ("dark", translate("theme_dark", self.language)),
        )
        self.fields["interface_language"].label = translate("language", self.language)
        self.fields["current_password"].label = translate("current_password", self.language)
        self.fields["new_password"].label = translate("new_password", self.language)
        self.fields["new_password_confirm"].label = translate("new_password_confirm", self.language)

    def clean_accent_color(self) -> str:
        value = self.cleaned_data["accent_color"]
        allowed = {choice[0] for choice in ACCENT_CHOICES}
        return value if value in allowed else "#2563eb"

    def clean_theme_mode(self) -> str:
        value = self.cleaned_data["theme_mode"]
        return value if value in {"light", "soft", "dark"} else "light"

    def clean_interface_language(self) -> str:
        return clean_language(self.cleaned_data.get("interface_language"))

    def clean(self) -> dict:
        cleaned = super().clean()
        password_fields = ("current_password", "new_password", "new_password_confirm")
        wants_password_change = any(cleaned.get(field) for field in password_fields)
        if wants_password_change:
            for field in password_fields:
                if not cleaned.get(field):
                    self.add_error(field, translate("required_field", self.language))
            if self.user and cleaned.get("current_password") and not self.user.check_password(cleaned["current_password"]):
                self.add_error("current_password", translate("current_password_wrong", self.language))
            if cleaned.get("new_password") and cleaned.get("new_password_confirm") and cleaned["new_password"] != cleaned["new_password_confirm"]:
                self.add_error("new_password_confirm", translate("passwords_mismatch", self.language))
        return cleaned

    def save_profile(self) -> bool:
        if not self.user or not self.profile:
            return False
        self.user.first_name = " ".join(self.cleaned_data.get("name", "").split())[:150]
        self.user.save(update_fields=["first_name"])
        self.profile.avatar_url = self.cleaned_data.get("avatar_url", "").strip()
        self.profile.accent_color = self.cleaned_data.get("accent_color") or "#2563eb"
        self.profile.theme_mode = self.cleaned_data.get("theme_mode") or "light"
        self.profile.interface_language = self.cleaned_data.get("interface_language") or "en"
        self.profile.save(update_fields=["avatar_url", "accent_color", "theme_mode", "interface_language", "updated_at"])
        if self.cleaned_data.get("new_password"):
            self.user.set_password(self.cleaned_data["new_password"])
            self.user.save(update_fields=["password"])
            return True
        return False


class CommunityWorkForm(forms.ModelForm):
    rights_confirm = forms.BooleanField(
        required=True,
        label="I confirm that I have the rights to publish this work.",
        error_messages={"required": "Confirm that you have the rights to publish this work."},
    )

    class Meta:
        model = CommunityWork
        fields = ("kind", "title", "excerpt", "body", "media_file", "cover_image", "access", "price_cherryx")
        widgets = {
            "body": forms.Textarea(attrs={"rows": 8}),
            "excerpt": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self) -> dict:
        cleaned = super().clean()
        access = cleaned.get("access")
        price = int(cleaned.get("price_cherryx") or 0)
        kind = cleaned.get("kind")
        media_file = cleaned.get("media_file")
        body = (cleaned.get("body") or "").strip()
        source_has_media = bool(getattr(self, "source_has_media", False))
        if access == CommunityWork.ACCESS_PAID and price <= 0:
            self.add_error("price_cherryx", "Set a CherryX price for paid works.")
        if kind in {CommunityWork.KIND_VIDEO, CommunityWork.KIND_IMAGE, CommunityWork.KIND_MUSIC} and not media_file and not source_has_media:
            self.add_error("media_file", "Upload a media file for this work type.")
        if kind == CommunityWork.KIND_TEXT and not body:
            self.add_error("body", "Add text content for text works.")
        return cleaned

    def __init__(self, *args, source_has_media: bool = False, **kwargs):
        self.source_has_media = source_has_media
        super().__init__(*args, **kwargs)
        if source_has_media:
            self.fields["media_file"].required = False
            self.fields["cover_image"].required = False
