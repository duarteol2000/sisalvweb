from django.contrib import admin
from .models import AutoInfracao, InfracaoTipo, AutoInfracaoAnexo, Enquadramento, AutoInfracaoMultaItem


@admin.register(InfracaoTipo)
class InfracaoTipoAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "prefeitura", "ativo")
    list_filter = ("ativo", "prefeitura")
    search_fields = ("nome", "codigo")


class AutoInfracaoAnexoInline(admin.TabularInline):
    model = AutoInfracaoAnexo
    extra = 0
    fields = ("tipo", "arquivo", "observacao", "largura_px", "altura_px", "otimizada")
    readonly_fields = ("largura_px", "altura_px", "otimizada")


@admin.register(AutoInfracao)
class AutoInfracaoAdmin(admin.ModelAdmin):
    list_display = ("protocolo", "nome_razao", "cpf_cnpj", "status", "criada_em")
    list_filter = ("status", "prefeitura")
    search_fields = ("protocolo", "nome_razao", "cpf_cnpj")
    filter_horizontal = ("fiscais", "tipos")
    inlines = [AutoInfracaoAnexoInline]


@admin.register(Enquadramento)
class EnquadramentoAdmin(admin.ModelAdmin):
    list_display = ("descricao", "codigo", "artigo", "prefeitura", "valor_base", "ativo")
    list_filter = ("ativo", "prefeitura")
    search_fields = ("descricao", "codigo", "artigo")


@admin.register(AutoInfracaoMultaItem)
class AutoInfracaoMultaItemAdmin(admin.ModelAdmin):
    list_display = ("auto_infracao", "enquadramento", "valor_unitario", "valor_homologado", "valor_total", "criada_em")
    list_filter = ("enquadramento",)
