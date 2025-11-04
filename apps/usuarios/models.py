# apps/usuarios/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from utils.choices import TIPO_USUARIO_CHOICES
from django.utils import timezone
from django.db import models
from django.db.models import JSONField


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('O e-mail é obrigatório')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        # default de tipo se não vier nada
        extra_fields.setdefault('tipo', 'VISUAL')
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('tipo', 'ADMIN')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superusuário precisa is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superusuário precisa is_superuser=True.')

        return self._create_user(email, password, **extra_fields)


class Usuario(AbstractUser):
    # Remover o campo username do AbstractUser
    username = None

    # Identificador passa a ser o e-mail
    email = models.EmailField('E-mail', unique=True)

    tipo = models.CharField(
        max_length=10,
        choices=TIPO_USUARIO_CHOICES,
        default='VISUAL',
        help_text='Perfil de acesso do usuário'
    )
    matricula = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text='Matrícula funcional (única). Opcional para VISUAL.'
    )

    # vínculo com prefeitura (adicionamos no passo anterior)
    prefeitura = models.ForeignKey(
        'prefeituras.Prefeitura',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='usuarios'
    )

    # Configurações essenciais para email como login
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # ao criar superusuário no manage.py createsuperuser, só vai pedir email e senha

    objects = UsuarioManager()

    class Meta:
        db_table = 'usuarios_usuario'
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'

    def __str__(self):
        nome = self.get_full_name() or self.email
        return f'{nome} ({self.tipo})'


# Auditoria de login (IP, data/hora, agente)
class UsuarioLoginLog(models.Model):
    usuario = models.ForeignKey('usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='logins')
    prefeitura = models.ForeignKey('prefeituras.Prefeitura', on_delete=models.SET_NULL, null=True, blank=True, related_name='logins_usuario')
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    logado_em = models.DateTimeField(default=timezone.now)
    logout_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'usuarios_login_log'
        verbose_name = 'Login de Usuário (auditoria)'
        verbose_name_plural = 'Logins de Usuários (auditoria)'
        ordering = ['-logado_em']

    def __str__(self):
        u = self.usuario and (self.usuario.get_full_name() or self.usuario.email) or '—'
        return f"{u} @ {self.ip or '?'} em {timezone.localtime(self.logado_em).strftime('%d/%m/%Y %H:%M')}"


AUDIT_ACOES = (
    ("VIEW", "Visualizou"),
    ("CREATE", "Criou"),
    ("UPDATE", "Editou"),
    ("DELETE", "Excluiu"),
    ("PRINT", "Imprimiu"),
    ("LINK", "Vinculou"),
    ("UNLINK", "Desvinculou"),
    ("OTHER", "Outra Ação"),
)


class AuditLog(models.Model):
    usuario = models.ForeignKey('usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='audits')
    prefeitura = models.ForeignKey('prefeituras.Prefeitura', on_delete=models.SET_NULL, null=True, blank=True, related_name='audits')
    acao = models.CharField(max_length=12, choices=AUDIT_ACOES, default='VIEW')
    recurso = models.CharField(max_length=60, blank=True)  # ex.: denuncias/notificacoes/autoinfracao
    app_label = models.CharField(max_length=60, blank=True)
    model = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=60, blank=True)
    url = models.CharField(max_length=300)
    metodo = models.CharField(max_length=8)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    extra = JSONField(null=True, blank=True)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'usuarios_audit_log'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['prefeitura', 'usuario', 'acao', 'criado_em']),
        ]

    def __str__(self):
        who = self.usuario and (self.usuario.get_full_name() or self.usuario.email) or '—'
        return f"{self.acao} {self.recurso} {self.model}#{self.object_id or '-'} por {who} em {timezone.localtime(self.criado_em).strftime('%d/%m/%Y %H:%M')}"
