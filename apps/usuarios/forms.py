from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Usuario


class UsuarioCreationForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("email", "first_name", "last_name", "tipo", "matricula", "prefeitura", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = ("email", "first_name", "last_name", "tipo", "matricula", "prefeitura", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")

