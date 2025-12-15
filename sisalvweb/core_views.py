from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone
from django.db import models
import logging

from apps.notificacoes.models import Notificacao
from apps.autoinfracao.models import AutoInfracao, AutoInfracaoMultaItem
from apps.prefeituras.models import Prefeitura
from apps.denuncias.models import Denuncia
from apps.notificacoes.models import Notificacao
from apps.cadastros.models import Pessoa
from apps.usuarios.models import Usuario

logger = logging.getLogger(__name__)


def _get_prefeitura_id(request):
    return request.session.get("prefeitura_id")


def _parse_date_param(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return timezone.datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


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
def api_mapa_heat(request):
    """Heatmap de Denúncias/Notificações/AIF por bbox/ano/tipo.

    Parâmetros:
    - tipo: ALL|DENUNCIA|NOTIFICACAO|AUTOINFRACAO
    - ano: ALL|YYYY
    - bbox: minLon,minLat,maxLon,maxLat (obrigatório)
    - metric: COUNT|SEVERIDADE

    Para metric=SEVERIDADE: considera apenas AIF e usa peso normalizado pelo p95
    do valor aplicado (cap no p95). Denúncias/Notificações não entram na severidade.
    """
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return HttpResponseBadRequest("Prefeitura não definida na sessão.")

    # valida usuário vinculado à prefeitura da sessão (exceto superusuário)
    if not getattr(request.user, "is_superuser", False):
        if getattr(request.user, "prefeitura_id", None) != prefeitura_id:
            return HttpResponseForbidden("Usuário sem permissão para a prefeitura da sessão.")

    tipo = (request.GET.get("tipo") or "ALL").upper()
    if tipo not in {"ALL", "DENUNCIA", "NOTIFICACAO", "AUTOINFRACAO"}:
        tipo = "ALL"
    ano = (request.GET.get("ano") or "ALL").upper()
    metric = (request.GET.get("metric") or "COUNT").upper()
    if metric not in {"COUNT", "SEVERIDADE"}:
        metric = "COUNT"
    bbox_str = request.GET.get("bbox")
    bbox = _parse_bbox(bbox_str) if bbox_str else None
    if not bbox:
        return HttpResponseBadRequest("Parâmetro bbox inválido. Esperado: minLon,minLat,maxLon,maxLat")

    min_lon, min_lat, max_lon, max_lat = bbox
    bbox_key = _discretize_bbox(bbox)
    cache_key = f"heat:{prefeitura_id}:{tipo}:{ano}:{metric}:{bbox_key}"
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    # Denúncias / Notificações (COUNT apenas) + Autos (COUNT/SEVERIDADE)
    points = []
    den_count = 0
    ntf_count = 0
    aif_count = 0

    # Denúncias (COUNT apenas)
    if metric == "COUNT" and tipo in ("ALL", "DENUNCIA"):
        den_qs = Denuncia.objects.filter(
            prefeitura_id=prefeitura_id,
            local_oco_lat__isnull=False,
            local_oco_lng__isnull=False,
            local_oco_lng__gte=min_lon,
            local_oco_lng__lte=max_lon,
            local_oco_lat__gte=min_lat,
            local_oco_lat__lte=max_lat,
        ).only("local_oco_lat", "local_oco_lng", "criada_em")
        if ano != "ALL":
            try:
                year = int(ano)
                den_qs = den_qs.filter(criada_em__year=year)
            except Exception:
                pass
        for d in den_qs:
            points.append({"lat": float(d.local_oco_lat), "lng": float(d.local_oco_lng), "weight": 1.0})
            den_count += 1

    # Notificações (COUNT apenas)
    if metric == "COUNT" and tipo in ("ALL", "NOTIFICACAO"):
        qs = Notificacao.objects.filter(
            prefeitura_id=prefeitura_id,
            latitude__isnull=False,
            longitude__isnull=False,
            longitude__gte=min_lon,
            longitude__lte=max_lon,
            latitude__gte=min_lat,
            latitude__lte=max_lat,
        ).exclude(status="CANCELADA").only("latitude", "longitude", "criada_em")
        if ano != "ALL":
            try:
                year = int(ano)
                qs = qs.filter(criada_em__year=year)
            except Exception:
                pass
        for n in qs:
            points.append({"lat": float(n.latitude), "lng": float(n.longitude), "weight": 1.0})
            ntf_count += 1

    # Autos de Infração (COUNT e SEVERIDADE)
    if tipo in ("ALL", "AUTOINFRACAO"):
        dec0 = models.Value(0, output_field=models.DecimalField(max_digits=12, decimal_places=2))
        items_sum_sq = (
            AutoInfracaoMultaItem.objects
            .filter(auto_infracao_id=models.OuterRef('pk'))
            .values('auto_infracao_id')
            .annotate(s=models.functions.Coalesce(models.Sum('valor_unitario'), dec0))
            .values('s')[:1]
        )
        aif_qs = AutoInfracao.objects.filter(
            prefeitura_id=prefeitura_id,
            latitude__isnull=False,
            longitude__isnull=False,
            longitude__gte=min_lon,
            longitude__lte=max_lon,
            latitude__gte=min_lat,
            latitude__lte=max_lat,
        ).only("latitude", "longitude", "criada_em")
        if ano != "ALL":
            try:
                year = int(ano)
                aif_qs = aif_qs.filter(criada_em__year=year)
            except Exception:
                pass
        # Anota valor_aplicado para SEVERIDADE
        aif_qs = aif_qs.annotate(valor_aplicado=models.functions.Coalesce('valor_infracao', models.Subquery(items_sum_sq), dec0))

        if metric == "COUNT":
            for a in aif_qs:
                points.append({"lat": float(a.latitude), "lng": float(a.longitude), "weight": 1.0})
                aif_count += 1
        else:
            # SEVERIDADE: normaliza por p95 (cap)
            vals = []
            buf = []
            for a in aif_qs:
                try:
                    v = float(a.valor_aplicado or 0)
                except Exception:
                    v = 0.0
                vals.append(v)
                buf.append((float(a.latitude), float(a.longitude), v))
                aif_count += 1
            def p95(arr):
                if not arr:
                    return 0.0
                s = sorted(arr)
                n = len(s)
                if n == 1:
                    return float(s[0])
                # índice aproximado do percentil 95
                k = 0.95 * (n - 1)
                f = int(k)
                c = min(f + 1, n - 1)
                if f == c:
                    return float(s[f])
                return float(s[f] + (s[c] - s[f]) * (k - f))
            cap = p95(vals)
            if cap <= 0:
                cap = max(vals) if vals else 1.0
                if cap <= 0:
                    cap = 1.0
            for lat, lng, v in buf:
                w = min(v, cap) / cap
                points.append({"lat": lat, "lng": lng, "weight": round(w, 4)})

    has_more = False
    if len(points) > 5000:
        points = points[:5000]
        has_more = True
    resp = {
        "points": points,
        "summary": {
            "DENUNCIA": {"count": den_count},
            "NOTIFICACAO": {"count": ntf_count},
            "AUTOINFRACAO": {"count": aif_count},
        },
    }
    cache.set(cache_key, resp, 90)
    jr = JsonResponse(resp)
    if has_more:
        jr["X-Has-More"] = "true"
    return jr


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
    if tipo not in {"ALL", "DENUNCIA", "NOTIFICACAO", "AUTOINFRACAO"}:
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

    # DENÚNCIAS
    if tipo in ("ALL", "DENUNCIA"):
        dqs = Denuncia.objects.filter(
            prefeitura_id=prefeitura_id,
            local_oco_lat__isnull=False,
            local_oco_lng__isnull=False,
        ).only("id", "protocolo", "local_oco_lat", "local_oco_lng", "criada_em")
        if bbox:
            dqs = dqs.filter(
                local_oco_lng__gte=min_lon,
                local_oco_lng__lte=max_lon,
                local_oco_lat__gte=min_lat,
                local_oco_lat__lte=max_lat,
            )
        if protocolo_q:
            dqs = dqs.filter(protocolo__icontains=protocolo_q)
        if ano != "ALL":
            try:
                year = int(ano)
                dqs = dqs.filter(criada_em__year=year)
            except Exception:
                pass
        for d in dqs:
            entry = {
                "tipo": "DENUNCIA",
                "protocolo": d.protocolo,
                "url": reverse("denuncias:detalhe", args=[d.id]),
                "ano": d.criada_em.year if d.criada_em else None,
            }
            add_entry(d.local_oco_lat, d.local_oco_lng, entry)

    # NOTIFICAÇÕES
    if tipo in ("ALL", "NOTIFICACAO"):
        qs = Notificacao.objects.filter(
            prefeitura_id=prefeitura_id,
            latitude__isnull=False,
            longitude__isnull=False,
        ).exclude(status="CANCELADA").only("id", "protocolo", "latitude", "longitude", "criada_em")
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


@login_required
@require_GET
def api_mapa_bairros(request):
    """
    Mapa agregado por bairro (Denúncia/Notificação/AIF), com centro aproximado e nível de densidade.

    Parâmetros:
    - tipo: ALL|DENUNCIA|NOTIFICACAO|AUTOINFRACAO
    - ano: ALL|YYYY
    - bbox: minLon,minLat,maxLon,maxLat (obrigatório)
    """
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return HttpResponseBadRequest("Prefeitura não definida na sessão.")

    # valida usuário vinculado à prefeitura da sessão (exceto superusuário)
    if not getattr(request.user, "is_superuser", False):
        if getattr(request.user, "prefeitura_id", None) != prefeitura_id:
            return HttpResponseForbidden("Usuário sem permissão para a prefeitura da sessão.")

    tipo = (request.GET.get("tipo") or "ALL").upper()
    if tipo not in {"ALL", "DENUNCIA", "NOTIFICACAO", "AUTOINFRACAO"}:
        tipo = "ALL"

    ano_param = (request.GET.get("ano") or "ALL").upper()
    year = None
    if ano_param != "ALL":
        try:
            year = int(ano_param)
        except Exception:
            ano_param = "ALL"
            year = None

    bbox_str = request.GET.get("bbox")
    bbox = _parse_bbox(bbox_str) if bbox_str else None
    if not bbox:
        return HttpResponseBadRequest("Parâmetro bbox inválido. Esperado: minLon,minLat,maxLon,maxLat")

    min_lon, min_lat, max_lon, max_lat = bbox
    bbox_key = _discretize_bbox(bbox)

    cache_key = f"mapa_bairros:{prefeitura_id}:{tipo}:{ano_param}:{bbox_key}"
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    # Acumuladores por bairro (texto)
    bairros = {}

    def _add_entry(nome_bairro, lat, lng, kind):
        if not nome_bairro:
            return
        nome = (str(nome_bairro) or "").strip()
        if not nome:
            return
        row = bairros.get(nome)
        if not row:
            row = {
                "bairro": nome,
                "denuncia": 0,
                "notificacao": 0,
                "autoinfracao": 0,
                "lat_sum": 0.0,
                "lng_sum": 0.0,
                "lat_count": 0,
                "lng_count": 0,
            }
            bairros[nome] = row
        if kind == "DENUNCIA":
            row["denuncia"] += 1
        elif kind == "NOTIFICACAO":
            row["notificacao"] += 1
        elif kind == "AUTOINFRACAO":
            row["autoinfracao"] += 1
        if lat is not None and lng is not None:
            try:
                flat = float(lat)
                flng = float(lng)
            except Exception:
                return
            row["lat_sum"] += flat
            row["lng_sum"] += flng
            row["lat_count"] += 1
            row["lng_count"] += 1

    # Denúncias
    if tipo in {"ALL", "DENUNCIA"}:
        den_qs = Denuncia.objects.filter(
            prefeitura_id=prefeitura_id,
            local_oco_bairro__isnull=False,
        ).exclude(local_oco_bairro__exact="")
        den_qs = den_qs.filter(
            local_oco_lat__isnull=False,
            local_oco_lng__isnull=False,
            local_oco_lng__gte=min_lon,
            local_oco_lng__lte=max_lon,
            local_oco_lat__gte=min_lat,
            local_oco_lat__lte=max_lat,
        ).only("local_oco_bairro", "local_oco_lat", "local_oco_lng", "criada_em")
        if year is not None:
            try:
                den_qs = den_qs.filter(criada_em__year=year)
            except Exception:
                pass
        for d in den_qs.iterator():
            _add_entry(d.local_oco_bairro, d.local_oco_lat, d.local_oco_lng, "DENUNCIA")

    # Notificações
    if tipo in {"ALL", "NOTIFICACAO"}:
        ntf_qs = Notificacao.objects.filter(
            prefeitura_id=prefeitura_id,
            bairro__isnull=False,
        ).exclude(bairro__exact="")
        ntf_qs = ntf_qs.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            longitude__gte=min_lon,
            longitude__lte=max_lon,
            latitude__gte=min_lat,
            latitude__lte=max_lat,
        ).only("bairro", "latitude", "longitude", "criada_em")
        if year is not None:
            try:
                ntf_qs = ntf_qs.filter(criada_em__year=year)
            except Exception:
                pass
        for n in ntf_qs.iterator():
            _add_entry(n.bairro, n.latitude, n.longitude, "NOTIFICACAO")

    # Autos de Infração
    if tipo in {"ALL", "AUTOINFRACAO"}:
        aif_qs = AutoInfracao.objects.filter(
            prefeitura_id=prefeitura_id,
            bairro__isnull=False,
        ).exclude(bairro__exact="")
        aif_qs = aif_qs.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            longitude__gte=min_lon,
            longitude__lte=max_lon,
            latitude__gte=min_lat,
            latitude__lte=max_lat,
        ).only("bairro", "latitude", "longitude", "criada_em")
        if year is not None:
            try:
                aif_qs = aif_qs.filter(criada_em__year=year)
            except Exception:
                pass
        for a in aif_qs.iterator():
            _add_entry(a.bairro, a.latitude, a.longitude, "AUTOINFRACAO")

    # Monta lista final de bairros com centro aproximado e classificação
    bairros_list = []
    for nome, row in bairros.items():
        total_den = int(row["denuncia"])
        total_ntf = int(row["notificacao"])
        total_aif = int(row["autoinfracao"])
        total = total_den + total_ntf + total_aif
        # valor_base depende do filtro de tipo atual
        if tipo == "DENUNCIA":
            valor_base = total_den
        elif tipo == "NOTIFICACAO":
            valor_base = total_ntf
        elif tipo == "AUTOINFRACAO":
            valor_base = total_aif
        else:  # ALL
            valor_base = total
        if valor_base <= 0:
            # não entra no mapa quando não há nada do tipo atual
            continue
        lat = row["lat_sum"] / row["lat_count"] if row["lat_count"] > 0 else None
        lng = row["lng_sum"] / row["lng_count"] if row["lng_count"] > 0 else None
        bairros_list.append({
            "bairro": nome,
            "lat": lat,
            "lng": lng,
            "total": total,
            "denuncia": total_den,
            "notificacao": total_ntf,
            "autoinfracao": total_aif,
            "valor_base": valor_base,
            # nivel será preenchido depois
        })

    # Classificação de densidade (BAIXA/MEDIA/ALTA) baseada em ordem relativa:
    # - Se houver mais de 1 bairro:
    #   - maior(es) valor_base => ALTA
    #   - menor(es) valor_base => BAIXA
    #   - intermediários => MEDIA
    # - Se só existir 1 bairro ou não houver variação => MEDIA
    valores = [b["valor_base"] for b in bairros_list if b["valor_base"] > 0]
    if len(valores) <= 1:
        for b in bairros_list:
            b["nivel"] = "MEDIA"
    else:
        max_v = max(valores)
        min_v = min(valores)
        if max_v == min_v:
            for b in bairros_list:
                b["nivel"] = "MEDIA"
        else:
            for b in bairros_list:
                vb = b["valor_base"]
                if vb == max_v:
                    b["nivel"] = "ALTA"
                elif vb == min_v:
                    b["nivel"] = "BAIXA"
                else:
                    b["nivel"] = "MEDIA"

    summary = {
        "total_geral": sum(b["total"] for b in bairros_list),
        "denuncia": sum(b["denuncia"] for b in bairros_list),
        "notificacao": sum(b["notificacao"] for b in bairros_list),
        "autoinfracao": sum(b["autoinfracao"] for b in bairros_list),
        "tipo_atual": tipo,
    }

    resp = {
        "bairros": bairros_list,
        "summary": summary,
    }
    cache.set(cache_key, resp, 60)
    return JsonResponse(resp)


