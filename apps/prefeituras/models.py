# apps/prefeituras/models.py
from django.db import models

def upload_logo_path(instance, filename):
    return f"prefeituras/logos/{instance.sigla_cidade}/{filename}"

class Prefeitura(models.Model):
    nome = models.CharField("Nome da Prefeitura", max_length=120)
    cidade = models.CharField("Cidade", max_length=120)
    sigla_cidade = models.CharField("Sigla da cidade (ex.: MNC)", max_length=10)
    codigo_ibge = models.CharField("Código IBGE", max_length=10)  # char p/ manter zeros à esquerda
    dominio_email = models.CharField("Domínio de e-mail institucional", max_length=120, blank=True)
    logotipo = models.ImageField("Logotipo", upload_to=upload_logo_path, blank=True, null=True)

    # Autoridades (básico, sem histórico por enquanto)
    secretario = models.CharField("Secretário(a)", max_length=120, blank=True)
    diretor = models.CharField("Diretor(a)", max_length=120, blank=True)

    ativo = models.BooleanField(default=True)

    # Centro geográfico (opcional) para mapas
    latitude = models.DecimalField(
        "Latitude",
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text='Ex.: -3.732700 (sul negativo). <a href="https://www.google.com/maps" target="_blank" rel="noopener">Abrir Google Maps</a>'
    )
    longitude = models.DecimalField(
        "Longitude",
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text='Ex.: -38.527000 (oeste negativo). <a href="https://www.google.com/maps" target="_blank" rel="noopener">Abrir Google Maps</a>'
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "prefeituras_prefeitura"
        verbose_name = "Prefeitura"
        verbose_name_plural = "Prefeituras"
        ordering = ["cidade", "nome"]

    def __str__(self):
        return f"{self.nome} - {self.cidade} ({self.sigla_cidade})"
