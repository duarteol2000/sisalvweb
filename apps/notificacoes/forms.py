# apps/notificacoes/forms.py
from django import forms
from .models import Notificacao, NotificacaoAnexo
from apps.usuarios.models import Usuario


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
    fiscais = forms.ModelMultipleChoiceField(
        queryset=Usuario.objects.none(), required=False, label="Fiscais"
    )
    class Meta:
        model = Notificacao
        fields = BASIC_FIELDS + ["ocorrido_em", "fiscais"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 7}),
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
        prefeitura_id = kwargs.pop("prefeitura_id", None)
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
        # Formato amigável para datetime-local
        if "ocorrido_em" in self.fields:
            try:
                self.fields["ocorrido_em"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"]
            except Exception:
                pass
            self.fields["ocorrido_em"].widget = forms.DateTimeInput(attrs={"type": "datetime-local"})

        # Carrega fiscais por prefeitura (quando informado)
        if prefeitura_id and 'fiscais' in self.fields:
            self.fields['fiscais'].queryset = Usuario.objects.filter(
                prefeitura_id=prefeitura_id,
                is_active=True,
                tipo__iexact='FISCAL',
            ).order_by('first_name', 'last_name', 'email')
            self.fields['fiscais'].widget = forms.CheckboxSelectMultiple()
            try:
                self.fields['fiscais'].label_from_instance = lambda u: (
                    (u.get_full_name() or u.email) +
                    (f" ({u.matricula})" if getattr(u, 'matricula', None) else '')
                )
            except Exception:
                pass
            # (debug removido)
            # Garante seleção marcada no GET (editar): lista de IDs como initial
            if not self.is_bound and getattr(self.instance, 'pk', None):
                try:
                    self.initial['fiscais'] = list(self.instance.fiscais.values_list('pk', flat=True))
                except Exception:
                    pass

    def clean(self):
        from utils.geo import to_float_or_none, clamp_lat_lng
        data = super().clean()
        # Latitude/Longitude: aceita vírgula, normaliza e valida faixa
        lat = to_float_or_none(self.data.get("latitude", data.get("latitude")))
        lng = to_float_or_none(self.data.get("longitude", data.get("longitude")))
        lat, lng = clamp_lat_lng(lat, lng)
        data["latitude"], data["longitude"] = lat, lng

        # Normaliza campos decimais de construção (aceita vírgula e/ou ponto)
        from decimal import Decimal, InvalidOperation
        def _norm_dec_field(field):
            v = self.data.get(field, data.get(field))
            if v in (None, ""): return
            if isinstance(v, (int, float)):
                data[field] = v
                return
            s = str(v).strip().replace(" ", "")
            has_dot = "." in s
            has_comma = "," in s
            if has_comma and has_dot:
                # ponto como milhar, vírgula como decimal (padrão BR)
                s = s.replace(".", "").replace(",", ".")
            elif has_comma and not has_dot:
                # apenas vírgula, tratar como decimal
                s = s.replace(",", ".")
            # else: já está com ponto decimal ou inteiro
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
    fiscais = forms.ModelMultipleChoiceField(
        queryset=Usuario.objects.none(), required=False, label="Fiscais"
    )
    class Meta:
        model = Notificacao
        fields = BASIC_FIELDS + ["ocorrido_em", "status", "conclusao_motivo", "conclusao_documento", "fiscais"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 8}),
            "prazo_regularizacao": date_widget,
            "conclusao_motivo": forms.Textarea(attrs={"rows": 2}),
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
        prefeitura_id = kwargs.pop("prefeitura_id", None)
        super().__init__(*args, **kwargs)
        pr = self.initial.get("prazo_regularizacao") or getattr(self.instance, "prazo_regularizacao", None)
        if pr:
            self.initial["prazo_regularizacao"] = pr.strftime("%Y-%m-%d")
        # datetime-local para ocorrido_em
        if "ocorrido_em" in self.fields:
            self.fields["ocorrido_em"].widget = forms.DateTimeInput(attrs={"type": "datetime-local"})
            occ = self.initial.get("ocorrido_em") or getattr(self.instance, "ocorrido_em", None)
            if occ:
                try:
                    self.initial["ocorrido_em"] = occ.strftime("%Y-%m-%dT%H:%M")
                except Exception:
                    pass
            try:
                self.fields["ocorrido_em"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"]
            except Exception:
                pass
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
        # Carrega fiscais por prefeitura (quando informado)
        # Fallback: se não vier prefeitura_id, tenta usar da própria instância
        if not prefeitura_id and getattr(self.instance, 'prefeitura_id', None):
            prefeitura_id = self.instance.prefeitura_id
        if prefeitura_id and 'fiscais' in self.fields:
            self.fields['fiscais'].queryset = Usuario.objects.filter(
                prefeitura_id=prefeitura_id,
                is_active=True,
                tipo__iexact='FISCAL',
            ).order_by('first_name', 'last_name', 'email')
            self.fields['fiscais'].widget = forms.CheckboxSelectMultiple()
            try:
                self.fields['fiscais'].label_from_instance = lambda u: (
                    (u.get_full_name() or u.email) +
                    (f" ({u.matricula})" if getattr(u, 'matricula', None) else '')
                )
            except Exception:
                pass
            # Em edição (GET), garante seleção inicial dos fiscais já vinculados
            if not self.is_bound and getattr(self.instance, 'pk', None):
                try:
                    ids = list(self.instance.fiscais.values_list('pk', flat=True))
                    self.initial['fiscais'] = [str(pk) for pk in ids]
                except Exception:
                    pass
            # (debug removido)

        # Ajusta widget de arquivo: aceitar PDF/DOC
        if 'conclusao_documento' in self.fields:
            self.fields['conclusao_documento'].widget = forms.ClearableFileInput(
                attrs={
                    'accept': '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                }
            )

    def clean(self):
        from utils.geo import to_float_or_none, clamp_lat_lng
        data = super().clean()
        lat = to_float_or_none(self.data.get("latitude", data.get("latitude")))
        lng = to_float_or_none(self.data.get("longitude", data.get("longitude")))
        lat, lng = clamp_lat_lng(lat, lng)
        data["latitude"], data["longitude"] = lat, lng
        # Normaliza campos decimais (aceita vírgula e/ou ponto)
        from decimal import Decimal, InvalidOperation
        def _norm_dec_field(field):
            v = self.data.get(field, data.get(field))
            if v in (None, ""): return
            if isinstance(v, (int, float)):
                data[field] = v
                return
            s = str(v).strip().replace(" ", "")
            has_dot = "." in s
            has_comma = "," in s
            if has_comma and has_dot:
                s = s.replace(".", "").replace(",", ".")
            elif has_comma and not has_dot:
                s = s.replace(",", ".")
            try:
                data[field] = Decimal(s)
            except InvalidOperation:
                self.add_error(field, "Valor inválido. Use ponto ou vírgula como decimal.")
        for f in ("area_m2", "testada_m", "pe_direito_m", "area_mezanino_m2"):
            _norm_dec_field(f)
        if data.get("mezanino") and not data.get("area_mezanino_m2"):
            self.add_error("area_mezanino_m2", "Informe a área do mezanino (m²).")

        # Validação do documento de conclusão (se enviado)
        f = self.files.get('conclusao_documento') or None
        if f:
            name = (getattr(f, 'name', '') or '').lower()
            ok_ext = name.endswith('.pdf') or name.endswith('.doc') or name.endswith('.docx')
            ctype = getattr(f, 'content_type', '') or ''
            ok_ct = ctype in ('application/pdf','application/msword','application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            if not (ok_ext or ok_ct):
                self.add_error('conclusao_documento', 'Apenas arquivos PDF ou DOC/DOCX são permitidos.')
        return data
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
    
