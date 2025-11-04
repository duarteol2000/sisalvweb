# utils/protocolo.py
import re
from django.utils import timezone

def _digits_only(texto: str) -> str:
    return re.sub(r"\D+", "", (texto or "").strip())

def _alnum_upper(texto: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", (texto or "")).upper()

def gerar_protocolo(codigo_ibge: str, sigla: str, matricula: str | None = None) -> str:
    """
    Formato:
      IBGE-SIGLA-AAAAMMDDhhmmss[-MATRICULA]

    Regras:
    - IBGE: apenas dígitos
    - SIGLA: maiúscula (ex.: DEN, NOT, INF...)
    - MATRÍCULA: opcional; se informada, vai ao final.
    """
    ibge = _digits_only(codigo_ibge)
    if not ibge:
        raise ValueError("Código IBGE inválido.")

    sigla_up = _alnum_upper(sigla)
    if not sigla_up:
        raise ValueError("SIGLA inválida.")

    ts = timezone.localtime().strftime("%Y%m%d%H%M%S")

    matricula_up = _alnum_upper(matricula) if matricula else ""
    if matricula_up:
        return f"{ibge}-{sigla_up}-{ts}-{matricula_up}"
    return f"{ibge}-{sigla_up}-{ts}"


def gerar_protocolo_para_instance(instance, sigla: str, user_field_names=("criado_por", "criada_por")) -> str:
    """Gera protocolo a partir de uma instance que possua `prefeitura` e
    possivelmente `criado_por` (ou `criada_por`) com `matricula`.

    - Busca `codigo_ibge` em `instance.prefeitura`.
    - Tenta encontrar matrícula do usuário criador, checando campos em `user_field_names`.
    - Usa `gerar_protocolo` para compor no padrão IBGE-SIGLA-AAAA...-MATRICULA.
    """
    pref = getattr(instance, "prefeitura", None)
    ibge = getattr(pref, "codigo_ibge", "") or ""
    matricula = None
    for field in user_field_names:
        user = getattr(instance, field, None)
        if user and getattr(user, "matricula", None):
            matricula = user.matricula
            break
    return gerar_protocolo(ibge, sigla, matricula=matricula)
