from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Value, DecimalField, OuterRef, Subquery
from django.db.models.functions import TruncMonth, Coalesce, Greatest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.utils import timezone
from django.http import HttpResponse
import csv

from .models import AutoInfracao, AutoInfracaoAnexo, Embargo, Interdicao
from .forms import (
    AutoInfracaoCreateForm,
    AutoInfracaoEditForm,
    AutoInfracaoMultaItemForm,
    InfracaoTipoForm,
    EnquadramentoForm,
    EmbargoEditForm,
    InterdicaoEditForm,
    EmbargoAnexoForm,
    InterdicaoAnexoForm,
    AutoInfracaoAnexoForm,
)
from .models import AutoInfracaoMultaItem, Enquadramento, InfracaoTipo
from apps.notificacoes.models import Notificacao
from apps.denuncias.models import Denuncia, DenunciaHistorico
from apps.usuarios.models import Usuario
from apps.cadastros.models import Pessoa, Imovel
from apps.usuarios.audit import log_event
from django.core.files.base import ContentFile
import os



def _get_prefeitura_id(request):
    return request.session.get("prefeitura_id")


@login_required
def listar(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    qs = AutoInfracao.objects.filter(prefeitura_id=prefeitura_id).order_by("-criada_em")

    # filtros básicos
    protocolo = request.GET.get("protocolo", "").strip()
    cpf_cnpj = request.GET.get("cpf_cnpj", "").strip()
    nome_razao = request.GET.get("nome_razao", "").strip()
    endereco = request.GET.get("endereco", "").strip()
    status = request.GET.get("status", "").strip()

    if protocolo:
        qs = qs.filter(protocolo__icontains=protocolo)
    if cpf_cnpj:
        qs = qs.filter(cpf_cnpj__icontains=cpf_cnpj)
    if nome_razao:
        qs = qs.filter(nome_razao__icontains=nome_razao)
    if endereco:
        qs = qs.filter(
            Q(logradouro__icontains=endereco)
            | Q(numero__icontains=endereco)
            | Q(bairro__icontains=endereco)
            | Q(cidade__icontains=endereco)
        )
    if status:
        qs = qs.filter(status=status)

    # Ordenação: crescente por dias de prazo (negativos primeiro, sem prazo no final)
    itens = list(qs)
    def _key(a):
        d = getattr(a, 'dias_restantes', None)
        return d if d is not None else 10**9
    itens.sort(key=_key)
    page_obj = Paginator(itens, 20).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    context = {
        "page_obj": page_obj,
        "filtros": {
            "protocolo": protocolo,
            "cpf_cnpj": cpf_cnpj,
            "nome_razao": nome_razao,
            "endereco": endereco,
            "status": status,
        },
        "status_choices": AutoInfracao._meta.get_field("status").choices,
        "querystring": querystring,
    }
    return render(request, "autoinfracao/listar_autoinfracao.html", context)


@login_required
def relatorio_arrecadacao(request):
    """Arrecadação AIF mensal: Multa aplicada, Homologada e Paga.
    Filtros: período (ano corrente padrão), status (multi), forma_pagamento (multi para pagos). CSV disponível.
    """
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

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
    year_start = today.replace(month=1, day=1)
    d_ini = _parse_date(request.GET.get("inicio")) or year_start
    d_fim = _parse_date(request.GET.get("fim")) or today
    if d_ini > d_fim:
        d_ini, d_fim = d_fim, d_ini
    dt_ini = timezone.make_aware(timezone.datetime(d_ini.year, d_ini.month, d_ini.day, 0, 0))
    dt_fim_ex = timezone.make_aware(timezone.datetime(d_fim.year, d_fim.month, d_fim.day, 0, 0)) + timezone.timedelta(days=1)

    # Filtros extras
    status_list = [s for s in request.GET.getlist('status') if s]
    forma_list = [f for f in request.GET.getlist('forma') if f]

    base = AutoInfracao.objects.filter(prefeitura_id=prefeitura_id)
    if status_list:
        base = base.filter(status__in=status_list)

    # Aplicada (por criada_em) — usa valor_infracao; se nulo, cai no somatório dos itens de multa
    aplicada_qs = base.filter(criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
    dec0 = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
    items_sum_sq = (
        AutoInfracaoMultaItem.objects
        .filter(auto_infracao_id=OuterRef('pk'))
        .values('auto_infracao_id')
        .annotate(s=Coalesce(Sum('valor_unitario'), dec0))
        .values('s')[:1]
    )
    aplicada_qs = aplicada_qs.annotate(
        valor_items=Subquery(items_sum_sq, output_field=DecimalField(max_digits=12, decimal_places=2)),
        valor_aplicado=Greatest(
            Coalesce('valor_infracao', dec0),
            Coalesce('valor_items', dec0),
            Coalesce('valor_multa_homologado', dec0)
        )
    )
    aplicada_month = (
        aplicada_qs
        .annotate(m=TruncMonth('criada_em'))
        .values('m')
        .annotate(v=Coalesce(Sum('valor_aplicado'), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))), q=Count('id'))
    )
    applied_map = { (r['m'].year, r['m'].month): { 'v': r['v'] or 0, 'q': r['q'] } for r in aplicada_month }

    # Homologada (por homologado_em se existir; senão criada_em), apenas com valor_multa_homologado definido
    hom_filter = Q(valor_multa_homologado__isnull=False) & (
        Q(homologado_em__gte=dt_ini, homologado_em__lt=dt_fim_ex) |
        Q(homologado_em__isnull=True, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
    )
    homolog_qs = base.filter(hom_filter)
    homolog_month = (
        homolog_qs
        .annotate(ref_dt=Coalesce('homologado_em', 'criada_em'))
        .annotate(m=TruncMonth('ref_dt'))
        .values('m')
        .annotate(v=Coalesce(Sum('valor_multa_homologado'), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))), q=Count('id'))
    )
    homolog_map = { (r['m'].year, r['m'].month): { 'v': r['v'] or 0, 'q': r['q'] } for r in homolog_month }

    # Pago (por pago_em; pago=True)
    pagos_qs = base.filter(pago=True, pago_em__isnull=False, pago_em__gte=d_ini, pago_em__lte=d_fim)
    if forma_list:
        pagos_qs = pagos_qs.filter(forma_pagamento__in=forma_list)
    pagos_month = (
        pagos_qs
        .annotate(m=TruncMonth('pago_em'))
        .values('m')
        .annotate(v=Coalesce(Sum('valor_pago'), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))), q=Count('id'))
    )
    pagos_map = { (r['m'].year, r['m'].month): { 'v': r['v'] or 0, 'q': r['q'] } for r in pagos_month }

    # Linha do tempo mensal
    months = []
    cur = timezone.datetime(d_ini.year, d_ini.month, 1)
    end = timezone.datetime(d_fim.year, d_fim.month, 1)
    while cur <= end:
        months.append((cur.year, cur.month))
        cur = timezone.datetime(cur.year + (1 if cur.month == 12 else 0), 1 if cur.month == 12 else cur.month + 1, 1)

    # Séries e tabela
    series_labels = [f"{y}-{m:02d}" for (y, m) in months]
    serie_apl = []
    serie_hom = []
    serie_pag = []
    table_rows = []
    total_apl_v = Decimal('0'); total_apl_q = 0
    total_hom_v = Decimal('0'); total_hom_q = 0
    total_pag_v = Decimal('0'); total_pag_q = 0

    for (y, m) in months:
        apl = applied_map.get((y, m), {'v': Decimal('0'), 'q': 0})
        hom = homolog_map.get((y, m), {'v': Decimal('0'), 'q': 0})
        pag = pagos_map.get((y, m), {'v': Decimal('0'), 'q': 0})
        serie_apl.append(float(apl['v'] or 0))
        serie_hom.append(float(hom['v'] or 0))
        serie_pag.append(float(pag['v'] or 0))
        total_apl_v += Decimal(apl['v'] or 0); total_apl_q += apl['q'] or 0
        total_hom_v += Decimal(hom['v'] or 0); total_hom_q += hom['q'] or 0
        total_pag_v += Decimal(pag['v'] or 0); total_pag_q += pag['q'] or 0
        ticket = (Decimal(pag['v'] or 0) / pag['q']) if (pag['q'] or 0) > 0 else Decimal('0')
        table_rows.append({
            'mes': f"{y}-{m:02d}",
            'apl_q': apl['q'] or 0, 'apl_v': apl['v'] or 0,
            'hom_q': hom['q'] or 0, 'hom_v': hom['v'] or 0,
            'pag_q': pag['q'] or 0, 'pag_v': pag['v'] or 0,
            'ticket': ticket,
        })

    # CSV
    if (request.GET.get('format') or '').lower() == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="aif_arrecadacao_mensal.csv"'
        w = csv.writer(resp)
        w.writerow(["Periodo", d_ini.isoformat(), d_fim.isoformat()])
        if status_list:
            w.writerow(["Status", ",".join(status_list)])
        if forma_list:
            w.writerow(["Formas", ",".join(forma_list)])
        w.writerow([])
        w.writerow(["Mes", "Qtd Aplicados", "Valor Multa", "Qtd Homologados", "Valor Homologado", "Qtd Pagos", "Valor Pago", "Ticket Medio Pago"])
        for r in table_rows:
            w.writerow([
                r['mes'], r['apl_q'], f"{Decimal(r['apl_v']):.2f}", r['hom_q'], f"{Decimal(r['hom_v']):.2f}", r['pag_q'], f"{Decimal(r['pag_v']):.2f}", f"{Decimal(r['ticket']):.2f}"
            ])
        w.writerow([])
        tk = (total_pag_v / total_pag_q) if total_pag_q > 0 else Decimal('0')
        w.writerow(["Totais", total_apl_q, f"{total_apl_v:.2f}", total_hom_q, f"{total_hom_v:.2f}", total_pag_q, f"{total_pag_v:.2f}", f"{tk:.2f}"])
        return resp

    status_choices = AutoInfracao._meta.get_field('status').choices
    from utils.choices import PAGAMENTO_FORMA_CHOICES
    ctx = {
        'inicio': d_ini, 'fim': d_fim,
        'status_sel': status_list, 'forma_sel': forma_list,
        'status_choices': status_choices, 'forma_choices': PAGAMENTO_FORMA_CHOICES,
        'labels': series_labels, 'serie_apl': serie_apl, 'serie_hom': serie_hom, 'serie_pag': serie_pag,
        'rows': table_rows,
        'totais': {
            'apl_q': total_apl_q, 'apl_v': total_apl_v,
            'hom_q': total_hom_q, 'hom_v': total_hom_v,
            'pag_q': total_pag_q, 'pag_v': total_pag_v,
            'ticket': (total_pag_v / total_pag_q) if total_pag_q > 0 else Decimal('0'),
        }
    }
    return render(request, "autoinfracao/relatorio_arrecadacao.html", ctx)


