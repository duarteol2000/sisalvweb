from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from apps.prefeituras.models import Prefeitura  # evitar import circular
from django.contrib import messages
from django.contrib.auth.decorators import login_required
import re

def login_view(request):
    # (Opcional mas recomendado) Bloquear reabertura de login estando logado
    if request.user.is_authenticated:
        messages.info(request, "Você já está autenticado. Para trocar de prefeitura, faça logout.")
        return redirect("home")

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        senha = request.POST.get("password", "")
        codigo_ibge_raw = request.POST.get("codigo_ibge", "") or ""

        # Normaliza: mantém apenas dígitos
        codigo_ibge = re.sub(r"\D+", "", codigo_ibge_raw)

        # Validação mínima do IBGE (6 ou 7 dígitos — mantendo seu padrão)
        if not codigo_ibge.isdigit() or len(codigo_ibge) not in (6, 7):
            messages.error(request, "Informe um Código IBGE válido (somente números, 6 ou 7 dígitos).")
            return render(request, "usuarios/login.html")

        # Autenticação por e-mail (USERNAME_FIELD='email')
        user = authenticate(request, email=email, password=senha)
        if user is None:
            messages.error(request, "E-mail ou senha inválidos.")
            return render(request, "usuarios/login.html")

        if not user.is_active:
            messages.error(request, "Usuário inativo. Contate o administrador.")
            return render(request, "usuarios/login.html")

        # Busca prefeitura pelo IBGE (somente ativas)
        try:
            prefeitura = Prefeitura.objects.get(codigo_ibge=codigo_ibge, ativo=True)
        except Prefeitura.DoesNotExist:
            messages.error(request, "Prefeitura não encontrada ou inativa para este código IBGE.")
            return render(request, "usuarios/login.html")

        # Verifica vínculo do usuário com a prefeitura informada
        if not getattr(user, "prefeitura_id", None):
            messages.error(request, "Seu usuário não possui prefeitura vinculada. Contate o administrador.")
            return render(request, "usuarios/login.html")

        if user.prefeitura_id != prefeitura.id:
            messages.error(request, "Usuário não pertence a esta prefeitura. Verifique o código IBGE informado.")
            return render(request, "usuarios/login.html")

        # Se já havia prefeitura em sessão, bloquear troca sem logout
        if "prefeitura_id" in request.session and request.session["prefeitura_id"] != prefeitura.id:
            messages.error(request, "Você precisa sair para trocar de prefeitura.")
            return redirect("login")

        # Login e fixar prefeitura na sessão
        login(request, user)
        request.session["prefeitura_id"] = prefeitura.id
        messages.success(request, f"Bem-vindo! Prefeitura ativa: {prefeitura.nome}.")
        return redirect("home")  # ajuste depois para a sua tela inicial/dash

    # GET: só renderiza o form — sem lista de prefeituras (não há mais dropdown)
    return render(request, "usuarios/login.html")



def logout_view(request):
    logout(request)
    request.session.flush()  # limpa prefeitura_id também
    return redirect("login")


@login_required
def home_view(request):
    # exige prefeitura em sessão
    prefeitura_id = request.session.get("prefeitura_id")
    if not prefeitura_id:
        messages.error(request, "Selecione a prefeitura para continuar.")
        return redirect("login")

    try:
        prefeitura = Prefeitura.objects.get(id=prefeitura_id, ativo=True)
    except Prefeitura.DoesNotExist:
        messages.error(request, "Prefeitura inválida ou inativa.")
        return redirect("login")

    return render(request, "usuarios/home.html", {
        "usuario": request.user,
        "prefeitura": prefeitura,
    })
