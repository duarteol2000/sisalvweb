# apps/denuncias/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import F, Value as V
from django.db.models.functions import Concat, Coalesce

from .models import Denuncia, DenunciaDocumentoImovel, DenunciaAnexo
from .forms import DenunciaOrigemForm, DenunciaFotosForm, process_photo_file  # usamos o form só para RENDER no GET
from apps.cadastros.models import Pessoa, Imovel
from apps.usuarios.audit import log_event

# ==========================================================
# Mapa de campos (centraliza nomes do model para filtros/annotate)
# Se preferir, pode remover e escrever direto os nomes dos campos.
# ==========================================================
DEN_FIELD = {
    "protocolo": "protocolo",
    "data_registro": "criada_em",
    "cpf_cnpj": "denunciado_cpf_cnpj",
    "nome": "denunciado_nome_razao",
    "rg": "denunciado_rg_ie",
    "telefone": "denunciado_telefone",
    # Endereço do ocorrido
    "end_logradouro": "local_oco_logradouro",
    "end_numero": "local_oco_numero",
    "end_bairro": "local_oco_bairro",
    "end_cidade": "local_oco_cidade",
    "tipo": "origem_denuncia",
    "status": "status",
}

# formset local só para render (sem salvar ainda), e sem campos extras na tela
DocumentoImovelFormSet = inlineformset_factory(
    parent_model=Denuncia,
    model=DenunciaDocumentoImovel,
    fields=["tipo", "arquivo", "observacao"],
    extra=2,           # mostra 2 linhas em branco
    can_delete=True,
)

# ==========================================================
# CADASTRAR — STEP 1 (SEU CÓDIGO ORIGINAL, INTACTO)
# ==========================================================
@login_required
def denuncia_nova_step1(request):
    pref_id = request.session.get("prefeitura_id")
    if not pref_id:
        messages.error(request, "Sessão sem prefeitura. Faça login e selecione a prefeitura.")
        return redirect("/")

    debug_exception = None

    if request.method == "POST":
        # DEBUG rápido (pode remover depois)
        print("---- UPLOAD DEBUG START ----")
        print("FILES KEYS:", list(request.FILES.keys()))
        print("FOTOS COUNT:", len(request.FILES.getlist("fotos")))
        for i, f in enumerate(request.FILES.getlist("fotos")):
            print(f"FOTO[{i}] name={getattr(f, 'name', '')} size={getattr(f, 'size', '?')}")
        print("---- UPLOAD DEBUG END ----")

        form = DenunciaOrigemForm(request.POST)
        try:
            if form.is_valid():
                # 1) Salvar núcleo
                obj: Denuncia = form.save(commit=False)
                obj.prefeitura_id = pref_id
                if request.user.is_authenticated:
                    obj.criado_por = request.user
                if not obj.denunciado_nome_razao:
                    obj.denunciado_nome_razao = "A DEFINIR"
                obj.save()
                log_event(request, 'CREATE', instance=obj)

                # 2) Documentos do Imóvel (opcionais)
                doc_formset = DocumentoImovelFormSet(
                    data=request.POST, files=request.FILES, instance=obj
                )
                if not doc_formset.is_valid():
                    messages.error(request, "Há erros nos documentos do imóvel. Corrija e envie novamente.")
                    # renderiza com erros do formset; fotos: apenas mostrar o input
                    fotos_form = DenunciaFotosForm(denuncia=obj)
                    nfe = doc_formset.non_form_errors()
                    debug_exception = nfe and "\n".join(nfe) or str(doc_formset.errors)
                    return render(
                        request,
                        "denuncias/cadastrar_denuncia.html",
                        {"form": form, "doc_formset": doc_formset, "fotos_form": fotos_form, "debug_exception": debug_exception},
                    )
                doc_formset.save()

                # 3) FOTOS (opcionais) — processar manualmente, sem validar pelo Form
                files_list = request.FILES.getlist("fotos")
                if files_list:
                    created = []
                    for f in files_list:
                        try:
                            processed_file, w, h, hsh = process_photo_file(f)
                            anexo = DenunciaAnexo(
                                denuncia=obj,
                                tipo="FOTO",
                                arquivo=processed_file,
                                observacao=(request.POST.get("observacao") or "").strip()[:140],
                                largura_px=w,
                                altura_px=h,
                                hash_sha256=hsh,
                                otimizada=True,
                            )
                            anexo.save()
                            created.append(anexo)
                        except ValidationError as ve:
                            messages.error(request, f"Foto inválida: {ve}")
                            # Recarrega página mantendo o que digitou, com linhas de docs e input de fotos
                            doc_formset = DocumentoImovelFormSet(instance=obj)
                            fotos_form = DenunciaFotosForm(denuncia=obj)
                            debug_exception = f"Erro ao processar foto: {ve}"
                            return render(
                                request,
                                "denuncias/cadastrar_denuncia.html",
                                {"form": form, "doc_formset": doc_formset, "fotos_form": fotos_form, "debug_exception": debug_exception},
                            )
                        except Exception as e:
                            messages.error(request, "Erro inesperado ao processar uma foto.")
                            doc_formset = DocumentoImovelFormSet(instance=obj)
                            fotos_form = DenunciaFotosForm(denuncia=obj)
                            debug_exception = f"EXCEPTION process_photo_file: {e}"
                            return render(
                                request,
                                "denuncias/cadastrar_denuncia.html",
                                {"form": form, "doc_formset": doc_formset, "fotos_form": fotos_form, "debug_exception": debug_exception},
                            )

                messages.success(
                    request,
                    "Origem, Denunciado, Local da ocorrência, Documentos (se informados) e Fotos (se enviadas) salvos com sucesso."
                )
                return redirect(reverse("denuncias:nova_step1"))

            # Form principal inválido
            debug_exception = form.errors.as_text()
            messages.error(request, "Há erros no formulário. Verifique os campos destacados abaixo.")
            dummy = Denuncia(prefeitura_id=pref_id)
            doc_formset = DocumentoImovelFormSet(instance=dummy)
            fotos_form = DenunciaFotosForm(denuncia=None)
            return render(
                request,
                "denuncias/cadastrar_denuncia.html",
                {"form": form, "doc_formset": doc_formset, "fotos_form": fotos_form, "debug_exception": debug_exception},
            )

        except Exception as exc:
            debug_exception = f"EXCEPTION:\n{exc}"
            messages.error(request, "Ocorreu um erro inesperado ao salvar a denúncia.")
            dummy = Denuncia(prefeitura_id=pref_id)
            doc_formset = DocumentoImovelFormSet(instance=dummy)
            fotos_form = DenunciaFotosForm(denuncia=None)
            return render(
                request,
                "denuncias/cadastrar_denuncia.html",
                {"form": form, "doc_formset": doc_formset, "fotos_form": fotos_form, "debug_exception": debug_exception},
            )

    # GET
    form = DenunciaOrigemForm()
    dummy = Denuncia(prefeitura_id=pref_id)
    doc_formset = DocumentoImovelFormSet(instance=dummy)
    fotos_form = DenunciaFotosForm(denuncia=None)  # só para renderizar o input

    return render(
        request,
        "denuncias/cadastrar_denuncia.html",
        {"form": form, "doc_formset": doc_formset, "fotos_form": fotos_form, "debug_exception": debug_exception},
    )