@login_required
def relatorio_arrecadacao_print(request):
    """Versão de impressão do relatório de Arrecadação AIF (mensal)."""
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    # Reaproveita a mesma lógica do relatório web (sem CSV)
    # Copiamos o essencial para montar o mesmo contexto 'ctx'
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
    year_start = today.replace(month=1, day=1)
    d_ini = _parse_date(request.GET.get("inicio")) or year_start
    d_fim = _parse_date(request.GET.get("fim")) or today
    if d_ini > d_fim:
        d_ini, d_fim = d_fim, d_ini
    dt_ini = timezone.make_aware(timezone.datetime(d_ini.year, d_ini.month, d_ini.day, 0, 0))
    dt_fim_ex = timezone.make_aware(timezone.datetime(d_fim.year, d_fim.month, d_fim.day, 0, 0)) + timezone.timedelta(days=1)

    status_list = [s for s in request.GET.getlist('status') if s]
    forma_list = [f for f in request.GET.getlist('forma') if f]

    base = AutoInfracao.objects.filter(prefeitura_id=prefeitura_id)
    if status_list:
        base = base.filter(status__in=status_list)

    aplicada_qs = base.filter(criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
    dec0 = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
    items_sum_sq = (
        AutoInfracaoMultaItem.objects
        .filter(auto_infracao_id=OuterRef('pk'))
        .values('auto_infracao_id')
        .annotate(s=Coalesce(Sum('valor_unitario'), dec0))
        .values('s')[:1]
    )
    aplicada_qs = aplicada_qs.annotate(
        valor_items=Subquery(items_sum_sq, output_field=DecimalField(max_digits=12, decimal_places=2)),
        valor_aplicado=Greatest(
            Coalesce('valor_infracao', dec0),
            Coalesce('valor_items', dec0),
            Coalesce('valor_multa_homologado', dec0)
        )
    )
    aplicada_month = (
        aplicada_qs
        .annotate(m=TruncMonth('criada_em'))
        .values('m')
        .annotate(v=Coalesce(Sum('valor_aplicado'), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))), q=Count('id'))
    )
    applied_map = { (r['m'].year, r['m'].month): { 'v': r['v'] or 0, 'q': r['q'] } for r in aplicada_month }

    hom_filter = Q(valor_multa_homologado__isnull=False) & (
        Q(homologado_em__gte=dt_ini, homologado_em__lt=dt_fim_ex) |
        Q(homologado_em__isnull=True, criada_em__gte=dt_ini, criada_em__lt=dt_fim_ex)
    )
    homolog_qs = base.filter(hom_filter)
    homolog_month = (
        homolog_qs
        .annotate(ref_dt=Coalesce('homologado_em', 'criada_em'))
        .annotate(m=TruncMonth('ref_dt'))
        .values('m')
        .annotate(v=Coalesce(Sum('valor_multa_homologado'), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))), q=Count('id'))
    )
    homolog_map = { (r['m'].year, r['m'].month): { 'v': r['v'] or 0, 'q': r['q'] } for r in homolog_month }

    pagos_qs = base.filter(pago=True, pago_em__isnull=False, pago_em__gte=d_ini, pago_em__lte=d_fim)
    if forma_list:
        pagos_qs = pagos_qs.filter(forma_pagamento__in=forma_list)
    pagos_month = (
        pagos_qs
        .annotate(m=TruncMonth('pago_em'))
        .values('m')
        .annotate(v=Coalesce(Sum('valor_pago'), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))), q=Count('id'))
    )
    pagos_map = { (r['m'].year, r['m'].month): { 'v': r['v'] or 0, 'q': r['q'] } for r in pagos_month }

    months = []
    cur = timezone.datetime(d_ini.year, d_ini.month, 1)
    end = timezone.datetime(d_fim.year, d_fim.month, 1)
    while cur <= end:
        months.append((cur.year, cur.month))
        cur = timezone.datetime(cur.year + (1 if cur.month == 12 else 0), 1 if cur.month == 12 else cur.month + 1, 1)

    series_labels = [f"{y}-{m:02d}" for (y, m) in months]
    serie_apl = []
    serie_hom = []
    serie_pag = []
    table_rows = []
    total_apl_v = Decimal('0'); total_apl_q = 0
    total_hom_v = Decimal('0'); total_hom_q = 0
    total_pag_v = Decimal('0'); total_pag_q = 0

    for (y, m) in months:
        apl = applied_map.get((y, m), {'v': Decimal('0'), 'q': 0})
        hom = homolog_map.get((y, m), {'v': Decimal('0'), 'q': 0})
        pag = pagos_map.get((y, m), {'v': Decimal('0'), 'q': 0})
        serie_apl.append(float(apl['v'] or 0))
        serie_hom.append(float(hom['v'] or 0))
        serie_pag.append(float(pag['v'] or 0))
        total_apl_v += Decimal(apl['v'] or 0); total_apl_q += apl['q'] or 0
        total_hom_v += Decimal(hom['v'] or 0); total_hom_q += hom['q'] or 0
        total_pag_v += Decimal(pag['v'] or 0); total_pag_q += pag['q'] or 0
        ticket = (Decimal(pag['v'] or 0) / pag['q']) if (pag['q'] or 0) > 0 else Decimal('0')
        table_rows.append({
            'mes': f"{y}-{m:02d}",
            'apl_q': apl['q'] or 0, 'apl_v': apl['v'] or 0,
            'hom_q': hom['q'] or 0, 'hom_v': hom['v'] or 0,
            'pag_q': pag['q'] or 0, 'pag_v': pag['v'] or 0,
            'ticket': ticket,
        })

    status_choices = AutoInfracao._meta.get_field('status').choices
    from utils.choices import PAGAMENTO_FORMA_CHOICES
    ctx = {
        'inicio': d_ini, 'fim': d_fim,
        'status_sel': status_list, 'forma_sel': forma_list,
        'status_choices': status_choices, 'forma_choices': PAGAMENTO_FORMA_CHOICES,
        'labels': series_labels, 'serie_apl': serie_apl, 'serie_hom': serie_hom, 'serie_pag': serie_pag,
        'rows': table_rows,
        'totais': {
            'apl_q': total_apl_q, 'apl_v': total_apl_v,
            'hom_q': total_hom_q, 'hom_v': total_hom_v,
            'pag_q': total_pag_q, 'pag_v': total_pag_v,
            'ticket': (total_pag_v / total_pag_q) if total_pag_q > 0 else Decimal('0'),
        }
    }
    return render(request, "autoinfracao/imprimir_arrecadacao.html", ctx)


