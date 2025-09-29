# utils/choices.py

# Perfis de usuário
TIPO_USUARIO_CHOICES = [
    ('ADMIN',  'Administrador'),
    ('FISCAL', 'Fiscal'),
    ('VISUAL', 'Visualização'),
]

# utils/choices.py

# Tipo de pessoa
PESSOA_TIPO_CHOICES = [
    ('PF', 'Pessoa Física'),
    ('PJ', 'Pessoa Jurídica'),
]

# Origem da denúncia (quem denunciou)
ORIGEM_DENUNCIA_CHOICES = [
    ('CONTRIBUINTE', 'Contribuinte'),
    ('FISCAL', 'Fiscal'),
]

# Status da denúncia
DENUNCIA_STATUS_CHOICES = [
    ('ABERTA', 'Aberta'),
    ('EM_ANALISE', 'Em análise'),
    ('ENCAMINHADA_NOTIFICACAO', 'Encaminhada para Notificação'),
    ('ARQUIVADA', 'Arquivada'),
    ('CANCELADA', 'Cancelada'),
]

# Procedência da denúncia
DENUNCIA_PROCEDENCIA_CHOICES = [
    ('INDETERMINADA', 'Indeterminada'),
    ('PROCEDE', 'Procede'),
    ('NAO_PROCEDE', 'Não procede'),
]

# Tipo de documento do imóvel
DOC_IMOVEL_TIPO_CHOICES = [
    ('MATRICULA', 'Matrícula do imóvel'),
    ('ESCRITURA', 'Escritura pública'),
    ('CONTRATO', 'Contrato de compra e venda'),
    ('IPTU', 'IPTU/Comprovantes'),
    ('OUTRO', 'Outro'),
]

# Tipo de anexo/evidência
ANEXO_TIPO_CHOICES = [
    ('FOTO', 'Foto'),
    ('DOCUMENTO', 'Documento'),
]

# Canal de registro (auditoria)
CANAL_REGISTRO_CHOICES = [
    ('INTERNO', 'Interno'),
    ('EXTERNO', 'Externo (tablet/portal)'),
]

# Ações do histórico (auditoria)
HIST_ACAO_CHOICES = [
    ('CRIACAO', 'Criação'),
    ('EDICAO', 'Edição'),
    ('MUDANCA_STATUS', 'Mudança de status'),
    ('INCLUSAO_ANEXO', 'Inclusão de anexo'),
    ('INCLUSAO_DOC_IMOVEL', 'Inclusão de doc. do imóvel'),
    ('VINCULO_FISCAL', 'Vínculo de fiscal'),
    ('ALTERACAO_PROCEDENCIA', 'Alteração de procedência'),
]