# ==========================================================
# LISTAR (com filtros e paginação) — NOVO
# ==========================================================
@login_required
def denuncia_list(request):
    prefeitura_id = request.session.get("prefeitura_id")
    if not prefeitura_id:
        messages.error(request, "Prefeitura não definida na sessão.")
        return redirect("usuarios:home")

    qs = Denuncia.objects.filter(prefeitura_id=prefeitura_id)

    # Filtros GET
    protocolo = request.GET.get("protocolo", "").strip()
    cpf_cnpj  = request.GET.get("cpf_cnpj", "").strip()
    nome      = request.GET.get("nome", "").strip()
    rg        = request.GET.get("rg", "").strip()
    telefone  = request.GET.get("telefone", "").strip()
    endereco  = request.GET.get("endereco", "").strip()
    pontoref  = request.GET.get("pontoref", "").strip()

    f = DEN_FIELD

    if protocolo:
        qs = qs.filter(**{f"{f['protocolo']}__icontains": protocolo})
    if cpf_cnpj:
        qs = qs.filter(**{f"{f['cpf_cnpj']}__icontains": cpf_cnpj})
    if nome:
        qs = qs.filter(**{f"{f['nome']}__icontains": nome})
    if rg:
        qs = qs.filter(**{f"{f['rg']}__icontains": rg})
    if telefone:
        qs = qs.filter(**{f"{f['telefone']}__icontains": telefone})

    # Endereço concatenado para exibição e busca
    qs = qs.annotate(
        endereco_concat=Concat(
            Coalesce(F(f["end_logradouro"]), V("")),
            V(", "),
            Coalesce(F(f["end_numero"]), V("")),
            V(" — "),
            Coalesce(F(f["end_bairro"]), V("")),
            V(" — "),
            Coalesce(F(f["end_cidade"]), V("")),
        )
    )
    if endereco:
        qs = qs.filter(endereco_concat__icontains=endereco)
    if pontoref:
        qs = qs.filter(local_oco_pontoref__icontains=pontoref)

    # Ordenação por data desc
    qs = qs.order_by(f"-{f['data_registro']}")

    # Paginação
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "protocolo": protocolo,
        "cpf_cnpj": cpf_cnpj,
        "nome": nome,
        "rg": rg,
        "telefone": telefone,
        "endereco": endereco,
        "pontoref": pontoref,
    }
    return render(request, "denuncias/listar_denuncias.html", context)