@login_required
def relatorio_risco(request):
    """Relatório de Risco & Prioridade por bairro (simplificado):
    - Volume (Den/NTF/AIF) no período
    - Recência (últimos 30 dias)
    - Severidade (soma valor aplicado de AIF)
    - Score = soma ponderada de métricas normalizadas
    """
    pref_id = _get_prefeitura_id(request)
    if not pref_id:
        return HttpResponseBadRequest("Prefeitura não definida.")

    # Filtros
    de = _parse_date_param(request.GET.get("de"))
    ate = _parse_date_param(request.GET.get("ate"))
    today = timezone.localdate()
    if not de and not ate:
        ate = today
        de = ate - timezone.timedelta(days=90)
    if de and not ate:
        ate = de
    if ate and not de:
        de = ate - timezone.timedelta(days=90)
    if de > ate:
        de, ate = ate, de
    dt_ini = timezone.make_aware(timezone.datetime(de.year, de.month, de.day, 0, 0))
    dt_fim_ex = timezone.make_aware(timezone.datetime(ate.year, ate.month, ate.day, 0, 0)) + timezone.timedelta(days=1)
    tipo = (request.GET.get("tipo") or "ALL").upper()
    if tipo not in {"ALL","DEN","NTF","AIF"}:
        tipo = "ALL"

    # Janela de recência (30d dentro do período)
    rec_ini_date = max(de, ate - timezone.timedelta(days=30))
    rec_ini = timezone.make_aware(timezone.datetime(rec_ini_date.year, rec_ini_date.month, rec_ini_date.day, 0, 0))

    # Janela anterior para tendência
    days_span = (ate - de).days + 1
    prev_ate = de - timezone.timedelta(days=1)
    prev_de = prev_ate - timezone.timedelta(days=days_span - 1)
    prev_dt_ini = timezone.make_aware(timezone.datetime(prev_de.year, prev_de.month, prev_de.day, 0, 0))
    prev_dt_fim_ex = timezone.make_aware(timezone.datetime(prev_ate.year, prev_ate.month, prev_ate.day, 0, 0)) + timezone.timedelta(days=1)

    # Acumuladores por bairro
    rows = {}  # bairro -> dict
    def add_row(bairro):
        if not bairro:
            return None
        key = str(bairro).strip()
        if not key:
            return None
        if key not in rows:
            rows[key] = {
                "bairro": key,
                "vol": 0,
                "vol_rec": 0,
                "vol_prev": 0,
                "sev": 0,
            }
        return rows[key]

    # Denúncias
    if tipo in ("ALL","DEN"):
        qs = Denuncia.objects.filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
        for r in qs.values("local_oco_bairro").annotate(c=models.Count("id")):
            row = add_row(r["local_oco_bairro"]);  
            if row: row["vol"] += r["c"]
        # recência
        rec_qs = qs.filter(criada_em__gte=rec_ini)
        for r in rec_qs.values("local_oco_bairro").annotate(c=models.Count("id")):
            row = add_row(r["local_oco_bairro"]);  
            if row: row["vol_rec"] += r["c"]
        # anterior
        prev_qs = Denuncia.objects.filter(prefeitura_id=pref_id, criada_em__gte=prev_dt_ini, criada_em__lt=prev_dt_fim_ex)
        for r in prev_qs.values("local_oco_bairro").annotate(c=models.Count("id")):
            row = add_row(r["local_oco_bairro"]);  
            if row: row["vol_prev"] += r["c"]

    # Notificações (ignora CANCELADA)
    if tipo in ("ALL","NTF"):
        qs = Notificacao.objects.filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex).exclude(status="CANCELADA")
        for r in qs.values("bairro").annotate(c=models.Count("id")):
            row = add_row(r["bairro"]);  
            if row: row["vol"] += r["c"]
        rec_qs = qs.filter(criada_em__gte=rec_ini)
        for r in rec_qs.values("bairro").annotate(c=models.Count("id")):
            row = add_row(r["bairro"]);  
            if row: row["vol_rec"] += r["c"]
        prev_qs = Notificacao.objects.filter(prefeitura_id=pref_id, criada_em__gte=prev_dt_ini, criada_em__lt=prev_dt_fim_ex).exclude(status="CANCELADA")
        for r in prev_qs.values("bairro").annotate(c=models.Count("id")):
            row = add_row(r["bairro"]);  
            if row: row["vol_prev"] += r["c"]

    # Autos de Infração (inclui severidade)
    if tipo in ("ALL","AIF"):
        dec0 = models.Value(0, output_field=models.DecimalField(max_digits=12, decimal_places=2))
        items_sum_sq = (
            AutoInfracaoMultaItem.objects
            .filter(auto_infracao_id=models.OuterRef('pk'))
            .values('auto_infracao_id')
            .annotate(s=models.functions.Coalesce(models.Sum('valor_unitario'), dec0))
            .values('s')[:1]
        )
        qs = AutoInfracao.objects.filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
        qs = qs.annotate(valor_aplicado=models.functions.Coalesce('valor_infracao', models.Subquery(items_sum_sq), dec0))
        for r in qs.values("bairro").annotate(c=models.Count("id"), sev=models.functions.Coalesce(models.Sum('valor_aplicado'), dec0)):
            row = add_row(r["bairro"])
            if row:
                row["vol"] += r["c"]
                try:
                    row["sev"] += float(r["sev"]) if r["sev"] is not None else 0
                except Exception:
                    pass
        # recência
        rec_qs = qs.filter(criada_em__gte=rec_ini)
        for r in rec_qs.values("bairro").annotate(c=models.Count("id")):
            row = add_row(r["bairro"]);  
            if row: row["vol_rec"] += r["c"]
        # anterior
        prev_qs = AutoInfracao.objects.filter(prefeitura_id=pref_id, criada_em__gte=prev_dt_ini, criada_em__lt=prev_dt_fim_ex)
        for r in prev_qs.values("bairro").annotate(c=models.Count("id")):
            row = add_row(r["bairro"]);  
            if row: row["vol_prev"] += r["c"]

    # Normalização e score
    vols = [r["vol"] for r in rows.values()] or [0]
    recs = [r["vol_rec"] for r in rows.values()] or [0]
    sevs = [r["sev"] for r in rows.values()] or [0]
    vmin, vmax = min(vols), max(vols)
    rmin, rmax = min(recs), max(recs)
    smin, smax = min(sevs), max(sevs)
    def norm(x, lo, hi):
        try:
            if hi == lo:
                return 0.0
            return (float(x) - float(lo)) / (float(hi) - float(lo))
        except Exception:
            return 0.0
    for r in rows.values():
        nv = norm(r["vol"], vmin, vmax)
        nr = norm(r["vol_rec"], rmin, rmax)
        ns = norm(r["sev"], smin, smax)
        # Pesos simples (ajustáveis futuramente): 0.4 volume, 0.2 recência, 0.4 severidade
        r["score"] = round(0.4*nv + 0.2*nr + 0.4*ns, 4)
        # Tendência (comparação com janela anterior)
        if r["vol_prev"] < r["vol"]:
            r["trend"] = "up"
        elif r["vol_prev"] > r["vol"]:
            r["trend"] = "down"
        else:
            r["trend"] = "flat"

    top_rows = sorted(rows.values(), key=lambda x: (-x["score"], -x["vol"], -x["sev"]))

    return render(request, "relatorios/risco.html", {
        "rows": top_rows,
        "de": de,
        "ate": ate,
        "tipo": tipo,
    })


