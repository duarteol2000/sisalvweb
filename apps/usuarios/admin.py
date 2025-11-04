# apps/usuarios/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, UsuarioLoginLog, AuditLog
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


@admin.register(UsuarioLoginLog)
class UsuarioLoginLogAdmin(admin.ModelAdmin):
    list_display = ("logado_em", "logout_em", "usuario", "prefeitura", "ip", "user_agent_short")
    list_filter = ("prefeitura", "usuario")
    search_fields = ("usuario__email", "usuario__first_name", "usuario__last_name", "ip", "user_agent")
    ordering = ("-logado_em",)
    date_hierarchy = "logado_em"
    readonly_fields = ("usuario", "prefeitura", "ip", "user_agent", "logado_em", "logout_em")

    def user_agent_short(self, obj):
        s = obj.user_agent or ""
        return (s[:60] + "…") if len(s) > 60 else s
    user_agent_short.short_description = _("User-Agent")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "acao", "usuario", "prefeitura", "recurso", "url", "ip")
    list_filter = ("acao", "recurso", "prefeitura")
    search_fields = ("usuario__email", "usuario__first_name", "usuario__last_name", "url", "ip")
    ordering = ("-criado_em",)
    date_hierarchy = "criado_em"
    readonly_fields = ("usuario", "prefeitura", "acao", "recurso", "app_label", "model", "object_id", "url", "metodo", "ip", "user_agent", "extra", "criado_em")

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
