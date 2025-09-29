from django.apps import AppConfig


class DenunciasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.denuncias'
    verbose_name = 'Denúncias'


def ready(self):
        # Registrar suporte a HEIC/HEIF no Pillow (se instalado)
        try:
            from pillow_heif import register_heif
            register_heif()
        except Exception:
            # Mantém silencioso: se o pacote não estiver instalado, não quebra o startup
            pass