@login_required
def relatorio_fiscais(request):
    """Relatório de carga por fiscal: contagem de atendimentos (NTF/AIF) por período,
    e backlog em aberto por fiscal."""
    pref_id = _get_prefeitura_id(request)
    if not pref_id:
        return HttpResponseBadRequest("Prefeitura não definida.")

    de = _parse_date_param(request.GET.get("de"))
    ate = _parse_date_param(request.GET.get("ate"))
    today = timezone.localdate()
    if not de and not ate:
        ate = today
        de = ate - timezone.timedelta(days=90)
    if de and not ate:
        ate = de
    if ate and not de:
        de = ate - timezone.timedelta(days=90)
    if de > ate:
        de, ate = ate, de
    dt_ini = timezone.make_aware(timezone.datetime(de.year, de.month, de.day, 0, 0))
    dt_fim_ex = timezone.make_aware(timezone.datetime(ate.year, ate.month, ate.day, 0, 0)) + timezone.timedelta(days=1)

    # Notificações por fiscal (período)
    ntf_counts = (
        Notificacao.objects
        .filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
        .exclude(status="CANCELADA")
        .values("fiscais")
        .annotate(c=models.Count("id"))
    )
    ntf_map = { r["fiscais"]: r["c"] for r in ntf_counts if r["fiscais"] }

    # AIF por fiscal (período)
    aif_counts = (
        AutoInfracao.objects
        .filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
        .values("fiscais")
        .annotate(c=models.Count("id"))
    )
    aif_map = { r["fiscais"]: r["c"] for r in aif_counts if r["fiscais"] }

    # Backlog em aberto (sem período) — desconsidera CANCELADA
    ntf_abertos = Notificacao.objects.filter(prefeitura_id=pref_id).exclude(status__in=["CONCLUIDA", "CANCELADA"]).values("fiscais").annotate(c=models.Count("id"))
    # Backlog AIF: exclui REGULARIZADO e CANCELADO (considerados encerrados)
    aif_abertos = (
        AutoInfracao.objects
        .filter(prefeitura_id=pref_id)
        .exclude(status__in=["REGULARIZADO", "CANCELADO"])
        .values("fiscais")
        .annotate(c=models.Count("id"))
    )
    ntf_ab_map = { r["fiscais"]: r["c"] for r in ntf_abertos if r["fiscais"] }
    aif_ab_map = { r["fiscais"]: r["c"] for r in aif_abertos if r["fiscais"] }

    # Monta linhas por fiscal ativo da prefeitura
    # Apenas usuários com perfil de Fiscal
    fiscais = Usuario.objects.filter(prefeitura_id=pref_id, is_active=True, tipo='FISCAL').order_by('first_name','last_name','email')
    rows = []
    for u in fiscais:
        nid = u.id
        n = ntf_map.get(nid, 0)
        a = aif_map.get(nid, 0)
        na = ntf_ab_map.get(nid, 0)
        aa = aif_ab_map.get(nid, 0)
        rows.append({
            "u": u,
            "ntf": n,
            "aif": a,
            "total": (n + a),
            "ntf_ab": na,
            "aif_ab": aa,
            "ab_total": (na + aa),
        })

    rows.sort(key=lambda r: (-r["total"], -r["ab_total"], (r["u"].get_full_name() or r["u"].email)))
    return render(request, "relatorios/fiscais.html", {
        "rows": rows,
        "de": de,
        "ate": ate,
    })