@login_required
def cadastrar(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    if request.method == "POST":
        form = AutoInfracaoCreateForm(request.POST, prefeitura_id=prefeitura_id)
        if form.is_valid():
            obj = form.save(commit=False)
            # Normaliza 'valor_infracao' em caso de entrada com vírgula
            raw_vi = (request.POST.get("valor_infracao") or "").strip()
            if raw_vi and form.cleaned_data.get("valor_infracao") in (None, ""):
                try:
                    from decimal import Decimal
                    s = raw_vi.replace(" ", "")
                    if "," in s and "." in s:
                        s = s.replace(".", "").replace(",", ".")
                    elif "," in s:
                        s = s.replace(",", ".")
                    vi = Decimal(s)
                    obj.valor_infracao = vi
                except Exception:
                    pass
            obj.prefeitura_id = prefeitura_id
            obj.criado_por = request.user
            obj.atualizada_por = request.user
            obj.save()
            log_event(request, 'CREATE', instance=obj)

            # Vincular Processo (herda de NTF/Denúncia quando existir; senão cria)
            try:
                from apps.processos.models import Processo
                proc = None
                if obj.notificacao_id and getattr(obj.notificacao, 'processo_id', None):
                    proc = obj.notificacao.processo
                elif obj.denuncia_id and getattr(obj.denuncia, 'processo_id', None):
                    proc = obj.denuncia.processo
                if proc is None:
                    base_proto = obj.notificacao.protocolo if obj.notificacao_id else (obj.denuncia.protocolo if obj.denuncia_id else obj.protocolo)
                    proc = Processo.objects.create(
                        prefeitura_id=prefeitura_id,
                        protocolo=base_proto,
                        status='ABERTO',
                        criado_por=getattr(request, 'user', None),
                    )
                    # retrovincula etapas anteriores, se houverem
                    if obj.denuncia_id and getattr(obj.denuncia, 'processo_id', None) is None:
                        d = obj.denuncia; d.processo = proc; d.save(update_fields=['processo'])
                    if obj.notificacao_id and getattr(obj.notificacao, 'processo_id', None) is None:
                        n = obj.notificacao; n.processo = proc; n.save(update_fields=['processo'])
                obj.processo = proc
                obj.save(update_fields=['processo'])
            except Exception:
                pass

            # Sugerir vínculos após criação independente
            pessoa_cand = _find_pessoa_candidata(
                prefeitura_id, obj.cpf_cnpj
            )
            imovel_cand = _find_imovel_candidato(
                prefeitura_id,
                logradouro=obj.logradouro,
                numero=obj.numero,
                bairro=obj.bairro,
                cidade=obj.cidade,
                uf=obj.uf,
                latitude=obj.latitude,
                longitude=obj.longitude,
            )

            # vincula M2M
            tipos = form.cleaned_data.get("tipos")
            fiscais = form.cleaned_data.get("fiscais")
            if tipos:
                obj.tipos.set(tipos)
            if fiscais:
                obj.fiscais.set(fiscais)

            # anexos (opcional)
            fotos = request.FILES.getlist("fotos")
            if fotos:
                existentes = obj.anexos.filter(tipo="FOTO").count()
                restante = max(0, 4 - existentes)
                if restante <= 0:
                    messages.warning(request, "Limite de 4 fotos atingido. Nenhuma nova foto foi adicionada.")
                else:
                    count = 0
                    for foto in fotos[:restante]:
                        anexo = AutoInfracaoAnexo(auto_infracao=obj, tipo="FOTO", arquivo=foto)
                        anexo.save(); anexo.processar_arquivo(); anexo.save(); count += 1
                    if len(fotos) > restante:
                        messages.warning(request, f"Apenas {restante} foto(s) foram processadas (limite total de 4).")
                    if count:
                        messages.success(request, f"{count} foto(s) anexada(s) com sucesso.")

            messages.success(request, f"Auto de Infração criado! Protocolo: {obj.protocolo}")
            if (pessoa_cand is not None) or (imovel_cand is not None):
                messages.info(request, "Encontramos possíveis vínculos com cadastros de referência. Confirme abaixo.")
                return redirect("autoinfracao:confirmar_vinculos", pk=obj.pk)
            return redirect(reverse("autoinfracao:detalhe", kwargs={"pk": obj.pk}))
        else:
            messages.error(request, "Erros no formulário. Verifique os campos.")
    else:
        form = AutoInfracaoCreateForm(prefeitura_id=prefeitura_id)

    return render(request, "autoinfracao/cadastrar_autoinfracao.html", {"form": form})


# ---------------------------------------------
# Helpers de detecção de vínculos (AIF)
# ---------------------------------------------
def _norm_doc(doc: str) -> str:
    if not doc:
        return ""
    return "".join([c for c in str(doc) if c.isdigit()])


def _find_pessoa_candidata(prefeitura_id: int, cpf_cnpj: str):
    doc = _norm_doc(cpf_cnpj)
    if not doc:
        return None
    return Pessoa.objects.filter(prefeitura_id=prefeitura_id, doc_num=doc).first()


def _find_imovel_candidato(prefeitura_id: int, *,
                           logradouro: str, numero: str, bairro: str, cidade: str, uf: str,
                           latitude, longitude):
    if all([logradouro, bairro, cidade, uf]) and (numero is not None):
        exact_qs = Imovel.objects.filter(
            prefeitura_id=prefeitura_id,
            logradouro__iexact=(logradouro or ""),
            numero__iexact=(numero or ""),
            bairro__iexact=(bairro or ""),
            cidade__iexact=(cidade or ""),
            uf__iexact=(uf or ""),
        )
        count = exact_qs.count()
        if count == 1:
            return exact_qs.first()
        elif count > 1:
            return None

    try:
        if latitude is not None and longitude is not None:
            lat = float(latitude)
            lng = float(longitude)
            eps = 0.0005
            near_qs = Imovel.objects.filter(
                prefeitura_id=prefeitura_id,
                latitude__isnull=False,
                longitude__isnull=False,
                latitude__gte=lat - eps, latitude__lte=lat + eps,
                longitude__gte=lng - eps, longitude__lte=lng + eps,
            )
            best = None
            best_d2 = None
            for im in near_qs[:50]:
                try:
                    ilat = float(im.latitude)
                    ilng = float(im.longitude)
                    d2 = (ilat - lat) ** 2 + (ilng - lng) ** 2
                    if best is None or d2 < best_d2:
                        best = im
                        best_d2 = d2
                except Exception:
                    continue
            if best is not None:
                return best
    except Exception:
        pass
    return None


@login_required
def confirmar_vinculos(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(AutoInfracao, pk=pk, prefeitura_id=prefeitura_id)

    # Se já possuir vínculos (ou origem), não confirmar
    if obj.pessoa_id or obj.imovel_id or obj.denuncia_id or obj.notificacao_id:
        return redirect("autoinfracao:detalhe", pk=obj.pk)

    pessoa_cand = _find_pessoa_candidata(prefeitura_id, obj.cpf_cnpj)
    imovel_cand = _find_imovel_candidato(
        prefeitura_id,
        logradouro=obj.logradouro,
        numero=obj.numero,
        bairro=obj.bairro,
        cidade=obj.cidade,
        uf=obj.uf,
        latitude=obj.latitude,
        longitude=obj.longitude,
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "skip":
            messages.info(request, "Vínculos não aplicados.")
            return redirect("autoinfracao:detalhe", pk=obj.pk)

        do_pessoa = request.POST.get("link_pessoa") == "on"
        do_imovel = request.POST.get("link_imovel") == "on"
        atualizar = request.POST.get("atualizar_campos") == "on"

        changed_fk = False
        if do_pessoa and pessoa_cand:
            obj.pessoa = pessoa_cand
            changed_fk = True
            if atualizar:
                obj.pessoa_tipo = 'PF' if pessoa_cand.tipo == 'PF' else 'PJ'
                obj.nome_razao = pessoa_cand.nome_razao or obj.nome_razao
                obj.cpf_cnpj = pessoa_cand.doc_num or obj.cpf_cnpj
                obj.telefone = pessoa_cand.telefone or obj.telefone
                obj.email = pessoa_cand.email or obj.email
        if do_imovel and imovel_cand:
            obj.imovel = imovel_cand
            changed_fk = True
            if atualizar:
                obj.cep = imovel_cand.cep or obj.cep
                obj.logradouro = imovel_cand.logradouro or obj.logradouro
                obj.numero = imovel_cand.numero or obj.numero
                obj.complemento = imovel_cand.complemento or obj.complemento
                obj.bairro = imovel_cand.bairro or obj.bairro
                obj.cidade = imovel_cand.cidade or obj.cidade
                obj.uf = imovel_cand.uf or obj.uf
                if imovel_cand.latitude is not None:
                    try:
                        obj.latitude = Decimal(str(imovel_cand.latitude))
                    except Exception:
                        obj.latitude = obj.latitude
                if imovel_cand.longitude is not None:
                    try:
                        obj.longitude = Decimal(str(imovel_cand.longitude))
                    except Exception:
                        obj.longitude = obj.longitude

        if changed_fk or atualizar:
            obj.atualizada_por = request.user
            obj.save()
            messages.success(request, "Vínculos aplicados com sucesso.")
        else:
            messages.info(request, "Nenhuma alteração aplicada.")
        return redirect("autoinfracao:detalhe", pk=obj.pk)

    return render(request, "autoinfracao/confirmar_vinculos.html", {
        "obj": obj,
        "pessoa_cand": pessoa_cand,
        "imovel_cand": imovel_cand,
    })


@login_required
def editar(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(AutoInfracao, pk=pk, prefeitura_id=prefeitura_id)

    # exclusão simples de item via GET
    del_id = request.GET.get("del_item")
    if del_id:
        mi = AutoInfracaoMultaItem.objects.filter(pk=del_id, auto_infracao=obj).first()
        if mi:
            mi.delete()
            # atualizar total homologado do AIF após remoção
            total = sum([
                (it.valor_homologado if it.valor_homologado is not None else it.valor_unitario) or Decimal('0')
                for it in obj.multas.all()
            ])
            obj.valor_multa_homologado = total
            obj.atualizada_por = request.user
            obj.save(update_fields=["valor_multa_homologado", "atualizada_por", "atualizada_em"])
            log_event(request, 'UPDATE', instance=obj, extra={'remove_item': del_id})
        messages.info(request, "Item de multa removido.")
        return redirect(request.path)

    # exclusão de anexo do AIF via GET
    del_ax = request.GET.get("del_aif_anexo")
    if del_ax:
        ax = obj.anexos.filter(pk=del_ax).first()
        if ax:
            ax.delete()
            messages.info(request, "Anexo removido.")
        return redirect(request.path)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_item":
            # Normaliza decimais com vírgula no POST (valor_unitario/valor_homologado)
            _post = request.POST.copy()
            for k in ("valor_unitario", "valor_homologado"):
                raw = (_post.get(k, "") or "").strip()
                if raw:
                    _post[k] = raw.replace(".", "").replace(",", ".")
            item_form = AutoInfracaoMultaItemForm(_post, prefeitura_id=prefeitura_id)
            if item_form.is_valid():
                it = item_form.save(commit=False)
                it.auto_infracao = obj
                # Valor homologado, se vazio, herda o valor da multa
                if it.valor_homologado in (None, ''):
                    it.valor_homologado = it.valor_unitario
                it.save()
                # atualizar total homologado do AIF
                try:
                    total = sum([
                        (mi.valor_homologado if mi.valor_homologado is not None else mi.valor_unitario) or Decimal('0')
                        for mi in obj.multas.all()
                    ])
                    obj.valor_multa_homologado = total
                    obj.atualizada_por = request.user
                    obj.save(update_fields=["valor_multa_homologado", "atualizada_por", "atualizada_em"])
                except Exception:
                    pass
                messages.success(request, "Item de multa adicionado.")
                return redirect(request.path)
            else:
                messages.error(request, "Erro ao adicionar item.")
            form = AutoInfracaoEditForm(instance=obj, prefeitura_id=prefeitura_id)
        elif action == "edit_item":
            # atualizar valor homologado de um item específico
            try:
                item_id = int(request.POST.get("item_id"))
            except Exception:
                messages.error(request, "Item inválido.")
                return redirect(request.path)
            it = obj.multas.filter(id=item_id).first()
            if not it:
                messages.error(request, "Item não encontrado.")
                return redirect(request.path)
            raw_val = (request.POST.get("valor_homologado", "") or "").strip()
            try:
                # aceita vírgula como separador decimal
                val = raw_val.replace(".", "").replace(",", ".") if "," in raw_val else raw_val
                dh = Decimal(val)
                dh = dh.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except (InvalidOperation, ValueError):
                messages.error(request, "Valor homologado inválido.")
                return redirect(request.path)
            it.valor_homologado = dh
            it.save()
            # atualizar total homologado do AIF
            total = sum([
                (mi.valor_homologado if mi.valor_homologado is not None else mi.valor_unitario) or Decimal('0')
                for mi in obj.multas.all()
            ])
            obj.valor_multa_homologado = total
            obj.homologado_por = request.user
            obj.homologado_em = timezone.localtime()
            obj.atualizada_por = request.user
            obj.save(update_fields=["valor_multa_homologado", "homologado_por", "homologado_em", "atualizada_por", "atualizada_em"])
            messages.success(request, "Valor homologado atualizado.")
            return redirect(request.path)
        elif action == "apply_discount":
            # aplicar desconto percentual global sobre todos os itens
            perc = (request.POST.get("desconto_percent", "") or "").strip()
            justificativa = request.POST.get("justificativa", "").strip()
            if not justificativa:
                messages.error(request, "Informe a justificativa para a homologação.")
                return redirect(request.path)
            try:
                # aceita vírgula como separador decimal
                perc_norm = perc.replace(".", "").replace(",", ".") if "," in perc else perc
                p = Decimal(perc_norm)
            except (InvalidOperation, ValueError):
                messages.error(request, "Percentual inválido.")
                return redirect(request.path)
            if p < 0 or p > 100:
                messages.error(request, "Percentual deve estar entre 0 e 100.")
                return redirect(request.path)
            fator = (Decimal('100') - p) / Decimal('100')
            total = Decimal('0')
            for it in obj.multas.all():
                base = it.valor_unitario or Decimal('0')
                novo = (base * fator).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                it.valor_homologado = novo
                it.save()
                total += novo
            obj.valor_multa_homologado = total
            obj.homologado_por = request.user
            obj.homologado_em = timezone.localtime()
            obj.atualizada_por = request.user
            obj.save(update_fields=["valor_multa_homologado", "homologado_por", "homologado_em", "atualizada_por", "atualizada_em"])
            messages.success(request, f"Desconto de {p}% aplicado. Total homologado atualizado.")
            return redirect(request.path)
        elif action == "add_aif_anexo":
            anexo_form = AutoInfracaoAnexoForm(request.POST, request.FILES)
            if anexo_form.is_valid():
                a = anexo_form.save(commit=False)
                a.auto_infracao = obj
                a.save()
                try:
                    if a.tipo == "FOTO":
                        a.processar_arquivo(); a.save()
                except Exception:
                    pass
                messages.success(request, "Anexo incluído ao AIF.")
                return redirect(request.path)
            else:
                messages.error(request, "Erro ao anexar arquivo no AIF.")
            form = AutoInfracaoEditForm(instance=obj, prefeitura_id=prefeitura_id)
        elif action == "regularizar_aif":
            # exige pelo menos um anexo do tipo Alvará
            has_alvara = obj.anexos.filter(tipo__in=["ALVARA_CONSTRUCAO", "ALVARA_FUNCIONAMENTO"]).exists()
            if not has_alvara:
                messages.error(request, "Anexe um Alvará (Construção/Funcionamento) antes de regularizar o AIF.")
                return redirect(request.path)
            obj.status = "REGULARIZADO"
            obj.regularizado_em = timezone.localtime()
            obj.atualizada_por = request.user
            obj.save(update_fields=["status", "regularizado_em", "atualizada_por", "atualizada_em"])
            messages.success(request, "AIF marcado como REGULARIZADO.")
            return redirect(request.path)
        else:
            form = AutoInfracaoEditForm(request.POST, instance=obj, prefeitura_id=prefeitura_id)
            if form.is_valid():
                obj = form.save(commit=False)
                # garantir cópia explícita do prazo (por segurança)
                obj.prazo_regularizacao_data = form.cleaned_data.get("prazo_regularizacao_data")
                # Normaliza 'valor_infracao' (aceita vírgula) e fallback para soma dos itens
                raw_vi = (request.POST.get("valor_infracao") or "").strip()
                vi_clean = form.cleaned_data.get("valor_infracao")
                if vi_clean in (None, "") and raw_vi:
                    try:
                        s = raw_vi.replace(" ", "")
                        if "," in s and "." in s:
                            s = s.replace(".", "").replace(",", ".")
                        elif "," in s:
                            s = s.replace(",", ".")
                        vi_clean = Decimal(s)
                    except Exception:
                        vi_clean = None
                if vi_clean is None:
                    try:
                        vi_clean = obj.total_infracao_itens
                    except Exception:
                        vi_clean = None
                obj.valor_infracao = vi_clean
                obj.atualizada_por = request.user
                obj.save()

                # M2M (força via POST para evitar filtragem do queryset)
                try:
                    tipos_ids = [int(x) for x in request.POST.getlist("tipos")]
                except Exception:
                    tipos_ids = []
                if tipos_ids:
                    obj.tipos.set(InfracaoTipo.objects.filter(pk__in=tipos_ids))
                else:
                    obj.tipos.clear()
                try:
                    fisc_ids = [int(x) for x in request.POST.getlist("fiscais")]
                except Exception:
                    fisc_ids = []
                if fisc_ids:
                    obj.fiscais.set(Usuario.objects.filter(pk__in=fisc_ids, prefeitura_id=prefeitura_id))
                else:
                    obj.fiscais.clear()

                # anexos
                fotos = request.FILES.getlist("fotos")
                if fotos:
                    existentes = obj.anexos.filter(tipo='FOTO').count()
                    restante = max(0, 4 - existentes)
                    if restante <= 0:
                        messages.warning(request, "Limite de 4 fotos atingido. Nenhuma nova foto foi adicionada.")
                    else:
                        count = 0
                        for foto in fotos[:restante]:
                            anexo = AutoInfracaoAnexo(auto_infracao=obj, tipo='FOTO', arquivo=foto)
                            anexo.save(); anexo.processar_arquivo(); anexo.save(); count += 1
                        if len(fotos) > restante:
                            messages.warning(request, f"Apenas {restante} foto(s) foram processadas (limite total de 4).")
                        if count:
                            messages.success(request, f"{count} foto(s) anexada(s) com sucesso.")

                messages.success(request, "Auto de Infração atualizado com sucesso.")
                return redirect(reverse("autoinfracao:detalhe", kwargs={"pk": obj.pk}))
            else:
                messages.error(request, "Erros no formulário. Verifique os campos.")
        item_form = AutoInfracaoMultaItemForm(prefeitura_id=prefeitura_id)
    else:
        form = AutoInfracaoEditForm(instance=obj, prefeitura_id=prefeitura_id)
        item_form = AutoInfracaoMultaItemForm(prefeitura_id=prefeitura_id)
        anexo_aif_form = AutoInfracaoAnexoForm()

    anexos_existentes = obj.anexos.all().order_by("-criada_em")
    try:
        tipos_qs = form.fields["tipos"].queryset
    except Exception:
        tipos_qs = InfracaoTipo.objects.none()
    return render(request, "autoinfracao/editar_autoinfracao.html", {
        "form": form,
        "obj": obj,
        "anexos_existentes": anexos_existentes,
        "itens_multa": obj.multas.all(),
        "item_form": item_form,
        "anexo_aif_form": anexo_aif_form if request.method == "GET" else AutoInfracaoAnexoForm(),
        "tipos_qs": tipos_qs,
    })


# ---------------------------------------------------------------------
# IMPRIMIR AIF (página simples para impressão)
# ---------------------------------------------------------------------
@login_required
def imprimir(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(AutoInfracao, pk=pk, prefeitura_id=prefeitura_id)
    anexos = obj.anexos.all().order_by("-criada_em")
    valor_homologado_total = obj.valor_multa_homologado or obj.total_multa
    # Galeria Hierárquica (AIF + NTF + Denúncia + Apontamentos) sem duplicar
    def _build_denuncia_gallery(den):
        gal = []
        seen = set()
        for fx in den.anexos.filter(tipo='FOTO').order_by('-criada_em'):
            h = fx.hash_sha256 or f"path:{getattr(fx.arquivo, 'name', '')}"
            if h in seen: continue
            seen.add(h)
            gal.append({'url': fx.arquivo.url if fx.arquivo else '', 'label': 'Denúncia', 'id': fx.id, 'owner': 'DEN'})
        try:
            for ap in getattr(den, 'apontamentos').all().order_by('-criado_em'):
                for ax in ap.anexos.all().order_by('-criada_em'):
                    h = ax.hash_sha256 or f"path:{getattr(ax.arquivo, 'name', '')}"
                    if h in seen: continue
                    seen.add(h)
                    gal.append({'url': ax.arquivo.url if ax.arquivo else '', 'label': 'Apontamento', 'id': ax.id, 'owner': 'APONT'})
        except Exception:
            pass
        return gal

    galeria = []
    seen_all = set()
    if obj.notificacao_id:
        # incluir galeria da notificação (que por sua vez herda da denúncia)
        try:
            # Reaproveita a função de detalhe da notificação? Simulamos aqui
            n = obj.notificacao
            # Denúncia
            if n.denuncia_id:
                for it in _build_denuncia_gallery(n.denuncia):
                    h = it.get('hash') or it.get('url')
                    if h in seen_all: continue
                    seen_all.add(h); galeria.append(it)
            # Próprias da notificação
            for nx in n.anexos.filter(tipo='FOTO').order_by('-criada_em'):
                h = nx.hash_sha256 or f"path:{getattr(nx.arquivo, 'name', '')}"
                if h in seen_all: continue
                seen_all.add(h); galeria.append({'url': nx.arquivo.url if nx.arquivo else '', 'label': 'Notificação'})
        except Exception:
            pass
    elif obj.denuncia_id:
        for it in _build_denuncia_gallery(obj.denuncia):
            h = it.get('hash') or it.get('url')
            if h in seen_all: continue
            seen_all.add(h); galeria.append(it)

    # Próprias do AIF
    for ax in anexos.filter(tipo='FOTO'):
        h = ax.hash_sha256 or f"path:{getattr(ax.arquivo, 'name', '')}"
        if h in seen_all: continue
        seen_all.add(h)
        galeria.append({'url': ax.arquivo.url if ax.arquivo else '', 'label': 'AIF', 'id': ax.id, 'owner': 'AIF'})

    ctx = {
        "obj": obj,
        "anexos": anexos,
        "denuncia": obj.denuncia,
        "notificacao": obj.notificacao,
        "valor_homologado_total": valor_homologado_total,
        "galeria": galeria,
    }
    log_event(request, 'PRINT', instance=obj)
    return render(request, "autoinfracao/imprimir_autoinfracao.html", ctx)


@login_required
def medidas_listar(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    # Geração rápida a partir de protocolo do AIF
    if request.method == "POST":
        proto = (request.POST.get("aif_protocolo") or "").strip()
        tipo_gen = (request.POST.get("tipo") or "").upper().strip()  # EMB ou ITD
        if not proto:
            messages.error(request, "Informe o protocolo do AIF.")
            return redirect(request.path)
        aif = AutoInfracao.objects.filter(prefeitura_id=prefeitura_id, protocolo__iexact=proto).first()
        if not aif:
            messages.error(request, "AIF não encontrado para este protocolo.")
            return redirect(request.path)
        if aif.status == "REGULARIZADO":
            messages.info(request, "AIF já regularizado — não é possível gerar medida.")
            return redirect(request.path)
        if tipo_gen == "EMB":
            return redirect(reverse("autoinfracao:gerar_embargo", kwargs={"aif_pk": aif.pk}))
        elif tipo_gen == "ITD":
            return redirect(reverse("autoinfracao:gerar_interdicao", kwargs={"aif_pk": aif.pk}))
        else:
            messages.error(request, "Tipo inválido. Escolha Embargo ou Interdição.")
            return redirect(request.path)

    tipo = request.GET.get("tipo", "").upper().strip()  # EMB, ITD ou vazio
    protocolo = request.GET.get("protocolo", "").strip()
    status = request.GET.get("status", "").strip()
    nome_razao = request.GET.get("nome_razao", "").strip()

    emb_qs = Embargo.objects.filter(prefeitura_id=prefeitura_id)
    it_qs = Interdicao.objects.filter(prefeitura_id=prefeitura_id)

    if protocolo:
        emb_qs = emb_qs.filter(protocolo__icontains=protocolo)
        it_qs = it_qs.filter(protocolo__icontains=protocolo)
    if status:
        emb_qs = emb_qs.filter(status=status)
        it_qs = it_qs.filter(status=status)
    if nome_razao:
        emb_qs = emb_qs.filter(auto_infracao__nome_razao__icontains=nome_razao)
        it_qs = it_qs.filter(auto_infracao__nome_razao__icontains=nome_razao)

    items = []
    if tipo in ("", "EMB"):
        for e in emb_qs:
            items.append({"tipo": "EMB", "obj": e, "data": e.criada_em})
    if tipo in ("", "ITD"):
        for i in it_qs:
            items.append({"tipo": "ITD", "obj": i, "data": i.criada_em})

    items.sort(key=lambda x: x["data"], reverse=True)

    page_obj = Paginator(items, 20).get_page(request.GET.get("page"))
    params = request.GET.copy(); params.pop('page', None); querystring = params.urlencode()
    status_choices = Embargo._meta.get_field("status").choices

    context = {
        "page_obj": page_obj,
        "status_choices": status_choices,
        "filtros": {
            "tipo": tipo,
            "protocolo": protocolo,
            "status": status,
            "nome_razao": nome_razao,
        },
        "querystring": querystring,
    }
    return render(request, "autoinfracao/listar_medidas.html", context)


@login_required
def detalhe(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(AutoInfracao, pk=pk, prefeitura_id=prefeitura_id)
    anexos = obj.anexos.all().order_by("-criada_em")

    # Galeria Hierárquica (AIF + NTF + Denúncia + Apontamentos) sem duplicar
    def _build_denuncia_gallery(den):
        gal = []
        seen = set()
        for fx in den.anexos.filter(tipo='FOTO').order_by('-criada_em'):
            h = fx.hash_sha256 or f"path:{getattr(fx.arquivo, 'name', '')}"
            if h in seen:
                continue
            seen.add(h)
            gal.append({'url': fx.arquivo.url if fx.arquivo else '', 'label': 'Denúncia'})
        try:
            for ap in getattr(den, 'apontamentos').all().order_by('-criado_em'):
                for ax in ap.anexos.all().order_by('-criada_em'):
                    h = ax.hash_sha256 or f"path:{getattr(ax.arquivo, 'name', '')}"
                    if h in seen:
                        continue
                    seen.add(h)
                    gal.append({'url': ax.arquivo.url if ax.arquivo else '', 'label': 'Apontamento'})
        except Exception:
            pass
        return gal

    galeria = []
    seen_all = set()
    if obj.notificacao_id:
        try:
            n = obj.notificacao
            if n.denuncia_id:
                for it in _build_denuncia_gallery(n.denuncia):
                    key = it.get('url')
                    if key in seen_all:
                        continue
                    seen_all.add(key)
                    galeria.append(it)
            for nx in n.anexos.filter(tipo='FOTO').order_by('-criada_em'):
                h = nx.hash_sha256 or f"path:{getattr(nx.arquivo, 'name', '')}"
                if h in seen_all:
                    continue
                seen_all.add(h)
                galeria.append({'url': nx.arquivo.url if nx.arquivo else '', 'label': 'Notificação'})
        except Exception:
            pass
    elif obj.denuncia_id:
        for it in _build_denuncia_gallery(obj.denuncia):
            key = it.get('url')
            if key in seen_all:
                continue
            seen_all.add(key)
            galeria.append(it)

    # Próprias do AIF
    for ax in anexos.filter(tipo='FOTO'):
        h = ax.hash_sha256 or f"path:{getattr(ax.arquivo, 'name', '')}"
        if h in seen_all:
            continue
        seen_all.add(h)
        galeria.append({'url': ax.arquivo.url if ax.arquivo else '', 'label': 'AIF'})

    return render(request, "autoinfracao/detalhe_autoinfracao.html", {"obj": obj, "anexos": anexos, "galeria": galeria})


@login_required
def gerar_embargo(request, aif_pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    aif = get_object_or_404(AutoInfracao, pk=aif_pk, prefeitura_id=prefeitura_id)
    if aif.status == "REGULARIZADO":
        messages.info(request, "AIF já regularizado — não é possível gerar Embargo.")
        return redirect("autoinfracao:detalhe", pk=aif.pk)
    emb = Embargo(
        prefeitura_id=prefeitura_id,
        auto_infracao=aif,
        criado_por=request.user,
        atualizada_por=request.user,
    )
    # Default sugerido: 10 dias (pode ser alterado depois)
    try:
        emb.prazo_regularizacao_data = (timezone.localdate() + timedelta(days=10))
    except Exception:
        pass
    emb.save()
    messages.success(request, f"Embargo gerado: {emb.protocolo}")
    return redirect("autoinfracao:embargo_detalhe", pk=emb.pk)


@login_required
def gerar_interdicao(request, aif_pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    aif = get_object_or_404(AutoInfracao, pk=aif_pk, prefeitura_id=prefeitura_id)
    if aif.status == "REGULARIZADO":
        messages.info(request, "AIF já regularizado — não é possível gerar Interdição.")
        return redirect("autoinfracao:detalhe", pk=aif.pk)
    it = Interdicao(
        prefeitura_id=prefeitura_id,
        auto_infracao=aif,
        motivo_tipo="FUNCIONAMENTO",
        criado_por=request.user,
        atualizada_por=request.user,
    )
    it.save()
    messages.success(request, f"Interdição gerada: {it.protocolo}")
    return redirect("autoinfracao:interdicao_detalhe", pk=it.pk)


@login_required
def embargo_detalhe(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(Embargo, pk=pk, prefeitura_id=prefeitura_id)
    return render(request, "autoinfracao/detalhe_embargo.html", {"obj": obj})


@login_required
def interdicao_detalhe(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(Interdicao, pk=pk, prefeitura_id=prefeitura_id)
    return render(request, "autoinfracao/detalhe_interdicao.html", {"obj": obj})


@login_required
def embargo_editar(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(Embargo, pk=pk, prefeitura_id=prefeitura_id)

    # excluir anexo via GET
    del_id = request.GET.get("del_anexo")
    if del_id:
        an = obj.anexos.filter(pk=del_id).first()
        if an:
            an.delete()
            messages.info(request, "Anexo removido.")
        return redirect(request.path)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_anexo":
            anexo_form = EmbargoAnexoForm(request.POST, request.FILES)
            if anexo_form.is_valid():
                an = anexo_form.save(commit=False)
                an.embargo = obj
                an.save()
                # processar apenas fotos
                try:
                    if an.tipo == "FOTO":
                        an.processar_arquivo(); an.save()
                except Exception:
                    pass
                messages.success(request, "Anexo adicionado.")
                return redirect(request.path)
            else:
                messages.error(request, "Erro ao anexar arquivo.")
            form = EmbargoEditForm(instance=obj)
        elif action == "regularizar":
            # Requer ao menos um anexo de Alvará de Construção/Regularização
            has_alvara = obj.anexos.filter(tipo="ALVARA_CONSTRUCAO").exists()
            if not has_alvara:
                messages.error(request, "Anexe um Alvará de Construção/Regularização antes de regularizar.")
                return redirect(request.path)
            obj.status = "REGULARIZADO"
            obj.atualizada_por = request.user
            obj.save(update_fields=["status", "atualizada_por", "atualizada_em"])
            messages.success(request, "Embargo marcado como REGULARIZADO.")
            return redirect(request.path)
        else:
            form = EmbargoEditForm(request.POST, instance=obj)
            if form.is_valid():
                o = form.save(commit=False)
                o.atualizada_por = request.user
                o.save()
                log_event(request, 'UPDATE', instance=o)
                messages.success(request, "Embargo atualizado.")
                return redirect(request.path)
            else:
                messages.error(request, "Erros no formulário.")
        anexo_form = EmbargoAnexoForm()
    else:
        form = EmbargoEditForm(instance=obj)
        anexo_form = EmbargoAnexoForm()

    return render(request, "autoinfracao/editar_embargo.html", {
        "obj": obj,
        "form": form,
        "anexos": obj.anexos.all().order_by("-criada_em"),
        "anexo_form": anexo_form,
    })


@login_required
def interdicao_editar(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(Interdicao, pk=pk, prefeitura_id=prefeitura_id)

    del_id = request.GET.get("del_anexo")
    if del_id:
        an = obj.anexos.filter(pk=del_id).first()
        if an:
            an.delete()
            messages.info(request, "Anexo removido.")
        return redirect(request.path)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_anexo":
            anexo_form = InterdicaoAnexoForm(request.POST, request.FILES)
            if anexo_form.is_valid():
                an = anexo_form.save(commit=False)
                an.interdicao = obj
                an.save()
                try:
                    if an.tipo == "FOTO":
                        an.processar_arquivo(); an.save()
                except Exception:
                    pass
                messages.success(request, "Anexo adicionado.")
                return redirect(request.path)
            else:
                messages.error(request, "Erro ao anexar arquivo.")
            form = InterdicaoEditForm(instance=obj)
        elif action == "regularizar":
            has_alvara = obj.anexos.filter(tipo="ALVARA_FUNCIONAMENTO").exists()
            if not has_alvara:
                messages.error(request, "Anexe um Alvará de Funcionamento antes de regularizar.")
                return redirect(request.path)
            obj.status = "REGULARIZADO"
            obj.atualizada_por = request.user
            obj.save(update_fields=["status", "atualizada_por", "atualizada_em"])
            messages.success(request, "Interdição marcada como REGULARIZADO.")
            return redirect(request.path)
        else:
            form = InterdicaoEditForm(request.POST, instance=obj)
            if form.is_valid():
                o = form.save(commit=False)
                o.atualizada_por = request.user
                o.save()
                messages.success(request, "Interdição atualizada.")
                return redirect(request.path)
            else:
                messages.error(request, "Erros no formulário.")
        anexo_form = InterdicaoAnexoForm()
    else:
        form = InterdicaoEditForm(instance=obj)
        anexo_form = InterdicaoAnexoForm()

    return render(request, "autoinfracao/editar_interdicao.html", {
        "obj": obj,
        "form": form,
        "anexos": obj.anexos.all().order_by("-criada_em"),
        "anexo_form": anexo_form,
    })


# Vínculos via UI
@login_required
def vincular_pessoa(request, pk):
    pref_id = request.session.get("prefeitura_id")
    if not pref_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")
    obj = get_object_or_404(AutoInfracao, pk=pk, prefeitura_id=pref_id)
    if request.method != "POST":
        return redirect("autoinfracao:detalhe", pk=pk)
    tipo = (request.POST.get("tipo") or "PF").upper()
    nome = (request.POST.get("nome_razao") or obj.nome_razao or "").strip()
    doc_tipo = (request.POST.get("doc_tipo") or "OUTRO").upper()
    doc_num = (request.POST.get("doc_num") or "").strip()
    email = (request.POST.get("email") or obj.email or "").strip()
    telefone = (request.POST.get("telefone") or obj.telefone or "").strip()
    pessoa = None
    if doc_num:
        pessoa = Pessoa.objects.filter(prefeitura_id=pref_id, doc_num=''.join(filter(str.isdigit, doc_num))).first()
    if not pessoa:
        pessoa = Pessoa.objects.create(
            prefeitura_id=pref_id,
            tipo=tipo if tipo in ("PF","PJ") else "PF",
            nome_razao=nome,
            doc_tipo=doc_tipo if doc_tipo in ("CPF","CNPJ","OUTRO") else "OUTRO",
            doc_num=''.join(filter(str.isdigit, doc_num)),
            email=email,
            telefone=telefone,
            ativo=True,
        )
    obj.pessoa = pessoa
    obj.save(update_fields=["pessoa"])
    log_event(request, 'LINK', instance=obj, extra={'pessoa_id': pessoa.id})
    messages.success(request, "Pessoa vinculada ao AIF.")
    return redirect("autoinfracao:detalhe", pk=pk)


@login_required
def vincular_imovel(request, pk):
    pref_id = request.session.get("prefeitura_id")
    if not pref_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")
    obj = get_object_or_404(AutoInfracao, pk=pk, prefeitura_id=pref_id)
    if request.method != "POST":
        return redirect("autoinfracao:detalhe", pk=pk)
    inscricao = (request.POST.get("inscricao") or "").strip()
    logradouro = (request.POST.get("logradouro") or obj.logradouro or "").strip() or "ENDERECO DESCONHECIDO"
    numero = (request.POST.get("numero") or obj.numero or "").strip()
    complemento = (request.POST.get("complemento") or obj.complemento or "").strip()
    bairro = (request.POST.get("bairro") or obj.bairro or "").strip()
    cidade = (request.POST.get("cidade") or obj.cidade or "").strip()
    uf = (request.POST.get("uf") or obj.uf or "CE").strip()
    cep = (request.POST.get("cep") or obj.cep or "").strip()
    imovel = None
    if inscricao:
        imovel = Imovel.objects.filter(prefeitura_id=pref_id, inscricao=inscricao).first()
    if not imovel:
        imovel = Imovel.objects.create(
            prefeitura_id=pref_id,
            inscricao=inscricao,
            logradouro=logradouro,
            numero=numero,
            complemento=complemento,
            bairro=bairro,
            cidade=cidade,
            uf=uf,
            cep=cep,
            ativo=True,
        )
    obj.imovel = imovel
    obj.save(update_fields=["imovel"])
    log_event(request, 'LINK', instance=obj, extra={'imovel_id': imovel.id})
    messages.success(request, "Imóvel vinculado ao AIF.")
    return redirect("autoinfracao:detalhe", pk=pk)


@login_required
def gerar_de_notificacao(request, notif_pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    notif = Notificacao.objects.filter(pk=notif_pk, prefeitura_id=prefeitura_id).first()
    if not notif:
        messages.error(request, "Notificação não encontrada para esta prefeitura.")
        return redirect("notificacoes:listar")

    # se já existir AIF para esta notificação, redireciona
    existente = AutoInfracao.objects.filter(notificacao_id=notif.pk, prefeitura_id=prefeitura_id).first()
    if existente:
        messages.info(request, "Já existe Auto de Infração para esta Notificação.")
        return redirect("autoinfracao:editar", pk=existente.pk)

    obj = AutoInfracao(
        prefeitura_id=prefeitura_id,
        notificacao=notif,
        denuncia=notif.denuncia,
        pessoa_tipo=notif.pessoa_tipo,
        nome_razao=notif.nome_razao,
        cpf_cnpj=notif.cpf_cnpj,
        rg=notif.rg,
        telefone=notif.telefone,
        email=notif.email,
        cep=notif.cep,
        logradouro=notif.logradouro,
        numero=notif.numero,
        complemento=notif.complemento,
        bairro=notif.bairro,
        cidade=notif.cidade,
        uf=notif.uf,
        latitude=notif.latitude,
        longitude=notif.longitude,
        descricao=notif.descricao,
        area_m2=getattr(notif, 'area_m2', None),
        testada_m=getattr(notif, 'testada_m', None),
        pe_direito_m=getattr(notif, 'pe_direito_m', None),
        duplex=getattr(notif, 'duplex', False),
        qtd_comodos=getattr(notif, 'qtd_comodos', None),
        compartimentacao=getattr(notif, 'compartimentacao', False),
        divisorias=getattr(notif, 'divisorias', False),
        mezanino=getattr(notif, 'mezanino', False),
        area_mezanino_m2=getattr(notif, 'area_mezanino_m2', None),
        criado_por=request.user,
        atualizada_por=request.user,
    )
    obj.save()
    # Copiar fotos da Notificação para o AIF
    try:
        count = 0
        for a in notif.anexos.all():
            if a.tipo != "FOTO" or not a.arquivo:
                continue
            a.arquivo.open("rb"); data = a.arquivo.read(); a.arquivo.close()
            filename = os.path.basename(a.arquivo.name)
            novo = AutoInfracaoAnexo(auto_infracao=obj, tipo="FOTO")
            novo.arquivo.save(filename, ContentFile(data), save=True)
            novo.processar_arquivo(); novo.save(); count += 1
        if count:
            messages.success(request, f"{count} foto(s) copiadas da Notificação.")
    except Exception as e:
        messages.warning(request, f"Falha ao copiar fotos: {e}")
    messages.success(request, f"Auto de Infração criado a partir da Notificação {notif.protocolo}.")
    return redirect("autoinfracao:editar", pk=obj.pk)


# ======= Catálogos (por prefeitura) =======

@login_required
def gerar_de_denuncia(request, den_pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    den = Denuncia.objects.filter(pk=den_pk, prefeitura_id=prefeitura_id).first()
    if not den:
        messages.error(request, "Denúncia não encontrada para esta prefeitura.")
        return redirect("denuncias:listar")

    existente = AutoInfracao.objects.filter(denuncia_id=den.pk, prefeitura_id=prefeitura_id).first()
    if existente:
        messages.info(request, "Já existe Auto de Infração para esta Denúncia.")
        return redirect("autoinfracao:editar", pk=existente.pk)

    obj = AutoInfracao(
        prefeitura_id=prefeitura_id,
        denuncia=den,
        pessoa_tipo=den.denunciado_tipo_pessoa,
        nome_razao=den.denunciado_nome_razao,
        cpf_cnpj=den.denunciado_cpf_cnpj,
        rg=den.denunciado_rg_ie,
        telefone=den.denunciado_telefone,
        email=den.denunciado_email,
        cep=den.local_oco_cep,
        logradouro=den.local_oco_logradouro,
        numero=den.local_oco_numero,
        complemento=den.local_oco_complemento,
        bairro=den.local_oco_bairro,
        cidade=den.local_oco_cidade,
        uf=den.local_oco_uf,
        latitude=den.local_oco_lat,
        longitude=den.local_oco_lng,
        descricao=den.descricao_oco,
        criado_por=request.user,
        atualizada_por=request.user,
    )
    obj.save()
    # Ao gerar AIF diretamente da Denúncia, marcar a Denúncia como PROCEDE + histórico
    try:
        if getattr(den, 'procedencia', None) != 'PROCEDE':
            den.procedencia = 'PROCEDE'
            den.save(update_fields=['procedencia'])
            try:
                xff = request.META.get('HTTP_X_FORWARDED_FOR')
                ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
            except Exception:
                ip = None
            DenunciaHistorico.objects.create(
                denuncia=den,
                acao='ALTERACAO_PROCEDENCIA',
                descricao='Procedência marcada PROCEDE ao gerar Auto de Infração.',
                feito_por=getattr(request, 'user', None),
                ip_origem=ip,
            )
    except Exception:
        pass
    # Copiar fotos da Denúncia para o AIF
    try:
        count = 0
        for a in den.anexos.all():
            if a.tipo != "FOTO" or not a.arquivo:
                continue
            a.arquivo.open("rb"); data = a.arquivo.read(); a.arquivo.close()
            filename = os.path.basename(a.arquivo.name)
            novo = AutoInfracaoAnexo(auto_infracao=obj, tipo="FOTO")
            novo.arquivo.save(filename, ContentFile(data), save=True)
            novo.processar_arquivo(); novo.save(); count += 1
        if count:
            messages.success(request, f"{count} foto(s) copiadas da Denúncia.")
    except Exception as e:
        messages.warning(request, f"Falha ao copiar fotos: {e}")
    messages.success(request, f"Auto de Infração criado a partir da Denúncia {den.protocolo}.")
    return redirect("autoinfracao:editar", pk=obj.pk)

@login_required
def tipos_listar(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return redirect("/")
    qs = InfracaoTipo.objects.filter(prefeitura_id=prefeitura_id).order_by("nome")
    return render(request, "autoinfracao/tipos_listar.html", {"page_obj": qs})


@login_required
def tipos_novo(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return redirect("/")
    if request.method == "POST":
        form = InfracaoTipoForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.prefeitura_id = prefeitura_id
            obj.save()
            messages.success(request, "Tipo de infração criado.")
            return redirect("autoinfracao:tipos_listar")
    else:
        form = InfracaoTipoForm()
    return render(request, "autoinfracao/tipos_form.html", {"form": form, "title": "Novo Tipo de Infração"})


@login_required
def tipos_editar(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return redirect("/")
    obj = get_object_or_404(InfracaoTipo, pk=pk, prefeitura_id=prefeitura_id)
    if request.method == "POST":
        form = InfracaoTipoForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Tipo de infração atualizado.")
            return redirect("autoinfracao:tipos_listar")
    else:
        form = InfracaoTipoForm(instance=obj)
    return render(request, "autoinfracao/tipos_form.html", {"form": form, "title": "Editar Tipo de Infração"})


@login_required
def enq_listar(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return redirect("/")
    qs = Enquadramento.objects.filter(prefeitura_id=prefeitura_id).order_by("descricao")
    return render(request, "autoinfracao/enq_listar.html", {"page_obj": qs})


@login_required
def enq_novo(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return redirect("/")
    if request.method == "POST":
        form = EnquadramentoForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.prefeitura_id = prefeitura_id
            obj.save()
            messages.success(request, "Enquadramento criado.")
            return redirect("autoinfracao:enq_listar")
    else:
        form = EnquadramentoForm()
    return render(request, "autoinfracao/enq_form.html", {"form": form, "title": "Novo Enquadramento"})


@login_required
def enq_editar(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        return redirect("/")
    obj = get_object_or_404(Enquadramento, pk=pk, prefeitura_id=prefeitura_id)
    if request.method == "POST":
        form = EnquadramentoForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Enquadramento atualizado.")
            return redirect("autoinfracao:enq_listar")
    else:
        form = EnquadramentoForm(instance=obj)
    return render(request, "autoinfracao/enq_form.html", {"form": form, "title": "Editar Enquadramento"})