# ==========================================================
# EDITAR — BÁSICO/STEP 1 (reaproveita o template de cadastro) — NOVO
# ==========================================================
@login_required
def denuncia_edit_basico(request, pk):
    prefeitura_id = request.session.get("prefeitura_id")
    if not prefeitura_id:
        messages.error(request, "Prefeitura não definida na sessão.")
        return redirect("usuarios:home")

    obj = get_object_or_404(Denuncia, pk=pk, prefeitura_id=prefeitura_id)

    if request.method == "POST":
        form = DenunciaOrigemForm(request.POST, instance=obj)
        if form.is_valid():
            obj_edit = form.save(commit=False)
            obj_edit.prefeitura_id = obj.prefeitura_id  # mantém integridade multi-prefeitura
            obj_edit.save()
            log_event(request, 'UPDATE', instance=obj_edit)
            messages.success(request, "Denúncia atualizada com sucesso (dados básicos).")
            return redirect("denuncias:listar")
        else:
            messages.error(request, "Corrija os erros do formulário.")
    else:
        form = DenunciaOrigemForm(instance=obj)

    return render(
        request,
        "denuncias/cadastrar_denuncia.html",  # reaproveita o mesmo template
        {"form": form, "obj": obj, "modo_edicao": True},
    )


# ==========================================================
# DETALHE — (SEU CÓDIGO, MANTIDO)
# ==========================================================
@login_required
def denuncia_detail(request, pk):
    prefeitura_id = request.session.get("prefeitura_id")
    if not prefeitura_id:
        messages.error(request, "Prefeitura não definida na sessão.")
        return redirect("usuarios:home")

    obj = get_object_or_404(Denuncia, pk=pk, prefeitura_id=prefeitura_id)

    # Monta endereço do ocorrido (string pronta pro template)
    endereco_oco = obj.local_oco_logradouro or ""
    if obj.local_oco_numero:
        endereco_oco += f", {obj.local_oco_numero}"
    if obj.local_oco_bairro:
        endereco_oco += f" — {obj.local_oco_bairro}"
    if obj.local_oco_cidade:
        endereco_oco += f" — {obj.local_oco_cidade}"
    if obj.local_oco_uf:
        endereco_oco += f"/{obj.local_oco_uf}"
    if obj.local_oco_cep:
        endereco_oco += f" • CEP: {obj.local_oco_cep}"
    if getattr(obj, 'local_oco_pontoref', ''):
        endereco_oco += f" • Ponto de ref.: {obj.local_oco_pontoref}"

    # Relacionados: Notificações e AIFs desta denúncia
    from apps.notificacoes.models import Notificacao
    from apps.autoinfracao.models import AutoInfracao
    notifs = Notificacao.objects.filter(denuncia_id=obj.id, prefeitura_id=prefeitura_id).order_by('-criada_em')
    aifs = AutoInfracao.objects.filter(denuncia_id=obj.id, prefeitura_id=prefeitura_id).order_by('-criada_em')

    context = {
        "obj": obj,
        "endereco_oco": endereco_oco,
        "notificacoes": notifs,
        "autos": aifs,
    }
    log_event(request, 'VIEW', instance=obj)
    return render(request, "denuncias/detalhe_denuncia.html", context)


# ===============================
# Vínculos via UI (sem admin)
# ===============================
@login_required
def denuncia_vincular_pessoa(request, pk):
    pref_id = request.session.get("prefeitura_id")
    if not pref_id:
        messages.error(request, "Prefeitura não definida na sessão.")
        return redirect("denuncias:listar")
    obj = get_object_or_404(Denuncia, pk=pk, prefeitura_id=pref_id)
    if request.method != "POST":
        return redirect("denuncias:detalhe", pk=pk)
    pessoa_id = request.POST.get("pessoa_id")
    doc_tipo = (request.POST.get("doc_tipo") or "OUTRO").upper()
    doc_num = (request.POST.get("doc_num") or "").strip()
    nome = (request.POST.get("nome_razao") or "").strip() or "INDERTEMINADO"
    tipo = (request.POST.get("tipo") or "PF").upper()
    email = (request.POST.get("email") or "").strip()
    telefone = (request.POST.get("telefone") or "").strip()
    pessoa = None
    if pessoa_id:
        pessoa = Pessoa.objects.filter(id=pessoa_id, prefeitura_id=pref_id, ativo=True).first()
    if not pessoa and doc_num:
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
    # salva e, se já houver pessoa e imóvel vinculados, marca procedência como PROCEDE
    obj.save(update_fields=["pessoa"])
    log_event(request, 'LINK', instance=obj, extra={'pessoa_id': pessoa.id})
    if obj.pessoa_id and obj.imovel_id and obj.procedencia != 'PROCEDE':
        obj.procedencia = 'PROCEDE'
        obj.save(update_fields=["procedencia"]) 
        messages.info(request, "Denúncia marcada como PROCEDE (pessoa e imóvel vinculados).")
    messages.success(request, "Pessoa vinculada à denúncia.")
    return redirect("denuncias:detalhe", pk=pk)


