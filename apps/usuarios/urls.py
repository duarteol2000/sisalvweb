# apps/usuarios/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views

app_name = "usuarios"

urlpatterns = [
    # URL de reset de senha (use o template que você quiser)
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="usuarios/password_reset.html"
        ),
        name="password_reset",
    ),
]
