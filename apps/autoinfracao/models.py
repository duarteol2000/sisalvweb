from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.prefeituras.models import Prefeitura
from apps.usuarios.models import Usuario
from utils.protocolo import gerar_protocolo_para_instance
from utils.choices import (
    PESSOA_TIPO_CHOICES,
    AIF_STATUS_CHOICES,
    MEDIDA_STATUS_CHOICES,
    LICENCA_TIPO_CHOICES,
    INTERDICAO_MOTIVO_CHOICES,
    PAGAMENTO_FORMA_CHOICES,
)
import os
import hashlib
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile


def upload_anexo_path_aif(instance, filename):
    # media/autoinfracao/anexos/<aif_id>/<filename>
    return f"autoinfracao/anexos/{instance.auto_infracao.id}/{filename}"


class InfracaoTipo(models.Model):
    """
    Catálogo de tipos de infração configurável por prefeitura.
    Se 'prefeitura' for nulo, considera-se "global" (disponível para todas).
    """
    prefeitura = models.ForeignKey(Prefeitura, on_delete=models.CASCADE, null=True, blank=True)
    codigo = models.CharField(max_length=30, blank=True)
    nome = models.CharField(max_length=140)
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "aif_infracao_tipo"
        verbose_name = "Tipo de Infração"
        verbose_name_plural = "Tipos de Infração"
        ordering = ["nome"]

    def __str__(self):
        lbl = self.nome
        if self.codigo:
            lbl = f"{self.codigo} — {lbl}"
        return lbl


