from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.prefeituras.models import Prefeitura
from apps.usuarios.models import Usuario
import os
import hashlib
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile

# ----------------------------------------
# Upload path dos anexos da notificação
# ----------------------------------------
def upload_anexo_path_notificacao(instance, filename):
    # media/notificacoes/anexos/<notificacao_id>/<filename>
    return f"notificacoes/anexos/{instance.notificacao.id}/{filename}"


from utils.protocolo import gerar_protocolo_para_instance
from utils.choices import (
    PESSOA_TIPO_CHOICES,
    NOTIFICACAO_STATUS_CHOICES,
    DOC_TIPO_CHOICES,
)

class Notificacao(models.Model):
    # 🔹 Identificação
    # Aumentado para 64 para comportar matrícula no protocolo (ex.: IBGE-SIGLA-DATA-MATRICULA)
    protocolo = models.CharField(max_length=64, unique=True, editable=False)
    prefeitura = models.ForeignKey(Prefeitura, on_delete=models.PROTECT)
    processo = models.ForeignKey('processos.Processo', on_delete=models.SET_NULL, null=True, blank=True, related_name='notificacoes')
    denuncia = models.ForeignKey("denuncias.Denuncia", null=True, blank=True, on_delete=models.SET_NULL)

    # 🔹 Dados do notificado
    pessoa_tipo = models.CharField(max_length=20, choices=PESSOA_TIPO_CHOICES)
    nome_razao = models.CharField("Nome / Razão Social", max_length=255)
    cpf_cnpj = models.CharField("CPF/CNPJ", max_length=18, blank=True, null=True)
    rg = models.CharField(max_length=20, blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # 🔹 Endereço
    cep = models.CharField(max_length=9, blank=True, null=True)
    logradouro = models.CharField(max_length=255)
    numero = models.CharField(max_length=20, blank=True, null=True)
    complemento = models.CharField(max_length=100, blank=True, null=True)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    uf = models.CharField(max_length=2, default="CE")
    # Ponto de referência do local da ocorrência
    pontoref_oco = models.CharField("Ponto de referência", max_length=140, blank=True)

    # 🔹 Geolocalização (opcional – útil quando não vier de Denúncia)
    latitude = models.FloatField(
        "Latitude",
        null=True, blank=True,
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
        help_text="Ex.: -3.876543"
    )
    longitude = models.FloatField(
        "Longitude",
        null=True, blank=True,
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)],
        help_text="Ex.: -38.654321"
    )

    # 🔹 Dados da notificação
    descricao = models.TextField("Descrição da irregularidade")
    documento_tipo = models.CharField("Tipo de Documento", max_length=30, choices=DOC_TIPO_CHOICES, blank=True, null=True)
    prazo_regularizacao = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=NOTIFICACAO_STATUS_CHOICES, default="ABERTA")
    # Conclusão (opcionais): motivo livre e documento (PDF/DOC)
    conclusao_motivo = models.TextField(blank=True, null=True)
    def upload_conclusao_path(instance, filename):
        # media/notificacoes/conclusao/<notificacao_id>/<filename>
        return f"notificacoes/conclusao/{instance.id or 'new'}/{filename}"
    conclusao_documento = models.FileField(upload_to=upload_conclusao_path, blank=True, null=True)
    # Quando ocorreu o fato (informado pelo fiscal)
    ocorrido_em = models.DateTimeField(blank=True, null=True)

    # Dados construtivos (para edificações)
    area_m2 = models.DecimalField("Área (m²)", max_digits=10, decimal_places=2, null=True, blank=True)
    testada_m = models.DecimalField("Testada (m)", max_digits=10, decimal_places=2, null=True, blank=True)
    pe_direito_m = models.DecimalField("Pé-direito (m)", max_digits=10, decimal_places=2, null=True, blank=True)
    duplex = models.BooleanField("Unidade duplex", default=False)
    qtd_comodos = models.PositiveIntegerField("Qtd. de cômodos (casas)", null=True, blank=True)
    compartimentacao = models.BooleanField("Compartimentação (galpão)", default=False)
    divisorias = models.BooleanField("Divisórias (galpão)", default=False)
    mezanino = models.BooleanField("Possui mezanino", default=False)
    area_mezanino_m2 = models.DecimalField("Área do mezanino (m²)", max_digits=10, decimal_places=2, null=True, blank=True)

    # 🔹 Auditoria
    criada_em = models.DateTimeField(default=timezone.now)
    atualizada_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name="notificacoes_criadas")
    atualizada_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name="notificacoes_editadas")

    # Equipe responsável (um ou mais fiscais)
    fiscais = models.ManyToManyField(Usuario, blank=True, related_name='notificacoes_atendidas')

    # Vínculos opcionais de referência
    pessoa = models.ForeignKey('cadastros.Pessoa', null=True, blank=True, on_delete=models.SET_NULL, related_name='notificacoes')
    imovel = models.ForeignKey('cadastros.Imovel', null=True, blank=True, on_delete=models.SET_NULL, related_name='notificacoes')

    def save(self, *args, **kwargs):
        # Normaliza lat/lng para float com 6 casas e ponto
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
        # Geração de protocolo (somente na criação)
        if not self.pk and not self.protocolo:
            # sigla fixa para NOTIFICAÇÃO
            self.protocolo = gerar_protocolo_para_instance(self, 'NOT')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.protocolo} - {self.nome_razao}"

    @property
    def dias_restantes(self):
        """Diferença em dias até o prazo de regularização.
        Valor negativo indica prazo vencido. Retorna None quando não há prazo.
        """
        if not self.prazo_regularizacao:
            return None
        from django.utils import timezone
        delta = self.prazo_regularizacao - timezone.localdate()
        return delta.days

    @property
    def prazo_badge_class(self):
        """Classe de badge compatível com Bootstrap conforme proximidade do prazo."""
        d = self.dias_restantes
        if d is None:
            return ''
        if d > 5:
            return 'bg-success'
        if d >= 1:
            return 'bg-warning'
        return 'bg-danger'


