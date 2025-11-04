from django.contrib import admin
from .models import Pessoa, Imovel, ImovelVinculo


@admin.register(Pessoa)
class PessoaAdmin(admin.ModelAdmin):
    list_display = ('nome_razao', 'tipo', 'doc_tipo', 'doc_num', 'prefeitura', 'ativo')
    search_fields = ('nome_razao', 'doc_num')
    list_filter = ('tipo', 'doc_tipo', 'ativo', 'prefeitura')


class ImovelVinculoInline(admin.TabularInline):
    model = ImovelVinculo
    extra = 1


@admin.register(Imovel)
class ImovelAdmin(admin.ModelAdmin):
    list_display = ('logradouro', 'numero', 'bairro', 'cidade', 'uf', 'inscricao', 'prefeitura', 'ativo')
    search_fields = ('logradouro', 'bairro', 'cidade', 'inscricao')
    list_filter = ('prefeitura', 'cidade', 'bairro', 'ativo')
    inlines = [ImovelVinculoInline]