@login_required
def relatorio_fiscais_quantitativo(request):
    """Relatório Quantitativo por Fiscal
    - Filtro por período (de/ate) ou por 'ano' (prioritário)
    - Contagem por fiscal: Denúncias (M2M fiscais), Notificações, AIF
    - Top bairros por fiscal (soma das categorias)
    - Gráfico simples (barras proporcionais) por fiscal (DEN/NTF/AIF)
    """
    pref_id = _get_prefeitura_id(request)
    if not pref_id:
        return HttpResponseBadRequest("Prefeitura não definida.")

    # Período
    de = _parse_date_param(request.GET.get("de"))
    ate = _parse_date_param(request.GET.get("ate"))
    ano_q = request.GET.get("ano")
    today = timezone.localdate()
    if ano_q:
        try:
            y = int(ano_q)
            de = timezone.datetime(y, 1, 1).date()
            ate = timezone.datetime(y, 12, 31).date()
        except Exception:
            ano_q = None
    if not de and not ate:
        ate = today
        de = ate - timezone.timedelta(days=90)
    if de and not ate:
        ate = de
    if ate and not de:
        de = ate - timezone.timedelta(days=90)
    if de > ate:
        de, ate = ate, de
    dt_ini = timezone.make_aware(timezone.datetime(de.year, de.month, de.day, 0, 0))
    dt_fim_ex = timezone.make_aware(timezone.datetime(ate.year, ate.month, ate.day, 0, 0)) + timezone.timedelta(days=1)

    # Apenas usuários com perfil de Fiscal
    fiscais = Usuario.objects.filter(prefeitura_id=pref_id, is_active=True, tipo='FISCAL').order_by('first_name','last_name','email')
    # Top N bairros por fiscal (configurável)
    try:
        top_n = int(request.GET.get("top") or 5)
    except Exception:
        top_n = 5
    top_n = max(1, min(20, top_n))

    # Coleta contagens por fiscal
    rows = []
    max_total = 0
    for u in fiscais:
        # Denúncias atendidas (M2M fiscais)
        den_count = Denuncia.objects.filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex, fiscais=u).count()
        # Notificações atendidas
        ntf_count = Notificacao.objects.filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex, fiscais=u).exclude(status="CANCELADA").count()
        # AIF atendidos
        aif_count = AutoInfracao.objects.filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex, fiscais=u).count()
        total = den_count + ntf_count + aif_count

        # Top bairros por fiscal (somando todas as categorias)
        bairros = {}
        # Denúncias por bairro
        for r in (Denuncia.objects
                  .filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex, fiscais=u)
                  .values("local_oco_bairro")
                  .annotate(c=models.Count("id"))):
            b = (r.get("local_oco_bairro") or "—").strip() or "—"
            bairros.setdefault(b, {"DEN":0, "NTF":0, "AIF":0, "total":0})
            bairros[b]["DEN"] += r["c"]; bairros[b]["total"] += r["c"]
        # Notificações por bairro
        for r in (Notificacao.objects
                  .filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex, fiscais=u)
                  .exclude(status="CANCELADA")
                  .values("bairro")
                  .annotate(c=models.Count("id"))):
            b = (r.get("bairro") or "—").strip() or "—"
            bairros.setdefault(b, {"DEN":0, "NTF":0, "AIF":0, "total":0})
            bairros[b]["NTF"] += r["c"]; bairros[b]["total"] += r["c"]
        # AIF por bairro
        for r in (AutoInfracao.objects
                  .filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex, fiscais=u)
                  .values("bairro")
                  .annotate(c=models.Count("id"))):
            b = (r.get("bairro") or "—").strip() or "—"
            bairros.setdefault(b, {"DEN":0, "NTF":0, "AIF":0, "total":0})
            bairros[b]["AIF"] += r["c"]; bairros[b]["total"] += r["c"]

        # Top N bairros
        top_bairros = sorted([
            {"bairro": b, **vals}
            for (b, vals) in bairros.items()
        ], key=lambda x: (-x["total"], x["bairro"]))[:top_n]

        rows.append({
            "u": u,
            "den": den_count,
            "ntf": ntf_count,
            "aif": aif_count,
            "total": total,
            "top_bairros": top_bairros,
        })
        if total > max_total:
            max_total = total

    rows.sort(key=lambda r: (-r["total"], (r["u"].get_full_name() or r["u"].email)))

    # Percentuais para gráfico (proporcionais ao maior total)
    denom = max_total or 1
    for r in rows:
        r["pct_den"] = round((r["den"] / denom) * 100.0, 2)
        r["pct_ntf"] = round((r["ntf"] / denom) * 100.0, 2)
        r["pct_aif"] = round((r["aif"] / denom) * 100.0, 2)

    years = list(range(timezone.localdate().year, timezone.localdate().year - 6, -1))

    return render(request, "relatorios/fiscais_quantitativo.html", {
        "rows": rows,
        "de": de,
        "ate": ate,
        "ano": ano_q,
        "years": years,
        "max_total": max_total or 1,
        "top_n": top_n,
    })


