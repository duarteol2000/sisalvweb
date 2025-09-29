# apps/usuarios/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from utils.choices import TIPO_USUARIO_CHOICES


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
