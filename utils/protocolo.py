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
