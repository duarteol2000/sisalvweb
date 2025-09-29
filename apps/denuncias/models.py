# apps/denuncias/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from utils.choices import (
    PESSOA_TIPO_CHOICES,
    ORIGEM_DENUNCIA_CHOICES,
    DENUNCIA_STATUS_CHOICES,
    DENUNCIA_PROCEDENCIA_CHOICES,
    DOC_IMOVEL_TIPO_CHOICES,
    ANEXO_TIPO_CHOICES,
    CANAL_REGISTRO_CHOICES,
    HIST_ACAO_CHOICES,
)
from utils.protocolo import gerar_protocolo


def upload_doc_imovel_path(instance, filename):
    # media/denuncias/documentos/<denuncia_id>/<filename>
    did = instance.denuncia_id or 'tmp'
    return f"denuncias/documentos/{did}/{filename}"

def upload_anexo_path(instance, filename):
    # media/denuncias/anexos/<denuncia_id>/<filename>
    did = instance.denuncia_id or 'tmp'
    return f"denuncias/anexos/{did}/{filename}"


class Denuncia(models.Model):
    # Amarrações
    prefeitura = models.ForeignKey('prefeituras.Prefeitura', on_delete=models.PROTECT, related_name='denuncias')
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='denuncias_criadas')
    fiscais = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='denuncias_atendidas')

    protocolo = models.CharField(max_length=64, unique=True, blank=True)

    # Origem (quem denunciou)
    origem_denuncia = models.CharField(max_length=20, choices=ORIGEM_DENUNCIA_CHOICES, default='CONTRIBUINTE')

    # Denunciante (básico/anonimo ou fiscal)
    denunciante_anonimo = models.BooleanField(default=False)
    denunciante_nome = models.CharField(max_length=120, blank=True)
    denunciante_email = models.EmailField(blank=True)
    denunciante_telefone = models.CharField(max_length=20, blank=True)
    denunciante_fiscal = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='denuncias_como_denunciante'
    )

    # Denunciado (alvo)
    denunciado_tipo_pessoa = models.CharField(max_length=2, choices=PESSOA_TIPO_CHOICES, default='PF')
    denunciado_nome_razao = models.CharField(max_length=180)
    denunciado_cpf_cnpj = models.CharField(max_length=20, blank=True)
    denunciado_rg_ie = models.CharField(max_length=20, blank=True)
    denunciado_email = models.EmailField(blank=True)
    denunciado_telefone = models.CharField(max_length=20, blank=True)

    # Endereço do denunciado
    denunciado_res_logradouro = models.CharField(max_length=140, blank=True)
    denunciado_res_numero = models.CharField(max_length=20, blank=True)
    denunciado_res_complemento = models.CharField(max_length=60, blank=True)
    denunciado_res_bairro = models.CharField(max_length=80, blank=True)
    denunciado_res_cidade = models.CharField(max_length=80, blank=True)
    denunciado_res_uf = models.CharField(max_length=2, blank=True)
    denunciado_res_cep = models.CharField(max_length=9, blank=True)

    # Local da ocorrência (endereçamento da denúncia)
    local_oco_logradouro = models.CharField(max_length=140)
    local_oco_numero = models.CharField(max_length=20, blank=True)  # pode ser lote/quadra
    local_oco_complemento = models.CharField(max_length=60, blank=True)
    local_oco_bairro = models.CharField(max_length=80)
    local_oco_cidade = models.CharField(max_length=80)
    local_oco_uf = models.CharField(max_length=2)
    local_oco_cep = models.CharField(max_length=9, blank=True)
    local_oco_lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    local_oco_lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    descricao_oco = models.TextField()

    # Situação
    status = models.CharField(max_length=30, choices=DENUNCIA_STATUS_CHOICES, default='ABERTA')
    procedencia = models.CharField(max_length=20, choices=DENUNCIA_PROCEDENCIA_CHOICES, default='INDETERMINADA')
    ativo = models.BooleanField(default=True)

    # Auditoria simples
    canal_registro = models.CharField(max_length=20, choices=CANAL_REGISTRO_CHOICES, default='INTERNO')
    ip_origem = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'denuncias_denuncia'
        verbose_name = 'Denúncia'
        verbose_name_plural = 'Denúncias'
        ordering = ['-criada_em']

    def __str__(self):
        return f"{self.protocolo or 'SEM-PROTOCOLO'} — {self.denunciado_nome_razao}"

    def save(self, *args, **kwargs):
        # Geração de protocolo (somente na criação)
        if not self.pk and not self.protocolo:
            ibge = (self.prefeitura.codigo_ibge if self.prefeitura else '') or ''
            matricula = None
            # Se houver usuário que está criando e você quiser protocolar com matrícula:
            if self.criado_por and getattr(self.criado_por, 'matricula', None):
                matricula = self.criado_por.matricula
            # sigla fixa para denúncia
            self.protocolo = gerar_protocolo(ibge, 'DEN', matricula=matricula)
        super().save(*args, **kwargs)


class DenunciaDocumentoImovel(models.Model):
    denuncia = models.ForeignKey(Denuncia, on_delete=models.CASCADE, related_name='documentos_imovel')
    tipo = models.CharField(max_length=20, choices=DOC_IMOVEL_TIPO_CHOICES)
    arquivo = models.FileField(upload_to=upload_doc_imovel_path)
    observacao = models.CharField(max_length=140, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'denuncias_documento_imovel'
        verbose_name = 'Documento do imóvel'
        verbose_name_plural = 'Documentos do imóvel'
        ordering = ['-criada_em']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.denuncia.protocolo}"


class DenunciaAnexo(models.Model):
    denuncia = models.ForeignKey(Denuncia, on_delete=models.CASCADE, related_name='anexos')
    tipo = models.CharField(max_length=15, choices=ANEXO_TIPO_CHOICES, default='DOCUMENTO')
    arquivo = models.FileField(upload_to=upload_anexo_path)
    observacao = models.CharField(max_length=140, blank=True)

    # 🔽 Campos leves para fotos (preenchidos quando tipo='FOTO')
    largura_px = models.IntegerField(null=True, blank=True)
    altura_px = models.IntegerField(null=True, blank=True)
    hash_sha256 = models.CharField(max_length=64, blank=True)  # armazenará o SHA-256 em hex
    otimizada = models.BooleanField(default=False)

    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'denuncias_anexo'
        verbose_name = 'Anexo/Evidência'
        verbose_name_plural = 'Anexos/Evidências'
        ordering = ['-criada_em']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.denuncia.protocolo}"



class DenunciaHistorico(models.Model):
    denuncia = models.ForeignKey(Denuncia, on_delete=models.CASCADE, related_name='historicos')
    acao = models.CharField(max_length=30, choices=HIST_ACAO_CHOICES)
    descricao = models.CharField(max_length=200, blank=True)
    feito_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    feito_em = models.DateTimeField(default=timezone.now)
    ip_origem = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'denuncias_historico'
        verbose_name = 'Histórico da denúncia'
        verbose_name_plural = 'Históricos da denúncia'
        ordering = ['-feito_em']

    def __str__(self):
        return f"{self.denuncia.protocolo} - {self.get_acao_display()}"
