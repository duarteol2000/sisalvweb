from django.core.management.base import BaseCommand
from utils.geo import to_float_or_none, clamp_lat_lng
from apps.notificacoes.models import Notificacao


class Command(BaseCommand):
    help = "Converte lat/lng com vírgula em Notificacao para float com ponto e 6 casas"

    def handle(self, *args, **options):
        fixed = 0
        for n in Notificacao.objects.all():
            lat = to_float_or_none(getattr(n, 'latitude', None))
            lng = to_float_or_none(getattr(n, 'longitude', None))
            lat, lng = clamp_lat_lng(lat, lng)
            changed = False
            if lat != getattr(n, 'latitude', None):
                n.latitude = lat
                changed = True
            if lng != getattr(n, 'longitude', None):
                n.longitude = lng
                changed = True
            if changed:
                n.save(update_fields=['latitude', 'longitude'])
                fixed += 1
        self.stdout.write(self.style.SUCCESS(f'Coordenadas normalizadas em {fixed} notificações.'))

