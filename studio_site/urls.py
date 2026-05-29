from __future__ import annotations

from django.urls import include, path


urlpatterns = [
    path("billing/", include("billing.urls")),
    path("", include("studio.urls")),
]