@login_required
def denuncia_vincular_imovel(request, pk):
    pref_id = request.session.get("prefeitura_id")
    if not pref_id:
        messages.error(request, "Prefeitura não definida na sessão.")
        return redirect("denuncias:listar")
    obj = get_object_or_404(Denuncia, pk=pk, prefeitura_id=pref_id)
    if request.method != "POST":
        return redirect("denuncias:detalhe", pk=pk)
    imovel_id = request.POST.get("imovel_id")
    inscricao = (request.POST.get("inscricao") or "").strip()
    logradouro = (request.POST.get("logradouro") or "").strip() or "ENDERECO DESCONHECIDO"
    numero = (request.POST.get("numero") or "").strip()
    complemento = (request.POST.get("complemento") or "").strip()
    bairro = (request.POST.get("bairro") or "").strip() or (obj.local_oco_bairro or "")
    cidade = (request.POST.get("cidade") or "").strip() or (obj.local_oco_cidade or "")
    uf = (request.POST.get("uf") or "").strip() or (obj.local_oco_uf or "CE")
    cep = (request.POST.get("cep") or "").strip()
    imovel = None
    if imovel_id:
        imovel = Imovel.objects.filter(id=imovel_id, prefeitura_id=pref_id, ativo=True).first()
    if not imovel and inscricao:
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
    if obj.pessoa_id and obj.imovel_id and obj.procedencia != 'PROCEDE':
        obj.procedencia = 'PROCEDE'
        obj.save(update_fields=["procedencia"]) 
        messages.info(request, "Denúncia marcada como PROCEDE (pessoa e imóvel vinculados).")
    messages.success(request, "Imóvel vinculado à denúncia.")
    return redirect("denuncias:detalhe", pk=pk)


# ==========================================================
# IMPRIMIR — ficha simplificada de Denúncia
# ==========================================================
@login_required
def denuncia_imprimir(request, pk):
    prefeitura_id = request.session.get("prefeitura_id")
    if not prefeitura_id:
        messages.error(request, "Prefeitura não definida na sessão.")
        return redirect("usuarios:home")

    obj = get_object_or_404(Denuncia, pk=pk, prefeitura_id=prefeitura_id)
    anexos = obj.anexos.all().order_by('-criada_em')

    # Endereço do ocorrido (string montada)
    endereco_oco = obj.local_oco_logradouro or ""
    if obj.local_oco_numero:
        endereco_oco += f", {obj.local_oco_numero}"
    if obj.local_oco_bairro:
        endereco_oco += f" — {obj.local_oco_bairro}"
    if obj.local_oco_cidade:
        endereco_oco += f" — {obj.local_oco_cidade}"
    if obj.local_oco_uf:
        endereco_oco += f"/{obj.local_oco_uf}"
    if obj.local_oco_cep:
        endereco_oco += f" • CEP: {obj.local_oco_cep}"

    # Ponto de referência: preferir o da própria Denúncia; senão, o da Notificação vinculada; por fim, usar complemento do local
    pontoref = obj.local_oco_pontoref or obj.local_oco_complemento or ''
    try:
        from apps.notificacoes.models import Notificacao
        nref = (
            Notificacao.objects.filter(denuncia_id=obj.id, prefeitura_id=prefeitura_id)
            .exclude(pontoref_oco='')
            .order_by('-criada_em')
            .values_list('pontoref_oco', flat=True)
            .first()
        )
        if (not pontoref) and nref:
            pontoref = nref
    except Exception:
        pass

    ctx = {
        "obj": obj,
        "anexos": anexos,
        "endereco_oco": endereco_oco,
        "pontoref": pontoref,
    }
    log_event(request, 'PRINT', instance=obj)
    return render(request, "denuncias/imprimir_denuncia.html", ctx)
