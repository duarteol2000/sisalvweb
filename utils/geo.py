def to_float_or_none(value):
    """Converte vários formatos (incl. vírgula) em float com ponto; None quando inválido."""
    if value is None:
        return None
    try:
        s = str(value).strip().replace(' ', '').replace(',', '.')
        if s == '':
            return None
        return float(s)
    except Exception:
        return None


def clamp_lat_lng(lat, lng):
    """Garante limites válidos para latitude/longitude; quando fora, retorna None no respectivo eixo."""
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if lng is not None and not (-180.0 <= lng <= 180.0):
        lng = None
    return lat, lng

