# apps/notificacoes/admin.py
from django.contrib import admin
from .models import Notificacao
@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ("protocolo","nome_razao","status","criada_em")
    search_fields = ("protocolo","nome_razao","cpf_cnpj")
    list_filter = ("status","criada_em")
