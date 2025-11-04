from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from apps.prefeituras.models import Prefeitura  # evitar import circular
from apps.usuarios.models import UsuarioLoginLog
from django.contrib import messages
from django.contrib.auth.decorators import login_required
import re
from django.utils import timezone
from datetime import datetime
from django.db.models import Count
from django.db.models.functions import TruncMonth
from apps.denuncias.models import Denuncia
from apps.notificacoes.models import Notificacao
from apps.autoinfracao.models import AutoInfracao

def login_view(request):
    # Já autenticado? Mantém seu comportamento
    if request.user.is_authenticated:
        messages.info(request, "Você já está autenticado. Para trocar de prefeitura, faça logout.")
        return redirect("home")

    # Flag para layout público
    ctx = {"PUBLIC_LAYOUT": True}

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        senha = request.POST.get("password") or ""
        codigo_ibge_raw = request.POST.get("codigo_ibge") or ""

        # Normaliza: mantém apenas dígitos
        codigo_ibge = re.sub(r"\D+", "", codigo_ibge_raw)

        # Validação mínima do IBGE (6 ou 7 dígitos)
        if not codigo_ibge.isdigit() or len(codigo_ibge) not in (6, 7):
            messages.error(request, "Informe um Código IBGE válido (somente números, 6 ou 7 dígitos).")
            return render(request, "usuarios/login.html", ctx)

        # Autenticação por e-mail
        # IMPORTANTE: usar username=email para compatibilidade geral
        user = authenticate(request, username=email, password=senha)
        if user is None:
            messages.error(request, "E-mail ou senha inválidos.")
            return render(request, "usuarios/login.html", ctx)

        if not user.is_active:
            messages.error(request, "Usuário inativo. Contate o administrador.")
            return render(request, "usuarios/login.html", ctx)

        # Busca prefeitura pelo IBGE (somente ativas)
        try:
            prefeitura = Prefeitura.objects.get(codigo_ibge=codigo_ibge, ativo=True)
        except Prefeitura.DoesNotExist:
            messages.error(request, "Prefeitura não encontrada ou inativa para este código IBGE.")
            return render(request, "usuarios/login.html", ctx)

        # Verifica vínculo do usuário com a prefeitura informada
        pref_id = getattr(user, "prefeitura_id", None)
        if not pref_id:
            messages.error(request, "Seu usuário não possui prefeitura vinculada. Contate o administrador.")
            return render(request, "usuarios/login.html", ctx)

        if pref_id != prefeitura.id:
            messages.error(request, "Usuário não pertence a esta prefeitura. Verifique o código IBGE informado.")
            return render(request, "usuarios/login.html", ctx)

        # Se já havia prefeitura em sessão, bloquear troca sem logout
        if "prefeitura_id" in request.session and request.session["prefeitura_id"] != prefeitura.id:
            messages.error(request, "Você precisa sair para trocar de prefeitura.")
            return redirect("login")

        # Login e fixar prefeitura na sessão
        login(request, user)
        request.session["prefeitura_id"] = prefeitura.id
        # Auditoria de login: IP, data/hora, user-agent
        def _get_client_ip(req):
            xff = req.META.get('HTTP_X_FORWARDED_FOR')
            if xff:
                return xff.split(',')[0].strip()
            return req.META.get('REMOTE_ADDR')
        try:
            UsuarioLoginLog.objects.create(
                usuario=user,
                prefeitura=prefeitura,
                ip=_get_client_ip(request),
                user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:300],
            )
        except Exception:
            # Auditoria não deve impedir o login
            pass

        messages.success(request, f"Bem-vindo! Prefeitura ativa: {prefeitura.nome}.")
        return redirect("home")  # ✅ redireciona para a sua tela inicial

    # GET
    return render(request, "usuarios/login.html", ctx)