class AutoInfracao(models.Model):
    # Identificação
    protocolo = models.CharField(max_length=64, unique=True, editable=False)
    prefeitura = models.ForeignKey(Prefeitura, on_delete=models.PROTECT)
    processo = models.ForeignKey('processos.Processo', on_delete=models.SET_NULL, null=True, blank=True, related_name='autos')
    denuncia = models.ForeignKey("denuncias.Denuncia", null=True, blank=True, on_delete=models.SET_NULL)
    notificacao = models.ForeignKey("notificacoes.Notificacao", null=True, blank=True, on_delete=models.SET_NULL)

    # Notificado
    pessoa_tipo = models.CharField(max_length=20, choices=PESSOA_TIPO_CHOICES)
    nome_razao = models.CharField(max_length=255)
    cpf_cnpj = models.CharField(max_length=18, blank=True, null=True)
    rg = models.CharField(max_length=20, blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # Endereço
    cep = models.CharField(max_length=9, blank=True, null=True)
    logradouro = models.CharField(max_length=255)
    numero = models.CharField(max_length=20, blank=True, null=True)
    complemento = models.CharField(max_length=100, blank=True, null=True)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    uf = models.CharField(max_length=2, default="CE")

    # Vínculos opcionais (referências)
    pessoa = models.ForeignKey('cadastros.Pessoa', null=True, blank=True, on_delete=models.SET_NULL, related_name='autos_infracao_ref')
    imovel = models.ForeignKey('cadastros.Imovel', null=True, blank=True, on_delete=models.SET_NULL, related_name='autos_infracao_ref')

    # Geolocalização (opcional)
    latitude = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
        help_text="Ex.: -3.876543"
    )
    longitude = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)],
        help_text="Ex.: -38.654321"
    )

    # Dados da infração
    descricao = models.TextField("Descrição/Constatação")
    status = models.CharField(max_length=20, choices=AIF_STATUS_CHOICES, default="ABERTO")

    # Prazos e valores
    prazo_regularizacao_data = models.DateField(null=True, blank=True)
    valor_infracao = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_multa_homologado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    homologado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="aif_homologados")
    homologado_em = models.DateTimeField(null=True, blank=True)
    regularizado_em = models.DateTimeField(null=True, blank=True)

    # Pagamento
    pago = models.BooleanField(default=False)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    pago_em = models.DateField(null=True, blank=True)
    forma_pagamento = models.CharField(max_length=20, choices=PAGAMENTO_FORMA_CHOICES, null=True, blank=True)
    guia_numero = models.CharField(max_length=60, null=True, blank=True)
    observacao_pagamento = models.CharField(max_length=200, blank=True)

    # Dados construtivos (solicitados)
    area_m2 = models.DecimalField("Área (m²)", max_digits=10, decimal_places=2, null=True, blank=True)
    testada_m = models.DecimalField("Testada (m)", max_digits=10, decimal_places=2, null=True, blank=True)
    pe_direito_m = models.DecimalField("Pé-direito (m)", max_digits=10, decimal_places=2, null=True, blank=True)
    duplex = models.BooleanField("Unidade duplex", default=False)
    qtd_comodos = models.PositiveIntegerField("Qtd. de cômodos (casas)", null=True, blank=True)
    compartimentacao = models.BooleanField("Compartimentação (galpão)", default=False)
    divisorias = models.BooleanField("Divisórias (galpão)", default=False)
    mezanino = models.BooleanField("Possui mezanino", default=False)
    area_mezanino_m2 = models.DecimalField("Área do mezanino (m²)", max_digits=10, decimal_places=2, null=True, blank=True)

    # Participantes
    fiscais = models.ManyToManyField(Usuario, blank=True, related_name="autos_infracao")

    # Catálogo de infrações selecionadas (muitos-para-muitos via through opcional)
    tipos = models.ManyToManyField(InfracaoTipo, blank=True, related_name="autos")

    # Auditoria
    criada_em = models.DateTimeField(default=timezone.now)
    atualizada_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name="aif_criados")
    atualizada_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name="aif_editados")

    class Meta:
        db_table = "aif_auto_infracao"
        verbose_name = "Auto de Infração"
        verbose_name_plural = "Autos de Infração"
        ordering = ["-criada_em"]

    def save(self, *args, **kwargs):
        # Normaliza lat/lng
        def _coerce_float6(val, lo=None, hi=None):
            if val in (None, ""): return None
            try:
                s = str(val).strip().replace(" ", "").replace(",", ".")
                f = float(s)
                if lo is not None and f < lo: return None
                if hi is not None and f > hi: return None
                return round(f, 6)
            except Exception:
                return None
        self.latitude = _coerce_float6(self.latitude, -90.0, 90.0)
        self.longitude = _coerce_float6(self.longitude, -180.0, 180.0)
        if not self.pk and not self.protocolo:
            self.protocolo = gerar_protocolo_para_instance(self, 'AIF')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.protocolo} — {self.nome_razao}"

    @property
    def total_multa(self):
        total = 0
        for item in getattr(self, 'multas', []).all() if hasattr(self, 'multas') else []:
            # Prevalece valor homologado; se ausente, usa valor da multa
            val = item.valor_homologado if item.valor_homologado is not None else item.valor_unitario
            try:
                total += (val or 0)
            except Exception:
                total += 0
        return total

    @property
    def total_infracao_itens(self):
        total = 0
        for item in getattr(self, 'multas', []).all() if hasattr(self, 'multas') else []:
            try:
                total += (item.valor_unitario or 0)
            except Exception:
                total += 0
        return total

    @property
    def dias_restantes(self):
        if not self.prazo_regularizacao_data:
            return None
        delta = self.prazo_regularizacao_data - timezone.localdate()
        return delta.days

    @property
    def prazo_badge_class(self):
        d = self.dias_restantes
        if d is None:
            return ''
        if d > 5:
            return 'bg-success'
        if d >= 1:
            return 'bg-warning'
        return 'bg-danger'


# ======== Embargo / Interdição ========

def upload_anexo_path_embargo(instance, filename):
    # media/autoinfracao/embargos/<embargo_id>/<filename>
    return f"autoinfracao/embargos/{instance.embargo.id}/{filename}"


def upload_anexo_path_interdicao(instance, filename):
    # media/autoinfracao/interdicoes/<interdicao_id>/<filename>
    return f"autoinfracao/interdicoes/{instance.interdicao.id}/{filename}"


