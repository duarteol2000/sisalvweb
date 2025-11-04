# apps/notificacoes/forms.py
from django import forms
from .models import Notificacao, NotificacaoAnexo


# --------------------------------------------------------
# Widget para permitir múltiplos arquivos
# --------------------------------------------------------
class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


# --------------------------------------------------------
# Campos principais usados nos forms
# --------------------------------------------------------
BASIC_FIELDS = [
    # dados do notificado
    "pessoa_tipo", "nome_razao", "cpf_cnpj", "rg", "telefone", "email",
    # endereço
    "cep", "logradouro", "numero", "complemento", "pontoref_oco", "bairro", "cidade", "uf",
    # geolocalização
    "latitude", "longitude",
    # construtivo
    "area_m2", "testada_m", "pe_direito_m", "duplex", "qtd_comodos", "compartimentacao", "divisorias", "mezanino", "area_mezanino_m2",
    # dados da notificação
    "descricao", "documento_tipo", "prazo_regularizacao",
]


# --------------------------------------------------------
# Widgets e helpers
# --------------------------------------------------------
class HTML5DateInput(forms.DateInput):
    input_type = "date"


date_widget = HTML5DateInput(format="%Y-%m-%d")
number6 = forms.NumberInput(attrs={"step": "0.000001", "placeholder": "Ex.: -3.876543"})


