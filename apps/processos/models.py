from django.db import models
from django.conf import settings


class Processo(models.Model):
    """Entidade-raiz para unificar um fluxo (Denúncia → Notificação → AIF → Medidas).
    Reutiliza o protocolo da etapa raiz (ex.: Denúncia/Notificação/AIF criada primeiro).
    """
    prefeitura = models.ForeignKey('prefeituras.Prefeitura', on_delete=models.PROTECT, related_name='processos')
    protocolo = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=30, blank=True, default='ABERTO')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'proc_processo'
        ordering = ['-criado_em']

    def __str__(self):
        return f"{self.protocolo}"


ETAPA_ORIGEM_CHOICES = (
    ('DEN', 'Denúncia'),
    ('NOT', 'Notificação'),
    ('AIF', 'Auto de Infração'),
    ('EMB', 'Embargo'),
    ('ITD', 'Interdição'),
)


def upload_foto_processo(instance, filename):
    proto = instance.processo and instance.processo.protocolo or 'PROC'
    return f"processos/{proto}/fotos/{filename}"


class FotoProcesso(models.Model):
    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name='fotos')
    arquivo = models.ImageField(upload_to=upload_foto_processo)
    etapa_origem = models.CharField(max_length=3, choices=ETAPA_ORIGEM_CHOICES)
    origem_id = models.PositiveIntegerField(null=True, blank=True)  # id da entidade origem (ex.: denuncia_id)
    uploader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    ordem = models.PositiveIntegerField(null=True, blank=True)
    legenda = models.CharField(max_length=140, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    largura_px = models.PositiveIntegerField(null=True, blank=True)
    altura_px = models.PositiveIntegerField(null=True, blank=True)
    hash_sha256 = models.CharField(max_length=64, blank=True)
    otimizada = models.BooleanField(default=False)
    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'proc_foto'
        ordering = ['ordem', 'criada_em']

    def __str__(self):
        return f"Foto {self.id or '-'} de {self.processo_id} ({self.etapa_origem})"

