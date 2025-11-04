from django.db import models

TIPO_PESSOA_CHOICES = (
    ("PF", "Pessoa Física"),
    ("PJ", "Pessoa Jurídica"),
)

DOC_TIPO_CHOICES = (
    ("CPF", "CPF"),
    ("CNPJ", "CNPJ"),
    ("OUTRO", "Outro"),
)

PAPEL_VINCULO_CHOICES = (
    ("PROPRIETARIO", "Proprietário"),
    ("POSSUIDOR", "Possuidor"),
    ("LOCATARIO", "Locatário"),
    ("RESPONSAVEL", "Responsável"),
)


class Pessoa(models.Model):
    prefeitura = models.ForeignKey('prefeituras.Prefeitura', on_delete=models.PROTECT, related_name='pessoas')
    tipo = models.CharField(max_length=2, choices=TIPO_PESSOA_CHOICES, default='PF')
    nome_razao = models.CharField(max_length=180)
    doc_tipo = models.CharField(max_length=5, choices=DOC_TIPO_CHOICES, default='OUTRO')
    doc_num = models.CharField(max_length=20, blank=True)  # somente dígitos quando CPF/CNPJ
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cad_pessoa'
        verbose_name = 'Pessoa'
        verbose_name_plural = 'Pessoas'
        indexes = [
            models.Index(fields=['prefeitura', 'doc_num']),
            models.Index(fields=['prefeitura', 'nome_razao']),
        ]
        ordering = ['nome_razao']

    def __str__(self):
        return f"{self.nome_razao} ({self.get_tipo_display()})"


class Imovel(models.Model):
    prefeitura = models.ForeignKey('prefeituras.Prefeitura', on_delete=models.PROTECT, related_name='imoveis')
    inscricao = models.CharField('Inscrição imobiliária', max_length=40, blank=True)
    logradouro = models.CharField(max_length=140)
    numero = models.CharField(max_length=20, blank=True)
    complemento = models.CharField(max_length=60, blank=True)
    bairro = models.CharField(max_length=80)
    cidade = models.CharField(max_length=80)
    uf = models.CharField(max_length=2)
    cep = models.CharField(max_length=9, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    pessoas = models.ManyToManyField(Pessoa, through='ImovelVinculo', blank=True, related_name='imoveis')

    class Meta:
        db_table = 'cad_imovel'
        verbose_name = 'Imóvel'
        verbose_name_plural = 'Imóveis'
        indexes = [
            models.Index(fields=['prefeitura', 'inscricao']),
            models.Index(fields=['prefeitura', 'bairro']),
        ]
        ordering = ['cidade', 'bairro', 'logradouro']

    def __str__(self):
        base = f"{self.logradouro}"
        if self.numero:
            base += f", {self.numero}"
        base += f" — {self.bairro} — {self.cidade}/{self.uf}"
        return base


class ImovelVinculo(models.Model):
    imovel = models.ForeignKey(Imovel, on_delete=models.CASCADE)
    pessoa = models.ForeignKey(Pessoa, on_delete=models.CASCADE)
    papel = models.CharField(max_length=20, choices=PAPEL_VINCULO_CHOICES, default='PROPRIETARIO')
    inicio = models.DateField(null=True, blank=True)
    fim = models.DateField(null=True, blank=True)
    observacao = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cad_imovel_vinculo'
        verbose_name = 'Vínculo Imóvel–Pessoa'
        verbose_name_plural = 'Vínculos Imóvel–Pessoa'
        indexes = [
            models.Index(fields=['imovel', 'pessoa', 'papel']),
        ]

    def __str__(self):
        return f"{self.pessoa} — {self.imovel} ({self.get_papel_display()})"

