from __future__ import annotations

from django.utils import translation

from .localization import DEFAULT_LANGUAGE, clean_language


class InterfaceLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = request.session.get("interface_language") or request.COOKIES.get("interface_language")
        if request.user.is_authenticated:
            try:
                language = request.user.studio_profile.interface_language or language
            except Exception:
                pass
        language = clean_language(language or DEFAULT_LANGUAGE)
        request.interface_language = language
        translation.activate(language)
        response = self.get_response(request)
        language = clean_language(getattr(request, "interface_language", language))
        response.set_cookie("interface_language", language, max_age=60 * 60 * 24 * 365, samesite="Lax")
        translation.deactivate()
        return response