# ----------------------------------------
# Model de Anexos da Notificação
# ----------------------------------------
class NotificacaoAnexo(models.Model):
    ANEXO_TIPO_CHOICES = [
        ("FOTO", "Foto"),
        ("DOCUMENTO", "Documento"),
        ("OUTRO", "Outro"),
    ]

    notificacao = models.ForeignKey(
        "notificacoes.Notificacao",
        on_delete=models.CASCADE,
        related_name="anexos",
    )
    tipo = models.CharField(max_length=20, choices=ANEXO_TIPO_CHOICES, default="FOTO")
    arquivo = models.FileField(upload_to=upload_anexo_path_notificacao)
    observacao = models.CharField(max_length=255, blank=True, null=True)
    largura_px = models.PositiveIntegerField(blank=True, null=True)
    altura_px = models.PositiveIntegerField(blank=True, null=True)
    hash_sha256 = models.CharField(max_length=64, blank=True, null=True)
    otimizada = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificacoes_anexo"
        verbose_name = "Anexo da Notificação"
        verbose_name_plural = "Anexos das Notificações"
        ordering = ["-criada_em"]

    def __str__(self):
        return f"{self.tipo} - {os.path.basename(self.arquivo.name)}"

    # ---------------------------------------------------
    # Função para gerar hash e metadados da imagem
    # ---------------------------------------------------
    def processar_arquivo(self):
        """Processa imagem (resize, hash, dimensões)"""
        if not self.arquivo:
            return

        try:
            MAX_KB = 100
            TARGET_KB = 95

            def _encode_jpeg(img, quality):
                buf = BytesIO()
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
                return buf.getvalue()

            img = Image.open(self.arquivo)
            # Redimensiona se necessário
            w, h = img.size
            if w and w > 1000:
                proporcao = 1000 / float(w)
                new_h = max(1, int(h * proporcao))
                img = img.resize((1000, new_h))
                w, h = img.size
            self.largura_px, self.altura_px = w, h

            # Busca binária simples para chegar perto de 95 KB, <= 100 KB
            lo, hi = 40, 95
            best = _encode_jpeg(img, 85)
            best_diff = abs((len(best)//1024) - TARGET_KB)
            for _ in range(8):
                mid = (lo + hi) // 2
                data = _encode_jpeg(img, mid)
                size_kb = len(data)//1024
                diff = abs(size_kb - TARGET_KB)
                if diff < best_diff and size_kb <= MAX_KB:
                    best, best_diff = data, diff
                if size_kb > MAX_KB or size_kb > TARGET_KB:
                    hi = mid - 1
                else:
                    lo = mid + 1

            # Salva como JPG
            base, _ext = os.path.splitext(os.path.basename(self.arquivo.name))
            new_name = f"{base}.jpg"
            self.arquivo.save(new_name, ContentFile(best), save=False)
            self.otimizada = True

            # Gerar hash SHA256
            hash_obj = hashlib.sha256()
            self.arquivo.seek(0)
            for chunk in self.arquivo.chunks():
                hash_obj.update(chunk)
            self.hash_sha256 = hash_obj.hexdigest()
            self.arquivo.seek(0)
        except Exception as e:
            print(f"[WARN] Falha ao processar anexo: {e}")

            
