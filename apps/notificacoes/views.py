# apps/notificacoes/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import Notificacao, NotificacaoAnexo
from apps.autoinfracao.models import AutoInfracao
from apps.denuncias.models import Denuncia, DenunciaHistorico
from django.core.files.base import ContentFile
import os
from .forms import NotificacaoCreateForm, NotificacaoEditForm
from apps.cadastros.models import Pessoa, Imovel
from decimal import Decimal
from apps.usuarios.audit import log_event


# ---------------------------------------------
# Helpers de detecção de vínculos candidatos
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
    # 1) Match por endereço exato (case-insensitive)
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
            # Ambíguo — não retornar candidato único
            return None

    # 2) Aproximação por geo (raio ~50m)
    try:
        if latitude is not None and longitude is not None:
            lat = float(latitude)
            lng = float(longitude)
            eps = 0.0005  # ~55m
            near_qs = Imovel.objects.filter(
                prefeitura_id=prefeitura_id,
                latitude__isnull=False,
                longitude__isnull=False,
                latitude__gte=lat - eps, latitude__lte=lat + eps,
                longitude__gte=lng - eps, longitude__lte=lng + eps,
            )
            # escolher o mais próximo
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


def _get_prefeitura_id(request):
    return request.session.get("prefeitura_id")


def _normalize_decimal_inputs(data):
    """Normaliza vírgulas/formatos para ponto decimal em campos decimais do formulário.
    Modifica o dict 'data' in-place (QueryDict mutável)."""
    def norm(v):
        if v in (None, ""):
            return v
        s = str(v).strip().replace(" ", "")
        has_dot = "." in s
        has_comma = "," in s
        if has_comma and has_dot:
            # Assume padrão BR: ponto como milhar, vírgula como decimal
            s = s.replace(".", "").replace(",", ".")
        elif has_comma and not has_dot:
            # Apenas vírgula, tratar como decimal
            s = s.replace(",", ".")
        else:
            # Apenas ponto ou nenhum separador — manter
            s = s
        return s
    for key in [
        "latitude", "longitude",
        "area_m2", "testada_m", "pe_direito_m", "area_mezanino_m2",
    ]:
        if key in data:
            data[key] = norm(data.get(key))


