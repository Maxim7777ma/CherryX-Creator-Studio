from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import Http404
from django.urls import include, path


def _private_media_denied(request, path: str):
    raise Http404("Private media is served only through protected download views.")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("billing/", include("billing.urls")),
    path("media/community/private/<path:path>", _private_media_denied, name="private_media_denied"),
    path("", include("studio.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
