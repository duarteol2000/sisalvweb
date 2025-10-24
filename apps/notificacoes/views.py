# apps/notificacoes/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import Notificacao, NotificacaoAnexo
from apps.autoinfracao.models import AutoInfracao
from apps.denuncias.models import Denuncia
from django.core.files.base import ContentFile
import os
from .forms import NotificacaoCreateForm, NotificacaoEditForm


def _get_prefeitura_id(request):
    return request.session.get("prefeitura_id")


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

    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))

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
        form = NotificacaoCreateForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.prefeitura_id = prefeitura_id
            obj.criada_por = request.user
            obj.atualizada_por = request.user
            obj.save()

            # Upload direto do request.FILES
            fotos = request.FILES.getlist("fotos")
            if fotos:
                count = 0
                for foto in fotos:
                    anexo = NotificacaoAnexo(notificacao=obj, tipo="FOTO", arquivo=foto)
                    anexo.save()
                    anexo.processar_arquivo()
                    anexo.save()
                    count += 1
                messages.success(request, f"{count} foto(s) anexada(s) com sucesso.")

            messages.success(request, f"Notificação criada com sucesso! Protocolo: {obj.protocolo}")
            # 👉 redireciona para o DETALHE (em vez de editar)
            return redirect(reverse("notificacoes:detalhe", kwargs={"pk": obj.pk}))
        else:
            messages.error(request, "Erros no formulário. Verifique os campos.")
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

    if request.method == "POST":
        form = NotificacaoEditForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.atualizada_por = request.user
            obj.save()

            fotos = request.FILES.getlist("fotos")
            if fotos:
                count = 0
                for foto in fotos:
                    anexo = NotificacaoAnexo(notificacao=obj, tipo="FOTO", arquivo=foto)
                    anexo.save()
                    anexo.processar_arquivo()
                    anexo.save()
                    count += 1
                messages.success(request, f"{count} foto(s) anexada(s) com sucesso.")

            messages.success(request, "Notificação atualizada com sucesso.")
            return redirect(reverse("notificacoes:detalhe", kwargs={"pk": obj.pk}))
        else:
            messages.error(request, "Erros no formulário. Verifique os campos.")
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
    return render(request, "notificacoes/detalhe_notificacao.html", {"obj": obj, "anexos": anexos, "aif": aif})


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
    return render(request, "notificacoes/imprimir_notificacao.html", {"obj": obj, "anexos": anexos})


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

    obj = Notificacao(
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
        criada_por=request.user,
        atualizada_por=request.user,
    )
    obj.save()
    # Copiar fotos da Denúncia para a Notificação
    try:
        count = 0
        for a in den.anexos.all():
            if a.tipo != "FOTO" or not a.arquivo:
                continue
            a.arquivo.open("rb")
            data = a.arquivo.read()
            a.arquivo.close()
            filename = os.path.basename(a.arquivo.name)
            novo = NotificacaoAnexo(notificacao=obj, tipo="FOTO")
            novo.arquivo.save(filename, ContentFile(data), save=True)
            novo.processar_arquivo()
            novo.save()
            count += 1
        if count:
            messages.success(request, f"{count} foto(s) copiadas da Denúncia.")
    except Exception as e:
        messages.warning(request, f"Falha ao copiar fotos: {e}")

    messages.success(request, f"Notificação criada a partir da Denúncia {den.protocolo}.")
    return redirect("notificacoes:editar", pk=obj.pk)
