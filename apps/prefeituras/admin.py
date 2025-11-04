# apps/prefeituras/admin.py
from django.contrib import admin
from .models import Prefeitura

@admin.register(Prefeitura)
class PrefeituraAdmin(admin.ModelAdmin):
    list_display = ("nome", "cidade", "sigla_cidade", "codigo_ibge", "latitude", "longitude", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "cidade", "sigla_cidade", "codigo_ibge")
    fieldsets = (
        (None, {
            'fields': ("nome", "cidade", "sigla_cidade", "codigo_ibge", "dominio_email", "logotipo", "ativo"),
        }),
        ("Autoridades", {
            'fields': ("secretario", "diretor"),
            'classes': ("collapse",),
        }),
        ("Centro do Mapa (opcional)", {
            'fields': ("latitude", "longitude"),
            'description': "Defina as coordenadas para centralizar o mapa na sua prefeitura.",
        }),
    )