class Embargo(models.Model):
    protocolo = models.CharField(max_length=64, unique=True, editable=False)
    prefeitura = models.ForeignKey(Prefeitura, on_delete=models.PROTECT)
    auto_infracao = models.ForeignKey('AutoInfracao', on_delete=models.PROTECT, related_name='embargos')

    status = models.CharField(max_length=20, choices=MEDIDA_STATUS_CHOICES, default='RASCUNHO')
    licenca_tipo = models.CharField(max_length=30, choices=LICENCA_TIPO_CHOICES, null=True, blank=True)
    exigencias_texto = models.TextField(blank=True)
    prazo_regularizacao_data = models.DateField(null=True, blank=True)

    afixado_no_local_em = models.DateTimeField(null=True, blank=True)
    entregue_ao_responsavel_em = models.DateTimeField(null=True, blank=True)

    criada_em = models.DateTimeField(default=timezone.now)
    atualizada_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='embargos_criados')
    atualizada_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='embargos_editados')

    class Meta:
        db_table = 'aif_embargo'
        verbose_name = 'Embargo'
        verbose_name_plural = 'Embargos'
        ordering = ['-criada_em']

    def save(self, *args, **kwargs):
        if not self.pk and not self.protocolo:
            self.protocolo = gerar_protocolo_para_instance(self, 'EMB')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.protocolo} — {self.auto_infracao.protocolo}"

    @property
    def processo(self):
        try:
            return self.auto_infracao.processo
        except Exception:
            return None

    @property
    def dias_restantes(self):
        if not self.prazo_regularizacao_data:
            return None
        delta = self.prazo_regularizacao_data - timezone.localdate()
        return delta.days

    @property
    def prazo_badge_class(self):
        d = self.dias_restantes
        if d is None:
            return ''
        if d > 5:
            return 'bg-success'
        if d >= 1:
            return 'bg-warning'
        return 'bg-danger'


class EmbargoAnexo(models.Model):
    TIPO_CHOICES = [
        ("ALVARA_CONSTRUCAO", "Alvará de Construção / Regularização"),
        ("FOTO", "Foto"),
        ("DOCUMENTO", "Documento"),
        ("OUTRO", "Outro"),
    ]

    embargo = models.ForeignKey(Embargo, on_delete=models.CASCADE, related_name='anexos')
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES, default="DOCUMENTO")
    arquivo = models.FileField(upload_to=upload_anexo_path_embargo)
    observacao = models.CharField(max_length=255, blank=True, null=True)
    largura_px = models.PositiveIntegerField(blank=True, null=True)
    altura_px = models.PositiveIntegerField(blank=True, null=True)
    hash_sha256 = models.CharField(max_length=64, blank=True, null=True)
    otimizada = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'aif_embargo_anexo'
        verbose_name = 'Anexo do Embargo'
        verbose_name_plural = 'Anexos do Embargo'
        ordering = ['-criada_em']

    def __str__(self):
        return f"{self.tipo} - {os.path.basename(self.arquivo.name)}"

    def processar_arquivo(self):
        if not self.arquivo:
            return
        try:
            MAX_KB = 100
            TARGET_KB = 95
            def _encode(img, quality):
                buf = BytesIO()
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
                return buf.getvalue()

            img = Image.open(self.arquivo)
            w, h = img.size
            if w and w > 1000:
                proporcao = 1000 / float(w)
                new_h = max(1, int((h or 0) * proporcao))
                img = img.resize((1000, new_h))
                w, h = img.size
            self.largura_px, self.altura_px = w, h

            lo, hi = 40, 95
            best = _encode(img, 85)
            best_diff = abs((len(best)//1024) - TARGET_KB)
            for _ in range(8):
                mid = (lo + hi)//2
                data = _encode(img, mid)
                size_kb = len(data)//1024
                diff = abs(size_kb - TARGET_KB)
                if diff < best_diff and size_kb <= MAX_KB:
                    best, best_diff = data, diff
                if size_kb > MAX_KB or size_kb > TARGET_KB:
                    hi = mid - 1
                else:
                    lo = mid + 1

            base, _ext = os.path.splitext(os.path.basename(self.arquivo.name))
            new_name = f"{base}.jpg"
            self.arquivo.save(new_name, ContentFile(best), save=False)
            self.otimizada = True

            # hash
            hash_obj = hashlib.sha256()
            self.arquivo.seek(0)
            for chunk in self.arquivo.chunks():
                hash_obj.update(chunk)
            self.hash_sha256 = hash_obj.hexdigest()
            self.arquivo.seek(0)
        except Exception as e:
            print(f"[WARN] Falha ao processar anexo de Embargo: {e}")


class Interdicao(models.Model):
    protocolo = models.CharField(max_length=64, unique=True, editable=False)
    prefeitura = models.ForeignKey(Prefeitura, on_delete=models.PROTECT)
    auto_infracao = models.ForeignKey('AutoInfracao', on_delete=models.PROTECT, related_name='interdicoes')

    status = models.CharField(max_length=20, choices=MEDIDA_STATUS_CHOICES, default='RASCUNHO')
    motivo_tipo = models.CharField(max_length=20, choices=INTERDICAO_MOTIVO_CHOICES)
    condicoes_texto = models.TextField(blank=True)
    prazo_regularizacao_data = models.DateField(null=True, blank=True)

    afixado_no_local_em = models.DateTimeField(null=True, blank=True)
    entregue_ao_responsavel_em = models.DateTimeField(null=True, blank=True)

    criada_em = models.DateTimeField(default=timezone.now)
    atualizada_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='interdicoes_criadas')
    atualizada_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='interdicoes_editadas')

    class Meta:
        db_table = 'aif_interdicao'
        verbose_name = 'Interdição'
        verbose_name_plural = 'Interdições'
        ordering = ['-criada_em']

    def save(self, *args, **kwargs):
        if not self.pk and not self.protocolo:
            self.protocolo = gerar_protocolo_para_instance(self, 'ITD')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.protocolo} — {self.auto_infracao.protocolo}"

    @property
    def processo(self):
        try:
            return self.auto_infracao.processo
        except Exception:
            return None

    @property
    def dias_restantes(self):
        if not self.prazo_regularizacao_data:
            return None
        delta = self.prazo_regularizacao_data - timezone.localdate()
        return delta.days

    @property
    def prazo_badge_class(self):
        d = self.dias_restantes
        if d is None:
            return ''
        if d > 5:
            return 'bg-success'
        if d >= 1:
            return 'bg-warning'
        return 'bg-danger'


