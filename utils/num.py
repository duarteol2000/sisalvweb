from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Any


def normalize_decimal_str(value: Any) -> Optional[str]:
    """Normaliza uma string numérica para formato com ponto decimal.

    Regras:
    - None/"" -> None
    - Remove espaços
    - Se tiver vírgula e ponto: ponto como milhar (removido), vírgula vira ponto
    - Se só vírgula: vírgula vira ponto
    - Se só ponto ou número: mantém
    Retorna string normalizada ou None.
    """
    if value in (None, ""):
        return None
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    s = str(value).strip().replace(" ", "")
    if s == "":
        return None
    has_dot = "." in s
    has_comma = "," in s
    if has_dot and has_comma:
        s = s.replace(".", "").replace(",", ".")
    elif has_comma and not has_dot:
        s = s.replace(",", ".")
    return s


def to_decimal(value: Any, *, quantize_exp: Optional[Decimal] = None) -> Optional[Decimal]:
    """Converte valor para Decimal após normalizar separadores.

    - quantize_exp: ex. Decimal('0.01') para forçar 2 casas (ROUND_HALF_UP)
    - Retorna None quando vazio/None ou quando inválido
    """
    s = normalize_decimal_str(value)
    if s is None:
        return None
    try:
        d = Decimal(s)
        if quantize_exp is not None:
            d = d.quantize(quantize_exp, rounding=ROUND_HALF_UP)
        return d
    except (InvalidOperation, ValueError):
        return None