def logout_view(request):
    # Auditoria de logout: marca logout_em no último log aberto
    try:
        from django.utils import timezone as _tz
        user = request.user if request.user.is_authenticated else None
        pref_id = request.session.get("prefeitura_id")
        if user is not None:
            from apps.usuarios.models import UsuarioLoginLog
            q = UsuarioLoginLog.objects.filter(usuario=user)
            if pref_id:
                q = q.filter(prefeitura_id=pref_id)
            last_open = q.filter(logout_em__isnull=True).order_by('-logado_em').first()
            if last_open:
                last_open.logout_em = _tz.now()
                last_open.save(update_fields=["logout_em"])
    except Exception:
        pass

    # Limpa sessão e retorna ao login
    logout(request)
    request.session.pop("prefeitura_id", None)
    return redirect("login")


@login_required
def home_view(request):
    pref_id = request.session.get("prefeitura_id")

    # Fallback: se a sessão não tem prefeitura, tenta puxar do usuário logado
    if not pref_id:
        user_pref_id = getattr(request.user, "prefeitura_id", None)
        if user_pref_id:
            try:
                prefeitura = Prefeitura.objects.get(id=user_pref_id, ativo=True)
                request.session["prefeitura_id"] = prefeitura.id
            except Prefeitura.DoesNotExist:
                messages.error(request, "Sua prefeitura está inativa ou indisponível.")
                logout(request)
                request.session.flush()
                return redirect("login")
        else:
            messages.error(request, "Seu usuário não possui prefeitura vinculada.")
            logout(request)
            request.session.flush()
            return redirect("login")
    else:
        try:
            prefeitura = Prefeitura.objects.get(id=pref_id, ativo=True)
        except Prefeitura.DoesNotExist:
            messages.error(request, "Prefeitura da sessão inválida ou inativa.")
            logout(request)
            request.session.flush()
            return redirect("login")

    # Dashboard: contagens do ano corrente (ou ano do GET)
    tz = timezone.get_current_timezone()
    try:
        ano = int(request.GET.get("ano", timezone.localdate().year))
    except Exception:
        ano = timezone.localdate().year
    dt_ini = datetime(ano, 1, 1, tzinfo=tz)
    dt_fim = datetime(ano + 1, 1, 1, tzinfo=tz)

    def _counts_by_status(qs, field="status"):
        counts = {r["status"]: r["c"] for r in qs.values("status").annotate(c=Count("id"))}
        total = qs.count()
        # choices para rótulos legíveis
        try:
            choices = dict(qs.model._meta.get_field(field).choices)
        except Exception:
            choices = {}
        items = []
        for code, label in choices.items():
            items.append({"code": code, "label": label, "count": counts.get(code, 0)})
        # adiciona quaisquer status não mapeados em choices
        for code, c in counts.items():
            if code not in choices:
                items.append({"code": code, "label": code, "count": c})
        return {"total": total, "por_status": items}

    def _counts_by_month(qs, dt_field="criada_em"):
        results = (
            qs.annotate(m=TruncMonth(dt_field))
              .values("m")
              .annotate(c=Count("id"))
              .order_by("m")
        )
        by_month = { (r["m"].month if hasattr(r["m"], "month") else r["m"]) : r["c"] for r in results }
        return [by_month.get(m, 0) for m in range(1,13)]

    den_qs = Denuncia.objects.filter(prefeitura_id=prefeitura.id, criada_em__gte=dt_ini, criada_em__lt=dt_fim)
    not_qs = Notificacao.objects.filter(prefeitura_id=prefeitura.id, criada_em__gte=dt_ini, criada_em__lt=dt_fim)
    aif_qs = AutoInfracao.objects.filter(prefeitura_id=prefeitura.id, criada_em__gte=dt_ini, criada_em__lt=dt_fim)

    stats_den = _counts_by_status(den_qs)
    stats_den["mensal"] = _counts_by_month(den_qs)
    stats_not = _counts_by_status(not_qs)
    stats_not["mensal"] = _counts_by_month(not_qs)
    stats_aif = _counts_by_status(aif_qs)
    stats_aif["mensal"] = _counts_by_month(aif_qs)

    stats = { "ano": ano, "denuncias": stats_den, "notificacoes": stats_not, "aif": stats_aif }

    # Opções de ano (atual e 5 anteriores)
    years = list(range(timezone.localdate().year, timezone.localdate().year - 6, -1))

    return render(request, "usuarios/home.html", {
        "usuario": request.user,
        "prefeitura": prefeitura,
        "stats": stats,
        "years": years,
    })
