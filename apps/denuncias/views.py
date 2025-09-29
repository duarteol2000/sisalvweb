# apps/denuncias/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.forms import inlineformset_factory

from .models import Denuncia, DenunciaDocumentoImovel, DenunciaAnexo
from .forms import DenunciaOrigemForm, DenunciaFotosForm, process_photo_file  # usamos o form só para RENDER no GET



# formset local só para render (sem salvar ainda), e sem campos extras na tela
DocumentoImovelFormSet = inlineformset_factory(
    parent_model=Denuncia,
    model=DenunciaDocumentoImovel,
    fields=["tipo", "arquivo", "observacao"],
    extra=2,           # mostra 2 linhas em branco
    can_delete=True,
)

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






'''
def _get_client_ip(request: HttpRequest) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        # primeiro IP na cadeia
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _inject_required_fields_if_present(request: HttpRequest, obj: Denuncia) -> None:
    """Preenche campos do model que não vêm no form, se existirem."""
    # prefeitura (obrigatória no seu model)
    if hasattr(obj, "prefeitura_id"):
        pref_id = request.session.get("prefeitura_id")
        if not pref_id:
            # Sem prefeitura na sessão, bloqueia e avisa
            raise DjangoValidationError({"prefeitura": ["Prefeitura não encontrada na sessão. Faça login novamente."]})
        obj.prefeitura_id = pref_id

    # usuário criador (opcional)
    if hasattr(obj, "criado_por_id") and request.user.is_authenticated:
        obj.criado_por = request.user

    # auditoria leve
    if hasattr(obj, "canal_registro") and not obj.canal_registro:
        obj.canal_registro = "INTERNO"
    if hasattr(obj, "user_agent"):
        obj.user_agent = request.META.get("HTTP_USER_AGENT", "")[:200]
    if hasattr(obj, "ip_origem"):
        obj.ip_origem = _get_client_ip(request)


def _get_prefeitura_da_sessao(request):
    pid = request.session.get('prefeitura_id')
    if not pid:
        return None
    try:
        return Prefeitura.objects.get(id=pid, ativo=True)
    except Prefeitura.DoesNotExist:
        return None

@login_required
def listar_denuncias(request):
    prefeitura = _get_prefeitura_da_sessao(request)
    if not prefeitura:
        messages.error(request, 'Prefeitura não definida na sessão.')
        return redirect('login')

    q = request.GET.get('q', '').strip()
    status_filtro = request.GET.get('status', '').strip()

    qs = Denuncia.objects.filter(prefeitura=prefeitura)
    if q:
        qs = qs.filter(
            Q(protocolo__icontains=q) |
            Q(denunciado_nome_razao__icontains=q) |
            Q(local_oco_logradouro__icontains=q) |
            Q(local_oco_bairro__icontains=q) |
            Q(local_oco_cidade__icontains=q)
        )
    if status_filtro:
        qs = qs.filter(status=status_filtro)

    denuncias = qs.select_related('prefeitura', 'criado_por').order_by('-criada_em')[:200]

    return render(request, 'denuncias/listar_denuncias.html', {
        'denuncias': denuncias,
        'q': q,
        'status_filtro': status_filtro,
    })

@login_required
def cadastrar_denuncia(request: HttpRequest):
    """
    Fluxo:
      1) Valida formulário principal e formset de documentos (podem estar vazios).
      2) Cria a denúncia (commit=False), injeta prefeitura/usuário/auditoria e salva.
      3) Salva documentos vinculados (se houver).
      4) Processa e salva fotos (se houver) — tudo em transação.
    """
    if request.method == "POST":
        form = DenunciaCreateForm(request.POST)
        # importante: FILES também no formset (por causa de 'arquivo')
        doc_formset = DocumentoImovelFormSet(request.POST, request.FILES)

        # Mantém o campo de fotos na tela em caso de erro nos outros forms
        fotos_form_preview = DenunciaFotosForm(request.POST, request.FILES, denuncia=None)

        # Validação inicial de form + formset (formset vazio é válido)
        if not (form.is_valid() and doc_formset.is_valid()):
            messages.error(request, "Há erros no formulário. Verifique os campos destacados.")
            if settings.DEBUG:
                logger.error("Erros de validação: form=%s | doc_formset=%s", form.errors, doc_formset.errors)
            return render(
                request,
                "denuncias/cadastrar_denuncia.html",
                {
                    "form": form,
                    "doc_formset": doc_formset,
                    "fotos_form": fotos_form_preview,
                },
            )

        try:
            with transaction.atomic():
                # 1) cria a instância sem salvar definitivo
                denuncia_obj: Denuncia = form.save(commit=False)

                # 2) injeta campos obrigatórios/auxiliares vindos do request
                _inject_required_fields_if_present(request, denuncia_obj)

                # 3) salva a denúncia (model vai gerar protocolo no save)
                denuncia_obj.save()

                # 4) vincula e salva os documentos do imóvel (se houver linhas preenchidas)
                doc_formset.instance = denuncia_obj
                doc_formset.save()  # se não tiver nada, não cria nada

                # 5) processa/salva as fotos (opcionais)
                fotos_form = DenunciaFotosForm(request.POST, request.FILES, denuncia=denuncia_obj)
                if fotos_form.is_valid():
                    fotos_form.save()  # cria 0..N anexos tipo FOTO
                else:
                    # força erro para rollback e exibir erros do fotos_form
                    raise DjangoValidationError(fotos_form.errors)

        except DjangoValidationError as ve:
            messages.error(request, "Houve erro ao processar os dados. Verifique os campos e arquivos enviados.")
            if settings.DEBUG:
                logger.exception("ValidationError ao salvar denúncia: %s", ve)
            # Se fotos_form falhou, usamos ele; senão, mantém o preview
            context_fotos = locals().get("fotos_form", fotos_form_preview)
            return render(
                request,
                "denuncias/cadastrar_denuncia.html",
                {
                    "form": form,
                    "doc_formset": doc_formset,
                    "fotos_form": context_fotos,
                },
            )

        except IntegrityError as ie:
            messages.error(request, "Não foi possível salvar a denúncia (integridade).")
            if settings.DEBUG:
                logger.exception("IntegrityError ao salvar denúncia: %s", ie)
                return render(
                    request,
                    "denuncias/cadastrar_denuncia.html",
                    {
                        "form": form,
                        "doc_formset": doc_formset,
                        "fotos_form": fotos_form_preview,
                    },
                )
            return render(
                request,
                "denuncias/cadastrar_denuncia.html",
                {
                    "form": form,
                    "doc_formset": doc_formset,
                    "fotos_form": fotos_form_preview,
                },
            )

        except Exception as e:
            messages.error(request, "Não foi possível salvar a denúncia. Tente novamente.")
            if settings.DEBUG:
                logger.exception("Exceção ao salvar denúncia: %s", e)
                return render(
                    request,
                    "denuncias/cadastrar_denuncia.html",
                    {
                        "form": form,
                        "doc_formset": doc_formset,
                        "fotos_form": fotos_form_preview,
                    },
                )
            return render(
                request,
                "denuncias/cadastrar_denuncia.html",
                {
                    "form": form,
                    "doc_formset": doc_formset,
                    "fotos_form": fotos_form_preview,
                },
            )

        # sucesso
        messages.success(request, "Denúncia cadastrada com sucesso!")
        try:
            return redirect(reverse("denuncias:detalhar", kwargs={"pk": denuncia_obj.pk}))
        except Exception:
            # caso ainda não exista a rota de detalhe
            return redirect(reverse("denuncias:nova"))

    # GET
    form = DenunciaCreateForm()
    doc_formset = DocumentoImovelFormSet()
    fotos_form = DenunciaFotosForm(denuncia=None)
    return render(
        request,
        "denuncias/cadastrar_denuncia.html",
        {
            "form": form,
            "doc_formset": doc_formset,
            "fotos_form": fotos_form,
        },
    )



@login_required
@transaction.atomic
def editar_denuncia(request, pk):
    prefeitura = _get_prefeitura_da_sessao(request)
    if not prefeitura:
        messages.error(request, 'Prefeitura não definida na sessão.')
        return redirect('login')

    denuncia = get_object_or_404(Denuncia, pk=pk, prefeitura=prefeitura)

    if request.method == 'POST':
        form_denuncia = DenunciaEditForm(request.POST, instance=denuncia)  # ⬅ aqui
        form_fotos = DenunciaFotosForm(request.POST, request.FILES, denuncia=denuncia)

        if form_denuncia.is_valid() and form_fotos.is_valid():
            form_denuncia.save()
            form_fotos.save()
            messages.success(request, 'Denúncia atualizada com sucesso!')
            return redirect('denuncias_detalhe', pk=denuncia.pk)
        else:
            messages.error(request, 'Corrija os erros do formulário.')
    else:
        form_denuncia = DenunciaEditForm(instance=denuncia)  # ⬅ aqui
        form_fotos = DenunciaFotosForm(denuncia=denuncia)

    return render(request, 'denuncias/editar_denuncia.html', {
        'denuncia': denuncia,
        'form_denuncia': form_denuncia,
        'form_fotos': form_fotos,
    })



@login_required
def detalhe_denuncia(request, pk):
    prefeitura = _get_prefeitura_da_sessao(request)
    if not prefeitura:
        messages.error(request, 'Prefeitura não definida na sessão.')
        return redirect('login')

    denuncia = get_object_or_404(Denuncia, pk=pk, prefeitura=prefeitura)
    return render(request, 'denuncias/detalhe_denuncia.html', {
        'denuncia': denuncia
    })

'''