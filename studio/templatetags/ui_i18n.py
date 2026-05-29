from __future__ import annotations

from django import template

from studio.localization import translate


register = template.Library()


@register.simple_tag(takes_context=True)
def ui(context, key: str) -> str:
    request = context.get("request")
    language = getattr(request, "interface_language", None) if request else None
    return translate(key, language)