@login_required
def listar(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    qs = Notificacao.objects.filter(prefeitura_id=prefeitura_id).order_by("-criada_em")

    # filtros
    protocolo = request.GET.get("protocolo", "").strip()
    cpf_cnpj = request.GET.get("cpf_cnpj", "").strip()
    nome_razao = request.GET.get("nome_razao", "").strip()
    rg = request.GET.get("rg", "").strip()
    telefone = request.GET.get("telefone", "").strip()
    endereco = request.GET.get("endereco", "").strip()
    status = request.GET.get("status", "").strip()
    # campo de ponto de referência removido do filtro/listagem

    if protocolo: qs = qs.filter(protocolo__icontains=protocolo)
    if cpf_cnpj: qs = qs.filter(cpf_cnpj__icontains=cpf_cnpj)
    if nome_razao: qs = qs.filter(nome_razao__icontains=nome_razao)
    if rg: qs = qs.filter(rg__icontains=rg)
    if telefone: qs = qs.filter(telefone__icontains=telefone)
    if endereco:
        qs = qs.filter(
            Q(logradouro__icontains=endereco)
            | Q(numero__icontains=endereco)
            | Q(bairro__icontains=endereco)
            | Q(cidade__icontains=endereco)
        )
    if status: qs = qs.filter(status=status)

    # Ordenação: crescente por dias de prazo (negativos primeiro, sem prazo no final)
    itens = list(qs)
    def _key(n):
        d = getattr(n, 'dias_restantes', None)
        return d if d is not None else 10**9
    itens.sort(key=_key)
    page_obj = Paginator(itens, 20).get_page(request.GET.get("page"))

    # Monta querystring sem o parâmetro 'page' para paginação estável
    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    context = {
        "page_obj": page_obj,
        "filtros": {
            "protocolo": protocolo, "cpf_cnpj": cpf_cnpj, "nome_razao": nome_razao,
            "rg": rg, "telefone": telefone, "endereco": endereco, "status": status,
        },
        "status_choices": Notificacao._meta.get_field("status").choices,
        "querystring": querystring,
    }
    return render(request, "notificacoes/listar_notificacoes.html", context)


@login_required
def criar(request):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    if request.method == "POST":
        data = request.POST.copy()
        _normalize_decimal_inputs(data)
        form = NotificacaoCreateForm(data)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.prefeitura_id = prefeitura_id
            obj.criado_por = request.user
            obj.atualizada_por = request.user
            obj.save()
            log_event(request, 'CREATE', instance=obj)

            # Vincular Processo (raiz = etapa que nasceu primeiro)
            try:
                from apps.processos.models import Processo
                proc = None
                # Se vier de Denúncia (form pode carregar denuncia_id), tenta herdar
                if getattr(obj, 'denuncia_id', None) and getattr(obj.denuncia, 'processo_id', None):
                    proc = obj.denuncia.processo
                if proc is None:
                    proc = Processo.objects.create(
                        prefeitura_id=prefeitura_id,
                        protocolo=(obj.denuncia.protocolo if getattr(obj, 'denuncia_id', None) else obj.protocolo),
                        status='ABERTO',
                        criado_por=getattr(request, 'user', None),
                    )
                    if getattr(obj, 'denuncia_id', None) and getattr(obj.denuncia, 'processo_id', None) is None:
                        den = obj.denuncia
                        den.processo = proc
                        den.save(update_fields=['processo'])
                obj.processo = proc
                obj.save(update_fields=['processo'])
            except Exception:
                pass

            # Tenta sugerir vínculos (somente em criação independente)
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

            # Upload direto do request.FILES
            fotos = request.FILES.getlist("fotos")
            if fotos:
                existentes = obj.anexos.filter(tipo="FOTO").count()
                restante = max(0, 4 - existentes)
                if restante <= 0:
                    messages.warning(request, "Limite de 4 fotos atingido. Nenhuma nova foto foi adicionada.")
                else:
                    count = 0
                    for foto in fotos[:restante]:
                        anexo = NotificacaoAnexo(notificacao=obj, tipo="FOTO", arquivo=foto)
                        anexo.save(); anexo.processar_arquivo(); anexo.save(); count += 1
                    if len(fotos) > restante:
                        messages.warning(request, f"Apenas {restante} foto(s) foram processadas (limite total de 4).")
                    if count:
                        messages.success(request, f"{count} foto(s) anexada(s) com sucesso.")

            messages.success(request, f"Notificação criada com sucesso! Protocolo: {obj.protocolo}")

            # Se houver candidatos, solicita confirmação de vínculos
            if (pessoa_cand is not None) or (imovel_cand is not None):
                messages.info(request, "Encontramos possíveis vínculos com cadastros de referência. Confirme abaixo.")
                return redirect("notificacoes:confirmar_vinculos", pk=obj.pk)

            # Sem candidatos — segue para detalhe
            return redirect(reverse("notificacoes:detalhe", kwargs={"pk": obj.pk}))
        else:
            # Expõe erros para facilitar diagnóstico
            errs = form.errors.as_json()
            messages.error(request, f"Erros no formulário. Verifique os campos. Detalhes: {errs}")
    else:
        form = NotificacaoCreateForm()

    return render(request, "notificacoes/cadastrar_notificacao.html", {"form": form})


@login_required
def editar(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(Notificacao, pk=pk, prefeitura_id=prefeitura_id)

    # Exclusão de anexo via GET
    del_ax = request.GET.get("del_anexo")
    if del_ax:
        ax = obj.anexos.filter(pk=del_ax).first()
        if ax:
            ax.delete()
            messages.info(request, "Anexo removido.")
        return redirect(request.path)

    if request.method == "POST":
        data = request.POST.copy()
        _normalize_decimal_inputs(data)
        form = NotificacaoEditForm(data, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            # Reaplicar precedência de geolocalização, como na geração a partir da Denúncia
            try:
                lat, lng = obj.latitude, obj.longitude
                # Preferir Imóvel vinculado com coordenadas
                if getattr(obj, 'imovel', None):
                    i = obj.imovel
                    if getattr(i, 'latitude', None) is not None:
                        lat = float(str(i.latitude).replace(',', '.'))
                    if getattr(i, 'longitude', None) is not None:
                        lng = float(str(i.longitude).replace(',', '.'))
                # Senão, cair para a Denúncia vinculada
                elif getattr(obj, 'denuncia', None):
                    d = obj.denuncia
                    if getattr(d, 'local_oco_lat', None) is not None:
                        lat = float(str(d.local_oco_lat).replace(',', '.'))
                    if getattr(d, 'local_oco_lng', None) is not None:
                        lng = float(str(d.local_oco_lng).replace(',', '.'))
                if lat is not None:
                    obj.latitude = round(float(lat), 6)
                if lng is not None:
                    obj.longitude = round(float(lng), 6)
            except Exception:
                pass
            obj.atualizada_por = request.user
            obj.save()
            log_event(request, 'UPDATE', instance=obj)

            fotos = request.FILES.getlist("fotos")
            if fotos:
                existentes = obj.anexos.filter(tipo="FOTO").count()
                restante = max(0, 4 - existentes)
                if restante <= 0:
                    messages.warning(request, "Limite de 4 fotos atingido. Nenhuma nova foto foi adicionada.")
                else:
                    count = 0
                    for foto in fotos[:restante]:
                        anexo = NotificacaoAnexo(notificacao=obj, tipo="FOTO", arquivo=foto)
                        anexo.save(); anexo.processar_arquivo(); anexo.save(); count += 1
                    if len(fotos) > restante:
                        messages.warning(request, f"Apenas {restante} foto(s) foram processadas (limite total de 4).")
                    if count:
                        messages.success(request, f"{count} foto(s) anexada(s) com sucesso.")

            messages.success(request, "Notificação atualizada com sucesso.")
            return redirect(reverse("notificacoes:detalhe", kwargs={"pk": obj.pk}))
        else:
            errs = form.errors.as_json()
            messages.error(request, f"Erros no formulário. Verifique os campos. Detalhes: {errs}")
    else:
        form = NotificacaoEditForm(instance=obj)

    anexos_existentes = obj.anexos.all().order_by("-criada_em")
    return render(request, "notificacoes/editar_notificacao.html", {
        "form": form,
        "obj": obj,
        "anexos_existentes": anexos_existentes,
    })


@login_required
def detalhe(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(Notificacao, pk=pk, prefeitura_id=prefeitura_id)
    anexos = obj.anexos.all().order_by("-criada_em")
    # AIF relacionado (se existir)
    aif = AutoInfracao.objects.filter(notificacao_id=obj.pk, prefeitura_id=prefeitura_id).order_by("-criada_em").first()

    # Galeria Hierárquica (Denúncia -> Apontamentos -> Notificação) sem duplicar
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
    if obj.denuncia_id:
        dgal = _build_denuncia_gallery(obj.denuncia)
        for it in dgal:
            h = it.get('hash') or it.get('url')
            if h in seen_all: continue
            seen_all.add(h)
            galeria.append(it)
    # Fotos próprias da notificação
    for nx in anexos.filter(tipo='FOTO'):
        h = nx.hash_sha256 or f"path:{getattr(nx.arquivo, 'name', '')}"
        if h in seen_all: continue
        seen_all.add(h)
        galeria.append({'url': nx.arquivo.url if nx.arquivo else '', 'label': 'Notificação', 'id': nx.id, 'owner': 'NOT'})

    # Documentos (não-fotos) da notificação
    docs = anexos.exclude(tipo='FOTO')

    return render(request, "notificacoes/detalhe_notificacao.html", {
        "obj": obj,
        "anexos": anexos,
        "aif": aif,
        "galeria": galeria,
        "docs": docs,
    })


@login_required
def vincular_pessoa(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")
    obj = get_object_or_404(Notificacao, pk=pk, prefeitura_id=prefeitura_id)
    if request.method != "POST":
        return redirect("notificacoes:detalhe", pk=pk)
    tipo = (request.POST.get("tipo") or "PF").upper()
    nome = (request.POST.get("nome_razao") or "").strip() or obj.nome_razao
    doc_tipo = (request.POST.get("doc_tipo") or "OUTRO").upper()
    doc_num = (request.POST.get("doc_num") or "").strip()
    email = (request.POST.get("email") or "").strip() or obj.email or ""
    telefone = (request.POST.get("telefone") or "").strip() or obj.telefone or ""
    pessoa = None
    if doc_num:
        pessoa = Pessoa.objects.filter(prefeitura_id=prefeitura_id, doc_num=''.join(filter(str.isdigit, doc_num))).first()
    if not pessoa:
        pessoa = Pessoa.objects.create(
            prefeitura_id=prefeitura_id,
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
    messages.success(request, "Pessoa vinculada à notificação.")
    return redirect("notificacoes:detalhe", pk=pk)


@login_required
def vincular_imovel(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")
    obj = get_object_or_404(Notificacao, pk=pk, prefeitura_id=prefeitura_id)
    if request.method != "POST":
        return redirect("notificacoes:detalhe", pk=pk)
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
        imovel = Imovel.objects.filter(prefeitura_id=prefeitura_id, inscricao=inscricao).first()
    if not imovel:
        imovel = Imovel.objects.create(
            prefeitura_id=prefeitura_id,
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
    messages.success(request, "Imóvel vinculado à notificação.")
    return redirect("notificacoes:detalhe", pk=pk)


# ---------------------------------------------------------------------
# CONFIRMAR VÍNCULOS (após criação independente)
# ---------------------------------------------------------------------
@login_required
def confirmar_vinculos(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(Notificacao, pk=pk, prefeitura_id=prefeitura_id)

    # Se já estiver vinculado (ou originado de denúncia), não precisa confirmar
    if obj.pessoa_id or obj.imovel_id or obj.denuncia_id:
        return redirect("notificacoes:detalhe", pk=obj.pk)

    # Recalcula candidatos a partir do snapshot do documento
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
            return redirect("notificacoes:detalhe", pk=obj.pk)

        do_pessoa = request.POST.get("link_pessoa") == "on"
        do_imovel = request.POST.get("link_imovel") == "on"
        atualizar = request.POST.get("atualizar_campos") == "on"

        # Aplica vínculos conforme seleção
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
                # Geo
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

        # Persiste alterações
        if changed_fk or atualizar:
            obj.atualizada_por = request.user
            obj.save()
            messages.success(request, "Vínculos aplicados com sucesso.")
        else:
            messages.info(request, "Nenhuma alteração aplicada.")
        return redirect("notificacoes:detalhe", pk=obj.pk)

    ctx = {
        "obj": obj,
        "pessoa_cand": pessoa_cand,
        "imovel_cand": imovel_cand,
    }
    return render(request, "notificacoes/confirmar_vinculos.html", ctx)


# ---------------------------------------------------------------------
# IMPRIMIR (página simples para impressão)
# ---------------------------------------------------------------------
@login_required
def imprimir(request, pk):
    prefeitura_id = _get_prefeitura_id(request)
    if not prefeitura_id:
        messages.warning(request, "Nenhuma prefeitura selecionada para a sessão.")
        return redirect("/")

    obj = get_object_or_404(Notificacao, pk=pk, prefeitura_id=prefeitura_id)
    anexos = obj.anexos.all().order_by("-criada_em")
    # Relacionados
    den = obj.denuncia  # pode ser None
    aifs = AutoInfracao.objects.filter(notificacao_id=obj.pk, prefeitura_id=prefeitura_id).order_by("-criada_em")

    # Galeria Hierárquica (Denúncia -> Apontamentos -> Notificação) sem duplicar
    def _build_denuncia_gallery(den_obj):
        gal = []
        seen = set()
        for fx in den_obj.anexos.filter(tipo='FOTO').order_by('-criada_em'):
            h = fx.hash_sha256 or f"path:{getattr(fx.arquivo, 'name', '')}"
            if h in seen:
                continue
            seen.add(h)
            gal.append({'url': fx.arquivo.url if fx.arquivo else '', 'label': 'Denúncia'})
        try:
            for ap in getattr(den_obj, 'apontamentos').all().order_by('-criado_em'):
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
    if den is not None:
        for it in _build_denuncia_gallery(den):
            key = it.get('url')
            if key in seen_all:
                continue
            seen_all.add(key)
            galeria.append(it)
    for nx in anexos.filter(tipo='FOTO'):
        h = nx.hash_sha256 or f"path:{getattr(nx.arquivo, 'name', '')}"
        if h in seen_all:
            continue
        seen_all.add(h)
        galeria.append({'url': nx.arquivo.url if nx.arquivo else '', 'label': 'Notificação'})

    log_event(request, 'PRINT', instance=obj)
    ctx = {"obj": obj, "anexos": anexos, "denuncia": den, "aifs": aifs, "galeria": galeria}
    return render(request, "notificacoes/imprimir_notificacao.html", ctx)


# ---------------------------------------------------------------------
# GERAR NOTIFICAÇÃO A PARTIR DE UMA DENÚNCIA
# ---------------------------------------------------------------------
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

    existente = Notificacao.objects.filter(denuncia_id=den.pk, prefeitura_id=prefeitura_id).order_by("-criada_em").first()
    if existente:
        messages.info(request, "Já existe Notificação para esta Denúncia.")
        return redirect("notificacoes:editar", pk=existente.pk)

    # Prefill a partir de vínculos (se existirem) — Pessoa e Imóvel
    p = getattr(den, 'pessoa', None)
    i = getattr(den, 'imovel', None)

    # Dados de pessoa/notificado
    if p is not None:
        pessoa_tipo = 'PF' if getattr(p, 'tipo', 'PF') == 'PF' else 'PJ'
        nome_razao = p.nome_razao or den.denunciado_nome_razao
        cpf_cnpj = p.doc_num or den.denunciado_cpf_cnpj
        telefone = p.telefone or den.denunciado_telefone
        email = p.email or den.denunciado_email
        rg = den.denunciado_rg_ie  # sem RG na Pessoa (mantém o da denúncia se houver)
    else:
        pessoa_tipo = den.denunciado_tipo_pessoa
        nome_razao = den.denunciado_nome_razao
        cpf_cnpj = den.denunciado_cpf_cnpj
        telefone = den.denunciado_telefone
        email = den.denunciado_email
        rg = den.denunciado_rg_ie

    # Dados de endereço/geo do local
    if i is not None:
        cep = i.cep or den.local_oco_cep
        logradouro = i.logradouro or den.local_oco_logradouro
        numero = i.numero or den.local_oco_numero
        complemento = i.complemento or den.local_oco_complemento
        bairro = i.bairro or den.local_oco_bairro
        cidade = i.cidade or den.local_oco_cidade
        uf = i.uf or den.local_oco_uf
        latitude = i.latitude if i.latitude is not None else den.local_oco_lat
        longitude = i.longitude if i.longitude is not None else den.local_oco_lng
    else:
        cep = den.local_oco_cep
        logradouro = den.local_oco_logradouro
        numero = den.local_oco_numero
        complemento = den.local_oco_complemento
        bairro = den.local_oco_bairro
        cidade = den.local_oco_cidade
        uf = den.local_oco_uf
        latitude = den.local_oco_lat
        longitude = den.local_oco_lng

    # Quantiza lat/lng em 6 casas (campo Notificação aceita 6)
    try:
        from decimal import Decimal, ROUND_HALF_UP
        if latitude is not None:
            latitude = Decimal(str(latitude)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        if longitude is not None:
            longitude = Decimal(str(longitude)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except Exception:
        pass

    obj = Notificacao(
        prefeitura_id=prefeitura_id,
        denuncia=den,
        pessoa_tipo=pessoa_tipo,
        nome_razao=nome_razao,
        cpf_cnpj=cpf_cnpj,
        rg=rg,
        telefone=telefone,
        email=email,
        cep=cep,
        logradouro=logradouro,
        numero=numero,
        complemento=complemento,
        bairro=bairro,
        cidade=cidade,
        uf=uf,
        latitude=latitude,
        longitude=longitude,
        pontoref_oco=getattr(den, 'local_oco_pontoref', '') or den.local_oco_complemento,
        descricao=den.descricao_oco,
        criado_por=request.user,
        atualizada_por=request.user,
    )
    obj.save()
    log_event(request, 'CREATE', instance=obj, extra={'from': 'denuncia', 'denuncia_id': den.pk})
    # Vincular Processo ao criar a partir da Denúncia
    try:
        from apps.processos.models import Processo
        proc = getattr(den, 'processo', None)
        if proc is None:
            proc = Processo.objects.create(
                prefeitura_id=prefeitura_id,
                protocolo=den.protocolo,
                status='ABERTO',
                criado_por=getattr(request, 'user', None),
            )
            den.processo = proc
            den.save(update_fields=['processo'])
        obj.processo = proc
        obj.save(update_fields=['processo'])
    except Exception:
        pass
    # Ao gerar Notificação, marcar a Denúncia como PROCEDE + histórico
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
                descricao='Procedência marcada PROCEDE ao gerar Notificação.',
                feito_por=getattr(request, 'user', None),
                ip_origem=ip,
            )
    except Exception:
        pass
    # Vincula referências para visão 360°
    if p is not None:
        obj.pessoa = p
    if i is not None:
        obj.imovel = i
    if obj.pessoa_id or obj.imovel_id:
        obj.save(update_fields=["pessoa", "imovel"]) 
    # Não copiar fotos físicas: a galeria unificada já exibe as da Denúncia sem duplicar

    messages.success(request, f"Notificação criada a partir da Denúncia {den.protocolo}.")
    return redirect("notificacoes:editar", pk=obj.pk)
