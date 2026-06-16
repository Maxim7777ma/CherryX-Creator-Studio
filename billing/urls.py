from __future__ import annotations

from django.urls import path

from . import views


app_name = "billing"

urlpatterns = [
    path("pricing/", views.pricing, name="pricing"),
    path("checkout/", views.checkout, name="checkout"),
    path("check-email/", views.check_email, name="check_email"),
]
