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
    "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
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
    class Meta:
        model = Notificacao
        fields = BASIC_FIELDS
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "prazo_regularizacao": date_widget,
            "latitude": number6,
            "longitude": number6,
            "area_m2": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 120.50"}),
            "testada_m": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 7.50"}),
            "pe_direito_m": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 2.80"}),
            "area_mezanino_m2": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 30.00"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Corrige exibição de data no input type=date
        pr = self.initial.get("prazo_regularizacao") or getattr(self.instance, "prazo_regularizacao", None)
        if pr:
            self.initial["prazo_regularizacao"] = pr.strftime("%Y-%m-%d")

    def clean(self):
        data = super().clean()
        if data.get("mezanino") and not data.get("area_mezanino_m2"):
            self.add_error("area_mezanino_m2", "Informe a área do mezanino (m²).")
        return data


# --------------------------------------------------------
# Formulário de Edição
# --------------------------------------------------------
class NotificacaoEditForm(forms.ModelForm):
    class Meta:
        model = Notificacao
        fields = BASIC_FIELDS + ["status"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "prazo_regularizacao": date_widget,
            "latitude": number6,
            "longitude": number6,
            "area_m2": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 120.50"}),
            "testada_m": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 7.50"}),
            "pe_direito_m": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 2.80"}),
            "area_mezanino_m2": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal", "placeholder": "ex.: 30.00"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pr = self.initial.get("prazo_regularizacao") or getattr(self.instance, "prazo_regularizacao", None)
        if pr:
            self.initial["prazo_regularizacao"] = pr.strftime("%Y-%m-%d")

    def clean(self):
        data = super().clean()
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
    
