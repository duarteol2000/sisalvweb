from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone
import logging

from apps.notificacoes.models import Notificacao
from apps.autoinfracao.models import AutoInfracao
from apps.prefeituras.models import Prefeitura

logger = logging.getLogger(__name__)


def _get_prefeitura_id(request):
    return request.session.get("prefeitura_id")


@login_required
def mapa_view(request):
    pref_id = request.session.get("prefeitura_id")
    center = {"lat": -3.7327, "lng": -38.5270, "zoom": 12}
    if pref_id:
        pref = Prefeitura.objects.filter(id=pref_id).first()
        if pref and pref.latitude and pref.longitude:
            center["lat"] = float(pref.latitude)
            center["lng"] = float(pref.longitude)
            center["zoom"] = 15
    return render(request, "core/mapa.html", {"center": center})


def _parse_bbox(bbox_str: str):
    try:
        parts = [float(x) for x in (bbox_str or "").split(",")]
        if len(parts) != 4:
            return None
        min_lon, min_lat, max_lon, max_lat = parts
        return min_lon, min_lat, max_lon, max_lat
    except Exception:
        return None


def _discretize_bbox(b):
    # arredonda para 3 casas e gera string sem caracteres problemáticos
    rounded = [round(x, 3) for x in b]
    return "_".join(f"{v:.3f}" for v in rounded)


@login_required
@require_GET
def api_mapa_processos(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return HttpResponseBadRequest("Prefeitura não definida na sessão.")

    # valida usuário vinculado à prefeitura da sessão (exceto superusuário)
    if not getattr(request.user, "is_superuser", False):
        if getattr(request.user, "prefeitura_id", None) != prefeitura_id:
            return HttpResponseForbidden("Usuário sem permissão para a prefeitura da sessão.")

    tipo = (request.GET.get("tipo") or "ALL").upper()
    if tipo not in {"ALL", "NOTIFICACAO", "AUTOINFRACAO"}:
        tipo = "ALL"
    ano = (request.GET.get("ano") or "ALL").upper()
    protocolo_q = (request.GET.get("protocolo") or "").strip()
    bbox_str = request.GET.get("bbox")
    bbox = _parse_bbox(bbox_str) if bbox_str else None
    # Sem protocolo, bbox é obrigatório
    if not protocolo_q and not bbox:
        return HttpResponseBadRequest("Parâmetro bbox inválido. Esperado: minLon,minLat,maxLon,maxLat")

    # cache simples 60s por prefeitura+filtros+bbox discretizado
    bbox_key = _discretize_bbox(bbox) if bbox else "-"
    cache_key = f"mapa:{prefeitura_id}:{tipo}:{ano}:{bbox_key}:{protocolo_q or '-'}"
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached, safe=False)

    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
    else:
        min_lon = min_lat = max_lon = max_lat = None

    features = {}

    def add_entry(lat, lng, entry):
        if lat is None or lng is None:
            return
        key = (float(lat), float(lng))
        if key not in features:
            features[key] = []
        features[key].append(entry)

    # NOTIFICAÇÕES
    if tipo in ("ALL", "NOTIFICACAO"):
        qs = Notificacao.objects.filter(
            prefeitura_id=prefeitura_id,
            latitude__isnull=False,
            longitude__isnull=False,
        ).only("id", "protocolo", "latitude", "longitude", "criada_em")
        if bbox:
            qs = qs.filter(
                longitude__gte=min_lon,
                longitude__lte=max_lon,
                latitude__gte=min_lat,
                latitude__lte=max_lat,
            )
        if protocolo_q:
            qs = qs.filter(protocolo__icontains=protocolo_q)
        if ano != "ALL":
            try:
                year = int(ano)
                qs = qs.filter(criada_em__year=year)
            except Exception:
                pass
        for n in qs:
            entry = {
                "tipo": "NOTIFICACAO",
                "protocolo": n.protocolo,
                "url": reverse("notificacoes:detalhe", args=[n.id]),
                "ano": n.criada_em.year if n.criada_em else None,
            }
            add_entry(n.latitude, n.longitude, entry)

    # AUTOS DE INFRAÇÃO
    if tipo in ("ALL", "AUTOINFRACAO"):
        qs = AutoInfracao.objects.filter(
            prefeitura_id=prefeitura_id,
            latitude__isnull=False,
            longitude__isnull=False,
        ).only("id", "protocolo", "latitude", "longitude", "criada_em")
        if bbox:
            qs = qs.filter(
                longitude__gte=min_lon,
                longitude__lte=max_lon,
                latitude__gte=min_lat,
                latitude__lte=max_lat,
            )
        if protocolo_q:
            qs = qs.filter(protocolo__icontains=protocolo_q)
        if ano != "ALL":
            try:
                year = int(ano)
                qs = qs.filter(criada_em__year=year)
            except Exception:
                pass
        for a in qs:
            entry = {
                "tipo": "AUTOINFRACAO",
                "protocolo": a.protocolo,
                "url": reverse("autoinfracao:detalhe", args=[a.id]),
                "ano": a.criada_em.year if a.criada_em else None,
            }
            add_entry(a.latitude, a.longitude, entry)

    # montar FeatureCollection, agregando por ponto
    features_list = []
    for (lat, lng), entradas in features.items():
        entradas_sorted = sorted(entradas, key=lambda e: (e["tipo"], e["protocolo"]))
        ponto_id = f"{lat:.6f},{lng:.6f}"
        features_list.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lng), float(lat)]},
            "properties": {
                "ponto_id": ponto_id,
                "entradas": entradas_sorted,
            },
        })

    has_more = False
    if len(features_list) > 5000:
        features_list = features_list[:5000]
        has_more = True

    resp = {
        "type": "FeatureCollection",
        "features": features_list,
    }

    # cache 60s
    cache.set(cache_key, resp, 60)

    # log de acesso
    logger.info(
        "api_mapa_processos user=%s pref=%s tipo=%s ano=%s bbox=%s protocolo=%s count=%s",
        getattr(request.user, "id", None), prefeitura_id, tipo, ano, bbox_key, protocolo_q or '', len(features_list)
    )

    jr = JsonResponse(resp, safe=False)
    if has_more:
        jr["X-Has-More"] = "true"
    return jr