class InterdicaoAnexo(models.Model):
    TIPO_CHOICES = [
        ("ALVARA_FUNCIONAMENTO", "Alvará de Funcionamento"),
        ("FOTO", "Foto"),
        ("DOCUMENTO", "Documento"),
        ("OUTRO", "Outro"),
    ]

    interdicao = models.ForeignKey(Interdicao, on_delete=models.CASCADE, related_name='anexos')
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES, default="DOCUMENTO")
    arquivo = models.FileField(upload_to=upload_anexo_path_interdicao)
    observacao = models.CharField(max_length=255, blank=True, null=True)
    largura_px = models.PositiveIntegerField(blank=True, null=True)
    altura_px = models.PositiveIntegerField(blank=True, null=True)
    hash_sha256 = models.CharField(max_length=64, blank=True, null=True)
    otimizada = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'aif_interdicao_anexo'
        verbose_name = 'Anexo da Interdição'
        verbose_name_plural = 'Anexos da Interdição'
        ordering = ['-criada_em']

    def __str__(self):
        return f"{self.tipo} - {os.path.basename(self.arquivo.name)}"

    def processar_arquivo(self):
        if not self.arquivo:
            return
        try:
            MAX_KB = 100
            TARGET_KB = 95
            def _encode(img, quality):
                buf = BytesIO()
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
                return buf.getvalue()

            img = Image.open(self.arquivo)
            w, h = img.size
            if w and w > 1000:
                proporcao = 1000 / float(w)
                new_h = max(1, int((h or 0) * proporcao))
                img = img.resize((1000, new_h))
                w, h = img.size
            self.largura_px, self.altura_px = w, h

            lo, hi = 40, 95
            best = _encode(img, 85)
            best_diff = abs((len(best)//1024) - TARGET_KB)
            for _ in range(8):
                mid = (lo + hi)//2
                data = _encode(img, mid)
                size_kb = len(data)//1024
                diff = abs(size_kb - TARGET_KB)
                if diff < best_diff and size_kb <= MAX_KB:
                    best, best_diff = data, diff
                if size_kb > MAX_KB or size_kb > TARGET_KB:
                    hi = mid - 1
                else:
                    lo = mid + 1

            base, _ext = os.path.splitext(os.path.basename(self.arquivo.name))
            new_name = f"{base}.jpg"
            self.arquivo.save(new_name, ContentFile(best), save=False)
            self.otimizada = True

            # hash
            hash_obj = hashlib.sha256()
            self.arquivo.seek(0)
            for chunk in self.arquivo.chunks():
                hash_obj.update(chunk)
            self.hash_sha256 = hash_obj.hexdigest()
            self.arquivo.seek(0)
        except Exception as e:
            print(f"[WARN] Falha ao processar anexo de Interdição: {e}")


class AutoInfracaoAnexo(models.Model):
    ANEXO_TIPO_CHOICES = [
        ("ALVARA_CONSTRUCAO", "Alvará de Construção / Regularização"),
        ("ALVARA_FUNCIONAMENTO", "Alvará de Funcionamento"),
        ("FOTO", "Foto"),
        ("DOCUMENTO", "Documento"),
        ("OUTRO", "Outro"),
    ]

    auto_infracao = models.ForeignKey(
        AutoInfracao, on_delete=models.CASCADE, related_name="anexos"
    )
    tipo = models.CharField(max_length=20, choices=ANEXO_TIPO_CHOICES, default="FOTO")
    arquivo = models.FileField(upload_to=upload_anexo_path_aif)
    observacao = models.CharField(max_length=255, blank=True, null=True)
    largura_px = models.PositiveIntegerField(blank=True, null=True)
    altura_px = models.PositiveIntegerField(blank=True, null=True)
    hash_sha256 = models.CharField(max_length=64, blank=True, null=True)
    otimizada = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "aif_anexo"
        verbose_name = "Anexo do AIF"
        verbose_name_plural = "Anexos do AIF"
        ordering = ["-criada_em"]

    def __str__(self):
        return f"{self.tipo} - {os.path.basename(self.arquivo.name)}"

    def processar_arquivo(self):
        if not self.arquivo:
            return
        try:
            MAX_KB = 100
            TARGET_KB = 95
            def _encode(img, quality):
                buf = BytesIO()
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
                return buf.getvalue()

            img = Image.open(self.arquivo)
            w, h = img.size
            if w and w > 1000:
                proporcao = 1000 / float(w)
                new_h = max(1, int((h or 0) * proporcao))
                img = img.resize((1000, new_h))
                w, h = img.size
            self.largura_px, self.altura_px = w, h

            lo, hi = 40, 95
            best = _encode(img, 85)
            best_diff = abs((len(best)//1024) - TARGET_KB)
            for _ in range(8):
                mid = (lo + hi)//2
                data = _encode(img, mid)
                size_kb = len(data)//1024
                diff = abs(size_kb - TARGET_KB)
                if diff < best_diff and size_kb <= MAX_KB:
                    best, best_diff = data, diff
                if size_kb > MAX_KB or size_kb > TARGET_KB:
                    hi = mid - 1
                else:
                    lo = mid + 1

            base, _ext = os.path.splitext(os.path.basename(self.arquivo.name))
            new_name = f"{base}.jpg"
            self.arquivo.save(new_name, ContentFile(best), save=False)
            self.otimizada = True

            # hash
            hash_obj = hashlib.sha256()
            self.arquivo.seek(0)
            for chunk in self.arquivo.chunks():
                hash_obj.update(chunk)
            self.hash_sha256 = hash_obj.hexdigest()
            self.arquivo.seek(0)
        except Exception as e:
            print(f"[WARN] Falha ao processar anexo AIF: {e}")


class Enquadramento(models.Model):
    """ Catálogo de enquadramentos legais/multas por prefeitura (ou global). """
    prefeitura = models.ForeignKey(Prefeitura, on_delete=models.CASCADE, null=True, blank=True)
    codigo = models.CharField(max_length=30, blank=True)
    artigo = models.CharField(max_length=60, blank=True)
    descricao = models.CharField(max_length=240)
    valor_base = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "aif_enquadramento"
        verbose_name = "Enquadramento Legal"
        verbose_name_plural = "Enquadramentos Legais"
        ordering = ["descricao"]

    def __str__(self):
        parts = [self.codigo or None, self.artigo or None, self.descricao]
        return " - ".join([p for p in parts if p])


class AutoInfracaoMultaItem(models.Model):
    auto_infracao = models.ForeignKey(AutoInfracao, on_delete=models.CASCADE, related_name="multas")
    enquadramento = models.ForeignKey(Enquadramento, on_delete=models.PROTECT)
    descricao = models.CharField(max_length=240, blank=True)
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    valor_homologado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "aif_multa_item"
        verbose_name = "Item de Multa"
        verbose_name_plural = "Itens de Multa"
        ordering = ["-criada_em"]

    def save(self, *args, **kwargs):
        # Se não houver valor homologado informado, usar o valor da multa
        if self.valor_homologado is None:
            self.valor_homologado = self.valor_unitario or 0
        # O total passa a refletir o valor homologado (prevalece)
        try:
            self.valor_total = (self.valor_homologado or 0)
        except Exception:
            self.valor_total = 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.enquadramento} = {self.valor_total} (homologado)"
