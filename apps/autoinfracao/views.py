from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.utils import timezone

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
from apps.denuncias.models import Denuncia
from apps.usuarios.models import Usuario
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

    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))
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
                    vi = Decimal(raw_vi.replace(".", "").replace(",", "."))
                    obj.valor_infracao = vi
                except Exception:
                    pass
            obj.prefeitura_id = prefeitura_id
            obj.criada_por = request.user
            obj.atualizada_por = request.user
            obj.save()

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
                count = 0
                for foto in fotos:
                    anexo = AutoInfracaoAnexo(auto_infracao=obj, tipo="FOTO", arquivo=foto)
                    anexo.save()
                    anexo.processar_arquivo()
                    anexo.save()
                    count += 1
                messages.success(request, f"{count} foto(s) anexada(s) com sucesso.")

            messages.success(request, f"Auto de Infração criado! Protocolo: {obj.protocolo}")
            return redirect(reverse("autoinfracao:detalhe", kwargs={"pk": obj.pk}))
        else:
            messages.error(request, "Erros no formulário. Verifique os campos.")
    else:
        form = AutoInfracaoCreateForm(prefeitura_id=prefeitura_id)

    return render(request, "autoinfracao/cadastrar_autoinfracao.html", {"form": form})


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
            item_form = AutoInfracaoMultaItemForm(request.POST, prefeitura_id=prefeitura_id)
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
            val = request.POST.get("valor_homologado", "").strip()
            try:
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
            perc = request.POST.get("desconto_percent", "").strip()
            justificativa = request.POST.get("justificativa", "").strip()
            if not justificativa:
                messages.error(request, "Informe a justificativa para a homologação.")
                return redirect(request.path)
            try:
                p = Decimal(perc)
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
                        vi_clean = Decimal(raw_vi.replace(".", "").replace(",", "."))
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
                    count = 0
                    for foto in fotos:
                        anexo = AutoInfracaoAnexo(auto_infracao=obj, tipo="FOTO", arquivo=foto)
                        anexo.save()
                        anexo.processar_arquivo()
                        anexo.save()
                        count += 1
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
    return render(request, "autoinfracao/detalhe_autoinfracao.html", {"obj": obj, "anexos": anexos})


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
        criada_por=request.user,
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
        criada_por=request.user,
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
        criada_por=request.user,
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
        criada_por=request.user,
        atualizada_por=request.user,
    )
    obj.save()
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