# --------------------------------------------------------
# Formulário de Criação
# --------------------------------------------------------
class NotificacaoCreateForm(forms.ModelForm):
    latitude = forms.CharField(required=False)
    longitude = forms.CharField(required=False)
    class Meta:
        model = Notificacao
        fields = BASIC_FIELDS
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "prazo_regularizacao": date_widget,
            # usar text + máscara JS para aceitar vírgula
            "latitude": forms.TextInput(attrs={"placeholder": "Ex.: -3.876543", "class": "js-decimal-6", "inputmode": "decimal"}),
            "longitude": forms.TextInput(attrs={"placeholder": "Ex.: -38.654321", "class": "js-decimal-6", "inputmode": "decimal"}),
            "area_m2": forms.TextInput(attrs={"placeholder": "Ex.: 120,50", "class": "js-decimal-2", "inputmode": "decimal"}),
            "testada_m": forms.TextInput(attrs={"placeholder": "Ex.: 7,50", "class": "js-decimal-2", "inputmode": "decimal"}),
            "pe_direito_m": forms.TextInput(attrs={"placeholder": "Ex.: 2,80", "class": "js-decimal-2", "inputmode": "decimal"}),
            "area_mezanino_m2": forms.TextInput(attrs={"placeholder": "Ex.: 30,00", "class": "js-decimal-2", "inputmode": "decimal"}),
            # inteiros amigáveis
            "qtd_comodos": forms.TextInput(attrs={"inputmode": "numeric", "class": "js-int", "placeholder": "Ex.: 4"}),
            # documentos/contatos
            "cpf_cnpj": forms.TextInput(attrs={"class": "js-doc", "inputmode": "numeric", "maxlength": 18}),
            "telefone": forms.TextInput(attrs={"class": "js-phone", "inputmode": "tel"}),
            "cep": forms.TextInput(attrs={"class": "js-cep", "inputmode": "numeric", "maxlength": 9}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Corrige exibição de data no input type=date
        pr = self.initial.get("prazo_regularizacao") or getattr(self.instance, "prazo_regularizacao", None)
        if pr:
            self.initial["prazo_regularizacao"] = pr.strftime("%Y-%m-%d")
        # Força lat/lng com 6 casas na renderização
        from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
        for fld in ("latitude", "longitude"):
            val = self.initial.get(fld) or getattr(self.instance, fld, None)
            if val not in (None, ""):
                try:
                    q = Decimal(str(val)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                    # Usa vírgula no placeholder/teclado BR ou deixa ponto? Mantemos ponto no value para evitar conflito
                    self.initial[fld] = f"{q:.6f}"
                except (InvalidOperation, ValueError):
                    pass

    def clean(self):
        from utils.geo import to_float_or_none, clamp_lat_lng
        data = super().clean()
        # Latitude/Longitude: aceita vírgula, normaliza e valida faixa
        lat = to_float_or_none(self.data.get("latitude", data.get("latitude")))
        lng = to_float_or_none(self.data.get("longitude", data.get("longitude")))
        lat, lng = clamp_lat_lng(lat, lng)
        data["latitude"], data["longitude"] = lat, lng

        # Normaliza campos decimais de construção (aceita vírgula)
        from decimal import Decimal, InvalidOperation
        def _norm_dec_field(field):
            v = self.data.get(field, data.get(field))
            if v in (None, ""): return
            if isinstance(v, (int, float)): 
                data[field] = v
                return
            s = str(v).strip().replace(" ", "").replace(".", "").replace(",", ".")
            try:
                data[field] = Decimal(s)
            except InvalidOperation:
                self.add_error(field, "Valor inválido. Use ponto ou vírgula como decimal.")
        for f in ("area_m2", "testada_m", "pe_direito_m", "area_mezanino_m2"):
            _norm_dec_field(f)
        if data.get("mezanino") and not data.get("area_mezanino_m2"):
            self.add_error("area_mezanino_m2", "Informe a área do mezanino (m²).")
        return data


# --------------------------------------------------------
# Formulário de Edição
# --------------------------------------------------------
class NotificacaoEditForm(forms.ModelForm):
    latitude = forms.CharField(required=False)
    longitude = forms.CharField(required=False)
    class Meta:
        model = Notificacao
        fields = BASIC_FIELDS + ["status"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "prazo_regularizacao": date_widget,
            "latitude": forms.TextInput(attrs={"placeholder": "Ex.: -3.876543", "class": "js-decimal-6", "inputmode": "decimal"}),
            "longitude": forms.TextInput(attrs={"placeholder": "Ex.: -38.654321", "class": "js-decimal-6", "inputmode": "decimal"}),
            "area_m2": forms.TextInput(attrs={"placeholder": "Ex.: 120,50", "class": "js-decimal-2", "inputmode": "decimal"}),
            "testada_m": forms.TextInput(attrs={"placeholder": "Ex.: 7,50", "class": "js-decimal-2", "inputmode": "decimal"}),
            "pe_direito_m": forms.TextInput(attrs={"placeholder": "Ex.: 2,80", "class": "js-decimal-2", "inputmode": "decimal"}),
            "area_mezanino_m2": forms.TextInput(attrs={"placeholder": "Ex.: 30,00", "class": "js-decimal-2", "inputmode": "decimal"}),
            "qtd_comodos": forms.TextInput(attrs={"inputmode": "numeric", "class": "js-int", "placeholder": "Ex.: 4"}),
            "cpf_cnpj": forms.TextInput(attrs={"class": "js-doc", "inputmode": "numeric", "maxlength": 18}),
            "telefone": forms.TextInput(attrs={"class": "js-phone", "inputmode": "tel"}),
            "cep": forms.TextInput(attrs={"class": "js-cep", "inputmode": "numeric", "maxlength": 9}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pr = self.initial.get("prazo_regularizacao") or getattr(self.instance, "prazo_regularizacao", None)
        if pr:
            self.initial["prazo_regularizacao"] = pr.strftime("%Y-%m-%d")
        # Força lat/lng com 6 casas na renderização
        from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
        for fld in ("latitude", "longitude"):
            val = self.initial.get(fld) or getattr(self.instance, fld, None)
            if val not in (None, ""):
                try:
                    q = Decimal(str(val)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                    self.initial[fld] = f"{q:.6f}"
                except (InvalidOperation, ValueError):
                    pass

    def clean(self):
        from utils.geo import to_float_or_none, clamp_lat_lng
        data = super().clean()
        lat = to_float_or_none(self.data.get("latitude", data.get("latitude")))
        lng = to_float_or_none(self.data.get("longitude", data.get("longitude")))
        lat, lng = clamp_lat_lng(lat, lng)
        data["latitude"], data["longitude"] = lat, lng
        # Normaliza campos decimais (aceita vírgula)
        from decimal import Decimal, InvalidOperation
        def _norm_dec_field(field):
            v = self.data.get(field, data.get(field))
            if v in (None, ""): return
            if isinstance(v, (int, float)):
                data[field] = v
                return
            s = str(v).strip().replace(" ", "").replace(".", "").replace(",", ".")
            try:
                data[field] = Decimal(s)
            except InvalidOperation:
                self.add_error(field, "Valor inválido. Use ponto ou vírgula como decimal.")
        for f in ("area_m2", "testada_m", "pe_direito_m", "area_mezanino_m2"):
            _norm_dec_field(f)
        if data.get("mezanino") and not data.get("area_mezanino_m2"):
            self.add_error("area_mezanino_m2", "Informe a área do mezanino (m²).")
        return data


# --------------------------------------------------------
# Formulário de Anexos (individual)
# --------------------------------------------------------
class NotificacaoAnexoForm(forms.ModelForm):
    class Meta:
        model = NotificacaoAnexo
        fields = ["tipo", "arquivo", "observacao"]


# --------------------------------------------------------
# Formulário de Fotos (múltiplas)
# --------------------------------------------------------
class NotificacaoFotosForm(forms.Form):
    fotos = forms.FileField(
        widget=MultiFileInput(attrs={"multiple": True, "accept": "image/*"}),
        required=False,
        label="Fotos da Notificação",
    )
    
