# apps/usuarios/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario
from django.utils.translation import gettext_lazy as _

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    # Como não temos username, usamos email
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'tipo', 'matricula', 'prefeitura', 'is_active', 'is_staff')
    list_filter = ('tipo', 'prefeitura', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('email', 'first_name', 'last_name', 'matricula')

    fieldsets = (
        (_('Credenciais'), {'fields': ('email', 'password')}),
        (_('Informações pessoais'), {'fields': ('first_name', 'last_name')}),
        (_('Perfil SISALV'), {'fields': ('tipo', 'matricula', 'prefeitura')}),
        (_('Permissões'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Datas importantes'), {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (_('Credenciais'), {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
        (_('Perfil SISALV'), {
            'classes': ('wide',),
            'fields': ('tipo', 'matricula', 'prefeitura'),
        }),
        (_('Permissões'), {
            'classes': ('wide',),
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
    )