@login_required
def relatorio_fiscais_bairros(request):
    """Bairros por Fiscal — Quantitativos (DEN/NTF/AIF)
    - Filtros: período (de/ate) ou ano, tipo=ALL|DEN|NTF|AIF
    - Lista os bairros com os fiscais mais atuantes no período, com contagem por categoria e total.
    - Exportação CSV completa (tabela longa bairro × fiscal).
    """
    pref_id = _get_prefeitura_id(request)
    if not pref_id:
        return HttpResponseBadRequest("Prefeitura não definida.")

    # Período
    de = _parse_date_param(request.GET.get("de"))
    ate = _parse_date_param(request.GET.get("ate"))
    ano_q = request.GET.get("ano")
    tipo = (request.GET.get("tipo") or "ALL").upper()
    if tipo not in {"ALL","DEN","NTF","AIF"}:
        tipo = "ALL"
    top_n = request.GET.get("top")
    try:
        top_n = int(top_n) if top_n else 10
    except Exception:
        top_n = 10

    today = timezone.localdate()
    if ano_q:
        try:
            y = int(ano_q)
            de = timezone.datetime(y, 1, 1).date()
            ate = timezone.datetime(y, 12, 31).date()
        except Exception:
            ano_q = None
    if not de and not ate:
        ate = today
        de = ate - timezone.timedelta(days=90)
    if de and not ate:
        ate = de
    if ate and not de:
        de = ate - timezone.timedelta(days=90)
    if de > ate:
        de, ate = ate, de
    dt_ini = timezone.make_aware(timezone.datetime(de.year, de.month, de.day, 0, 0))
    dt_fim_ex = timezone.make_aware(timezone.datetime(ate.year, ate.month, ate.day, 0, 0)) + timezone.timedelta(days=1)

    # Fiscais elegíveis (perfil fiscal)
    fiscais_qs = Usuario.objects.filter(prefeitura_id=pref_id, is_active=True, tipo='FISCAL')
    fiscais_map = {u.id: (u.get_full_name() or u.email) for u in fiscais_qs}

    bairros = {}  # nome -> { total, fisc: {id -> {DEN,NTF,AIF,total}} }

    def _touch_bairro(nome):
        key = (nome or "—").strip() or "—"
        if key not in bairros:
            bairros[key] = {"total": 0, "fisc": {}}
        return key

    # Denúncias
    if tipo in ("ALL","DEN"):
        den_qs = (Denuncia.objects
                 .filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
                 .values("local_oco_bairro", "fiscais")
                 .annotate(c=models.Count("id")))
        for r in den_qs:
            fid = r.get("fiscais")
            if not fid or fid not in fiscais_map:
                continue
            b = _touch_bairro(r.get("local_oco_bairro"))
            fisc = bairros[b]["fisc"].setdefault(fid, {"DEN":0,"NTF":0,"AIF":0,"total":0})
            fisc["DEN"] += r["c"]; fisc["total"] += r["c"]; bairros[b]["total"] += r["c"]

    # Notificações
    if tipo in ("ALL","NTF"):
        ntf_qs = (Notificacao.objects
                 .filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
                 .exclude(status="CANCELADA")
                 .values("bairro", "fiscais")
                 .annotate(c=models.Count("id")))
        for r in ntf_qs:
            fid = r.get("fiscais")
            if not fid or fid not in fiscais_map:
                continue
            b = _touch_bairro(r.get("bairro"))
            fisc = bairros[b]["fisc"].setdefault(fid, {"DEN":0,"NTF":0,"AIF":0,"total":0})
            fisc["NTF"] += r["c"]; fisc["total"] += r["c"]; bairros[b]["total"] += r["c"]

    # AIF
    if tipo in ("ALL","AIF"):
        aif_qs = (AutoInfracao.objects
                 .filter(prefeitura_id=pref_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
                 .values("bairro", "fiscais")
                 .annotate(c=models.Count("id")))
        for r in aif_qs:
            fid = r.get("fiscais")
            if not fid or fid not in fiscais_map:
                continue
            b = _touch_bairro(r.get("bairro"))
            fisc = bairros[b]["fisc"].setdefault(fid, {"DEN":0,"NTF":0,"AIF":0,"total":0})
            fisc["AIF"] += r["c"]; fisc["total"] += r["c"]; bairros[b]["total"] += r["c"]

    # Export CSV (completo)
    if (request.GET.get("export") or "").lower() == "csv":
        import csv
        from django.utils.text import slugify as _slug
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        fname = f"bairros_por_fiscal_{de.strftime('%Y%m%d')}_{ate.strftime('%Y%m%d')}.csv"
        resp["Content-Disposition"] = f"attachment; filename={_slug(fname)}"
        writer = csv.writer(resp)
        writer.writerow(["bairro", "fiscal_id", "fiscal", "den", "ntf", "aif", "total"])
        for bairro, info in sorted(bairros.items(), key=lambda kv: (-kv[1]["total"], kv[0])):
            for fid, agg in sorted(info["fisc"].items(), key=lambda kv: (-kv[1]["total"], kv[0])):
                writer.writerow([bairro, fid, fiscais_map.get(fid, str(fid)), agg["DEN"], agg["NTF"], agg["AIF"], agg["total"]])
        return resp

    # Monta linhas de exibição (top fisc por bairro)
    rows = []
    for bairro, info in bairros.items():
        fisc_list = [
            {"id": fid, "nome": fiscais_map.get(fid, str(fid)), **agg}
            for fid, agg in info["fisc"].items()
        ]
        fisc_list.sort(key=lambda x: (-x["total"], x["nome"]))
        top_list = fisc_list[:top_n]
        restantes = max(0, len(fisc_list) - len(top_list))
        rows.append({
            "bairro": bairro,
            "total": info["total"],
            "fiscais": top_list,
            "fiscais_total": len(fisc_list),
            "restantes": restantes,
        })

    rows.sort(key=lambda r: (-r["total"], r["bairro"]))
    years = list(range(timezone.localdate().year, timezone.localdate().year - 6, -1))

    return render(request, "relatorios/fiscais_bairros.html", {
        "rows": rows,
        "de": de,
        "ate": ate,
        "ano": ano_q,
        "years": years,
        "tipo": tipo,
        "top_n": top_n,
    })
@login_required
def relatorio_operacional(request):
    """Painel: Entradas, Saídas e Processos Ativos por período, com CSV.

    - Entradas: criadas no período (criada_em)
    - Saídas: encerradas no período (por status de fechamento, com fallback em atualizado)
    - Processos Ativos: status não-encerrado em relação ao fim do período
    """
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return HttpResponseBadRequest("Prefeitura não definida na sessão.")

    def _parse_date(s):
        if not s:
            return None
        s = s.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return timezone.datetime.strptime(s, fmt).date()
            except Exception:
                pass
        return None

    today = timezone.localdate()
    # padrão: mês corrente
    default_start = today.replace(day=1)
    default_end = today

    d_ini = _parse_date(request.GET.get("inicio")) or default_start
    d_fim = _parse_date(request.GET.get("fim")) or default_end
    if d_ini > d_fim:
        d_ini, d_fim = d_fim, d_ini
    # janelas datetime (início inclusivo, fim exclusivo via +1 dia)
    dt_ini = timezone.make_aware(timezone.datetime(d_ini.year, d_ini.month, d_ini.day, 0, 0))
    dt_fim_ex = timezone.make_aware(timezone.datetime(d_fim.year, d_fim.month, d_fim.day, 0, 0)) + timezone.timedelta(days=1)

    # Conjuntos de status de encerramento por módulo
    DEN_FECHADOS = {"ARQUIVADA", "CANCELADA"}
    NOT_FECHADOS = {"CONCLUIDA", "CANCELADA"}
    AIF_FECHADOS = {"REGULARIZADO", "CANCELADO"}

    # Entradas
    den_entradas = Denuncia.objects.filter(prefeitura_id=prefeitura_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex).count()
    # Notificações CANCELADAS não entram no operacional (como se fossem excluídas)
    not_entradas = Notificacao.objects.filter(prefeitura_id=prefeitura_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex).exclude(status="CANCELADA").count()
    aif_entradas = AutoInfracao.objects.filter(prefeitura_id=prefeitura_id, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex).count()

    # Saídas
    den_saidas = Denuncia.objects.filter(prefeitura_id=prefeitura_id, status__in=DEN_FECHADOS, atualizada_em__gte=dt_ini, atualizada_em__lt=dt_fim_ex).count()
    not_saidas = Notificacao.objects.filter(prefeitura_id=prefeitura_id, status__in=NOT_FECHADOS, atualizada_em__gte=dt_ini, atualizada_em__lt=dt_fim_ex).exclude(status="CANCELADA").count()
    # AIF: REGULARIZADO usa regularizado_em; CANCELADO usa atualizada_em
    aif_saidas_reg = AutoInfracao.objects.filter(prefeitura_id=prefeitura_id, status="REGULARIZADO", regularizado_em__isnull=False, regularizado_em__date__gte=d_ini, regularizado_em__date__lte=d_fim).count()
    aif_saidas_canc = AutoInfracao.objects.filter(prefeitura_id=prefeitura_id, status="CANCELADO", atualizada_em__gte=dt_ini, atualizada_em__lt=dt_fim_ex).count()
    aif_saidas = aif_saidas_reg + aif_saidas_canc

    # Processos Ativos (saldo) no fim do período: status não-encerrado e criados até o fim do período
    den_ativos = Denuncia.objects.filter(prefeitura_id=prefeitura_id, criada_em__lt=dt_fim_ex).exclude(status__in=DEN_FECHADOS).count()
    not_ativos = Notificacao.objects.filter(prefeitura_id=prefeitura_id, criada_em__lt=dt_fim_ex).exclude(status__in=NOT_FECHADOS).exclude(status="CANCELADA").count()
    aif_ativos = AutoInfracao.objects.filter(prefeitura_id=prefeitura_id, criada_em__lt=dt_fim_ex).exclude(status__in=AIF_FECHADOS).count()

    data = {
        "periodo": {"inicio": d_ini, "fim": d_fim},
        "denuncias": {"entradas": den_entradas, "saidas": den_saidas, "ativos": den_ativos},
        "notificacoes": {"entradas": not_entradas, "saidas": not_saidas, "ativos": not_ativos},
        "aif": {"entradas": aif_entradas, "saidas": aif_saidas, "ativos": aif_ativos},
    }

    if (request.GET.get("format") or "").lower() == "csv":
        import csv
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = "attachment; filename=relatorio_operacional.csv"
        w = csv.writer(resp)
        w.writerow(["Período", d_ini.isoformat(), d_fim.isoformat()])
        w.writerow([])
        w.writerow(["Módulo", "Entradas", "Saídas", "Processos Ativos"])
        w.writerow(["Denúncias", data["denuncias"]["entradas"], data["denuncias"]["saidas"], data["denuncias"]["ativos"]])
        w.writerow(["Notificações", data["notificacoes"]["entradas"], data["notificacoes"]["saidas"], data["notificacoes"]["ativos"]])
        w.writerow(["Autos de Infração", data["aif"]["entradas"], data["aif"]["saidas"], data["aif"]["ativos"]])
        return resp

    return render(request, "relatorios/operacional.html", {"data": data})


# ==========================================================
# Relatório: Pessoa 360
# ==========================================================
from django.db.models import Q
from django.utils.dateparse import parse_date
import csv


@login_required
def relatorio_pessoa_busca(request):
    pref_id = _get_prefeitura_id(request)
    if not pref_id:
        return render(request, "relatorios/pessoa_busca.html", {"erro": "Prefeitura não definida na sessão."})
    q = (request.GET.get("q") or "").strip()
    pessoas = []
    if q:
        qnum = "".join([c for c in q if c.isdigit()])
        base = Pessoa.objects.filter(prefeitura_id=pref_id)
        if qnum:
            pessoas = list(base.filter(Q(doc_num__icontains=qnum) | Q(nome_razao__icontains=q)).order_by("nome_razao")[:50])
        else:
            pessoas = list(base.filter(nome_razao__icontains=q).order_by("nome_razao")[:50])
    return render(request, "relatorios/pessoa_busca.html", {"q": q, "pessoas": pessoas})


def _parse_dates(request):
    d1 = request.GET.get("de") or ""
    d2 = request.GET.get("ate") or ""
    try:
        return (parse_date(d1) if d1 else None, parse_date(d2) if d2 else None)
    except Exception:
        return (None, None)


def _apply_common_filters(qs, tipo, request):
    de, ate = _parse_dates(request)
    if de:
        qs = qs.filter(criada_em__date__gte=de)
    if ate:
        qs = qs.filter(criada_em__date__lte=ate)
    endereco = (request.GET.get("endereco") or "").strip()
    if endereco:
        if tipo == "DEN":
            qs = qs.filter(
                Q(local_oco_logradouro__icontains=endereco)
                | Q(local_oco_bairro__icontains=endereco)
                | Q(local_oco_cidade__icontains=endereco)
            )
        else:
            qs = qs.filter(
                Q(logradouro__icontains=endereco)
                | Q(bairro__icontains=endereco)
                | Q(cidade__icontains=endereco)
            )
    bairro = (request.GET.get("bairro") or "").strip()
    if bairro:
        if tipo == "DEN":
            qs = qs.filter(local_oco_bairro__icontains=bairro)
        else:
            qs = qs.filter(bairro__icontains=bairro)
    fiscal_id = request.GET.get("fiscal")
    if fiscal_id:
        try:
            qs = qs.filter(fiscais__id=int(fiscal_id))
        except Exception:
            pass
    return qs


@login_required
def relatorio_pessoa(request, pessoa_id: int):
    pref_id = _get_prefeitura_id(request)
    if not pref_id:
        return render(request, "relatorios/pessoa_busca.html", {"erro": "Prefeitura não definida na sessão."})
    pessoa = Pessoa.objects.filter(pk=pessoa_id, prefeitura_id=pref_id).first()
    if not pessoa:
        return render(request, "relatorios/pessoa_busca.html", {"erro": "Pessoa não encontrada para esta prefeitura."})

    # Filtros
    tipo = (request.GET.get("tipo") or "ALL").upper()
    tipos = {"DEN", "NTF", "AIF", "ALL"}
    if tipo not in tipos:
        tipo = "ALL"

    # Opções de fiscais no filtro
    fiscais_opts = Usuario.objects.filter(prefeitura_id=pref_id, is_active=True, tipo__iexact="FISCAL").order_by("first_name","last_name","email")

    den = nots = aifs = []
    total_den = total_ntf = total_aif = 0
    # Denúncias
    if tipo in ("ALL", "DEN"):
        den_qs = Denuncia.objects.filter(prefeitura_id=pref_id, pessoa_id=pessoa.id).order_by("-criada_em")
        den_qs = _apply_common_filters(den_qs, "DEN", request)
        den = list(den_qs)
        total_den = len(den)
    # Notificações
    if tipo in ("ALL", "NTF"):
        ntf_qs = Notificacao.objects.filter(prefeitura_id=pref_id, pessoa_id=pessoa.id).exclude(status="CANCELADA").order_by("-criada_em")
        ntf_qs = _apply_common_filters(ntf_qs, "NTF", request)
        nots = list(ntf_qs)
        total_ntf = len(nots)
    # Autos
    if tipo in ("ALL", "AIF"):
        from apps.autoinfracao.models import AutoInfracao
        aif_qs = AutoInfracao.objects.filter(prefeitura_id=pref_id, pessoa_id=pessoa.id).order_by("-criada_em")
        aif_qs = _apply_common_filters(aif_qs, "AIF", request)
        aifs = list(aif_qs)
        total_aif = len(aifs)

    # Totais
    totals = {"den": total_den, "ntf": total_ntf, "aif": total_aif}

    # Prefeitura para exibir logo e cabeçalho
    pref = Prefeitura.objects.filter(pk=pref_id).first()

    return render(request, "relatorios/pessoa_relatorio.html", {
        "pref": pref,
        "pessoa": pessoa,
        "fiscais_opts": fiscais_opts,
        "tipo": tipo,
        "den": den,
        "nots": nots,
        "aifs": aifs,
        "totals": totals,
        "de": request.GET.get("de", ""),
        "ate": request.GET.get("ate", ""),
        "endereco": request.GET.get("endereco", ""),
        "bairro": request.GET.get("bairro", ""),
        "fiscal": request.GET.get("fiscal", ""),
    })


@login_required
def relatorio_pessoa_csv(request, pessoa_id: int):
    pref_id = _get_prefeitura_id(request)
    if not pref_id:
        return HttpResponseBadRequest("Prefeitura não definida.")
    pessoa = Pessoa.objects.filter(pk=pessoa_id, prefeitura_id=pref_id).first()
    if not pessoa:
        return HttpResponseBadRequest("Pessoa não encontrada.")
    tipo = (request.GET.get("tipo") or "DEN").upper()
    if tipo not in {"DEN","NTF","AIF"}:
        tipo = "DEN"

    if tipo == "DEN":
        qs = Denuncia.objects.filter(prefeitura_id=pref_id, pessoa_id=pessoa.id).order_by("-criada_em")
        qs = _apply_common_filters(qs, "DEN", request)
        rows = [
            (
                x.protocolo,
                x.criada_em,
                getattr(x, 'ocorrido_em', None),
                x.get_status_display(),
                x.get_procedencia_display(),
                f"{x.local_oco_logradouro}, {x.local_oco_numero} — {x.local_oco_bairro} — {x.local_oco_cidade}",
            ) for x in qs
        ]
        header = ["Protocolo","Data Registro","Ocorrido em","Status","Procedência","Endereço do Ocorrido"]
        filename = f"pessoa_{pessoa.id}_denuncias.csv"
    elif tipo == "NTF":
        qs = Notificacao.objects.filter(prefeitura_id=pref_id, pessoa_id=pessoa.id).exclude(status="CANCELADA").order_by("-criada_em")
        qs = _apply_common_filters(qs, "NTF", request)
        rows = [
            (
                x.protocolo,
                x.criada_em,
                getattr(x, 'ocorrido_em', None),
                x.get_status_display(),
                x.prazo_regularizacao,
                f"{x.logradouro}, {x.numero} — {x.bairro} — {x.cidade}",
            ) for x in qs
        ]
        header = ["Protocolo","Data Registro","Ocorrido em","Status","Prazo Regularização","Endereço"]
        filename = f"pessoa_{pessoa.id}_notificacoes.csv"
    else:
        from apps.autoinfracao.models import AutoInfracao
        qs = AutoInfracao.objects.filter(prefeitura_id=pref_id, pessoa_id=pessoa.id).order_by("-criada_em")
        qs = _apply_common_filters(qs, "AIF", request)
        rows = [
            (
                x.protocolo,
                x.criada_em,
                getattr(x, 'ocorrido_em', None),
                x.get_status_display(),
                getattr(x, 'valor_multa_aplicada', None),
                x.valor_multa_homologado,
                f"{x.logradouro}, {x.numero} — {x.bairro} — {x.cidade}",
            ) for x in qs
        ]
        header = ["Protocolo","Data Registro","Ocorrido em","Status","Valor Aplicado","Valor Homologado","Endereço"]
        filename = f"pessoa_{pessoa.id}_autos.csv"

    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f"attachment; filename={filename}"
    writer = csv.writer(resp)
    writer.writerow([f"Pessoa: {pessoa.nome_razao}"])
    writer.writerow(header)
    for r in rows:
        writer.writerow(r)
    return resp


@login_required
def relatorio_pessoa_imprimir(request, pessoa_id: int):
    pref_id = _get_prefeitura_id(request)
    if not pref_id:
        return HttpResponseBadRequest("Prefeitura não definida.")
    pessoa = Pessoa.objects.filter(pk=pessoa_id, prefeitura_id=pref_id).first()
    if not pessoa:
        return HttpResponseBadRequest("Pessoa não encontrada.")

    # Filtros e datasets (mesma lógica da tela)
    tipo = (request.GET.get("tipo") or "ALL").upper()
    if tipo not in {"ALL","DEN","NTF","AIF"}:
        tipo = "ALL"
    den = nots = aifs = []
    if tipo in ("ALL","DEN"):
        den_qs = Denuncia.objects.filter(prefeitura_id=pref_id, pessoa_id=pessoa.id).order_by("-criada_em")
        den_qs = _apply_common_filters(den_qs, "DEN", request)
        den = list(den_qs)
    if tipo in ("ALL","NTF"):
        ntf_qs = Notificacao.objects.filter(prefeitura_id=pref_id, pessoa_id=pessoa.id).exclude(status="CANCELADA").order_by("-criada_em")
        ntf_qs = _apply_common_filters(ntf_qs, "NTF", request)
        nots = list(ntf_qs)
    if tipo in ("ALL","AIF"):
        from apps.autoinfracao.models import AutoInfracao
        aif_qs = AutoInfracao.objects.filter(prefeitura_id=pref_id, pessoa_id=pessoa.id).order_by("-criada_em")
        aif_qs = _apply_common_filters(aif_qs, "AIF", request)
        aifs = list(aif_qs)

    pref = Prefeitura.objects.filter(pk=pref_id).first()

    ctx = {
        "pref": pref,
        "pessoa": pessoa,
        "den": den,
        "nots": nots,
        "aifs": aifs,
        "tipo": tipo,
        "de": request.GET.get("de", ""),
        "ate": request.GET.get("ate", ""),
        "endereco": request.GET.get("endereco", ""),
        "bairro": request.GET.get("bairro", ""),
    }
    return render(request, "relatorios/pessoa_relatorio_print.html", ctx)
