# apps/prefeituras/admin.py
from django.contrib import admin
from .models import Prefeitura

@admin.register(Prefeitura)
class PrefeituraAdmin(admin.ModelAdmin):
    list_display = ("nome", "cidade", "sigla_cidade", "codigo_ibge", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "cidade", "sigla_cidade", "codigo_ibge")
