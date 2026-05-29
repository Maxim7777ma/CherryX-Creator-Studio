from __future__ import annotations

from .localization import clean_language, language_options


def interface_language(request):
    active = clean_language(getattr(request, "interface_language", None))
    return {
        "interface_language": active,
        "language_options": language_options(active),
    }
