# apps/denuncias/admin.py
from django.contrib import admin
from .models import Denuncia, DenunciaDocumentoImovel, DenunciaAnexo, DenunciaHistorico

class DenunciaDocumentoImovelInline(admin.TabularInline):
    model = DenunciaDocumentoImovel
    extra = 0

class DenunciaAnexoInline(admin.TabularInline):
    model = DenunciaAnexo
    extra = 0

class DenunciaHistoricoInline(admin.TabularInline):
    model = DenunciaHistorico
    extra = 0
    readonly_fields = ('feito_em',)

@admin.register(Denuncia)
class DenunciaAdmin(admin.ModelAdmin):
    list_display = ('protocolo', 'prefeitura', 'denunciado_nome_razao', 'status', 'procedencia', 'criada_em')
    list_filter = ('prefeitura', 'status', 'procedencia', 'origem_denuncia', 'canal_registro', 'ativo')
    search_fields = ('protocolo', 'denunciado_nome_razao', 'denunciado_cpf_cnpj',
                     'local_oco_logradouro', 'local_oco_bairro', 'local_oco_cidade')
    autocomplete_fields = ('prefeitura', 'criado_por', 'denunciante_fiscal', 'fiscais')
    inlines = [DenunciaDocumentoImovelInline, DenunciaAnexoInline, DenunciaHistoricoInline]
    fieldsets = (
        ('Identificação', {
            'fields': ('prefeitura', 'protocolo', 'status', 'procedencia', 'ativo')
        }),
        ('Origem', {
            'fields': ('origem_denuncia', 'denunciante_anonimo', 'denunciante_nome', 'denunciante_email',
                       'denunciante_telefone', 'denunciante_fiscal')
        }),
        ('Denunciado (alvo)', {
            'fields': (
                'denunciado_tipo_pessoa', 'denunciado_nome_razao', 'denunciado_cpf_cnpj', 'denunciado_rg_ie',
                'denunciado_email', 'denunciado_telefone',
                'denunciado_res_logradouro', 'denunciado_res_numero', 'denunciado_res_complemento',
                'denunciado_res_bairro', 'denunciado_res_cidade', 'denunciado_res_uf', 'denunciado_res_cep',
            )
        }),
        ('Local da ocorrência', {
            'fields': (
                'local_oco_logradouro', 'local_oco_numero', 'local_oco_complemento',
                'local_oco_bairro', 'local_oco_cidade', 'local_oco_uf', 'local_oco_cep',
                'local_oco_lat', 'local_oco_lng', 'descricao_oco',
            )
        }),
        ('Execução/Atendimento', {
            'fields': ('fiscais', )
        }),
        ('Auditoria', {
            'fields': ('criado_por', 'canal_registro', 'ip_origem', 'user_agent', 'criada_em', 'atualizada_em')
        }),
    )
    readonly_fields = ('protocolo', 'criada_em', 'atualizada_em')

@admin.register(DenunciaDocumentoImovel)
class DenunciaDocumentoImovelAdmin(admin.ModelAdmin):
    list_display = ('denuncia', 'tipo', 'arquivo', 'criada_em')
    list_filter = ('tipo',)
    search_fields = ('denuncia__protocolo',)

@admin.register(DenunciaAnexo)
class DenunciaAnexoAdmin(admin.ModelAdmin):
    list_display = ('denuncia', 'tipo', 'arquivo', 'criada_em')
    list_filter = ('tipo',)
    search_fields = ('denuncia__protocolo',)

@admin.register(DenunciaHistorico)
class DenunciaHistoricoAdmin(admin.ModelAdmin):
    list_display = ('denuncia', 'acao', 'feito_por', 'feito_em')
    list_filter = ('acao',)
    search_fields = ('denuncia__protocolo',)
    readonly_fields = ('feito_em',)
